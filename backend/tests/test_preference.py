"""好みメモ・興味プロファイルの修正案・プロファイルの履歴（偽の Haiku を使う）。"""

from datetime import timedelta
from itertools import count as counter
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, col, select

from app.db import get_session
from app.main import create_app
from app.models import (
    LlmUsage,
    PreferenceNote,
    ProfileProposal,
    ProfileVersion,
    Run,
    Score,
    Topic,
)
from app.schemas.preference import PreferenceOutput, ProposalDraft
from app.services import preference as service
from app.services.app_settings import load_settings, save_settings
from app.services.collect.score import score_pending
from app.services.llm.context import build_scoring_context
from app.services.preference import UPDATE_EVERY, maybe_update
from tests.fake_llm import score_output
from tests.test_collect_analyze import grouped, make_article, make_source
from tests.test_collect_digest import NOW, make_llm, make_run, selected_topic

_ids = counter(100)
PROFILE = "# 興味\n- Claude Code の活用\n- 新しいモデルの性能比較\n- 暗号資産の話題\n"


@pytest.fixture(autouse=True)
def profile(session: Session) -> None:
    save_settings(session, load_settings(session).model_copy(update={"profile": PROFILE}))
    for version in session.exec(select(ProfileVersion)).all():  # 初期設定の版は数えない
        session.delete(version)
    session.commit()


def rated_topics(session: Session, amount: int, *, rating: str = "like") -> list[Topic]:
    run = session.get(Run, 1) or make_run(session)
    topics = []
    for n in range(1, amount + 1):
        topic = selected_topic(session, run, next(_ids))
        topic.rating = rating
        topic.rated_at = NOW - timedelta(days=1) + timedelta(minutes=n)  # 更新より前に付けた評価
        session.add(topic)
        topics.append(topic)
    session.commit()
    return topics


def output(*proposals: ProposalDraft, memo: str = "好みのメモです") -> PreferenceOutput:
    return PreferenceOutput(memo=memo, proposals=list(proposals))


def draft(kind: str, before: str, after: str, ids: list[int]) -> ProposalDraft:
    return ProposalDraft(
        kind=kind,
        before_text=before,
        after_text=after,
        reason="理由です",
        evidence_topic_ids=ids,
    )


async def update(session: Session, out: PreferenceOutput, force: bool = False) -> Any:
    llm, backend = make_llm(lambda *_: out)
    report = await maybe_update(
        session, llm, run=None, settings=load_settings(session), now=NOW, force=force
    )
    return report, backend


# --- いつ更新するか -------------------------------------------------------------


async def test_not_called_until_twenty_ratings_have_accumulated(session: Session) -> None:
    rated_topics(session, UPDATE_EVERY - 1)
    report, backend = await update(session, output())
    assert not report.updated and backend.calls == []
    assert service.feedback_since_last_note(session) == UPDATE_EVERY - 1


async def test_called_at_twenty_and_the_count_restarts_after_the_note(session: Session) -> None:
    topics = rated_topics(session, UPDATE_EVERY)
    report, backend = await update(session, output())
    assert report.updated and len(backend.calls) == 1
    note = session.exec(select(PreferenceNote)).one()
    assert note.source == "haiku" and note.based_on_count == UPDATE_EVERY
    assert service.feedback_since_last_note(session) == 0  # 数え直し
    again, backend2 = await update(session, output())
    assert not again.updated and backend2.calls == []
    # 新しい評価が20件たまると、また更新される
    for t in rated_topics(session, UPDATE_EVERY):
        t.rated_at = NOW + timedelta(days=1)
        session.add(t)
    session.commit()
    third, _ = await update(session, output())
    assert third.updated and topics


async def test_force_updates_with_few_ratings_but_not_with_none(session: Session) -> None:
    empty, backend = await update(session, output(), force=True)
    assert not empty.updated and backend.calls == []  # 評価が0件なら材料がない
    rated_topics(session, 3)
    forced, _ = await update(session, output(), force=True)
    assert forced.updated


async def test_a_missed_topic_counts_as_feedback(session: Session) -> None:
    topic = selected_topic(session, make_run(session), 1)
    topic.missed = True
    topic.missed_at = NOW
    session.add(topic)
    session.commit()
    assert service.feedback_since_last_note(session) == 1


