"""DB エンジンとセッション。

テーブルは app/models/ に SQLModel で定義する（必要になったら作る）。
"""

from collections.abc import Iterator

from sqlmodel import Session, create_engine

from app.config import get_settings

engine = create_engine(get_settings().database_url, connect_args={"check_same_thread": False})


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
