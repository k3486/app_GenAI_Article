"""アプリ設定。値は環境変数からのみ読む（.env ファイルは読まない）。"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/config.py → リポジトリ直下
REPO_ROOT = Path(__file__).resolve().parents[2]

LLMProvider = Literal["anthropic", "openai"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    app_name: str = "ai-news-dashboard"
    database_url: str = f"sqlite:///{REPO_ROOT / 'data' / 'app.db'}"
    # LLM の API キー。どちらか一方だけ設定されていればよい（空・空白だけは未設定とみなす）
    anthropic_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None

    @field_validator("anthropic_api_key", "openai_api_key", mode="before")
    @classmethod
    def _blank_to_none(cls, value: object) -> object:
        if isinstance(value, SecretStr):
            value = value.get_secret_value()
        if isinstance(value, str) and not value.strip():
            return None
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()


def get_llm_provider(settings: Settings | None = None) -> LLMProvider:
    """使う LLM の提供元を返す。両方のキーがあるときは Anthropic を優先する。"""
    settings = settings or get_settings()
    if settings.anthropic_api_key is not None:
        return "anthropic"
    if settings.openai_api_key is not None:
        return "openai"
    raise RuntimeError(
        "LLM の API キーがありません。ANTHROPIC_API_KEY か OPENAI_API_KEY を設定してください"
    )
