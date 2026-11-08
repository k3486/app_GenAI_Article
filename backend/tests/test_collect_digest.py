"""整理記事の作成（偽の Haiku を使う）。"""

from datetime import UTC, datetime, timedelta

from sqlmodel import Session, select

from app.models import Article, ArticleText, Digest, LlmUsage, Run, RunIssue, Score, Source, Topic
from app.schemas.analysis import (
    DigestOutput,
    DigestParagraph,
    DigestSection,
    ParagraphVerdict,
    VerifyOutput,
)
from app.services.app_settings import load_settings
from app.services.collect.digest import digest_selected
from app.services.llm.budget import Budget
from app.services.llm.client import Llm
from app.services.llm.errors import LlmError, LlmFormatError
from app.services.llm.skills import load_skill
from tests.fake_llm import FakeBackend

NOW = datetime(2026, 11, 7, 3, 0, tzinfo=UTC)


def make_llm(responder, *, run_limit: float = 0.5) -> tuple[Llm, FakeBackend]:  # type: ignore[no-untyped-def]
    backend = FakeBackend(responder)
    budget = Budget(run_limit_usd=run_limit, month_limit_usd=10.0, month_spent_usd=0.0)
    return Llm(backend, "claude-haiku-5-5", budget), backend


def responder(  # type: ignore[no-untyped-def]
    written: DigestOutput | None = None,
    *,
    ai: tuple[int, ...] = (),
    verify: VerifyOutput | LlmError | None = None,
    write_error: LlmError | None = None,
):
    """書き手（DigestOutput）と校閲（VerifyOutput）の呼び出しに、それぞれ答える偽物。"""

    def respond(output_type: type, system: list[str], user: str):  # type: ignore[no-untyped-def]
        if output_type is VerifyOutput:
            if verify is not None:
                return verify
            count = user.count("<段落 index=")
            return VerifyOutput(
                verdicts=[
                    ParagraphVerdict(
                        index=i, origin="ai" if i in ai else "article", reason="テスト"
                    )
                    for i in range(count)
                ]
            )
        return write_error or written or digest_output()

    return respond


def digest_output(note: str = "本文") -> DigestOutput:
    return DigestOutput(
        lead=["1行目です。", "2行目です。", "3行目です。"],
        sections=[
            DigestSection(
                heading="何が変わったか",
                paragraphs=[
                    DigestParagraph(text=f"{note}の事実です。", inference=False),
                    DigestParagraph(text=f"{note}の推測です。", inference=True),
                ],
            )
        ],
    )


def make_run(session: Session) -> Run:
    run = Run(trigger="manual", started_at=NOW, heartbeat_at=NOW)
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def selected_topic(
    session: Session,
    run: Run,
    n: int,
    *,
    selection: str = "selected",
    article_type: str = "announcement",
    total: int = 80,
    fetch_status: str = "full",
    body: str | None = None,
) -> Topic:
    topic = Topic(selection=selection, run_id=run.id, created_at=NOW)
    session.add(topic)
    session.flush()
    source = Source(key=f"s{n}", name=f"情報源{n}", kind="official")
    session.add(source)
    session.flush()
    rep = Article(
        topic_id=topic.id,
        source_id=source.id,
        role="representative",
        domain=f"s{n}.example.com",
        url=f"https://s{n}.example.com/a",
        url_normalized=f"https://s{n}.example.com/a",
        title_original=f"Title {n}",
        published_at=NOW - timedelta(hours=1),
        stage="scored",
        fetch_status=fetch_status,
        summary="summary",
    )
    session.add(rep)
    session.flush()
    session.add(ArticleText(article_id=rep.id or 0, body=body or f"本文{n}", length=10))
    session.add(
        Score(
            topic_id=topic.id or 0,
            interest=4,
            practical=4,
            freshness=4,
            trust=4,
            depth=4,
            weights={"interest": 20, "practical": 25, "freshness": 25, "trust": 15, "depth": 15},
            official_bonus=0,
            total=total,
            article_type=article_type,
            category="models",
            title_ja=f"記事{n}",
        )
    )
    session.commit()
    return topic


def add_related(session: Session, topic: Topic, n: int, *, fetch_status: str = "full") -> None:
    other = Article(
        topic_id=topic.id,
        role="related",
        domain="rel.example.com",
        url=f"https://rel.example.com/{n}",
        url_normalized=f"https://rel.example.com/{n}",
        title_original=f"Related {n}",
        published_at=NOW,
        stage="grouped",
        fetch_status=fetch_status,
        summary="summary",
    )
    session.add(other)
    session.flush()
    session.add(ArticleText(article_id=other.id or 0, body=f"関連本文{n}", length=10))
    session.commit()


