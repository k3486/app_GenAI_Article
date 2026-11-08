"""/api 配下のルーターを集約する。新しいルーターはここで include する。"""

from fastapi import APIRouter

from app.api import chat, health, insights, preference, settings, status, topics

api_router = APIRouter(prefix="/api")
api_router.include_router(health.router)
api_router.include_router(topics.router)
api_router.include_router(chat.router)
api_router.include_router(preference.router)
api_router.include_router(status.router)
api_router.include_router(insights.router)
api_router.include_router(settings.router)
