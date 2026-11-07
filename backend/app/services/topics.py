"""話題の一覧・詳細・操作（★・👍👎・読了など）。api は薄く、処理はここに置く。"""

from datetime import UTC, datetime, timedelta
from typing import Any, Literal, cast

from sqlalchemy import func, update
from sqlmodel import Session, col, select
from sqlmodel.sql.expression import Select, SelectOfScalar

from app.models import Article, Digest, Score, Source, Topic
from app.schemas.topics import (
    ArticleType,
    CriterionKey,
    TopicCard,
    TopicDetail,
    TopicList,
    TopicStatePatch,
)
from app.services.app_settings import load_settings
from app.services.scoring import CRITERIA, build_breakdown
from app.services.search import search_topic_ids

View = Literal["latest", "favorites", "backlog", "all", "rejected"]
SortKey = Literal["score", "published_at", "selected_at", "title_ja", "source_name"]

LATEST_DAYS = 7
# 未読のまま 30 日たった記事は、自動で「見送り」にする（「後で読む」は除く）
AUTO_DISMISS_DAYS = 30
_SELECTED = ("selected", "major")


def _now() -> datetime:
    return datetime.now(UTC)


def auto_dismiss(session: Session, now: datetime | None = None) -> int:
    """未読のまま30日たった選定記事を「見送り」にする。変えた件数を返す。"""
    cutoff = (now or _now()) - timedelta(days=AUTO_DISMISS_DAYS)
    result = session.execute(
        update(Topic)
        .where(
            col(Topic.selection).in_(_SELECTED),
            col(Topic.read_state) == "unread",
            col(Topic.backlog).is_(False),
            col(Topic.selected_at) < cutoff,
        )
        .values(read_state="dismissed", read_at=now or _now())
    )
    session.commit()
    return int(getattr(result, "rowcount", 0) or 0)


def rejection_reason(card_total: int, interest: int, threshold: int) -> str:
    if interest < 3:
        return "関心との一致が低い（2以下）ため、通常の選定に入れませんでした。"
    return f"合計が{card_total}点で、選定の線（{threshold}点）に届きませんでした。"


def _to_card(
    topic: Topic,
    score: Score,
    article: Article,
    source: Source | None,
    related_count: int,
    threshold: int,
) -> TopicCard:
    scores: dict[CriterionKey, int] = {key: int(getattr(score, key)) for key in CRITERIA}
    weights: dict[CriterionKey, int] = {key: int(score.weights[key]) for key in CRITERIA}
    breakdown = build_breakdown(
        scores,
        weights,
        article_type=cast(ArticleType, score.article_type),
        official=score.official_bonus > 0,
        reason=score.reason,
    )
    assert topic.id is not None
    return TopicCard.model_validate(
        {
            "id": topic.id,
            "title_ja": score.title_ja,
            "summary_1line": score.summary_1line,
            "summary_5lines": score.summary_5lines,
            "url": article.url,
            "selection": topic.selection,
            "score": breakdown.total,
            "breakdown": breakdown.model_dump(),
            "article_type": score.article_type,
            "category": score.category,
            "tags": score.tags,
            "source_name": source.name if source else article.domain,
            "source_kind": source.kind if source else "media",
            "published_at": article.published_at,
            "published_estimated": article.published_estimated,
            "selected_at": topic.selected_at or score.scored_at,
            "run_id": topic.run_id or 0,
            "image_url": article.image_url,
            "related_count": related_count,
            "rejection_reason": (
                rejection_reason(breakdown.total, scores["interest"], threshold)
                if topic.selection == "rejected"
                else None
            ),
            "state": {
                "read_state": topic.read_state,
                "backlog": topic.backlog,
                "starred": topic.starred,
                "rating": topic.rating,
                "dislike_reason": topic.dislike_reason,
                "missed": topic.missed,
            },
        }
    )


def _joined[S: (Select[*tuple[Any, ...]], SelectOfScalar[Any])](stmt: S) -> S:
    """話題 ＋ 採点 ＋ 代表記事 ＋ 情報源 をつなぐ。採点前（pending）の話題は出さない。"""
    return (
        stmt.select_from(Topic)
        .join(Score, col(Score.topic_id) == col(Topic.id))
        .join(
            Article,
            (col(Article.topic_id) == col(Topic.id)) & (col(Article.role) == "representative"),
        )
        .outerjoin(Source, col(Source.id) == col(Article.source_id))
        .where(col(Topic.selection) != "pending")
    )


def _view_filter[S: (Select[*tuple[Any, ...]], SelectOfScalar[Any])](
    stmt: S, view: View, now: datetime
) -> S:
    selected = col(Topic.selection).in_(_SELECTED)
    if view == "rejected":
        return stmt.where(col(Topic.selection) == "rejected")
    if view == "favorites":
        return stmt.where(col(Topic.selection) != "rejected", col(Topic.starred).is_(True))
    if view == "backlog":
        # 未読の選定記事は自動で入る。「後で読む」は、見送りになるまで残る
        return stmt.where(
            selected,
            col(Topic.read_state) != "dismissed",
            (col(Topic.read_state) == "unread") | col(Topic.backlog).is_(True),
        )
    if view == "latest":
        return stmt.where(selected, col(Topic.selected_at) >= now - timedelta(days=LATEST_DAYS))
    return stmt.where(selected)