async def test_digest_is_saved_for_selected_topics_only(session: Session) -> None:
    run = make_run(session)
    chosen = selected_topic(session, run, 1)
    major = selected_topic(session, run, 2, selection="major")
    rejected = selected_topic(session, run, 3, selection="rejected")
    llm, _ = make_llm(responder())
    report = await digest_selected(session, llm, run=run, settings=load_settings(session), now=NOW)
    assert report.created == 2 and report.failed == 0
    assert session.get(Digest, chosen.id) is not None
    assert session.get(Digest, major.id) is not None
    assert session.get(Digest, rejected.id) is None
    saved = session.get(Digest, chosen.id)
    assert saved is not None
    assert saved.article_type == "announcement" and saved.model_id == "claude-haiku-5-5"
    assert saved.sections[0]["paragraphs"][1] == {"text": "本文の推測です。", "inference": True}
    assert {u.purpose for u in session.exec(select(LlmUsage)).all()} == {"digest", "verify"}


async def test_skill_follows_the_article_type_and_includes_the_shared_style(
    session: Session,
) -> None:
    run = make_run(session)
    selected_topic(session, run, 1, article_type="paper")
    selected_topic(session, run, 2, article_type="howto")
    llm, backend = make_llm(responder())
    await digest_selected(session, llm, run=run, settings=load_settings(session), now=NOW)
    systems = {c.system[0] for c in backend.calls if c.output_type is DigestOutput}
    assert any("論文・研究" in s and "最大2,000字" in s for s in systems)
    assert any("活用ノウハウ・事例" in s for s in systems)
    assert all("出どころを分ける" in s for s in systems)  # 共通の文体


async def test_materials_include_the_body_and_full_text_related_articles_only(
    session: Session,
) -> None:
    run = make_run(session)
    topic = selected_topic(session, run, 1, body="代表の本文")
    add_related(session, topic, 1)
    add_related(session, topic, 2, fetch_status="partial")
    llm, backend = make_llm(responder())
    await digest_selected(session, llm, run=run, settings=load_settings(session), now=NOW)
    user = next(c.user for c in backend.calls if c.output_type is DigestOutput)
    assert "代表の本文" in user and "関連本文1" in user
    assert "関連本文2" not in user  # 全文のない関連記事は使わない
    assert "https://" not in user  # URL は Haiku に渡さない


async def test_existing_digest_is_not_recreated(session: Session) -> None:
    run = make_run(session)
    selected_topic(session, run, 1)
    llm, backend = make_llm(responder())
    settings = load_settings(session)
    await digest_selected(session, llm, run=run, settings=settings, now=NOW)
    again = await digest_selected(session, llm, run=run, settings=settings, now=NOW)
    assert again.created == 0 and len(backend.calls) == 2  # 書く・校閲の1回ずつだけ


async def test_failure_leaves_no_digest_records_an_issue_and_is_retried(
    session: Session,
) -> None:
    run = make_run(session)
    topic = selected_topic(session, run, 1)
    llm, _ = make_llm(responder(write_error=LlmFormatError("形式が不正")))
    settings = load_settings(session)
    report = await digest_selected(session, llm, run=run, settings=settings, now=NOW)
    assert (report.created, report.failed) == (0, 1)
    assert session.get(Digest, topic.id) is None
    issue = session.exec(select(RunIssue)).one()
    assert issue.stage == "整理記事" and "次回" in issue.message
    ok_llm, _ = make_llm(responder())
    retried = await digest_selected(session, ok_llm, run=run, settings=settings, now=NOW)
    assert retried.created == 1 and session.get(Digest, topic.id) is not None


async def test_verifier_turns_unsupported_paragraphs_into_ai_opinion(session: Session) -> None:
    """書き手が事実とした段落でも、校閲が AI の意見と判定すれば AI の意見にする。"""
    run = make_run(session)
    topic = selected_topic(session, run, 1)
    llm, _ = make_llm(responder(ai=(0,)))  # 段落0（書き手は事実）を校閲が AI の意見と判定
    await digest_selected(session, llm, run=run, settings=load_settings(session), now=NOW)
    saved = session.get(Digest, topic.id)
    assert saved is not None
    flags = [p["inference"] for s in saved.sections for p in s["paragraphs"]]
    assert flags == [True, True]  # 0: 校閲が AI / 1: 書き手が AI（校閲は記事の内容）


