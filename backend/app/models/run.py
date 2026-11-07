from datetime import datetime

from sqlalchemy import Column
from sqlmodel import Field, SQLModel

from app.models.types import UTCDateTime, utcnow


class Run(SQLModel, table=True):
    """更新の実行履歴。ハートビートが止まった実行は「失敗」と見なす。"""

    __tablename__ = "runs"

    id: int | None = Field(default=None, primary_key=True)
    trigger: str  # manual | scheduled
    status: str = "running"  # running | succeeded | partial | budget_stopped | failed
    started_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(UTCDateTime, nullable=False, index=True)
    )
    finished_at: datetime | None = Field(default=None, sa_column=Column(UTCDateTime))
    heartbeat_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(UTCDateTime, nullable=False)
    )
    new_count: int = 0
    scored_count: int = 0
    selected_count: int = 0
    cost_usd: float = 0.0
    model_id: str = ""
    previous_model_id: str | None = None


class RunIssue(SQLModel, table=True):
    """更新中に起きた問題（全文を取れなかったサイトなど）。"""

    __tablename__ = "run_issues"

    id: int | None = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="runs.id", index=True)
    source_name: str
    stage: str
    message: str


class SearchQuery(SQLModel, table=True):
    """Haiku が作った検索語（画面で確認できるように残す）。"""

    __tablename__ = "search_queries"

    id: int | None = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="runs.id", index=True)
    query: str
    language: str  # en | ja
    result_count: int = 0


class LlmUsage(SQLModel, table=True):
    """Haiku の使用量と費用。月・1回の上限の判定と、画面の費用表示に使う。"""

    __tablename__ = "llm_usage"

    id: int | None = Field(default=None, primary_key=True)
    run_id: int | None = Field(default=None, foreign_key="runs.id", index=True)
    topic_id: int | None = Field(default=None, foreign_key="topics.id")
    purpose: str  # score | group | compose | queries | chat | preference
    model_id: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cost_usd: float = 0.0
    created_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(UTCDateTime, nullable=False, index=True)
    )
