from datetime import UTC, datetime, timedelta

from pydantic import BaseModel
from sqlmodel import Session, select

from app.models import Article, ArticleText, LlmUsage, Run, RunIssue, Score, Source, Topic
from app.schemas.analysis import GroupOutput, TopicJoin
from app.schemas.settings import Settings
from app.services.app_settings import load_settings
from app.services.collect.group import group_new
from app.services.collect.score import score_pending
from app.services.collect.select import select_scored
from app.services.llm.budget import Budget
from app.services.llm.client import Llm
from app.services.llm.errors import LlmError, LlmUnavailableError
from tests.fake_llm import FakeBackend, score_output

NOW = datetime(2026, 11, 7, 3, 0, tzinfo=UTC)
MODEL = "claude-haiku-5-5"


def make_run(session: Session) -> Run:
    run = Run(trigger="manual", started_at=NOW, heartbeat_at=NOW)
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def make_source(session: Session, key: str, kind: str = "media") -> Source:
    source = Source(key=key, name=key.upper(), kind=kind)
    session.add(source)
    session.commit()
    session.refresh(source)
    return source


def make_article(
    session: Session,
    source: Source,
    n: int,
    *,
    stage: str = "fetched",
    fetch_status: str = "full",
    hours_ago: int = 1,
    link_key: str | None = None,
    body: str | None = None,
    is_paper: bool = False,
) -> Article:
    article = Article(
        source_id=source.id,
        domain=f"{source.key}.example.com",
        url=f"https://{source.key}.example.com/{n}",
        url_normalized=f"https://{source.key}.example.com/{n}",
        title_original=f"Title {n}",
        published_at=NOW - timedelta(hours=hours_ago),
        stage=stage,
        fetch_status=fetch_status,
        link_key=link_key,
        is_paper=is_paper,
        summary="summary",
    )
    session.add(article)
    session.flush()
    assert article.id is not None
    text = body if body is not None else f"Body of article {n}"
    session.add(ArticleText(article_id=article.id, body=text, length=len(text)))
    session.commit()
    session.refresh(article)
    return article


def make_llm(responder, **kw: object) -> tuple[Llm, FakeBackend]:  # type: ignore[no-untyped-def]
    backend = FakeBackend(responder, **kw)  # type: ignore[arg-type]
    budget = Budget(run_limit_usd=0.5, month_limit_usd=10.0, month_spent_usd=0.0)
    return Llm(backend, MODEL, budget), backend


def no_group(*_: object) -> BaseModel:
    return GroupOutput(joins=[], same_topic_sets=[])


# --- 話題のまとめ ---


async def test_same_link_key_is_grouped_without_calling_haiku(session: Session) -> None:
    run = make_run(session)
    official = make_source(session, "lab", "official")
    media = make_source(session, "news", "media")
    a1 = make_article(session, media, 1, link_key="arxiv:2611.0001", hours_ago=5)
    a2 = make_article(session, official, 2, link_key="arxiv:2611.0001", hours_ago=2)
    llm, backend = make_llm(no_group)
    report = await group_new(session, llm, run=run, now=NOW)
    session.refresh(a1)
    session.refresh(a2)
    assert backend.calls == []  # 共通リンクだけで決まる分は、Haiku を使わない
    assert a1.topic_id == a2.topic_id and a1.stage == a2.stage == "grouped"
    assert (a2.role, a1.role) == ("representative", "related")  # 公式が代表
    assert (report.new_topics, report.merged) == (1, 1)


async def test_link_key_joins_an_existing_topic(session: Session) -> None:
    run = make_run(session)
    src = make_source(session, "news")
    old = make_article(session, src, 1, stage="scored", link_key="arxiv:1", hours_ago=30)
    topic = Topic(selection="pending", run_id=run.id, created_at=NOW)
    session.add(topic)
    session.flush()
    old.topic_id = topic.id
    session.add(old)
    session.commit()
    new = make_article(session, src, 2, link_key="arxiv:1")
    report = await group_new(session, None, run=run, now=NOW)
    session.refresh(new)
    assert new.topic_id == topic.id and new.role == "related" and report.joined == 1


