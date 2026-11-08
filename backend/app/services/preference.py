"""好みメモと、興味プロファイルの修正案（フィードバックループ）。

評価（👍/👎/実はよかった）が前回のメモから20件以上たまったら、更新の最後に Haiku を1回呼び、
好みメモを書き直し、プロファイルの修正案（最大3件）を出す。修正案は自動では反映せず、
利用者が承認・編集して承認・却下する。プロファイルは変わるたびに履歴（版）に残り、戻せる。
"""

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_
from sqlmodel import Session, col, select

from app.models import (
    PreferenceNote,
    ProfileProposal,
    ProfileVersion,
    Run,
    Score,
    Topic,
)
from app.schemas.preference import (
    MEMO_MAX_CHARS,
    EvidenceTopic,
    PreferenceOutput,
    PreferenceState,
    ProposalDraft,
    ProposalOut,
    VersionOut,
)
from app.schemas.settings import Settings
from app.services.app_settings import load_settings, save_settings
from app.services.llm.client import Llm
from app.services.llm.errors import BudgetExceededError, LlmError
from app.services.llm.ledger import record_usage
from app.services.llm.skills import load_skill

UPDATE_EVERY = 20  # 前回のメモより後に付いた評価がこの件数になったら更新する（設計で決定）
EVALUATION_LIMIT = 60  # Haiku に見せる評価の最大件数（新しい順）
MAX_PROPOSALS = 3
REJECT_MEMORY_DAYS = 30  # 却下した修正案と同じ内容は、この期間は出さない
_DISLIKE = {
    "not_interested": "興味なし",
    "already_known": "もう知っていた",
    "low_quality": "質が低い",
}


class ProposalNotFoundError(Exception):
    pass


class ProposalDecidedError(Exception):
    """すでに承認・却下された修正案。"""


class ProfileMismatchError(Exception):
    """修正案の「変更前の文」が、今のプロファイルに見つからない（プロファイルが変わった）。"""


class VersionNotFoundError(Exception):
    pass


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass
class PreferenceReport:
    updated: bool = False
    proposals: int = 0
    feedback_count: int = 0
    failed: bool = False
    budget_stopped: bool = False


# --- 好みメモ -------------------------------------------------------------------


def current_note(session: Session) -> PreferenceNote | None:
    return session.exec(select(PreferenceNote).order_by(col(PreferenceNote.id).desc())).first()


def current_memo(session: Session) -> str:
    note = current_note(session)
    return note.text if note else ""


def _evaluated(session: Session) -> list[tuple[Topic, Score]]:
    """評価（👍/👎/実はよかった）の付いた話題（付けた日時の新しい順）。"""
    rows = session.exec(
        select(Topic, Score)
        .join(Score, col(Score.topic_id) == col(Topic.id))
        .where(or_(col(Topic.rating).is_not(None), col(Topic.missed).is_(True)))
    ).all()
    return sorted(rows, key=lambda r: _evaluated_at(r[0]), reverse=True)


def _evaluated_at(topic: Topic) -> datetime:
    times = [t for t in (topic.rated_at, topic.missed_at) if t is not None]
    return max(times) if times else datetime.min.replace(tzinfo=UTC)


def feedback_since_last_note(session: Session) -> int:
    note = current_note(session)
    rows = _evaluated(session)
    if note is None:
        return len(rows)
    return sum(1 for t, _ in rows if _evaluated_at(t) > _aware(note.created_at))


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def get_state(session: Session) -> PreferenceState:
    note = current_note(session)
    return PreferenceState(
        text=note.text if note else "",
        source="none" if note is None else note.source,
        updated_at=note.created_at if note else None,
        feedback_since=feedback_since_last_note(session),
        update_every=UPDATE_EVERY,
    )


def save_memo(session: Session, text: str, now: datetime | None = None) -> PreferenceState:
    """画面で好みメモを直した。新しい行として残し、次の更新までの数え直しの起点にもする。"""
    session.add(
        PreferenceNote(
            text=text.strip()[:MEMO_MAX_CHARS], source="manual", created_at=now or _now()
        )
    )
    session.commit()
    return get_state(session)


# --- Haiku による更新 -----------------------------------------------------------


