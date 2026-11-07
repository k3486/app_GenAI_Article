"""更新の実行状況・費用の API 入出力の型。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

RunStatus = Literal["running", "succeeded", "partial", "budget_stopped", "failed"]


class RunIssue(BaseModel):
    source_name: str
    stage: str
    message: str


class SearchQuery(BaseModel):
    query: str
    language: Literal["en", "ja"]
    result_count: int


class RunSummary(BaseModel):
    id: int
    status: RunStatus
    trigger: Literal["manual", "scheduled"]
    started_at: datetime
    finished_at: datetime | None
    new_count: int
    scored_count: int
    selected_count: int
    cost_usd: float
    model_id: str
    previous_model_id: str | None
    issues: list[RunIssue]
    search_queries: list[SearchQuery]


class Budget(BaseModel):
    month_cost_usd: float
    month_limit_usd: float
    run_limit_usd: float


class AppStatus(BaseModel):
    latest_run: RunSummary | None
    budget: Budget
    # 試しのデータで動いている間は True（画面に注意書きを出す）
    sample_mode: bool
