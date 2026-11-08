"""Haiku を呼ぶ口。予算の予約・精算、形式が壊れたときの1回のやり直し、使用量の返却まで行う。

DB には書かない（並列で呼ぶため。記録は呼び出し側が1件ずつ llm_usage に書く）。
"""

import json
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from app.services.llm.backend import Effort, LlmBackend, RawResult, RawTurn, ToolSpec
from app.services.llm.budget import Budget
from app.services.llm.errors import LlmFormatError
from app.services.llm.pricing import cost_usd, estimate_usd
from app.services.llm.skills import Skill


@dataclass(frozen=True)
class Usage:
    model_id: str
    input_tokens: int  # キャッシュ書き込みを含む
    output_tokens: int
    cache_read_tokens: int
    cost_usd: float


@dataclass(frozen=True)
class LlmResult[T: BaseModel]:
    parsed: T
    usage: Usage
    skill_version: str


def _usage_of(
    model_id: str, *, input_tokens: int, output_tokens: int, cache_write: int, cache_read: int
) -> Usage:
    return Usage(
        model_id=model_id,
        input_tokens=input_tokens + cache_write,
        output_tokens=output_tokens,
        cache_read_tokens=cache_read,
        cost_usd=cost_usd(
            model_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_write_tokens=cache_write,
            cache_read_tokens=cache_read,
        ),
    )


def _usage(model_id: str, raw: RawResult[BaseModel]) -> Usage:
    return _usage_of(
        model_id,
        input_tokens=raw.input_tokens,
        output_tokens=raw.output_tokens,
        cache_write=raw.cache_write_tokens,
        cache_read=raw.cache_read_tokens,
    )


class Llm:
    def __init__(self, backend: LlmBackend, model_id: str, budget: Budget) -> None:
        self._backend = backend
        self.model_id = model_id
        self.budget = budget

    async def run[T: BaseModel](
        self,
        skill: Skill,
        *,
        context: str,
        user: str,
        output_type: type[T],
        effort: Effort = "low",
        max_tokens: int = 4000,
    ) -> LlmResult[T]:
        """スキルを1回実行する。system の並びは「スキル（不変）→ context（プロファイル等）」。

        失敗時は LlmError（BudgetExceededError を含む）を出す。形式の不正は1回だけやり直す。
        """
        system = [skill.text, context] if context else [skill.text]
        total = Usage(self.model_id, 0, 0, 0, 0.0)
        for attempt in (1, 2):
            estimate = estimate_usd(
                self.model_id,
                input_chars=sum(len(s) for s in system) + len(user),
                max_output_tokens=max_tokens,
            )
            self.budget.reserve(estimate)
            try:
                raw = await self._backend.parse(
                    model=self.model_id,
                    system=system,
                    user=user,
                    output_type=output_type,
                    effort=effort,
                    max_tokens=max_tokens,
                )
            except LlmFormatError:
                self.budget.settle(estimate, 0.0)
                if attempt == 2:
                    raise
                continue
            except BaseException:
                self.budget.settle(estimate, 0.0)
                raise
            usage = _usage(self.model_id, raw)
            self.budget.settle(estimate, usage.cost_usd)
            total = Usage(
                self.model_id,
                total.input_tokens + usage.input_tokens,
                total.output_tokens + usage.output_tokens,
                total.cache_read_tokens + usage.cache_read_tokens,
                total.cost_usd + usage.cost_usd,
            )
            return LlmResult(parsed=raw.parsed, usage=total, skill_version=skill.version)
        raise AssertionError("unreachable")

    async def converse(
        self,
        skill: Skill,
        *,
        context: str,
        messages: list[dict[str, Any]],
        tools: list[ToolSpec],
        allow_tools: bool = True,
        effort: Effort = "medium",
        max_tokens: int = 4000,
    ) -> tuple[RawTurn, Usage]:
        """ツールを使える呼び出しを1回行う（予算の予約・精算つき）。やり直しはしない。

        system の並びは「スキル（不変）→ context（記事など）」。失敗時は LlmError を出す。
        """
        system = [skill.text, context] if context else [skill.text]
        chars = (
            sum(len(s) for s in system)
            + len(json.dumps(messages, default=str, ensure_ascii=False))
            + len(json.dumps([t.input_schema for t in tools], ensure_ascii=False))
        )
        estimate = estimate_usd(self.model_id, input_chars=chars, max_output_tokens=max_tokens)
        self.budget.reserve(estimate)
        try:
            turn = await self._backend.converse(
                model=self.model_id,
                system=system,
                messages=messages,
                tools=tools,
                allow_tools=allow_tools,
                effort=effort,
                max_tokens=max_tokens,
            )
        except BaseException:
            self.budget.settle(estimate, 0.0)
            raise
        usage = _usage_of(
            self.model_id,
            input_tokens=turn.input_tokens,
            output_tokens=turn.output_tokens,
            cache_write=turn.cache_write_tokens,
            cache_read=turn.cache_read_tokens,
        )
        self.budget.settle(estimate, usage.cost_usd)
        return turn, usage
