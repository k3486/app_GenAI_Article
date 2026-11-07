"""DB のバックアップ。

👍👎や好みメモは使うほど価値が増えるデータなので、更新が終わるたびにコピーを残す。
SQLite の標準のバックアップ機能を使うので、書き込み中でも壊れたコピーにならない。
"""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.engine import Engine

from app.config import REPO_ROOT

DEFAULT_DIR = REPO_ROOT / "data" / "backups"
_PREFIX = "app-"
_SUFFIX = ".db"


def backup_sqlite(
    engine: Engine,
    backup_dir: Path = DEFAULT_DIR,
    *,
    keep: int = 7,
    now: datetime | None = None,
) -> Path | None:
    """コピーを作り、古いものは keep 世代だけ残して消す。SQLite 以外は何もしない（None）。"""
    if engine.dialect.name != "sqlite":
        return None
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%d-%H%M%S")
    destination = backup_dir / f"{_PREFIX}{stamp}{_SUFFIX}"

    raw = engine.raw_connection()
    try:
        source = raw.driver_connection
        assert isinstance(source, sqlite3.Connection)
        target = sqlite3.connect(destination)
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        raw.close()

    copies = sorted(backup_dir.glob(f"{_PREFIX}*{_SUFFIX}"))
    for old in copies[: max(0, len(copies) - keep)]:
        old.unlink()
    return destination
