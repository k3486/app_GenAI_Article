"""Alembic（表の形の変更を管理する仕組み）の設定。

接続先は app.config の DATABASE_URL（環境変数）から取る。コードを変えずに
SQLite から PostgreSQL へ移せるようにするため、ここには接続先を書かない。
"""

from logging.config import fileConfig

from sqlalchemy.engine import Connection
from sqlmodel import SQLModel
from sqlmodel.sql.sqltypes import AutoString

import app.models  # noqa: F401  すべての表を SQLModel.metadata に登録する
from alembic import context
from app.config import get_settings
from app.db import make_engine
from app.models.types import UTCDateTime

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

url = get_settings().database_url
# configparser は % を特別扱いするので、エスケープして渡す
config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
target_metadata = SQLModel.metadata

# 全文検索用の補助表（SQLite の FTS5 が作る表）は、Alembic の管理対象にしない
_EXTERNAL_PREFIX = "topic_search"


def include_object(
    object_: object, name: str | None, type_: str, reflected: bool, compare_to: object
) -> bool:
    return not (type_ == "table" and name is not None and name.startswith(_EXTERNAL_PREFIX))


def render_item(type_: str, obj: object, autogen_context: object) -> str | bool:
    """移行ファイルがアプリのコードに依存しないよう、独自の型を標準の型で書き出す。"""
    if type_ == "type":
        if isinstance(obj, UTCDateTime):
            return "sa.DateTime()"
        if isinstance(obj, AutoString):
            return "sa.String()"
    return False


def _configure(connection: Connection | None, **kwargs: object) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=include_object,
        render_item=render_item,
        compare_type=True,
        # SQLite は列の変更ができないので、表を作り直す方式（batch）で変更する
        render_as_batch=True,
        **kwargs,
    )


def run_migrations_offline() -> None:
    _configure(None, url=url, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = make_engine(url)
    with engine.connect() as connection:
        _configure(connection)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
