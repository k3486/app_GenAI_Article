from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import app.models  # noqa: F401  すべての表を登録する
from app.config import get_settings
from app.db import configure_sqlite, get_session
from app.main import create_app
from app.services.search import create_search_index
from scripts.seed_sample import seed


@pytest.fixture(autouse=True)
def no_real_llm_key(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """テスト中に本物の Anthropic API を呼ばない（キーが環境にあっても使えなくする）。"""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def session() -> Iterator[Session]:
    """テストごとに新しいメモリ上の SQLite を使う（本番と同じ設定・全文検索の表つき）。"""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    configure_sqlite(engine)
    SQLModel.metadata.create_all(engine)
    with engine.begin() as connection:
        create_search_index(connection)
    with Session(engine) as session:
        yield session


@pytest.fixture
def seeded(session: Session) -> Session:
    """試しのデータ（scripts/seed_sample.py）を入れた DB。"""
    seed(session)
    return session


@pytest.fixture
def client(session: Session) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app) as client:
        yield client
