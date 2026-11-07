from fastapi import FastAPI

from app.api import api_router
from app.config import get_settings


def create_app() -> FastAPI:
    app = FastAPI(title=get_settings().app_name)
    app.include_router(api_router)
    return app


app = create_app()
