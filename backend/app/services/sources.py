"""情報源（一覧の正は config/sources.yaml。ここでは成績つきの閲覧と、有効／無効の切り替え）。"""

from sqlalchemy import func
from sqlmodel import Session, col, select

from app.models import Article, Score, Source, Topic
from app.schemas.insights import SourceStat
from app.schemas.settings import SourceInfo


def source_stats(session: Session) -> dict[str, SourceStat]:
    """情報源ごとの成績（候補・選定・👍👎・平均点）。名前で引ける。"""
    name = func.coalesce(col(Source.name), col(Article.domain))
    rows = session.exec(
        select(Topic, Score, name, col(Source.kind))
        .select_from(Topic)
        .join(Score, col(Score.topic_id) == col(Topic.id))
        .join(
            Article,
            (col(Article.topic_id) == col(Topic.id)) & (col(Article.role) == "representative"),
        )
        .outerjoin(Source, col(Source.id) == col(Article.source_id))
        .where(col(Topic.selection) != "pending")
    ).all()
    grouped: dict[str, list[tuple[Topic, Score, str]]] = {}
    for topic, score, source_name, kind in rows:
        grouped.setdefault(str(source_name), []).append((topic, score, str(kind or "media")))
    stats: dict[str, SourceStat] = {}
    for source_name, items in grouped.items():
        stats[source_name] = SourceStat.model_validate(
            {
                "source_name": source_name,
                "kind": items[0][2],
                "candidates": len(items),
                "selected": sum(1 for t, _, _ in items if t.selection != "rejected"),
                "likes": sum(1 for t, _, _ in items if t.rating == "like"),
                "dislikes": sum(1 for t, _, _ in items if t.rating == "dislike"),
                "avg_score": round(sum(s.total for _, s, _ in items) / len(items), 1),
            }
        )
    return stats


def list_sources(session: Session) -> list[SourceInfo]:
    stats = source_stats(session)
    sources = session.exec(select(Source).order_by(col(Source.id))).all()
    result: list[SourceInfo] = []
    for source in sources:
        stat = stats.get(source.name)
        result.append(
            SourceInfo.model_validate(
                {
                    "key": source.key,
                    "name": source.name,
                    "kind": source.kind,
                    "enabled": source.enabled,
                    "candidates": stat.candidates if stat else 0,
                    "selected": stat.selected if stat else 0,
                    "likes": stat.likes if stat else 0,
                    "avg_score": stat.avg_score if stat else None,
                }
            )
        )
    return result


def set_source_enabled(session: Session, key: str, enabled: bool) -> SourceInfo | None:
    source = session.exec(select(Source).where(col(Source.key) == key)).first()
    if source is None:
        return None
    source.enabled = enabled
    session.add(source)
    session.commit()
    return next(s for s in list_sources(session) if s.key == key)
