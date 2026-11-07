"""DB エンジンとセッション。

テーブルは app/models/ に SQLModel で定義し、表の形の変更は Alembic（backend/alembic/）で行う。
接続先は環境変数 DATABASE_URL だけで切り替える（PostgreSQL へ移すときもコードは変えない）。
"""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

from sqlalchemy import event
from sqlalchemy.engine import Engine, make_url
from sqlmodel import Session, create_engine

from app.config import get_settings


def configure_sqlite(engine: Engine) -> None:
    """SQLite を、複数のプロセス（API と更新処理）から同時に使えるようにする。

    WAL: 読み込みが書き込みを待たない／busy_timeout: 書き込みが重なったら少し待つ／
    foreign_keys: 外部キーを実際に守る（SQLite は既定では守らない）。
    """

    def on_connect(dbapi_connection: Any, _record: object) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    event.listen(engine, "connect", on_connect)


def make_engine(url: str) -> Engine:
    parsed = make_url(url)
    if parsed.get_backend_name() != "sqlite":
        return create_engine(url)
    if parsed.database and parsed.database != ":memory:":
        Path(parsed.database).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, connect_args={"check_same_thread": False})
    configure_sqlite(engine)
    return engine


engine = make_engine(get_settings().database_url)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
