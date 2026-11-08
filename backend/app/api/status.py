from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.db import get_session
from app.schemas.runs import AppStatus, RunSummary
from app.services import runs as runs_service
from app.services.run_launcher import launch_collect

router = APIRouter(tags=["status"])

SessionDep = Annotated[Session, Depends(get_session)]


def get_launcher() -> runs_service.Launcher:
    """更新の処理を起動する関数（テストでは差し替える）。"""
    return launch_collect


LauncherDep = Annotated[runs_service.Launcher, Depends(get_launcher)]


@router.get("/status")
def get_status(session: SessionDep) -> AppStatus:
    """前回の更新結果・今月の費用・更新中かどうか（画面の上部に表示する）。"""
    return runs_service.get_status(session)


@router.post("/runs", status_code=202)
def start_run(session: SessionDep, launcher: LauncherDep) -> AppStatus:
    """「更新」ボタン。更新の処理を別プロセスで起動し、待たずに現在の状態を返す。"""
    try:
        runs_service.start_run(session, launcher)
    except runs_service.RunAlreadyRunningError:
        raise HTTPException(
            status_code=409, detail="更新中です。終わるまでお待ちください"
        ) from None
    except runs_service.RunLaunchError:
        raise HTTPException(
            status_code=500, detail="更新の処理を起動できませんでした。実行履歴をご確認ください"
        ) from None
    return runs_service.get_status(session)


@router.get("/runs")
def list_runs(session: SessionDep) -> list[RunSummary]:
    return runs_service.list_runs(session)
