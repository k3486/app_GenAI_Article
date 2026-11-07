from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.db import get_session
from app.schemas.settings import Settings, SourceInfo, SourcePatch
from app.services import app_settings, sources

router = APIRouter(tags=["settings"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/settings")
def get_settings(session: SessionDep) -> Settings:
    return app_settings.load_settings(session)


@router.put("/settings")
def put_settings(settings: Settings, session: SessionDep) -> Settings:
    return app_settings.save_settings(session, settings)


@router.get("/sources")
def list_sources(session: SessionDep) -> list[SourceInfo]:
    return sources.list_sources(session)


@router.patch("/sources/{key}")
def patch_source(key: str, patch: SourcePatch, session: SessionDep) -> SourceInfo:
    source = sources.set_source_enabled(session, key, patch.enabled)
    if source is None:
        raise HTTPException(status_code=404, detail="情報源が見つかりません")
    return source
