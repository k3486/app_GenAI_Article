"""全文検索（タイトル・要約・タグ・整理記事・メモ）。検索の窓口はここに隔離する。

SQLite は FTS5（trigram: 3文字ずつに区切る方式。日本語でも部分一致で探せる）を使う。
PostgreSQL へ移すときは、この窓口だけを pg_trgm に差し替える（他の場所は変えない）。
本文は DB に保存するが、検索の対象にはしない。
"""

from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlmodel import Session, col, select

from app.models import Digest, Note, Score

SEARCH_TABLE = "topic_search"
_MIN_TRIGRAM = 3


def create_search_index(connection: Connection) -> None:
    """検索用の表を作る（SQLite だけ。Alembic の移行と、テスト用の作成から呼ぶ）。"""
    if connection.dialect.name != "sqlite":
        return
    connection.exec_driver_sql(
        f"CREATE VIRTUAL TABLE IF NOT EXISTS {SEARCH_TABLE} "
        "USING fts5(topic_id UNINDEXED, body, tokenize='trigram')"
    )


def drop_search_index(connection: Connection) -> None:
    if connection.dialect.name != "sqlite":
        return
    connection.exec_driver_sql(f"DROP TABLE IF EXISTS {SEARCH_TABLE}")


def _document(score: Score, digest: Digest | None, notes: list[str]) -> str:
    parts = [score.title_ja, score.summary_1line, *score.summary_5lines, *score.tags, *notes]
    if digest is not None:
        for section in digest.sections:
            parts.append(str(section.get("heading", "")))
            parts.extend(str(p.get("text", "")) for p in section.get("paragraphs", []))
    return "\n".join(p for p in parts if p)


def index_topic(session: Session, topic_id: int) -> None:
    """話題の検索用の文章を作り直す（採点・整理記事を保存したあとに呼ぶ）。"""
    connection = session.connection()
    if connection.dialect.name != "sqlite":
        return
    score = session.get(Score, topic_id)
    connection.execute(text(f"DELETE FROM {SEARCH_TABLE} WHERE topic_id = :id"), {"id": topic_id})
    if score is None:
        return
    notes = session.exec(select(Note.text).where(col(Note.topic_id) == topic_id)).all()
    body = _document(score, session.get(Digest, topic_id), list(notes))
    connection.execute(
        text(f"INSERT INTO {SEARCH_TABLE} (topic_id, body) VALUES (:id, :body)"),
        {"id": topic_id, "body": body},
    )


def search_topic_ids(session: Session, query: str) -> set[int]:
    """検索語に一致する話題の ID。3文字未満は、全文を舐める部分一致で探す。"""
    connection = session.connection()
    needle = query.strip()
    if connection.dialect.name != "sqlite":
        raise NotImplementedError("この DB の全文検索は、移行のときに pg_trgm で実装する")
    if len(needle) >= _MIN_TRIGRAM:
        phrase = '"' + needle.replace('"', '""') + '"'
        rows = connection.execute(
            text(f"SELECT topic_id FROM {SEARCH_TABLE} WHERE {SEARCH_TABLE} MATCH :q"),
            {"q": phrase},
        )
    else:
        escaped = needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        rows = connection.execute(
            text(f"SELECT topic_id FROM {SEARCH_TABLE} WHERE body LIKE :q ESCAPE '\\'"),
            {"q": f"%{escaped}%"},
        )
    return {int(row[0]) for row in rows}