async def test_manual_memo_restarts_the_count_too(session: Session) -> None:
    rated_topics(session, 5)
    service.save_memo(session, "自分で書いたメモ", now=NOW + timedelta(hours=1))
    state = service.get_state(session)
    assert state.source == "manual" and state.text == "自分で書いたメモ"
    assert state.feedback_since == 0 and state.update_every == 20


async def test_cost_is_recorded_as_preference_usage(session: Session) -> None:
    rated_topics(session, UPDATE_EVERY)
    await update(session, output())
    usage = session.exec(select(LlmUsage)).one()
    assert usage.purpose == "preference" and usage.cost_usd > 0


async def test_haiku_failure_changes_nothing_and_is_retried(session: Session) -> None:
    from app.services.llm.errors import LlmFormatError

    rated_topics(session, UPDATE_EVERY)
    llm, _ = make_llm(lambda *_: LlmFormatError("不正"))
    report = await maybe_update(session, llm, run=None, settings=load_settings(session), now=NOW)
    assert report.failed and not report.updated
    assert session.exec(select(PreferenceNote)).all() == []
    assert service.feedback_since_last_note(session) == UPDATE_EVERY  # 次回また試す


# --- 修正案の確かめ -------------------------------------------------------------


async def test_valid_proposals_are_saved_and_invalid_ones_are_dropped(session: Session) -> None:
    topics = rated_topics(session, UPDATE_EVERY)
    ids = [topics[0].id or 0, topics[1].id or 0]
    out = output(
        draft("add", "", "- ローカルLLMの運用", ids),  # 有効
        draft("add", "", "- Claude Code の活用", ids),  # すでにプロファイルにある
        draft("remove", "- 存在しない文", "", ids),  # 変更前の文が無い
    )
    report, _ = await update(session, out)
    assert report.proposals == 1
    saved = session.exec(select(ProfileProposal)).one()
    assert (saved.kind, saved.after_text, saved.status) == (
        "add",
        "- ローカルLLMの運用",
        "pending",
    )
    assert saved.evidence_topic_ids == ids


async def test_more_invalid_proposals_are_dropped(session: Session) -> None:
    topics = rated_topics(session, UPDATE_EVERY)
    ids = [topics[0].id or 0]
    out = output(
        draft("rephrase", "- 暗号資産の話題", "- 暗号資産の話題", ids),  # 変化なし
        draft("remove", "- 暗号資産の話題", "", [9999]),  # 根拠が評価済みの話題でない
        draft("add", "", "", ids),  # 追加する文が空
    )
    report, _ = await update(session, out)
    assert report.updated and report.proposals == 0
    assert session.exec(select(ProfileProposal)).all() == []
    assert session.exec(select(PreferenceNote)).one().text == "好みのメモです"  # メモは残る


async def test_at_most_three_pending_proposals(session: Session) -> None:
    topics = rated_topics(session, UPDATE_EVERY)
    ids = [topics[0].id or 0]
    out = output(*(draft("add", "", f"- 新しい好み{i}", ids) for i in range(3)))
    await update(session, out)
    assert len(session.exec(select(ProfileProposal)).all()) == 3
    # 未決が3件あるので、次の更新では増えない
    for t in rated_topics(session, UPDATE_EVERY):
        t.rated_at = NOW + timedelta(days=1)
        session.add(t)
    session.commit()
    await update(session, output(draft("add", "", "- 4つ目の好み", ids)))
    assert len(session.exec(select(ProfileProposal)).all()) == 3


