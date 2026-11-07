from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session, select

from app.db import get_session

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    database: str


@router.get("/health")
def health(session: Annotated[Session, Depends(get_session)]) -> HealthResponse:
    session.exec(select(1)).one()
    return HealthResponse(status="ok", database="ok")
