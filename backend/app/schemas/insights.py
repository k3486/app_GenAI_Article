"""分析シートの API 出力の型。"""

from datetime import date

from pydantic import BaseModel

from app.schemas.topics import Category, SourceKind


class CategoryCount(BaseModel):
    category: Category
    count: int


class TrendPoint(BaseModel):
    date: date
    category: Category
    count: int


class BacklogPoint(BaseModel):
    date: date
    count: int


class SourceStat(BaseModel):
    source_name: str
    kind: SourceKind
    candidates: int
    selected: int
    likes: int
    dislikes: int
    avg_score: float | None


class ScoreBin(BaseModel):
    label: str
    topics: int
    like_rate: float | None


class Effectiveness(BaseModel):
    # 選定記事のうち 👍 の割合 / 落選記事のうち「実はよかった」の割合
    selected_like_rate: float | None
    rejected_missed_rate: float | None
    score_bins: list[ScoreBin]


class Insights(BaseModel):
    categories: list[CategoryCount]
    trend: list[TrendPoint]
    backlog: list[BacklogPoint]
    sources: list[SourceStat]
    effectiveness: Effectiveness
