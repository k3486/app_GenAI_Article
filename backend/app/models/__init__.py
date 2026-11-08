"""DB のテーブル。Alembic が全テーブルを見つけられるよう、ここですべて import する。"""

from app.models.chat import ChatMessage, Note
from app.models.preference import PreferenceNote, ProfileProposal, ProfileVersion
from app.models.run import LlmUsage, Run, RunIssue, SearchQuery
from app.models.setting import Setting
from app.models.source import Source
from app.models.topic import Article, ArticleText, Digest, Score, Topic

__all__ = [
    "Article",
    "ArticleText",
    "ChatMessage",
    "Digest",
    "LlmUsage",
    "Note",
    "PreferenceNote",
    "ProfileProposal",
    "ProfileVersion",
    "Run",
    "RunIssue",
    "Score",
    "SearchQuery",
    "Setting",
    "Source",
    "Topic",
]
