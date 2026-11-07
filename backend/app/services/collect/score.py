"""採点（代表記事ごとに Haiku を1回）。同時5件で並列に呼び、DB への書き込みはここで1件ずつ行う。

本文を取れなかった代表（概要のみ）は、同じ話題の他媒体の本文を材料に足す（G2 の決定）。
"""

import asyncio
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from sqlmodel import Session, col, select

from app.models import Article, ArticleText, Run, RunIssue, Score, Source, Topic
from app.schemas.analysis import ScoreOutput
from app.schemas.settings import Settings
from app.schemas.topics import CriterionKey
from app.services.llm.client import Llm, LlmResult
from app.services.llm.context import build_scoring_context
from app.services.llm.errors import BudgetExceededError, LlmError
from app.services.llm.ledger import record_usage
from app.services.llm.skills import load_skill
from app.services.scoring import OFFICIAL_BONUS, compute_total

CONCURRENCY = 5
BODY_LIMIT = 20_000
RELATED_LIMIT = 3
RELATED_BODY_LIMIT = 6_000


@dataclass
class ScoreReport:
    scored: int = 0
    failed: int = 0
    deferred: int = 0  # 件数の上限で次回に回した代表
    budget_stopped: bool = False


@dataclass(frozen=True)
class _Job:
    article_id: int
    topic_id: int
    official: bool
    source_name: str
    user: str


def _clean(text: str) -> str:
    return text.replace("</article>", "< /article>").replace("<article", "< article")


def _body(session: Session, article: Article, limit: int) -> str:
    row = session.get(ArticleText, article.id)
    return _clean((row.body if row else article.summary)[:limit])


def _build_job(session: Session, article: Article, source: Source | None) -> _Job:
    assert article.id is not None and article.topic_id is not None
    full = article.fetch_status == "full"
    name = source.name if source else article.domain
    kind = source.kind if source else "media"
    parts = [
        "<article>",
        f"タイトル: {_clean(article.title_original)}",
        f"情報源: {name}（{kind}）",
        f"公開日: {article.published_at:%Y-%m-%d}",
        f"本文の状態: {'全文' if full else '概要のみ（全文未取得）'}",
        f"<本文>\n{_body(session, article, BODY_LIMIT)}\n</本文>",
    ]
    if not full:
        others = session.exec(
            select(Article).where(
                col(Article.topic_id) == article.topic_id,
                col(Article.role) == "related",
                col(Article.fetch_status) == "full",
            )
        ).all()[:RELATED_LIMIT]
        for other in others:
            parts.append(
                f"<同じ話題を扱う他媒体の記事>\nタイトル: {_clean(other.title_original)}\n"
                f"{_body(session, other, RELATED_BODY_LIMIT)}\n</同じ話題を扱う他媒体の記事>"
            )
    parts.append("</article>")
    return _Job(
        article_id=article.id,
        topic_id=article.topic_id,
        official=kind == "official",
        source_name=name,
        user="\n".join(parts),
    )


def _pick(session: Session, limit: int) -> tuple[list[tuple[Article, Source | None]], int]:
    """採点待ちの代表を「公式 → 新しい順」で並べ、上限までを返す（残りの件数も返す）。"""
    rows = session.exec(
        select(Article, Source)
        .join(Topic, col(Topic.id) == col(Article.topic_id))
        .join(Source, col(Source.id) == col(Article.source_id), isouter=True)
        .where(
            col(Article.role) == "representative",
            col(Article.stage) == "grouped",
            col(Topic.selection) == "pending",
        )
    ).all()
    ordered = sorted(
        rows,
        key=lambda r: (
            0 if (r[1] and r[1].kind == "official") else 1,
            -r[0].published_at.timestamp(),
        ),
    )
    picked: list[tuple[Article, Source | None]] = [(a, src) for a, src in ordered[:limit]]
    return picked, max(0, len(ordered) - limit)


async def score_pending(
    session: Session, llm: Llm, *, run: Run, settings: Settings, now: datetime
) -> ScoreReport:
    picked, deferred = _pick(session, settings.max_scored)
    report = ScoreReport(deferred=deferred)
    if not picked:
        return report
    skill = load_skill("score")
    context = build_scoring_context(session, settings.profile)
    jobs = [_build_job(session, article, source) for article, source in picked]
    weights = settings.weights.as_dict()
    gate = asyncio.Semaphore(CONCURRENCY)

    async def work(job: _Job) -> tuple[_Job, LlmResult[ScoreOutput] | LlmError]:
        async with gate:
            try:
                return job, await llm.run(
                    skill,
                    context=context,
                    user=job.user,
                    output_type=ScoreOutput,
                    effort="low",
                    max_tokens=4000,
                )
            except LlmError as error:
                return job, error

    errors: Counter[str] = Counter()
    examples: dict[str, str] = {}
    for finished in asyncio.as_completed([asyncio.create_task(work(j)) for j in jobs]):
        job, result = await finished
        if isinstance(result, BudgetExceededError):
            report.budget_stopped = True
            continue
        if isinstance(result, LlmError):
            report.failed += 1
            kind = type(result).__name__
            errors[kind] += 1
            examples.setdefault(kind, str(result))
            continue
        out = result.parsed
        session.add(
            Score(
                topic_id=job.topic_id,
                interest=out.interest,
                practical=out.practical,
                freshness=out.freshness,
                trust=out.trust,
                depth=out.depth,
                weights={str(k): v for k, v in weights.items()},
                official_bonus=_bonus(job.official),
                total=_total(out, weights, job.official),
                reason=out.reason,
                article_type=out.article_type,
                category=out.category,
                tags=out.tags,
                title_ja=out.title_ja,
                summary_1line=out.summary_1line,
                summary_5lines=out.summary_5lines,
                model_id=llm.model_id,
                skill_version=result.skill_version,
                run_id=run.id,
                scored_at=now,
            )
        )
        article = session.get(Article, job.article_id)
        assert article is not None
        article.stage = "scored"
        session.add(article)
        record_usage(session, run, result.usage, purpose="score", topic_id=job.topic_id)
        report.scored += 1
        run.scored_count += 1
        run.heartbeat_at = datetime.now(now.tzinfo)
        session.add(run)
        session.commit()  # 1件ごとに保存する（止まっても、ここまでは残る）
    for kind, count in errors.items():
        session.add(
            RunIssue(
                run_id=run.id or 0,
                source_name="Haiku",
                stage="採点",
                message=(
                    f"{count}件の採点に失敗しました（{kind}: {examples[kind][:120]}）。"
                    "次回の更新で再試行します"
                ),
            )
        )
    session.commit()
    return report


def _bonus(official: bool) -> int:
    return OFFICIAL_BONUS if official else 0


def _total(out: ScoreOutput, weights: Mapping[CriterionKey, int], official: bool) -> int:
    return compute_total(
        {
            "interest": out.interest,
            "practical": out.practical,
            "freshness": out.freshness,
            "trust": out.trust,
            "depth": out.depth,
        },
        weights,
        official=official,
    )