async def test_fact_label_requires_both_writer_and_verifier(session: Session) -> None:
    run = make_run(session)
    topic = selected_topic(session, run, 1)
    written = DigestOutput(
        lead=["1行目です。", "2行目です。", "3行目です。"],
        sections=[
            DigestSection(
                heading="a",
                paragraphs=[
                    DigestParagraph(text="事実", inference=False),
                    DigestParagraph(text="意見", inference=True),
                ],
            )
        ],
    )
    llm, _ = make_llm(responder(written))  # 校閲は両方とも記事の内容と判定
    await digest_selected(session, llm, run=run, settings=load_settings(session), now=NOW)
    saved = session.get(Digest, topic.id)
    assert saved is not None
    flags = [p["inference"] for s in saved.sections for p in s["paragraphs"]]
    assert flags == [
        False,
        True,
    ]  # 書き手が AI の意見とした段落は、校閲が記事の内容と言っても AI の意見


async def test_paragraph_without_a_verdict_is_treated_as_ai_opinion(session: Session) -> None:
    run = make_run(session)
    topic = selected_topic(session, run, 1)
    only_first = VerifyOutput(
        verdicts=[ParagraphVerdict(index=0, origin="article", reason="テスト")]
    )
    llm, _ = make_llm(responder(verify=only_first))
    await digest_selected(session, llm, run=run, settings=load_settings(session), now=NOW)
    saved = session.get(Digest, topic.id)
    assert saved is not None
    flags = [p["inference"] for s in saved.sections for p in s["paragraphs"]]
    assert flags == [False, True]  # 段落1は判定がない（かつ書き手も AI の意見）


async def test_verifier_gets_numbered_paragraphs_and_the_materials(session: Session) -> None:
    run = make_run(session)
    selected_topic(session, run, 1, body="代表の本文")
    llm, backend = make_llm(responder())
    await digest_selected(session, llm, run=run, settings=load_settings(session), now=NOW)
    verify_calls = [c for c in backend.calls if c.output_type is VerifyOutput]
    assert len(verify_calls) == 1
    user = verify_calls[0].user
    assert "代表の本文" in user  # 材料と照らすために本文を渡す
    assert '<段落 index="0">' in user and '<段落 index="1">' in user
    assert "本文の事実です。" in user
    assert "判定" in verify_calls[0].system[0]


async def test_verification_failure_leaves_no_digest_and_is_retried(session: Session) -> None:
    run = make_run(session)
    topic = selected_topic(session, run, 1)
    llm, _ = make_llm(responder(verify=LlmFormatError("校閲の形式が不正")))
    settings = load_settings(session)
    report = await digest_selected(session, llm, run=run, settings=settings, now=NOW)
    assert (report.created, report.failed) == (0, 1)
    assert session.get(Digest, topic.id) is None  # 校閲を通っていない整理記事は出さない
    purposes = {u.purpose for u in session.exec(select(LlmUsage)).all()}
    assert purposes == {"digest"}  # 書いた分の実費は残る
    assert session.exec(select(RunIssue)).one().stage == "整理記事"
    ok_llm, _ = make_llm(responder())
    retried = await digest_selected(session, ok_llm, run=run, settings=settings, now=NOW)
    assert retried.created == 1


async def test_budget_limit_stops_and_leaves_the_rest_for_next_time(session: Session) -> None:
    run = make_run(session)
    for n in (1, 2, 3):
        selected_topic(session, run, n)
    llm, _ = make_llm(responder(), run_limit=0.0000001)
    report = await digest_selected(session, llm, run=run, settings=load_settings(session), now=NOW)
    assert report.budget_stopped and report.created == 0
    assert session.exec(select(Digest)).all() == []


async def test_digest_is_searchable_after_creation(session: Session) -> None:
    from app.services.search import search_topic_ids

    run = make_run(session)
    topic = selected_topic(session, run, 1)
    llm, _ = make_llm(responder(digest_output("固有キーワード")))
    await digest_selected(session, llm, run=run, settings=load_settings(session), now=NOW)
    assert topic.id in search_topic_ids(session, "固有キーワード")


def test_lead_must_be_exactly_three_lines() -> None:
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        DigestOutput(lead=["1行だけ"], sections=digest_output().sections)


def test_every_article_type_has_a_skill_with_the_style_appended() -> None:
    for name in ("announcement", "howto", "paper", "analysis", "industry"):
        skill = load_skill(f"compose-{name}", shared=("_style.md",))
        assert "構成" in skill.text and "URL・リンク・記事 ID を書かない" in skill.text