def _evaluation_lines(rows: list[tuple[Topic, Score]]) -> str:
    lines: list[str] = []
    for topic, score in rows[:EVALUATION_LIMIT]:
        marks: list[str] = []
        if topic.rating == "like":
            marks.append("👍")
        if topic.rating == "dislike":
            reason = _DISLIKE.get(topic.dislike_reason or "", "")
            marks.append(f"👎{f'（{reason}）' if reason else ''}")
        if topic.missed:
            marks.append("実はよかった")
        lines.append(
            f"- 話題ID {topic.id}｜{'・'.join(marks)}｜{score.title_ja}（{score.category}）"
            f"｜{score.summary_1line}"
        )
    return "\n".join(lines)


def _rejected_recently(session: Session, now: datetime) -> list[ProfileProposal]:
    since = now - timedelta(days=REJECT_MEMORY_DAYS)
    rows = session.exec(
        select(ProfileProposal).where(
            col(ProfileProposal.status) == "rejected",
        )
    ).all()
    return [p for p in rows if p.decided_at and _aware(p.decided_at) >= since]


def _valid_proposals(
    drafts: list[ProposalDraft],
    *,
    profile: str,
    evaluated_ids: set[int],
    rejected: list[ProfileProposal],
    pending: list[ProfileProposal],
) -> list[ProposalDraft]:
    """Haiku の出力を確かめて、使えない修正案は捨てる。"""
    seen = {(p.kind, p.before_text.strip(), p.after_text.strip()) for p in [*rejected, *pending]}
    kept: list[ProposalDraft] = []
    for d in drafts:
        before, after = d.before_text.strip(), d.after_text.strip()
        key = (d.kind, before, after)
        if key in seen:
            continue  # 却下した内容、すでに出ている内容と同じ
        if d.kind == "add" and (not after or after in profile or before):
            continue
        if d.kind == "remove" and (not before or before not in profile or after):
            continue
        if d.kind == "rephrase" and (
            not before or before not in profile or not after or after == before
        ):
            continue
        evidence = [i for i in dict.fromkeys(d.evidence_topic_ids) if i in evaluated_ids]
        if not evidence or not d.reason.strip():
            continue
        seen.add(key)
        kept.append(
            ProposalDraft(
                kind=d.kind,
                before_text=before,
                after_text=after,
                reason=d.reason.strip(),
                evidence_topic_ids=evidence[:3],
            )
        )
    return kept


async def maybe_update(
    session: Session,
    llm: Llm,
    *,
    run: Run | None,
    settings: Settings,
    now: datetime | None = None,
    force: bool = False,
) -> PreferenceReport:
    """評価が20件たまっていれば、好みメモと修正案を作る（force なら件数に関係なく）。"""
    now = now or _now()
    rows = _evaluated(session)
    report = PreferenceReport(feedback_count=feedback_since_last_note(session))
    if not rows or (report.feedback_count < UPDATE_EVERY and not force):
        return report
    note = current_note(session)
    pending = list(
        session.exec(select(ProfileProposal).where(col(ProfileProposal.status) == "pending")).all()
    )
    context = (
        f"# 興味プロファイル\n{settings.profile.strip()}\n\n"
        f"# 今の好みメモ\n{note.text if note else '（まだありません）'}"
    )
    rejected = _rejected_recently(session, now)

    def lines(proposals: list[ProfileProposal]) -> str:
        return (
            "\n".join(f"- [{p.kind}] {p.before_text} → {p.after_text}" for p in proposals)
            or "（なし）"
        )

    user = (
        f"# 評価の一覧（新しい順・最大{EVALUATION_LIMIT}件）\n{_evaluation_lines(rows)}\n\n"
        f"# 最近却下された修正案\n{lines(rejected)}\n\n"
        f"# すでに出ている未決の修正案\n{lines(pending)}"
    )
    try:
        result = await llm.run(
            load_skill("preference"),
            context=context,
            user=user,
            output_type=PreferenceOutput,
            effort="medium",
            max_tokens=6000,
        )
    except BudgetExceededError:
        report.budget_stopped = True
        return report
    except LlmError:
        report.failed = True
        return report
    out = result.parsed
    record_usage(session, run, result.usage, purpose="preference")
    session.add(
        PreferenceNote(
            text=out.memo.strip()[:MEMO_MAX_CHARS],
            source="haiku",
            based_on_count=len(rows),
            run_id=run.id if run else None,
            created_at=now,
        )
    )
    room = max(0, MAX_PROPOSALS - len(pending))
    drafts = _valid_proposals(
        out.proposals,
        profile=settings.profile,
        evaluated_ids={t.id for t, _ in rows if t.id is not None},
        rejected=rejected,
        pending=pending,
    )[:room]
    for d in drafts:
        session.add(
            ProfileProposal(
                kind=d.kind,
                before_text=d.before_text,
                after_text=d.after_text,
                reason=d.reason,
                evidence_topic_ids=d.evidence_topic_ids,
                run_id=run.id if run else None,
                created_at=now,
            )
        )
    session.commit()
    report.updated = True
    report.proposals = len(drafts)
    return report