async def test_haiku_decides_joins_and_sets_and_ignores_unknown_ids(session: Session) -> None:
    run = make_run(session)
    src = make_source(session, "news")
    first = make_article(session, src, 1, hours_ago=30)
    topic = Topic(selection="pending", run_id=run.id, created_at=NOW - timedelta(hours=30))
    session.add(topic)
    session.flush()
    first.topic_id, first.stage = topic.id, "scored"
    session.add(first)
    session.commit()
    a2, a3, a4, a5 = (make_article(session, src, n) for n in (2, 3, 4, 5))
    assert topic.id is not None and a2.id and a3.id and a4.id

    def responder(*_: object) -> BaseModel:
        return GroupOutput(
            joins=[
                TopicJoin(article_id=a2.id or 0, topic_id=topic.id or 0),
                TopicJoin(article_id=999, topic_id=topic.id or 0),
            ],
            same_topic_sets=[[a3.id or 0, a4.id or 0, 12345]],
        )

    llm, backend = make_llm(responder)
    report = await group_new(session, llm, run=run, now=NOW)
    for a in (a2, a3, a4, a5):
        session.refresh(a)
    assert a2.topic_id == topic.id
    assert a3.topic_id == a4.topic_id and a3.topic_id != a5.topic_id
    assert (report.joined, report.merged, report.new_topics) == (1, 1, 2)
    assert "話題ID" in backend.calls[0].system[1] and "Title 1" in backend.calls[0].system[1]
    assert session.exec(select(LlmUsage)).one().purpose == "group"


async def test_haiku_failure_makes_single_topics_and_records_the_issue(session: Session) -> None:
    run = make_run(session)
    src = make_source(session, "news")
    a1, a2 = make_article(session, src, 1), make_article(session, src, 2)
    llm, _ = make_llm(lambda *_: LlmUnavailableError("down"))
    report = await group_new(session, llm, run=run, now=NOW)
    session.refresh(a1)
    session.refresh(a2)
    assert a1.topic_id != a2.topic_id and report.llm_failed
    assert session.exec(select(RunIssue)).one().stage == "話題のまとめ"


async def test_group_without_llm_still_creates_single_topics(session: Session) -> None:
    run = make_run(session)
    a1 = make_article(session, make_source(session, "news"), 1)
    await group_new(session, None, run=run, now=NOW)
    session.refresh(a1)
    assert a1.topic_id is not None and a1.stage == "grouped" and a1.role == "representative"


# --- 採点 ---


def grouped(session: Session, run: Run, article: Article) -> Topic:
    topic = Topic(selection="pending", run_id=run.id, created_at=NOW)
    session.add(topic)
    session.flush()
    article.topic_id, article.stage = topic.id, "grouped"
    session.add(article)
    session.commit()
    return topic


async def test_score_writes_scores_usage_and_computes_the_total(session: Session) -> None:
    run = make_run(session)
    official = make_source(session, "lab", "official")
    article = make_article(session, official, 1)
    topic = grouped(session, run, article)
    llm, backend = make_llm(
        lambda *_: score_output(interest=5, practical=5, freshness=5, trust=5, depth=5)
    )
    report = await score_pending(session, llm, run=run, settings=load_settings(session), now=NOW)
    score = session.get(Score, topic.id)
    assert score is not None and report.scored == 1
    assert score.total == 105  # 100点 + 公式 5点
    assert score.official_bonus == 5 and score.model_id == MODEL and len(score.skill_version) == 12
    session.refresh(article)
    assert article.stage == "scored"
    usage = session.exec(select(LlmUsage)).one()
    assert usage.purpose == "score" and usage.topic_id == topic.id and usage.cost_usd > 0
    session.refresh(run)
    assert run.scored_count == 1 and run.cost_usd == usage.cost_usd
    assert "興味プロファイル" in backend.calls[0].system[1]
    assert "Body of article 1" in backend.calls[0].user


async def test_score_respects_the_cap_and_prefers_official_then_newest(session: Session) -> None:
    run = make_run(session)
    official = make_source(session, "lab", "official")
    media = make_source(session, "news")
    old_official = make_article(session, official, 1, hours_ago=40)
    new_media = make_article(session, media, 2, hours_ago=1)
    older_media = make_article(session, media, 3, hours_ago=20)
    topics = {a.id: grouped(session, run, a) for a in (old_official, new_media, older_media)}
    settings = load_settings(session).model_copy(update={"max_scored": 2})
    llm, _ = make_llm(lambda *_: score_output())
    report = await score_pending(session, llm, run=run, settings=settings, now=NOW)
    scored = set(session.exec(select(Score.topic_id)).all())
    assert scored == {topics[old_official.id].id, topics[new_media.id].id}
    assert report.deferred == 1
    session.refresh(older_media)
    assert older_media.stage == "grouped"  # 次回に回る


