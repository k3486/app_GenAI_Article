from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.db import get_session
from app.schemas.runs import AppStatus, RunSummary
from app.services import runs as runs_service

router = APIRouter(tags=["status"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/status")
def get_status(session: SessionDep) -> AppStatus:
    """前回の更新結果・今月の費用・更新中かどうか（画面の上部に表示する）。"""
    return runs_service.get_status(session)


@router.post("/runs", status_code=202)
def start_run() -> AppStatus:
    """「更新」ボタン。収集〜整理の処理は段階 4〜6 で作るので、いまは受け付けない。"""
    raise HTTPException(
        status_code=501, detail="更新処理はまだ実装されていません（段階6で実装します）"
    )


@router.get("/runs")
def list_runs(session: SessionDep) -> list[RunSummary]:
    return runs_service.list_runs(session)
