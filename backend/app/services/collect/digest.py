"""整理記事（選定・重大ニュースの話題ごとに Haiku を1回）。

同時4件で並列に呼び、DB への書き込みは1件ずつ行う。

書いた段落は、別の Haiku（校閲）が材料と照らして、「記事に書かれていること」か
「AI が付け加えたこと」かを判定する。書き手と校閲の**どちらかが AI の意見と判定した段落**を、
AI の意見として保存する（事実と表示されるのは、両方が記事の内容と認めたものだけ）。
校閲に失敗したときは作らず、次回に再試行する。

材料は、代表記事の本文（最大2万字）と、同じ話題の関連記事（本文のあるもの最大3件・各2万字）。
URL は Haiku に書かせない（画面が DB の URL から一覧を作る）。
"""

import asyncio
from collections import Counter
from dataclasses import dataclass
from datetime import datetime

from sqlmodel import Session, col, select

from app.models import Article, Digest, Run, RunIssue, Score, Source, Topic
from app.schemas.analysis import DigestOutput, VerifyOutput
from app.schemas.settings import Settings
from app.services.collect.score import _body, _clean
from app.services.llm.client import Llm, LlmResult
from app.services.llm.errors import BudgetExceededError, LlmError
from app.services.llm.ledger import record_usage
from app.services.llm.skills import Skill, load_skill
from app.services.search import index_topic

CONCURRENCY = 4
BODY_LIMIT = 20_000
RELATED_LIMIT = 3
RELATED_BODY_LIMIT = 20_000
MAX_TOKENS = 8000  # 考える分の出力も含む（論文は最大2,000字）
VERIFY_MAX_TOKENS = 6000
_SKILLS = {
    "announcement": "compose-announcement",
    "howto": "compose-howto",
    "paper": "compose-paper",
    "analysis": "compose-analysis",
    "industry": "compose-industry",
}


@dataclass
class DigestReport:
    created: int = 0
    failed: int = 0
    budget_stopped: bool = False


@dataclass(frozen=True)
class _Job:
    topic_id: int
    article_type: str
    user: str


def skill_for(article_type: str) -> Skill:
    return load_skill(_SKILLS[article_type], shared=("_style.md",))


def _build_job(session: Session, topic: Topic, score: Score) -> _Job | None:
    rep = session.exec(
        select(Article).where(
            col(Article.topic_id) == topic.id, col(Article.role) == "representative"
        )
    ).first()
    if rep is None or topic.id is None:
        return None
    source = session.get(Source, rep.source_id) if rep.source_id else None
    full = rep.fetch_status == "full"
    parts = [
        "<article>",
        f"タイトル: {_clean(rep.title_original)}",
        f"情報源: {source.name if source else rep.domain}（{source.kind if source else 'media'}）",
        f"公開日: {rep.published_at:%Y-%m-%d}",
        f"本文の状態: {'全文' if full else '概要のみ（全文未取得）'}",
        f"<本文>\n{_body(session, rep, BODY_LIMIT)}\n</本文>",
        "</article>",
    ]
    related = session.exec(
        select(Article, Source)
        .join(Source, col(Source.id) == col(Article.source_id), isouter=True)
        .where(
            col(Article.topic_id) == topic.id,
            col(Article.role) == "related",
            col(Article.fetch_status) == "full",
        )
        .order_by(col(Article.published_at))
    ).all()[:RELATED_LIMIT]
    for other, src in related:
        parts.append(
            "<同じ話題を扱う他媒体の記事>\n"
            f"タイトル: {_clean(other.title_original)}\n"
            f"情報源: {src.name if src else other.domain}\n"
            f"{_body(session, other, RELATED_BODY_LIMIT)}\n</同じ話題を扱う他媒体の記事>"
        )
    return _Job(topic_id=topic.id, article_type=score.article_type, user="\n".join(parts))


def _pick(session: Session, only: list[int] | None) -> list[tuple[Topic, Score]]:
    """整理記事がまだない選定・重大の話題を、重大 → 点数の高い順で返す。"""
    stmt = (
        select(Topic, Score)
        .join(Score, col(Score.topic_id) == col(Topic.id))
        .where(
            col(Topic.selection).in_(["selected", "major"]),
            col(Topic.id).not_in(select(Digest.topic_id)),
        )
    )
    if only is not None:
        stmt = stmt.where(col(Topic.id).in_(only))
    rows = list(session.exec(stmt).all())
    rows.sort(key=lambda r: (r[0].selection != "major", -r[1].total, r[0].id or 0))
    return rows