async def test_rejected_content_is_not_proposed_again_for_thirty_days(session: Session) -> None:
    topics = rated_topics(session, UPDATE_EVERY)
    ids = [topics[0].id or 0]
    await update(session, output(draft("add", "", "- 却下される好み", ids)))
    proposal = session.exec(select(ProfileProposal)).one()
    service.reject(session, proposal.id or 0, now=NOW)

    for t in rated_topics(session, UPDATE_EVERY):
        t.rated_at = NOW + timedelta(days=1)
        session.add(t)
    session.commit()
    same = output(draft("add", "", "- 却下される好み", ids))
    llm, _ = make_llm(lambda *_: same)
    now_29 = NOW + timedelta(days=29)
    await maybe_update(session, llm, run=None, settings=load_settings(session), now=now_29)
    assert len(session.exec(select(ProfileProposal)).all()) == 1  # 29日後はまだ出さない
    # 同じ「種類」でも、別の内容なら出る（種類ごとには止めない）
    other = output(draft("add", "", "- 別の好み", ids))
    llm2, _ = make_llm(lambda *_: other)
    for t in rated_topics(session, UPDATE_EVERY):
        t.rated_at = now_29 + timedelta(hours=1)
        session.add(t)
    session.commit()
    await maybe_update(session, llm2, run=None, settings=load_settings(session), now=now_29)
    assert {p.after_text for p in session.exec(select(ProfileProposal)).all()} == {
        "- 却下される好み",
        "- 別の好み",
    }
    # 30日をすぎたら、同じ内容をまた出してよい
    for t in rated_topics(session, UPDATE_EVERY):
        t.rated_at = NOW + timedelta(days=40)
        session.add(t)
    session.commit()
    llm3, _ = make_llm(lambda *_: same)
    await maybe_update(
        session, llm3, run=None, settings=load_settings(session), now=NOW + timedelta(days=31)
    )
    assert [p.after_text for p in session.exec(select(ProfileProposal)).all()].count(
        "- 却下される好み"
    ) == 2


# --- 採否・履歴 -----------------------------------------------------------------


def make_proposal(session: Session, kind: str, before: str, after: str) -> ProfileProposal:
    p = ProfileProposal(
        kind=kind,
        before_text=before,
        after_text=after,
        reason="理由",
        evidence_topic_ids=[],
        created_at=NOW,
    )
    session.add(p)
    session.commit()
    session.refresh(p)
    return p


def test_approve_add_appends_to_the_profile_and_records_versions(session: Session) -> None:
    p = make_proposal(session, "add", "", "- ローカルLLMの運用")
    out = service.approve(session, p.id or 0)
    assert out.status == "approved" and out.applied_text == "- ローカルLLMの運用"
    assert load_settings(session).profile == PROFILE + "- ローカルLLMの運用\n"
    versions = session.exec(select(ProfileVersion).order_by(col(ProfileVersion.id))).all()
    assert [(v.source, v.text == PROFILE) for v in versions] == [
        ("initial", True),
        ("proposal", False),
    ]
    assert versions[1].proposal_id == p.id


def test_approve_rephrase_remove_and_edited_text(session: Session) -> None:
    p = make_proposal(session, "rephrase", "- 新しいモデルの性能比較", "- 新モデルの比較")
    service.approve(session, p.id or 0, edited_text="- 新しいモデルを自分の用途で比べる")
    assert "- 新しいモデルを自分の用途で比べる\n" in load_settings(session).profile
    assert service.list_proposals(session, "approved")[0].applied_text == (
        "- 新しいモデルを自分の用途で比べる"
    )
    r = make_proposal(session, "remove", "- 暗号資産の話題\n", "")
    service.approve(session, r.id or 0)
    profile = load_settings(session).profile
    assert "暗号資産" not in profile and "Claude Code" in profile


def test_approve_fails_when_the_before_text_is_gone_and_changes_nothing(session: Session) -> None:
    p = make_proposal(session, "remove", "- 暗号資産の話題", "")
    save_settings(
        session,
        load_settings(session).model_copy(update={"profile": "全く別の文章"}),
    )
    with pytest.raises(service.ProfileMismatchError):
        service.approve(session, p.id or 0)
    session.refresh(p)
    assert p.status == "pending" and load_settings(session).profile == "全く別の文章"


def test_decided_or_unknown_proposals_cannot_be_decided_again(session: Session) -> None:
    p = make_proposal(session, "add", "", "- 好み")
    service.reject(session, p.id or 0)
    with pytest.raises(service.ProposalDecidedError):
        service.approve(session, p.id or 0)
    with pytest.raises(service.ProposalDecidedError):
        service.reject(session, p.id or 0)
    with pytest.raises(service.ProposalNotFoundError):
        service.approve(session, 9999)
    assert load_settings(session).profile == PROFILE  # 却下では変わらない


