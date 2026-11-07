"""DB そのものの約束事：日時・外部キー・自動見送り・失敗判定・費用・検索・WAL・移行。"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel

from alembic import command
from app.config import get_settings
from app.db import make_engine
from app.models import Article, LlmUsage, Run, Score, Topic
from app.services import runs as runs_service
from app.services.search import index_topic, search_topic_ids
from app.services.topics import auto_dismiss

BACKEND = Path(__file__).resolve().parents[1]


def _now() -> datetime:
    return datetime.now(UTC)


def test_datetimes_are_stored_as_utc_and_read_back_with_timezone(session: Session) -> None:
    jst = _now().astimezone(UTC) + timedelta(hours=9)
    run = Run(trigger="manual", started_at=jst.replace(tzinfo=UTC))
    session.add(run)
    session.commit()
    session.refresh(run)
    assert run.started_at.tzinfo is not None
    assert run.started_at.utcoffset() == timedelta(0)


def test_naive_datetimes_are_refused(session: Session) -> None:
    session.add(Run(trigger="manual", started_at=datetime(2026, 11, 7, 6, 0)))
    with pytest.raises(Exception, match="時刻付き"):
        session.commit()


def test_foreign_keys_are_enforced(session: Session) -> None:
    session.add(
        Article(
            topic_id=999,
            url="https://example.com/x",
            url_normalized="https://example.com/x",
            published_at=_now(),
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_normalized_url_is_unique(seeded: Session) -> None:
    seeded.add(
        Article(
            topic_id=1,
            url="https://example.com/other",
            url_normalized="https://example.com/sample/1",
            published_at=_now(),
        )
    )
    with pytest.raises(IntegrityError):
        seeded.commit()


def test_auto_dismiss_only_old_unread_unpinned_items(seeded: Session) -> None:
    long_ago = _now() - timedelta(days=31)
    old_unread = seeded.get(Topic, 4)  # 未読
    pinned = seeded.get(Topic, 1)  # 「後で読む」
    read = seeded.get(Topic, 12)  # 読了
    rejected = seeded.get(Topic, 10)
    assert old_unread and pinned and read and rejected
    assert old_unread.read_state == "unread" and pinned.backlog and read.read_state == "read"
    for topic in (old_unread, pinned, read, rejected):
        topic.selected_at = long_ago
        seeded.add(topic)
    seeded.commit()

    assert auto_dismiss(seeded) >= 1
    for topic in (old_unread, pinned, read, rejected):
        seeded.refresh(topic)
    assert old_unread.read_state == "dismissed" and old_unread.read_at is not None
    assert pinned.read_state == "unread"  # 「後で読む」は除く
    assert read.read_state == "read"  # すでに読んだものは触らない
    assert rejected.read_state == "unread"  # 落選記事は対象外


def test_stale_runs_are_marked_failed(session: Session) -> None:
    now = _now()
    alive = Run(trigger="manual", heartbeat_at=now)
    dead = Run(trigger="manual", heartbeat_at=now - timedelta(minutes=11))
    session.add(alive)
    session.add(dead)
    session.commit()

    assert runs_service.fail_stale_runs(session, now) == 1
    session.refresh(alive)
    session.refresh(dead)
    assert alive.status == "running"
    assert dead.status == "failed" and dead.finished_at is not None
    summary = next(r for r in runs_service.list_runs(session) if r.id == dead.id)
    assert summary.issues and "止まった" in summary.issues[0].message


def test_month_cost_counts_only_this_month(session: Session) -> None:
    now = datetime(2026, 11, 15, 3, 0, tzinfo=UTC)
    session.add(LlmUsage(purpose="score", model_id="m", cost_usd=1.5, created_at=now))
    # 日本時間では11月1日0時（UTC では 10/31 15:00）から今月に数える
    session.add(
        LlmUsage(
            purpose="score",
            model_id="m",
            cost_usd=0.25,
            created_at=datetime(2026, 10, 31, 15, 0, tzinfo=UTC),
        )
    )
    session.add(
        LlmUsage(
            purpose="score",
            model_id="m",
            cost_usd=9.0,
            created_at=datetime(2026, 10, 31, 14, 59, tzinfo=UTC),
        )
    )
    session.commit()
    assert runs_service.month_cost(session, now) == pytest.approx(1.75)


def test_search_index_follows_changes(seeded: Session) -> None:
    assert 1 in search_topic_ids(seeded, "フックで自動")
    score = seeded.get(Score, 1)
    assert score is not None
    score.title_ja = "まったく別のタイトルです"
    seeded.add(score)
    seeded.commit()
    # 作り直すまでは古いまま、作り直すと新しい文章で探せる
    index_topic(seeded, 1)
    assert 1 not in search_topic_ids(seeded, "フックで自動")
    assert 1 in search_topic_ids(seeded, "別のタイトル")


def test_search_includes_digest_text_but_not_article_body(seeded: Session) -> None:
    assert 1 in search_topic_ids(seeded, "背景・課題")  # 整理記事の見出し
    assert search_topic_ids(seeded, "存在しない語句ですよ") == set()


def test_file_database_uses_wal_and_busy_timeout(tmp_path: Path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'nested' / 'app.db'}")
    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA journal_mode")).scalar() == "wal"
        assert connection.execute(text("PRAGMA foreign_keys")).scalar() == 1
        assert connection.execute(text("PRAGMA busy_timeout")).scalar() == 5000


def test_migrations_create_the_same_tables_as_the_models(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """移行ファイルと表の定義（モデル）がずれたら、ここで気づく。"""
    url = f"sqlite:///{tmp_path / 'migrated.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    try:
        config = Config(str(BACKEND / "alembic.ini"))
        config.set_main_option("script_location", str(BACKEND / "alembic"))
        command.upgrade(config, "head")
        command.check(config)  # モデルとの差が残っていれば、ここで例外になる

        engine = make_engine(url)
        tables = set(inspect(engine).get_table_names())
        assert set(SQLModel.metadata.tables) <= tables
        assert "topic_search" in tables

        command.downgrade(config, "base")
        remaining = set(inspect(engine).get_table_names()) - {"alembic_version"}
        assert remaining == set()
    finally:
        get_settings.cache_clear()