def _listing(out: DigestOutput) -> str:
    """校閲に渡す、番号つきの段落の一覧。"""
    items: list[str] = []
    for section in out.sections:
        for paragraph in section.paragraphs:
            text = _clean(paragraph.text).replace("</段落>", "< /段落>")
            items.append(f'<段落 index="{len(items)}">\n[{section.heading}] {text}\n</段落>')
    return "<整理記事>\n" + "\n".join(items) + "\n</整理記事>"


def merge_verdicts(out: DigestOutput, checked: VerifyOutput) -> list[dict[str, object]]:
    """書き手の印と校閲の判定を合わせる。どちらかが AI の意見なら AI の意見（判定なしも）。"""
    origin = {v.index: v.origin for v in checked.verdicts}
    sections: list[dict[str, object]] = []
    index = 0
    for section in out.sections:
        paragraphs: list[dict[str, object]] = []
        for paragraph in section.paragraphs:
            is_ai = paragraph.inference or origin.get(index, "ai") == "ai"
            paragraphs.append({"text": paragraph.text, "inference": is_ai})
            index += 1
        sections.append({"heading": section.heading, "paragraphs": paragraphs})
    return sections


def profile_context(profile: str) -> str:
    return f"# 興味プロファイル\n{profile.strip()}"


async def digest_selected(
    session: Session,
    llm: Llm,
    *,
    run: Run | None,
    settings: Settings,
    now: datetime,
    only: list[int] | None = None,
) -> DigestReport:
    report = DigestReport()
    jobs = [
        job
        for topic, score in _pick(session, only)
        if (job := _build_job(session, topic, score)) is not None
    ]
    if not jobs:
        return report
    context = profile_context(settings.profile)
    skills = {t: skill_for(t) for t in {j.article_type for j in jobs}}
    verify_skill = load_skill("verify")
    gate = asyncio.Semaphore(CONCURRENCY)

    async def work(
        job: _Job,
    ) -> tuple[
        _Job,
        LlmResult[DigestOutput] | LlmError,
        LlmResult[VerifyOutput] | LlmError | None,
    ]:
        async with gate:
            try:
                written = await llm.run(
                    skills[job.article_type],
                    context=context,
                    user=job.user,
                    output_type=DigestOutput,
                    effort="medium",
                    max_tokens=MAX_TOKENS,
                )
            except LlmError as error:
                return job, error, None
            try:
                checked = await llm.run(
                    verify_skill,
                    context="",
                    user=f"{job.user}\n{_listing(written.parsed)}",
                    output_type=VerifyOutput,
                    effort="medium",
                    max_tokens=VERIFY_MAX_TOKENS,
                )
            except LlmError as error:
                return job, written, error
            return job, written, checked

    errors: Counter[str] = Counter()
    examples: dict[str, str] = {}

    def fail(error: LlmError) -> None:
        report.failed += 1
        kind = type(error).__name__
        errors[kind] += 1
        examples.setdefault(kind, str(error))

    for finished in asyncio.as_completed([asyncio.create_task(work(j)) for j in jobs]):
        job, written, checked = await finished
        if isinstance(written, LlmError):
            if isinstance(written, BudgetExceededError):
                report.budget_stopped = True
            else:
                fail(written)
            continue
        # 書いた分の費用は、校閲に失敗しても実費として残す
        record_usage(session, run, written.usage, purpose="digest", topic_id=job.topic_id)
        if isinstance(checked, LlmError) or checked is None:
            session.commit()
            if isinstance(checked, BudgetExceededError):
                report.budget_stopped = True
            elif checked is not None:
                fail(checked)
            continue
        record_usage(session, run, checked.usage, purpose="verify", topic_id=job.topic_id)
        session.add(
            Digest(
                topic_id=job.topic_id,
                article_type=job.article_type,
                lead=written.parsed.lead,
                sections=merge_verdicts(written.parsed, checked.parsed),
                model_id=llm.model_id,
                skill_version=f"{written.skill_version}+{checked.skill_version}",
                created_at=now,
            )
        )
        session.flush()
        index_topic(session, job.topic_id)
        report.created += 1
        if run is not None:
            run.heartbeat_at = datetime.now(now.tzinfo)
            session.add(run)
        session.commit()  # 1件ごとに保存する（止まっても、ここまでは残る）
    if run is not None:
        for kind, count in errors.items():
            session.add(
                RunIssue(
                    run_id=run.id or 0,
                    source_name="Haiku",
                    stage="整理記事",
                    message=(
                        f"{count}件の整理記事の作成に失敗しました"
                        f"（{kind}: {examples[kind][:120]}）。次回の更新で再試行します"
                    ),
                )
            )
        session.commit()
    return report
