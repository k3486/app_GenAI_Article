"""Haiku の出力の型。構造化出力の定義はこの型から作る（スキルのファイルには形を書かない）。"""

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.topics import ArticleType, Category


class ScoreOutput(BaseModel):
    """採点スキルの出力。合計点・選定はプログラムが計算する（Haiku は 5観点の点数だけ）。"""

    interest: int = Field(ge=1, le=5, description="関心との一致（1〜5）")
    practical: int = Field(
        ge=1,
        le=5,
        description="実用性＝再現性・汎用性（1〜5）。論文・発表・リリースは実務や事業への示唆の大きさ",
    )
    freshness: int = Field(ge=1, le=5, description="新しさ・重要度（1〜5）")
    trust: int = Field(ge=1, le=5, description="信頼性（1〜5）")
    depth: int = Field(ge=1, le=5, description="内容の深さ（1〜5）")
    reason: str = Field(description="点数の理由（日本語で1行）")
    article_type: ArticleType
    category: Category
    tags: list[str] = Field(description="自由タグ（日本語、3〜5個）")
    title_ja: str = Field(description="日本語タイトル")
    summary_1line: str = Field(description="日本語の1行要約（60字以内）")
    summary_5lines: list[str] = Field(description="日本語の5行要約（各行60字以内、5行）")


class TopicJoin(BaseModel):
    """新着の記事を、すでにある話題に入れる。"""

    article_id: int
    topic_id: int


class GroupOutput(BaseModel):
    """話題のまとめスキルの出力。どれにも当てはまらない記事は、何も書かない（単独の話題になる）。"""

    joins: list[TopicJoin] = Field(description="既存の話題と同じ内容の新着記事")
    same_topic_sets: list[list[int]] = Field(
        description="新着の記事どうしで同じ内容のもの（記事 ID の組。2件以上）"
    )


class DigestParagraph(BaseModel):
    text: str = Field(description="段落の本文（日本語・ですます調）")
    inference: bool = Field(
        description="AI（執筆者）の意見・推測・評価なら true（画面では「AI の意見」と表示される）"
    )


class DigestSection(BaseModel):
    heading: str = Field(description="見出し（構成の項目名）")
    paragraphs: list[DigestParagraph] = Field(min_length=1)


class DigestOutput(BaseModel):
    """整理記事スキルの出力。URL は書かない（末尾の URL 一覧はプログラムが DB から付ける）。"""

    lead: list[str] = Field(
        min_length=3, max_length=3, description="先頭の3行まとめ（各行は1文、80字以内）"
    )
    sections: list[DigestSection] = Field(
        min_length=1, description="種類ごとの構成の項目。書くことがない項目は省く"
    )


class ParagraphVerdict(BaseModel):
    index: int = Field(description="段落の番号")
    origin: Literal["article", "ai"] = Field(
        description="article=材料に書かれていること／ai=AI が付け加えた意見・推測・評価"
    )
    reason: str = Field(description="理由（日本語・30字以内）")


class VerifyOutput(BaseModel):
    """整理記事の校閲スキルの出力。すべての段落に1つずつ判定を返す。"""

    verdicts: list[ParagraphVerdict]
