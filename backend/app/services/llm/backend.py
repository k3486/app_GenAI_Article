"""Anthropic API を呼ぶ唯一の場所。テストでは LlmBackend を満たす偽物に差し替える。"""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

import anthropic
import pydantic
from pydantic import BaseModel

from app.config import get_settings
from app.services.llm.errors import LlmFormatError, LlmRefusedError, LlmUnavailableError

Effort = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class RawResult[T: BaseModel]:
    parsed: T
    input_tokens: int  # キャッシュに関係しない入力
    output_tokens: int
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0


@dataclass(frozen=True)
class ModelEntry:
    id: str
    created_at: datetime
    active: bool


class LlmBackend(Protocol):
    async def parse[T: BaseModel](
        self,
        *,
        model: str,
        system: list[str],
        user: str,
        output_type: type[T],
        effort: Effort,
        max_tokens: int,
    ) -> RawResult[T]: ...

    async def list_models(self) -> list[ModelEntry]: ...


class AnthropicBackend:
    """公式 SDK（AsyncAnthropic）。一時エラー（429・5xx・通信）は SDK が2回まで自動でやり直す。"""

    def __init__(self, client: anthropic.AsyncAnthropic | None = None) -> None:
        if client is None:
            key = get_settings().anthropic_api_key
            if key is None:
                raise LlmUnavailableError("ANTHROPIC_API_KEY が設定されていません")
            client = anthropic.AsyncAnthropic(api_key=key.get_secret_value(), max_retries=2)
        self._client = client

    async def parse[T: BaseModel](
        self,
        *,
        model: str,
        system: list[str],
        user: str,
        output_type: type[T],
        effort: Effort,
        max_tokens: int,
    ) -> RawResult[T]:
        # 変わらない前半から最後のブロックまでをキャッシュの対象にする
        blocks: list[anthropic.types.TextBlockParam] = [
            {"type": "text", "text": text} for text in system
        ]
        blocks[-1]["cache_control"] = {"type": "ephemeral"}
        try:
            message = await self._client.messages.parse(
                model=model,
                max_tokens=max_tokens,
                system=blocks,
                messages=[{"role": "user", "content": user}],
                output_format=output_type,
                output_config={"effort": effort},
            )
        except (pydantic.ValidationError, ValueError) as error:
            raise LlmFormatError(f"出力の形が不正です: {error}") from error
        except anthropic.APIError as error:
            raise LlmUnavailableError(f"{type(error).__name__}: {error}") from error
        if message.stop_reason == "refusal":
            raise LlmRefusedError("モデルが応答を拒否しました")
        if message.stop_reason == "max_tokens":
            raise LlmFormatError("出力が長すぎて途中で切れました")
        if message.parsed_output is None:
            raise LlmFormatError("出力を読み取れませんでした")
        usage = message.usage
        return RawResult(
            parsed=message.parsed_output,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_write_tokens=usage.cache_creation_input_tokens or 0,
            cache_read_tokens=usage.cache_read_input_tokens or 0,
        )

    async def list_models(self) -> list[ModelEntry]:
        try:
            return [
                ModelEntry(id=m.id, created_at=m.created_at, active=m.lifecycle == "active")
                async for m in self._client.models.list(limit=100)
            ]
        except anthropic.APIError as error:
            raise LlmUnavailableError(f"モデル一覧を取得できません: {error}") from error
