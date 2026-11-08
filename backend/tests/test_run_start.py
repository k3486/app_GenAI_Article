"""更新ボタン（POST /api/runs）と、更新の実行の行の扱い。"""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.api.status import get_launcher
from app.db import get_session
from app.main import create_app
from app.models import Run, RunIssue
from app.services.collect import run as collect_run
from app.services.collect.group import GroupReport, group_new
from app.services.collect.run import run_collection
from app.services.runs import RunAlreadyRunningError, start_run
from tests.helpers import public_resolver
from tests.test_collect_pipeline import NOW, end_to_end_config, end_to_end_web


class Launches:
    """更新の処理の起動を記録するだけの偽物。"""

    def __init__(self, error: OSError | None = None) -> None:
        self.ids: list[int] = []
        self.error = error

    def __call__(self, run_id: int) -> None:
        if self.error:
            raise self.error
        self.ids.append(run_id)


@pytest.fixture
def launches() -> Launches:
    return Launches()


@pytest.fixture
def api(session: Session, launches: Launches) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_launcher] = lambda: launches
    with TestClient(app) as client:
        yield client


def test_start_creates_a_running_row_and_launches_once(
    api: TestClient, session: Session, launches: Launches
) -> None:
    response = api.post("/api/runs")
    assert response.status_code == 202
    run = session.exec(select(Run)).one()
    assert run.status == "running" and run.trigger == "manual"
    assert launches.ids == [run.id]
    assert response.json()["latest_run"]["status"] == "running"


def test_second_start_while_running_is_refused(
    api: TestClient, session: Session, launches: Launches
) -> None:
    api.post("/api/runs")
    response = api.post("/api/runs")
    assert response.status_code == 409
    assert "更新中" in response.json()["detail"]
    assert len(launches.ids) == 1 and len(session.exec(select(Run)).all()) == 1


def test_a_stalled_run_is_failed_first_so_a_new_one_can_start(
    api: TestClient, session: Session, launches: Launches
) -> None:
    old = datetime.now(UTC) - timedelta(minutes=30)
    session.add(Run(trigger="manual", status="running", started_at=old, heartbeat_at=old))
    session.commit()
    assert api.post("/api/runs").status_code == 202
    statuses = sorted(r.status for r in session.exec(select(Run)).all())
    assert statuses == ["failed", "running"] and len(launches.ids) == 1


def test_launch_failure_marks_the_row_failed_and_records_an_issue(session: Session) -> None:
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_launcher] = lambda: Launches(OSError("起動できない"))
    with TestClient(app) as client:
        response = client.post("/api/runs")
    assert response.status_code == 500
    run = session.exec(select(Run)).one()
    assert run.status == "failed"
    issue = session.exec(select(RunIssue)).one()
    assert issue.stage == "起動" and "OSError" in issue.message
    # 失敗にしたので、次の更新は押せる
    assert start_run(session, Launches()).status == "running"


def test_database_allows_only_one_running_row(session: Session) -> None:
    session.add(Run(trigger="manual", status="running"))
    session.commit()
    session.add(Run(trigger="manual", status="running"))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
    session.add(Run(trigger="manual", status="succeeded"))  # 実行中以外は何行でも
    session.add(Run(trigger="manual", status="succeeded"))
    session.commit()


def test_start_run_function_refuses_when_another_is_running(session: Session) -> None:
    start_run(session, Launches())
    with pytest.raises(RunAlreadyRunningError):
        start_run(session, Launches())


async def test_collection_uses_the_row_made_by_the_button(session: Session) -> None:
    button_row = start_run(session, Launches())
    web = end_to_end_web()
    summary = await run_collection(
        session,
        end_to_end_config(),
        run_id=button_row.id,
        now=NOW,
        transport=web.transport(),
        resolver=public_resolver,
        use_browser=False,
        use_llm=False,
    )
    runs = session.exec(select(Run)).all()
    assert len(runs) == 1  # 新しい行は作らない
    assert summary.run_id == button_row.id
    assert runs[0].status in ("succeeded", "partial") and runs[0].finished_at is not None


async def test_make_collect_while_running_is_refused(session: Session) -> None:
    start_run(session, Launches())
    with pytest.raises(RunAlreadyRunningError):
        await run_collection(
            session,
            end_to_end_config(),
            now=NOW,
            use_browser=False,
            use_llm=False,
        )
    assert len(session.exec(select(Run)).all()) == 1


async def test_unexpected_error_marks_the_run_failed_and_reraises(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def boom(*_: object, **__: object) -> object:
        raise RuntimeError("想定外の失敗")

    monkeypatch.setattr(collect_run, "discover", boom)
    with pytest.raises(RuntimeError):
        await run_collection(
            session,
            end_to_end_config(),
            now=NOW,
            resolver=public_resolver,
            use_browser=False,
            use_llm=False,
        )
    run = session.exec(select(Run)).one()
    assert run.status == "failed" and run.finished_at is not None
    issue = session.exec(select(RunIssue)).one()
    assert "RuntimeError" in issue.message and "想定外" in issue.message
    assert start_run(session, Launches()).status == "running"  # 実行中のまま残らない


async def test_finishing_does_not_overwrite_a_run_already_failed_as_stalled(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """10分の判定で先に失敗にされた実行を、後から「成功」で上書きしない。"""
    button_row = start_run(session, Launches())

    async def stalled_meanwhile(*args: Any, **kwargs: Any) -> GroupReport:
        row = session.get(Run, button_row.id)
        assert row is not None
        row.status = "failed"  # 処理の途中で、別の判定が失敗にした状況
        session.add(row)
        session.commit()
        return await group_new(*args, **kwargs)

    monkeypatch.setattr("app.services.collect.run.group_new", stalled_meanwhile)
    web = end_to_end_web()
    summary = await run_collection(
        session,
        end_to_end_config(),
        run_id=button_row.id,
        now=NOW,
        transport=web.transport(),
        resolver=public_resolver,
        use_browser=False,
        use_llm=True,  # キーが無いので Haiku は使えず、話題のまとめだけが動く
    )
    run = session.get(Run, button_row.id)
    assert run is not None and run.status == "failed"
    assert summary.status == "failed"
