from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from app.models.types import UTCDateTime, utcnow


class ChatMessage(SQLModel, table=True):
    """壁打ち（話題ごとの Haiku との会話）の発言。"""

    __tablename__ = "chat_messages"

    id: int | None = Field(default=None, primary_key=True)
    topic_id: int = Field(foreign_key="topics.id", index=True)
    role: str  # user | assistant
    content: str
    # assistant の発言で使ったツール: [{"name": str, "input": {...}}]
    tool_log: list[dict[str, Any]] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )
    cost_usd: float = 0.0
    status: str = "ok"  # ok | limited（費用の上限で回答できなかった）
    created_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(UTCDateTime, nullable=False)
    )


class Note(SQLModel, table=True):
    """整理記事の下に残すメモ（壁打ちの回答から、または手で書く）。"""

    __tablename__ = "notes"

    id: int | None = Field(default=None, primary_key=True)
    topic_id: int = Field(foreign_key="topics.id", index=True)
    chat_message_id: int | None = Field(default=None, foreign_key="chat_messages.id")
    text: str
    created_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(UTCDateTime, nullable=False)
    )
