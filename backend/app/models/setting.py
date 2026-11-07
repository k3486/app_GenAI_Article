from typing import Any

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class Setting(SQLModel, table=True):
    """画面から変える設定（興味プロファイル・重み・しきい値・上限・件数など）。"""

    __tablename__ = "settings"

    key: str = Field(primary_key=True)
    value: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