def _sort_column(sort: SortKey) -> Any:
    return {
        "score": col(Score.total),
        "published_at": col(Article.published_at),
        "selected_at": col(Topic.selected_at),
        "title_ja": col(Score.title_ja),
        "source_name": func.coalesce(col(Source.name), col(Article.domain)),
    }[sort]


def _related_counts(session: Session, topic_ids: list[int]) -> dict[int, int]:
    if not topic_ids:
        return {}
    rows = session.exec(
        select(col(Article.topic_id), func.count())
        .where(col(Article.topic_id).in_(topic_ids), col(Article.role) == "related")
        .group_by(col(Article.topic_id))
    ).all()
    return {int(topic_id): int(count) for topic_id, count in rows if topic_id is not None}


def list_topics(
    session: Session,
    *,
    view: View,
    q: str | None = None,
    article_type: str | None = None,
    category: str | None = None,
    source: str | None = None,
    sort: SortKey | None = None,
    descending: bool = True,
    page: int = 1,
    page_size: int = 50,
    now: datetime | None = None,
) -> TopicList:
    moment = now or _now()
    if view == "backlog":
        auto_dismiss(session, moment)

    def narrowed[S: (Select[*tuple[Any, ...]], SelectOfScalar[Any])](stmt: S) -> S:
        stmt = _view_filter(_joined(stmt), view, moment)
        if q:
            stmt = stmt.where(col(Topic.id).in_(search_topic_ids(session, q)))
        if article_type:
            stmt = stmt.where(col(Score.article_type) == article_type)
        if category:
            stmt = stmt.where(col(Score.category) == category)
        if source:
            stmt = stmt.where(func.coalesce(col(Source.name), col(Article.domain)) == source)
        return stmt

    total = session.exec(narrowed(select(func.count(col(Topic.id))))).one()
    stmt = narrowed(select(Topic, Score, Article, Source))
    if sort is None:
        # 既定: 更新の回の新しい順 → 点数の高い順
        stmt = stmt.order_by(col(Topic.run_id).desc(), col(Score.total).desc(), col(Topic.id))
    else:
        column = _sort_column(sort)
        stmt = stmt.order_by(column.desc() if descending else column.asc(), col(Topic.id))
    rows = session.exec(stmt.offset((page - 1) * page_size).limit(page_size)).all()

    threshold = load_settings(session).threshold
    counts = _related_counts(session, [t.id for t, _, _, _ in rows if t.id is not None])
    items = [_to_card(t, s, a, src, counts.get(t.id or 0, 0), threshold) for t, s, a, src in rows]
    return TopicList(items=items, total=total, page=page, page_size=page_size)


def get_topic(session: Session, topic_id: int) -> TopicDetail | None:
    row = session.exec(
        _joined(select(Topic, Score, Article, Source)).where(col(Topic.id) == topic_id)
    ).first()
    if row is None:
        return None
    topic, score, article, source = row
    articles = session.exec(
        select(Article, Source)
        .join(Source, col(Source.id) == col(Article.source_id), isouter=True)
        .where(col(Article.topic_id) == topic_id)
        .order_by(col(Article.role).desc(), col(Article.published_at))
    ).all()
    related = [a for a, _ in articles if a.role == "related"]
    card = _to_card(topic, score, article, source, len(related), load_settings(session).threshold)

    digest_row = session.get(Digest, topic_id)
    digest = (
        {
            "lead": digest_row.lead,
            "sections": digest_row.sections,
            "model_id": digest_row.model_id,
            "created_at": digest_row.created_at,
        }
        if digest_row
        else None
    )
    return TopicDetail.model_validate(
        {
            **card.model_dump(),
            "digest": digest,
            "articles": [
                {
                    "title": a.title_original or score.title_ja,
                    "url": a.url,
                    "source_name": src.name if src else a.domain,
                    "role": a.role,
                    "published_at": a.published_at,
                }
                for a, src in articles
            ],
        }
    )


def patch_state(
    session: Session, topic_id: int, patch: TopicStatePatch, now: datetime | None = None
) -> TopicCard | None:
    """送ったフィールドだけを変える。日時（読了・評価）も一緒に記録する。"""
    topic = session.get(Topic, topic_id)
    if topic is None or topic.selection == "pending":
        return None
    now = now or _now()
    changes = patch.model_dump(exclude_unset=True)

    if "read_state" in changes and changes["read_state"] is not None:
        topic.read_state = changes["read_state"]
        topic.read_at = None if topic.read_state == "unread" else now
    for field in ("backlog", "starred"):
        if field in changes and changes[field] is not None:
            setattr(topic, field, changes[field])
    if "rating" in changes:
        topic.rating = changes["rating"]
        topic.rated_at = now if topic.rating else None
        if topic.rating != "dislike":
            topic.dislike_reason = None
    if "dislike_reason" in changes and topic.rating == "dislike":
        topic.dislike_reason = changes["dislike_reason"]
    if "missed" in changes and changes["missed"] is not None:
        topic.missed = changes["missed"]
        topic.missed_at = now if topic.missed else None
    session.add(topic)
    session.commit()

    row = session.exec(
        _joined(select(Topic, Score, Article, Source)).where(col(Topic.id) == topic_id)
    ).one()
    t, s, a, src = row
    counts = _related_counts(session, [topic_id])
    return _to_card(t, s, a, src, counts.get(topic_id, 0), load_settings(session).threshold)
