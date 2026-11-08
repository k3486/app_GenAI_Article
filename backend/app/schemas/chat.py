"""壁打ち（Haiku との会話）とメモの入出力の型。"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

QUESTION_MAX_CHARS = 2000
NOTE_MAX_CHARS = 2000


class ChatMessageOut(BaseModel):
    id: int
    role: Literal["user", "assistant"]
    content: str
    tool_log: list[dict[str, Any]]
    cost_usd: float
    status: Literal["ok", "limited"]
    created_at: datetime


class ChatState(BaseModel):
    messages: list[ChatMessageOut]
    rounds_used: int
    rounds_limit: int


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=QUESTION_MAX_CHARS)


class NoteOut(BaseModel):
    id: int
    topic_id: int
    chat_message_id: int | None
    text: str
    created_at: datetime


class NoteIn(BaseModel):
    text: str = Field(min_length=1, max_length=NOTE_MAX_CHARS)
    chat_message_id: int | None = None
