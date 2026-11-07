import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import text
from sqlmodel import SQLModel

import app.models  # noqa: F401
from app.db import make_engine
from app.services.backup import backup_sqlite


def test_backup_is_a_usable_copy_and_keeps_only_recent_generations(tmp_path: Path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'app.db'}")
    SQLModel.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO sources (key, name, kind, enabled, created_at) "
                "VALUES ('a', 'テスト', 'media', 1, '2026-11-07 00:00:00')"
            )
        )

    backup_dir = tmp_path / "backups"
    base = datetime(2026, 11, 7, 6, 0, tzinfo=UTC)
    paths = [
        backup_sqlite(engine, backup_dir, keep=3, now=base + timedelta(days=i)) for i in range(5)
    ]
    assert all(p is not None for p in paths)

    # 新しい3世代だけが残る
    remaining = sorted(p.name for p in backup_dir.glob("app-*.db"))
    assert remaining == [p.name for p in paths[2:] if p is not None]

    # コピーは、そのまま開けて、中身が入っている
    latest = paths[-1]
    assert latest is not None
    with sqlite3.connect(latest) as copy:
        assert copy.execute("SELECT name FROM sources").fetchone() == ("テスト",)
