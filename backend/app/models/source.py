from datetime import datetime

from sqlalchemy import Column
from sqlmodel import Field, SQLModel

from app.models.types import UTCDateTime, utcnow


class Source(SQLModel, table=True):
    """情報源。一覧の正は config/sources.yaml で、ここには有効／無効の切り替えを持つ。"""

    __tablename__ = "sources"

    id: int | None = Field(default=None, primary_key=True)
    key: str = Field(unique=True, index=True)
    name: str
    kind: str  # official | media | paper
    enabled: bool = True
    created_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(UTCDateTime, nullable=False)
    )
