"""話題（一覧の1行）と、その記事・本文・点数・整理記事。"""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Column, Text
from sqlmodel import Field, SQLModel

from app.models.types import UTCDateTime, utcnow


class Topic(SQLModel, table=True):
    """話題。代表記事に関連記事がぶら下がる。あなたの操作で変わる状態もここに持つ。"""

    __tablename__ = "topics"

    id: int | None = Field(default=None, primary_key=True)
    # pending（採点待ち）| selected | major（重大ニュース）| rejected
    selection: str = Field(default="pending", index=True)
    run_id: int | None = Field(default=None, foreign_key="runs.id", index=True)
    selected_at: datetime | None = Field(default=None, sa_column=Column(UTCDateTime, index=True))
    created_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(UTCDateTime, nullable=False)
    )

    # --- あなたの操作 ---
    read_state: str = "unread"  # unread | read | dismissed
    backlog: bool = False  # 「後で読む」
    starred: bool = False
    rating: str | None = None  # like | dislike
    dislike_reason: str | None = None  # not_interested | already_known | low_quality
    missed: bool = False  # 落選記事への「実はよかった」
    read_at: datetime | None = Field(default=None, sa_column=Column(UTCDateTime))
    rated_at: datetime | None = Field(default=None, sa_column=Column(UTCDateTime))
    missed_at: datetime | None = Field(default=None, sa_column=Column(UTCDateTime))


class Article(SQLModel, table=True):
    """取り込んだ記事（代表・関連の両方）。"""

    __tablename__ = "articles"

    id: int | None = Field(default=None, primary_key=True)
    topic_id: int | None = Field(default=None, foreign_key="topics.id", index=True)
    role: str = "representative"  # representative | related
    source_id: int | None = Field(default=None, foreign_key="sources.id")
    domain: str = ""
    url: str
    url_normalized: str = Field(unique=True, index=True)
    title_original: str = ""
    language: str = "en"
    published_at: datetime = Field(sa_column=Column(UTCDateTime, nullable=False))
    published_estimated: bool = False
    discovered_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(UTCDateTime, nullable=False)
    )
    run_id: int | None = Field(default=None, foreign_key="runs.id")
    image_url: str | None = None
    # discovered | fetched | grouped | scored | composed
    stage: str = Field(default="discovered", index=True)
    fetch_status: str = "none"  # none | partial | full | failed
    fetch_attempts: int = 0
    fetch_error: str | None = None  # 直近の取得の失敗の理由（画面・レポート用）
    # RSS などの概要。全文が取れなかったとき、これで採点する
    summary: str = Field(default="", sa_column=Column(Text, nullable=False, server_default=""))
    # 同じ話題をまとめるための共通リンクの鍵（公式ページの URL や arXiv ID）
    link_key: str | None = Field(default=None, index=True)
    is_paper: bool = False


class ArticleText(SQLModel, table=True):
    """本文。大きいので別表にする（将来 S3 などに移しやすい）。"""

    __tablename__ = "article_texts"

    article_id: int = Field(foreign_key="articles.id", primary_key=True)
    body: str = Field(sa_column=Column(Text, nullable=False))
    length: int = 0


class Score(SQLModel, table=True):
    """採点の結果（代表記事ごと）。5観点の点数と、そのときの重みを保存する。"""

    __tablename__ = "scores"

    topic_id: int = Field(foreign_key="topics.id", primary_key=True)
    interest: int
    practical: int
    freshness: int
    trust: int
    depth: int
    weights: dict[str, int] = Field(sa_column=Column(JSON, nullable=False))
    official_bonus: int = 0
    total: int
    reason: str = ""
    article_type: str  # announcement | howto | paper | analysis | industry
    category: str
    tags: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    title_ja: str
    summary_1line: str = ""
    summary_5lines: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    model_id: str = ""
    skill_version: str = ""
    run_id: int | None = Field(default=None, foreign_key="runs.id")
    scored_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(UTCDateTime, nullable=False)
    )


class Digest(SQLModel, table=True):
    """整理記事（選定された話題ごとに1つ）。"""

    __tablename__ = "digests"

    topic_id: int = Field(foreign_key="topics.id", primary_key=True)
    article_type: str
    lead: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    # [{"heading": str, "paragraphs": [{"text": str, "inference": bool}]}]
    sections: list[dict[str, Any]] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )
    model_id: str = ""
    skill_version: str = ""
    created_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(UTCDateTime, nullable=False)
    )