# --- 修正案の採否 ---------------------------------------------------------------


def _out(session: Session, p: ProfileProposal) -> ProposalOut:
    titles = {
        s.topic_id: s.title_ja
        for s in session.exec(
            select(Score).where(col(Score.topic_id).in_(p.evidence_topic_ids or [-1]))
        ).all()
    }
    return ProposalOut(
        id=p.id or 0,
        kind=p.kind,
        before_text=p.before_text,
        after_text=p.after_text,
        reason=p.reason,
        evidence=[
            EvidenceTopic(id=i, title_ja=titles[i]) for i in p.evidence_topic_ids if i in titles
        ],
        status=p.status,
        applied_text=p.applied_text,
        created_at=p.created_at,
        decided_at=p.decided_at,
    )


def list_proposals(session: Session, status: str | None = None) -> list[ProposalOut]:
    stmt = select(ProfileProposal).order_by(col(ProfileProposal.id).desc())
    if status:
        stmt = stmt.where(col(ProfileProposal.status) == status)
    return [_out(session, p) for p in session.exec(stmt).all()]


def count_pending(session: Session) -> int:
    return len(
        session.exec(
            select(ProfileProposal.id).where(col(ProfileProposal.status) == "pending")
        ).all()
    )


def _apply(profile: str, p: ProfileProposal, text: str) -> str:
    if p.kind == "add":
        return profile.rstrip("\n") + "\n" + text + "\n"
    if p.before_text not in profile:
        raise ProfileMismatchError
    if p.kind == "remove":
        return re.sub(r"\n{3,}", "\n\n", profile.replace(p.before_text, "", 1))
    return profile.replace(p.before_text, text, 1)


def approve(
    session: Session,
    proposal_id: int,
    edited_text: str | None = None,
    now: datetime | None = None,
) -> ProposalOut:
    """修正案をプロファイルに反映する。編集した文があれば、それを反映する（remove は除く）。"""
    p = session.get(ProfileProposal, proposal_id)
    if p is None:
        raise ProposalNotFoundError
    if p.status != "pending":
        raise ProposalDecidedError
    text = (edited_text or "").strip() or p.after_text
    settings = load_settings(session)
    new_profile = _apply(settings.profile, p, text)  # 合わなければ ProfileMismatchError
    save_settings(
        session,
        settings.model_copy(update={"profile": new_profile}),
        profile_source="proposal",
        proposal_id=p.id,
    )
    p.status = "approved"
    p.applied_text = None if p.kind == "remove" else text
    p.decided_at = now or _now()
    session.add(p)
    session.commit()
    return _out(session, p)


def reject(session: Session, proposal_id: int, now: datetime | None = None) -> ProposalOut:
    p = session.get(ProfileProposal, proposal_id)
    if p is None:
        raise ProposalNotFoundError
    if p.status != "pending":
        raise ProposalDecidedError
    p.status = "rejected"
    p.decided_at = now or _now()
    session.add(p)
    session.commit()
    return _out(session, p)


# --- プロファイルの履歴 ---------------------------------------------------------


def list_versions(session: Session) -> list[VersionOut]:
    rows = session.exec(select(ProfileVersion).order_by(col(ProfileVersion.id).desc())).all()
    return [
        VersionOut(id=v.id or 0, text=v.text, source=v.source, created_at=v.created_at)
        for v in rows
    ]


def restore_version(session: Session, version_id: int) -> VersionOut:
    """古い版のプロファイルに戻す（戻した結果も、新しい版として履歴に残る）。"""
    version = session.get(ProfileVersion, version_id)
    if version is None:
        raise VersionNotFoundError
    settings = load_settings(session)
    save_settings(
        session, settings.model_copy(update={"profile": version.text}), profile_source="restore"
    )
    newest = session.exec(select(ProfileVersion).order_by(col(ProfileVersion.id).desc())).first()
    # 今のプロファイルと同じ文に戻した（変化なし）ときは、版は増えない
    chosen = newest or version
    return VersionOut(
        id=chosen.id or 0,
        text=chosen.text,
        source=chosen.source,
        created_at=chosen.created_at,
    )
