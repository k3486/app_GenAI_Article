from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from app.db import get_session
from app.schemas.topics import (
    ArticleType,
    Category,
    TopicCard,
    TopicDetail,
    TopicList,
    TopicStatePatch,
)
from app.services import topics as topics_service
from app.services.topics import SortKey, View

router = APIRouter(prefix="/topics", tags=["topics"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.get("")
def list_topics(
    session: SessionDep,
    view: Annotated[View, Query(description="どのシートの一覧か")] = "latest",
    q: Annotated[str | None, Query(description="タイトル・要約・タグ・整理記事の検索")] = None,
    article_type: Annotated[ArticleType | None, Query(alias="type")] = None,
    category: Category | None = None,
    source: str | None = None,
    sort: SortKey | None = None,
    order: Literal["asc", "desc"] = "desc",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> TopicList:
    return topics_service.list_topics(
        session,
        view=view,
        q=q,
        article_type=article_type,
        category=category,
        source=source,
        sort=sort,
        descending=order == "desc",
        page=page,
        page_size=page_size,
    )


@router.get("/{topic_id}")
def get_topic(topic_id: int, session: SessionDep) -> TopicDetail:
    topic = topics_service.get_topic(session, topic_id)
    if topic is None:
        raise HTTPException(status_code=404, detail="話題が見つかりません")
    return topic


@router.patch("/{topic_id}/state")
def patch_state(topic_id: int, patch: TopicStatePatch, session: SessionDep) -> TopicCard:
    card = topics_service.patch_state(session, topic_id, patch)
    if card is None:
        raise HTTPException(status_code=404, detail="話題が見つかりません")
    return card
