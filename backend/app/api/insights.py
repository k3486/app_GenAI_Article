from typing import Annotated

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.db import get_session
from app.schemas.insights import Insights
from app.services import insights as insights_service

router = APIRouter(tags=["insights"])


@router.get("/insights")
def get_insights(session: Annotated[Session, Depends(get_session)]) -> Insights:
    return insights_service.get_insights(session)