async def test_partial_representative_borrows_the_text_of_related_articles(
    session: Session,
) -> None:
    run = make_run(session)
    official = make_source(session, "lab", "official")
    media = make_source(session, "news")
    rep = make_article(session, official, 1, fetch_status="partial", body="short summary")
    related = make_article(session, media, 2, body="The full story from the media.")
    topic = grouped(session, run, rep)
    related.topic_id, related.role, related.stage = topic.id, "related", "grouped"
    session.add(related)
    session.commit()
    llm, backend = make_llm(lambda *_: score_output())
    await score_pending(session, llm, run=run, settings=load_settings(session), now=NOW)
    user = backend.calls[0].user
    assert "概要のみ（全文未取得）" in user and "The full story from the media." in user


async def test_failures_are_recorded_and_the_article_is_left_for_next_time(
    session: Session,
) -> None:
    run = make_run(session)
    src = make_source(session, "news")
    ok, bad = make_article(session, src, 1), make_article(session, src, 2)
    t_ok, _t_bad = grouped(session, run, ok), grouped(session, run, bad)

    def responder(_t: type[BaseModel], _s: list[str], user: str) -> BaseModel | LlmError:
        return LlmUnavailableError("503") if "Title 2" in user else score_output()

    llm, _ = make_llm(responder)
    report = await score_pending(session, llm, run=run, settings=load_settings(session), now=NOW)
    assert (report.scored, report.failed) == (1, 1)
    assert session.get(Score, t_ok.id) is not None
    session.refresh(bad)
    assert bad.stage == "grouped"
    assert session.exec(select(RunIssue)).one().stage == "採点"


async def test_budget_stops_scoring_and_leaves_the_rest_pending(session: Session) -> None:
    run = make_run(session)
    src = make_source(session, "news")
    articles = [make_article(session, src, n) for n in range(1, 4)]
    for a in articles:
        grouped(session, run, a)
    # 1回の実費が 1回の上限（$0.5）を超える偽物: 最初の1件で上限に達する
    backend = FakeBackend(lambda *_: score_output(), input_tokens=6_000_000)
    llm = Llm(backend, MODEL, Budget(run_limit_usd=0.5, month_limit_usd=10, month_spent_usd=0))
    report = await score_pending(session, llm, run=run, settings=load_settings(session), now=NOW)
    assert report.budget_stopped and report.scored == 1 and len(backend.calls) == 1
    stages = sorted(session.get(Article, a.id).stage for a in articles)  # type: ignore[union-attr]
    assert stages == ["grouped", "grouped", "scored"]  # 残りは次回に回る


async def test_feedback_is_put_into_the_context(session: Session) -> None:
    run = make_run(session)
    src = make_source(session, "news")
    liked = make_article(session, src, 1, stage="scored")
    topic = grouped(session, run, liked)
    liked.stage = "scored"  # 採点済み（再採点の対象にしない）
    session.add(liked)
    session.add(
        Score(
            topic_id=topic.id or 0,
            interest=3,
            practical=3,
            freshness=3,
            trust=3,
            depth=3,
            weights={},
            total=50,
            article_type="howto",
            category="know_how",
            title_ja="好きだった記事",
        )
    )
    topic.rating = "like"
    session.add(topic)
    session.commit()
    target = make_article(session, src, 2)
    grouped(session, run, target)
    llm, backend = make_llm(lambda *_: score_output())
    await score_pending(session, llm, run=run, settings=load_settings(session), now=NOW)
    assert "好きだった記事" in backend.calls[0].system[1]


# --- 選定 ---


def scored_topic(
    session: Session,
    run: Run,
    n: int,
    *,
    level: int,
    interest: int | None = None,
    freshness: int | None = None,
) -> Topic:
    """5観点を同じ点（level）にした採点済みの話題。level 3→50点、4→75点、5→100点。"""
    topic = Topic(selection="pending", run_id=run.id, created_at=NOW)
    session.add(topic)
    session.flush()
    session.add(
        Score(
            topic_id=topic.id or 0,
            interest=interest or level,
            practical=level,
            freshness=freshness or level,
            trust=level,
            depth=level,
            weights={"interest": 20, "practical": 25, "freshness": 25, "trust": 15, "depth": 15},
            official_bonus=0,
            total=0,  # 選定は内訳から計算し直す
            article_type="howto",
            category="know_how",
            title_ja=f"記事{n}",
        )
    )
    session.commit()
    return topic


def settings_with(session: Session, **update: int) -> Settings:
    return load_settings(session).model_copy(update=update)


