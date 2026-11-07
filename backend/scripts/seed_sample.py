"""開発用：試しのデータを DB に入れる。

使い方（backend/ で）:
    uv run python -m scripts.seed_sample           # 試しのデータを入れる（空の DB 向け）
    uv run python -m scripts.seed_sample --reset   # 記事・実行履歴などを全部消してから入れ直す
    uv run python -m scripts.seed_sample --clear   # 全部消すだけ（本物の記事で確認するとき）

先に表を作っておく（make migrate）。画面の上部に「試しのデータ」の注意書きが出る。
"""

import argparse
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, text
from sqlmodel import Session, col, select

from app.db import engine
from app.models import (
    Article,
    ArticleText,
    Digest,
    LlmUsage,
    Run,
    RunIssue,
    Score,
    SearchQuery,
    Setting,
    Source,
    Topic,
)
from app.schemas.topics import CriterionKey
from app.services.app_settings import set_sample_mode
from app.services.scoring import (
    DEFAULT_WEIGHTS,
    build_breakdown,
    decide_selection,
)
from app.services.search import SEARCH_TABLE, index_topic
from scripts.sample_data import FILLER, HEADINGS, INFERENCE_HEADINGS, SOURCES, Seed, seeds

MODEL = "claude-haiku-5-5"
_QUERIES = [
    ("Claude Code hooks workflow", "en", 8),
    ("AI agent tool design best practices", "en", 7),
    ("生成AI 業務活用 事例", "ja", 9),
    ("LLM evaluation benchmark pitfalls", "en", 6),
    ("AI 規制 施行 企業 対応", "ja", 5),
]
_CRITERIA: tuple[CriterionKey, ...] = ("interest", "practical", "freshness", "trust", "depth")

# 試しのデータの選定の線。本番の既定値（DEFAULT_THRESHOLD）を変えても、画面確認用のデータは変えない
SAMPLE_THRESHOLD = 60


def _run_start(now: datetime, day: int) -> datetime:
    return now.replace(hour=6, minute=0, second=0, microsecond=0) - timedelta(days=day)


def clear(session: Session) -> None:
    """記事・話題・実行履歴・費用・情報源を全部消す（画面で変えた設定は残す）。"""
    for model in (
        LlmUsage,
        RunIssue,
        SearchQuery,
        Digest,
        Score,
        ArticleText,
        Article,
        Topic,
        Run,
    ):
        session.execute(delete(model))
    session.execute(delete(Source))
    session.execute(delete(Setting).where(col(Setting.key) == "sample_mode"))
    if session.connection().dialect.name == "sqlite":
        session.execute(text(f"DELETE FROM {SEARCH_TABLE}"))
    session.commit()


def _digest(topic_id: int, seed: Seed, started: datetime) -> Digest:
    sections = []
    for i, heading in enumerate(HEADINGS[seed.article_type]):
        if i == 0:
            paragraphs = [{"text": sentence, "inference": False} for sentence in seed.body]
        else:
            paragraphs = [
                {"text": FILLER[i % len(FILLER)], "inference": heading in INFERENCE_HEADINGS}
            ]
        sections.append({"heading": heading, "paragraphs": paragraphs})
    return Digest(
        topic_id=topic_id,
        article_type=seed.article_type,
        lead=[seed.one_line, seed.body[0], seed.body[1]],
        sections=sections,
        model_id=MODEL,
        skill_version="sample",
        created_at=started + timedelta(minutes=3),
    )


