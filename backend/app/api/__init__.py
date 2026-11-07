"""/api 配下のルーターを集約する。新しいルーターはここで include する。"""

from fastapi import APIRouter

from app.api import health

api_router = APIRouter(prefix="/api")
api_router.include_router(health.router)
