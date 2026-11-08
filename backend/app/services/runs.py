"""更新の実行履歴・状態・費用の集計。"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from app.models import LlmUsage, ProfileProposal, Run, RunIssue, SearchQuery
from app.schemas.runs import AppStatus, Budget, RunSummary
from app.services.app_settings import is_sample_mode, load_settings

# ハートビート（生きている印）がこれ以上止まった実行は「失敗」と見なす
STALE_AFTER = timedelta(minutes=10)
_JST = timedelta(hours=9)


def _now() -> datetime:
    return datetime.now(UTC)


def fail_stale_runs(session: Session, now: datetime | None = None) -> int:
    """作業員が落ちて印が止まった実行を失敗にする（更新ボタンが押せなくなる事故を防ぐ）。"""
    now = now or _now()
    stale = session.exec(
        select(Run).where(col(Run.status) == "running", col(Run.heartbeat_at) < now - STALE_AFTER)
    ).all()
    for run in stale:
        run.status = "failed"
        run.finished_at = now
        session.add(run)
        session.add(
            RunIssue(
                run_id=run.id or 0,
                source_name="更新処理",
                stage="全体",
                message="更新処理の応答が止まったため、失敗として扱いました",
            )
        )
    session.commit()
    return len(stale)


class RunAlreadyRunningError(Exception):
    """すでに更新が動いている。"""


class RunLaunchError(Exception):
    """更新の処理（別プロセス）を起動できなかった。"""


# 実行の行の ID を受け取り、更新の処理を別プロセスで起動する関数
Launcher = Callable[[int], None]


def start_run(session: Session, launcher: Launcher) -> Run:
    """「更新」ボタン: 実行の行を作って、更新の処理を別プロセスで起動する（待たずに返す）。"""
    fail_stale_runs(session)
    if session.exec(select(Run.id).where(col(Run.status) == "running")).first() is not None:
        raise RunAlreadyRunningError
    run = Run(trigger="manual", status="running")
    session.add(run)
    try:
        session.commit()
    except IntegrityError as error:  # 同時に押された（部分一意インデックスに当たった）
        session.rollback()
        raise RunAlreadyRunningError from error
    session.refresh(run)
    assert run.id is not None
    try:
        launcher(run.id)
    except OSError as error:
        run.status = "failed"
        run.finished_at = _now()
        session.add(run)
        session.add(
            RunIssue(
                run_id=run.id,
                source_name="更新処理",
                stage="起動",
                message=(
                    f"更新の処理を起動できませんでした"
                    f"（{type(error).__name__}: {str(error)[:120]}）"
                ),
            )
        )
        session.commit()
        raise RunLaunchError from error
    return run


def _summary(session: Session, run: Run) -> RunSummary:
    assert run.id is not None
    issues = session.exec(select(RunIssue).where(col(RunIssue.run_id) == run.id)).all()
    queries = session.exec(
        select(SearchQuery).where(col(SearchQuery.run_id) == run.id).order_by(col(SearchQuery.id))
    ).all()
    data: dict[str, Any] = {
        "id": run.id,
        "status": run.status,
        "trigger": run.trigger,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "new_count": run.new_count,
        "scored_count": run.scored_count,
        "selected_count": run.selected_count,
        "cost_usd": run.cost_usd,
        "model_id": run.model_id,
        "previous_model_id": run.previous_model_id,
        "issues": [
            {"source_name": i.source_name, "stage": i.stage, "message": i.message} for i in issues
        ],
        "search_queries": [
            {"query": q.query, "language": q.language, "result_count": q.result_count}
            for q in queries
        ],
    }
    return RunSummary.model_validate(data)


def list_runs(session: Session) -> list[RunSummary]:
    fail_stale_runs(session)
    runs = session.exec(select(Run).order_by(col(Run.started_at).desc(), col(Run.id).desc())).all()
    return [_summary(session, r) for r in runs]


def _month_start_utc(now: datetime) -> datetime:
    """今月の始まり（日本時間の1日 0時）を UTC で返す。"""
    jst = now + _JST
    return jst.replace(day=1, hour=0, minute=0, second=0, microsecond=0) - _JST


def month_cost(session: Session, now: datetime | None = None) -> float:
    now = now or _now()
    total = session.exec(
        select(func.coalesce(func.sum(col(LlmUsage.cost_usd)), 0.0)).where(
            col(LlmUsage.created_at) >= _month_start_utc(now)
        )
    ).one()
    return float(total)


def get_status(session: Session) -> AppStatus:
    fail_stale_runs(session)
    settings = load_settings(session)
    latest = session.exec(
        select(Run).order_by(col(Run.started_at).desc(), col(Run.id).desc()).limit(1)
    ).first()
    return AppStatus(
        latest_run=_summary(session, latest) if latest else None,
        budget=Budget(
            month_cost_usd=round(month_cost(session), 4),
            month_limit_usd=settings.month_limit_usd,
            run_limit_usd=settings.run_limit_usd,
        ),
        pending_proposals=session.exec(
            select(func.count())
            .select_from(ProfileProposal)
            .where(col(ProfileProposal.status) == "pending")
        ).one(),
        sample_mode=is_sample_mode(session),
    )
