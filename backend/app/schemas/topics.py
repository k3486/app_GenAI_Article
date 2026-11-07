"""話題（一覧の1行＝代表記事＋関連記事）の API 入出力の型。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ArticleType = Literal["announcement", "howto", "paper", "analysis", "industry"]
Category = Literal[
    "dev_tools_agents",
    "models",
    "use_cases",
    "know_how",
    "regulation_safety",
    "industry_trends",
    "other",
]
SourceKind = Literal["official", "media", "paper"]
Selection = Literal["selected", "major", "rejected"]
ReadState = Literal["unread", "read", "dismissed"]
Rating = Literal["like", "dislike"]
DislikeReason = Literal["not_interested", "already_known", "low_quality"]
CriterionKey = Literal["interest", "practical", "freshness", "trust", "depth"]


class TopicState(BaseModel):
    """あなたの操作で変わる状態。"""

    read_state: ReadState = "unread"
    backlog: bool = False
    starred: bool = False
    rating: Rating | None = None
    dislike_reason: DislikeReason | None = None
    missed: bool = False


class TopicStatePatch(BaseModel):
    """状態の更新。送ったフィールドだけを変える（null を送ると消す）。"""

    read_state: ReadState | None = None
    backlog: bool | None = None
    starred: bool | None = None
    rating: Rating | None = None
    dislike_reason: DislikeReason | None = None
    missed: bool | None = None


class CriterionScore(BaseModel):
    key: CriterionKey
    label: str
    score: int = Field(ge=1, le=5)
    weight: int


class ScoreBreakdown(BaseModel):
    criteria: list[CriterionScore]
    official_bonus: int
    total: int
    reason: str


class TopicCard(BaseModel):
    id: int
    title_ja: str
    summary_1line: str
    summary_5lines: list[str]
    url: str
    selection: Selection
    score: int
    breakdown: ScoreBreakdown
    article_type: ArticleType
    category: Category
    tags: list[str]
    source_name: str
    source_kind: SourceKind
    published_at: datetime
    published_estimated: bool
    selected_at: datetime
    run_id: int
    image_url: str | None
    related_count: int
    rejection_reason: str | None
    state: TopicState


class TopicList(BaseModel):
    items: list[TopicCard]
    total: int
    page: int
    page_size: int


class Paragraph(BaseModel):
    text: str
    # True の段落は Haiku の推測（画面で「（考察）」として区別して表示する）
    inference: bool = False


class DigestSection(BaseModel):
    heading: str
    paragraphs: list[Paragraph]


class Digest(BaseModel):
    lead: list[str]
    sections: list[DigestSection]
    model_id: str
    created_at: datetime


class RelatedArticle(BaseModel):
    title: str
    url: str
    source_name: str
    role: Literal["representative", "related"]
    published_at: datetime


class TopicDetail(TopicCard):
    digest: Digest | None
    # 整理記事の末尾に出す URL 一覧（プログラムが DB の URL から作る）
    articles: list[RelatedArticle]