def test_select_applies_threshold_and_cap(session: Session) -> None:
    run = make_run(session)
    top = scored_topic(session, run, 1, level=5)
    second = scored_topic(session, run, 2, level=4)
    third = scored_topic(session, run, 3, level=4)
    low = scored_topic(session, run, 4, level=3)  # 50点: しきい値 60 未満
    settings = settings_with(session, max_selected=2, max_major=0)
    report = select_scored(session, run=run, settings=settings, now=NOW)
    states = {t.id: t.selection for t in (top, second, third, low)}
    assert states == {
        top.id: "selected",
        second.id: "selected",  # 同点は先に出たものを優先
        third.id: "rejected",
        low.id: "rejected",
    }
    assert (report.selected, report.major, report.rejected) == (2, 0, 2)
    session.refresh(top)
    assert top.selected_at == NOW
    session.refresh(run)
    assert run.selected_count == 2


def test_overflow_with_top_freshness_becomes_major(session: Session) -> None:
    run = make_run(session)
    best = scored_topic(session, run, 1, level=5)
    fresh = scored_topic(session, run, 2, level=4, freshness=5)  # 上限からあふれるが新しさ 5
    plain = scored_topic(session, run, 3, level=4)
    settings = settings_with(session, max_selected=1, max_major=1)
    report = select_scored(session, run=run, settings=settings, now=NOW)
    for t in (best, fresh, plain):
        session.refresh(t)
    assert (best.selection, fresh.selection, plain.selection) == ("selected", "major", "rejected")
    assert (report.selected, report.major, report.rejected) == (1, 1, 1)


def test_low_interest_never_enters_the_normal_selection_but_can_be_major(
    session: Session,
) -> None:
    run = make_run(session)
    off_topic_big_news = scored_topic(session, run, 1, level=5, interest=2)
    off_topic_minor = scored_topic(session, run, 2, level=4, interest=2)
    settings = settings_with(session, max_selected=10, max_major=3)
    select_scored(session, run=run, settings=settings, now=NOW)
    session.refresh(off_topic_big_news)
    session.refresh(off_topic_minor)
    assert off_topic_big_news.selection == "major"
    assert off_topic_minor.selection == "rejected"


def test_already_decided_topics_are_left_alone(session: Session) -> None:
    run = make_run(session)
    decided = scored_topic(session, run, 1, level=5)
    decided.selection = "rejected"
    session.add(decided)
    session.commit()
    report = select_scored(session, run=run, settings=load_settings(session), now=NOW)
    session.refresh(decided)
    assert decided.selection == "rejected" and report.selected == 0


def test_recompute_applies_new_settings_without_haiku_and_keeps_selected_at(
    session: Session,
) -> None:
    run = make_run(session)
    kept = scored_topic(session, run, 1, level=5)
    border = scored_topic(session, run, 2, level=4)  # 75点
    settings = settings_with(session, threshold=60, max_selected=10, max_major=0)
    select_scored(session, run=run, settings=settings, now=NOW)
    session.refresh(kept)
    session.refresh(border)
    assert (kept.selection, border.selection) == ("selected", "selected")

    later = NOW + timedelta(days=1)
    stricter = settings_with(session, threshold=80, max_selected=10, max_major=0)
    dry = select_scored(
        session, run=None, settings=stricter, now=later, recompute=True, dry_run=True
    )
    session.refresh(border)
    assert dry.rejected == 1 and border.selection == "selected"  # dry_run は保存しない

    select_scored(session, run=None, settings=stricter, now=later, recompute=True)
    session.refresh(kept)
    session.refresh(border)
    assert (kept.selection, border.selection) == ("selected", "rejected")
    assert kept.selected_at == NOW  # 選定日は変えない


def test_recompute_refreshes_the_official_bonus_from_the_current_rule(session: Session) -> None:
    run = make_run(session)
    topic = scored_topic(session, run, 1, level=5)
    score = session.get(Score, topic.id)
    assert score is not None
    score.official_bonus, score.total = 10, 110  # 加点が +10 だった頃の保存値
    session.add(score)
    session.commit()
    select_scored(session, run=None, settings=load_settings(session), now=NOW, recompute=True)
    session.refresh(score)
    assert (score.official_bonus, score.total) == (5, 105)


def test_the_cap_applies_per_run_when_recomputing(session: Session) -> None:
    first, second = make_run(session), make_run(session)
    a = scored_topic(session, first, 1, level=5)
    b = scored_topic(session, second, 2, level=5)
    for topic, run in ((a, first), (b, second)):
        score = session.get(Score, topic.id)
        assert score is not None
        score.run_id = run.id
        session.add(score)
    session.commit()
    settings = settings_with(session, max_selected=1, max_major=0)
    select_scored(session, run=None, settings=settings, now=NOW, recompute=True)
    session.refresh(a)
    session.refresh(b)
    assert (a.selection, b.selection) == ("selected", "selected")  # 回ごとに1件まで