def seed(session: Session, now: datetime | None = None) -> None:
    now = now or datetime.now(UTC)
    weights: dict[CriterionKey, int] = dict(DEFAULT_WEIGHTS)
    sources: dict[str, Source] = {}
    for key, name, kind in SOURCES:
        source = Source(key=key, name=name, kind=kind)
        session.add(source)
        sources[key] = source
    session.flush()

    runs: dict[int, Run] = {}
    for run_id, day, status, new, cost in (
        (1, 2, "succeeded", 31, 0.11),
        (2, 1, "partial", 44, 0.14),
        (3, 0, "succeeded", 38, 0.13),
    ):
        started = _run_start(now, day)
        run = Run(
            id=run_id,
            trigger="scheduled" if day else "manual",
            status=status,
            started_at=started,
            finished_at=started + timedelta(minutes=4, seconds=20),
            heartbeat_at=started + timedelta(minutes=4),
            new_count=new,
            cost_usd=cost,
            model_id=MODEL,
            previous_model_id="claude-haiku-4-5" if run_id == 3 else None,
        )
        session.add(run)
        session.flush()  # 外部キーのため、実行履歴を先に保存する
        runs[run_id] = run
        session.add(
            LlmUsage(
                run_id=run_id,
                purpose="score",
                model_id=MODEL,
                cost_usd=cost,
                created_at=started + timedelta(minutes=2),
            )
        )
        for query, language, count in _QUERIES:
            session.add(
                SearchQuery(run_id=run_id, query=query, language=language, result_count=count)
            )
        if status == "partial":
            session.add(
                RunIssue(
                    run_id=run_id,
                    source_name="Example AI Research",
                    stage="本文の取得",
                    message="ページの取得に失敗（タイムアウト）。次回の更新で再試行します",
                )
            )
    # 壁打ちなど、更新以外で使った費用の例
    session.add(LlmUsage(purpose="chat", model_id=MODEL, cost_usd=2.0, created_at=now))
    session.flush()

    for index, item in enumerate(seeds(), start=1):
        source = sources[item.source]
        run_id = 3 - item.day
        started = _run_start(now, item.day)
        scores: dict[CriterionKey, int] = {
            key: value for key, value in zip(_CRITERIA, item.scores, strict=True)
        }
        breakdown = build_breakdown(
            scores,
            weights,
            article_type=item.article_type,
            official=source.kind == "official",
            reason=f"関心{scores['interest']}・新しさ{scores['freshness']}・信頼{scores['trust']}。"
            "（サンプルの理由。実データでは Haiku が1行で書きます）",
        )
        selection = decide_selection(breakdown, SAMPLE_THRESHOLD)
        state = item.state
        topic = Topic(
            id=index,
            selection=selection,
            run_id=run_id,
            selected_at=started,
            read_state=state.read_state,
            backlog=state.backlog,
            starred=state.starred,
            rating=state.rating,
            dislike_reason=state.dislike_reason,
            missed=state.missed,
            read_at=started + timedelta(days=1) if state.read_state != "unread" else None,
            rated_at=started + timedelta(hours=2) if state.rating else None,
            missed_at=started + timedelta(hours=2) if state.missed else None,
        )
        session.add(topic)
        session.flush()
        published = started - timedelta(hours=3 + index % 9)
        article = Article(
            topic_id=index,
            role="representative",
            source_id=source.id,
            domain="example.com",
            url=f"https://example.com/sample/{index}",
            url_normalized=f"https://example.com/sample/{index}",
            title_original=item.title,
            language="ja",
            published_at=published,
            published_estimated=index % 11 == 0,
            discovered_at=started,
            run_id=run_id,
            stage="composed" if selection != "rejected" else "scored",
            fetch_status="full",
        )
        session.add(article)
        session.flush()
        assert article.id is not None
        session.add(
            ArticleText(
                article_id=article.id,
                body="\n".join([item.title, *item.body]),
                length=len(item.title),
            )
        )
        for n in range(1, item.related + 1):
            url = f"https://example.com/sample/{index}/related-{n}"
            session.add(
                Article(
                    topic_id=index,
                    role="related",
                    domain="example.com",
                    url=url,
                    url_normalized=url,
                    title_original=f"{item.title}（関連記事 {n}）",
                    language="ja",
                    published_at=published + timedelta(hours=n),
                    discovered_at=started,
                    run_id=run_id,
                    stage="grouped",
                    fetch_status="full",
                )
            )
        session.add(
            Score(
                topic_id=index,
                **scores,
                weights={k: v for k, v in weights.items()},
                official_bonus=breakdown.official_bonus,
                total=breakdown.total,
                reason=breakdown.reason,
                article_type=item.article_type,
                category=item.category,
                tags=list(item.tags),
                title_ja=item.title,
                summary_1line=item.one_line,
                summary_5lines=[
                    item.one_line,
                    *item.body,
                    f"情報源：{source.name}",
                    breakdown.reason,
                ],
                model_id=MODEL,
                skill_version="sample",
                run_id=run_id,
                scored_at=started,
            )
        )
        if selection != "rejected":
            session.add(_digest(index, item, started))
        session.flush()
        index_topic(session, index)

    for run_id, run in runs.items():
        mine = [t for t in session.exec(select(Topic).where(col(Topic.run_id) == run_id)).all()]
        run.scored_count = len(mine)
        run.selected_count = sum(1 for t in mine if t.selection != "rejected")
        session.add(run)
    set_sample_mode(session, True)
    session.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description="試しのデータを DB に入れる")
    parser.add_argument("--reset", action="store_true", help="全部消してから入れ直す")
    parser.add_argument("--clear", action="store_true", help="全部消すだけ")
    args = parser.parse_args()
    with Session(engine) as session:
        if args.reset or args.clear:
            clear(session)
            print("記事・実行履歴・費用・情報源を消しました")
        if args.clear:
            return
        if session.exec(select(Topic)).first() is not None:
            raise SystemExit("すでにデータがあります。入れ直すときは --reset を付けてください")
        seed(session)
        print(f"試しのデータを入れました（話題 {len(seeds())} 件）")


if __name__ == "__main__":
    main()