def test_profile_versions_are_added_only_when_the_profile_changes_and_can_be_restored(
    session: Session,
) -> None:
    save_settings(session, load_settings(session))  # 変更なし
    assert session.exec(select(ProfileVersion)).all() == []
    save_settings(session, load_settings(session).model_copy(update={"profile": "新しい文章"}))
    save_settings(
        session, load_settings(session).model_copy(update={"max_scored": 40})
    )  # 他の設定
    versions = service.list_versions(session)
    assert [(v.source, v.text) for v in versions] == [
        ("manual", "新しい文章"),
        ("initial", PROFILE),
    ]
    restored = service.restore_version(session, versions[1].id)
    assert load_settings(session).profile == PROFILE and restored.source == "restore"
    assert [v.source for v in service.list_versions(session)] == ["restore", "manual", "initial"]
    with pytest.raises(service.VersionNotFoundError):
        service.restore_version(session, 9999)


# --- 採点への反映 ---------------------------------------------------------------


def test_memo_section_appears_in_the_scoring_context_only_when_there_is_a_memo(
    session: Session,
) -> None:
    assert "好みメモ" not in build_scoring_context(session, PROFILE, "")
    context = build_scoring_context(session, PROFILE, "実践的な記事を好みます")
    assert "# 好みメモ" in context and "実践的な記事を好みます" in context
    assert context.index("# 興味プロファイル") < context.index("# 好みメモ")
    assert context.index("# 好みメモ") < context.index("# 最近の評価")


async def test_scoring_uses_the_memo_and_records_the_feedback_ids_on_the_run(
    session: Session,
) -> None:
    liked = rated_topics(session, 2)
    dislike = rated_topics(session, 1, rating="dislike")
    service.save_memo(session, "実践的な記事を好みます", now=NOW)
    run = session.get(Run, 1)
    assert run is not None
    source = make_source(session, "lab", "official")
    article = make_article(session, source, 1)
    grouped(session, run, article)
    llm, backend = make_llm(lambda *_: score_output())
    await score_pending(session, llm, run=run, settings=load_settings(session), now=NOW)
    assert "実践的な記事を好みます" in backend.calls[0].system[1]
    session.refresh(run)
    assert run.feedback_topic_ids == sorted(t.id for t in [*liked, *dislike])  # type: ignore[type-var]
    assert session.exec(select(Score)).all()


# --- API ----------------------------------------------------------------------


@pytest.fixture
def api(session: Session) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    return TestClient(app)


def test_api_flow_state_proposals_approve_reject_versions_and_badge(
    api: TestClient, session: Session
) -> None:
    assert api.get("/api/preference").json()["source"] == "none"
    assert api.put("/api/preference", json={"text": "メモ"}).json()["text"] == "メモ"
    assert api.put("/api/preference", json={"text": "あ" * 801}).status_code == 422

    a = make_proposal(session, "add", "", "- 好みA")
    b = make_proposal(session, "add", "", "- 好みB")
    assert api.get("/api/status").json()["pending_proposals"] == 2
    assert len(api.get("/api/proposals", params={"status": "pending"}).json()) == 2

    approved = api.post(f"/api/proposals/{a.id}/approve", json={"edited_text": "- 好みA改"})
    assert approved.status_code == 200 and approved.json()["applied_text"] == "- 好みA改"
    assert api.post(f"/api/proposals/{a.id}/approve").status_code == 409
    assert api.post(f"/api/proposals/{b.id}/reject").json()["status"] == "rejected"
    assert api.post("/api/proposals/9999/reject").status_code == 404
    assert api.get("/api/status").json()["pending_proposals"] == 0
    assert "- 好みA改" in api.get("/api/settings").json()["profile"]

    versions = api.get("/api/profile/versions").json()
    assert [v["source"] for v in versions] == ["proposal", "initial"]
    restore = api.post(f"/api/profile/versions/{versions[1]['id']}/restore")
    assert restore.status_code == 200 and api.get("/api/settings").json()["profile"] == PROFILE
    assert api.post("/api/profile/versions/9999/restore").status_code == 404


def test_api_approve_with_a_changed_profile_returns_409_with_a_reason(
    api: TestClient, session: Session
) -> None:
    p = make_proposal(session, "remove", "- 暗号資産の話題", "")
    save_settings(session, load_settings(session).model_copy(update={"profile": "別の文章"}))
    response = api.post(f"/api/proposals/{p.id}/approve")
    assert response.status_code == 409 and "プロファイルが変わった" in response.json()["detail"]
