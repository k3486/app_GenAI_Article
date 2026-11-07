"""DB のテーブル。Alembic が全テーブルを見つけられるよう、ここですべて import する。"""

from app.models.run import LlmUsage, Run, RunIssue, SearchQuery
from app.models.setting import Setting
from app.models.source import Source
from app.models.topic import Article, ArticleText, Digest, Score, Topic

__all__ = [
    "Article",
    "ArticleText",
    "Digest",
    "LlmUsage",
    "Run",
    "RunIssue",
    "Score",
    "SearchQuery",
    "Setting",
    "Source",
    "Topic",
]
