"""好みメモ・興味プロファイルの修正案・プロファイルの履歴。"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.db import get_session
from app.schemas.preference import (
    ApproveIn,
    PreferenceIn,
    PreferenceState,
    ProposalOut,
    VersionOut,
)
from app.services import preference as service

router = APIRouter(tags=["preference"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/preference")
def get_preference(session: SessionDep) -> PreferenceState:
    return service.get_state(session)


@router.put("/preference")
def put_preference(body: PreferenceIn, session: SessionDep) -> PreferenceState:
    return service.save_memo(session, body.text)


@router.get("/proposals")
def list_proposals(
    session: SessionDep, status: Literal["pending", "approved", "rejected"] | None = None
) -> list[ProposalOut]:
    return service.list_proposals(session, status)


@router.post("/proposals/{proposal_id}/approve")
def approve_proposal(
    proposal_id: int, session: SessionDep, body: ApproveIn | None = None
) -> ProposalOut:
    try:
        return service.approve(session, proposal_id, body.edited_text if body else None)
    except service.ProposalNotFoundError:
        raise HTTPException(status_code=404, detail="修正案が見つかりません") from None
    except service.ProposalDecidedError:
        raise HTTPException(status_code=409, detail="この修正案はすでに決定済みです") from None
    except service.ProfileMismatchError:
        raise HTTPException(
            status_code=409,
            detail="プロファイルが変わったため、変更前の文が見つかりません。内容を確認してください",
        ) from None


@router.post("/proposals/{proposal_id}/reject")
def reject_proposal(proposal_id: int, session: SessionDep) -> ProposalOut:
    try:
        return service.reject(session, proposal_id)
    except service.ProposalNotFoundError:
        raise HTTPException(status_code=404, detail="修正案が見つかりません") from None
    except service.ProposalDecidedError:
        raise HTTPException(status_code=409, detail="この修正案はすでに決定済みです") from None


@router.get("/profile/versions")
def list_versions(session: SessionDep) -> list[VersionOut]:
    return service.list_versions(session)


@router.post("/profile/versions/{version_id}/restore")
def restore_version(version_id: int, session: SessionDep) -> VersionOut:
    try:
        return service.restore_version(session, version_id)
    except service.VersionNotFoundError:
        raise HTTPException(status_code=404, detail="その版が見つかりません") from None
