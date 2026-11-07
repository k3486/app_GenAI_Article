"""Haiku の偽物。Anthropic API を呼ばずに、決めた応答を返す（LlmBackend を満たす）。"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from pydantic import BaseModel

from app.schemas.analysis import ScoreOutput
from app.services.llm.backend import Effort, ModelEntry, RawResult
from app.services.llm.errors import LlmError

Responder = Callable[[type[BaseModel], list[str], str], BaseModel | LlmError]


def score_output(**override: object) -> ScoreOutput:
    data: dict[str, object] = {
        "interest": 4,
        "practical": 4,
        "freshness": 4,
        "trust": 4,
        "depth": 4,
        "reason": "テスト用の理由",
        "article_type": "announcement",
        "category": "models",
        "tags": ["テスト"],
        "title_ja": "テストの記事",
        "summary_1line": "1行要約",
        "summary_5lines": ["1", "2", "3", "4", "5"],
    }
    data.update(override)
    return ScoreOutput.model_validate(data)


@dataclass
class Call:
    model: str
    system: list[str]
    user: str
    output_type: type[BaseModel]
    effort: Effort


@dataclass
class FakeBackend:
    responder: Responder
    models: list[ModelEntry] | LlmError = field(
        default_factory=lambda: [
            ModelEntry("claude-haiku-5-5", datetime(2026, 10, 1, tzinfo=UTC), True)
        ]
    )
    input_tokens: int = 1000
    output_tokens: int = 200
    calls: list[Call] = field(default_factory=list)

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
        self.calls.append(Call(model, system, user, output_type, effort))
        result = self.responder(output_type, system, user)
        if isinstance(result, LlmError):
            raise result
        assert isinstance(result, output_type)
        return RawResult(
            parsed=result, input_tokens=self.input_tokens, output_tokens=self.output_tokens
        )

    async def list_models(self) -> list[ModelEntry]:
        if isinstance(self.models, LlmError):
            raise self.models
        return self.models
