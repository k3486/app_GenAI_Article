"""ツールを使う Haiku の往復（壁打ち用）。

Haiku が読み取り専用のツールを自分で呼び、結果を見て答えるまでを繰り返す。
呼び出しのたびに費用を予約・精算する（`Llm.converse`）ので、上限を超えるときは止まる。
ツールの回数には上限があり、使い切ったら、ツールなしで回答だけを出させる。
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.services.llm.backend import Effort, ToolSpec
from app.services.llm.client import Llm, Usage
from app.services.llm.errors import BudgetExceededError, LlmFormatError
from app.services.llm.skills import Skill

MAX_TOOL_CALLS = 6  # 1回の回答でツールを呼べる回数（設計で決定）
MAX_TOOL_RESULT_CHARS = 20_000
LIMITED_TEXT = (
    "費用の上限に達したため、回答できませんでした。上限を確認して、もう一度お試しください。"
)


class ToolError(Exception):
    """ツールの実行に失敗した（理由は Haiku にそのまま伝える）。"""


@dataclass(frozen=True)
class Tool:
    spec: ToolSpec
    run: Callable[[dict[str, Any]], str]  # 読み取り専用。失敗は ToolError


@dataclass
class AgentResult:
    text: str
    usage: Usage
    tool_log: list[dict[str, Any]] = field(default_factory=list)  # 使ったツールの名前と引数
    limited: bool = False  # 費用の上限で回答できなかった


def _add(a: Usage, b: Usage) -> Usage:
    return Usage(
        a.model_id,
        a.input_tokens + b.input_tokens,
        a.output_tokens + b.output_tokens,
        a.cache_read_tokens + b.cache_read_tokens,
        a.cost_usd + b.cost_usd,
    )


def _execute(tool: Tool | None, arguments: dict[str, Any]) -> tuple[str, bool]:
    """ツールを1回実行する。戻り値は（結果の文章, 失敗したか）。"""
    if tool is None:
        return "そのツールはありません", True
    try:
        return tool.run(arguments)[:MAX_TOOL_RESULT_CHARS], False
    except ToolError as error:
        return str(error), True


async def run_agent(
    llm: Llm,
    skill: Skill,
    *,
    context: str,
    history: list[dict[str, Any]],
    tools: list[Tool],
    max_tool_calls: int = MAX_TOOL_CALLS,
    max_tokens: int = 4000,
    effort: Effort = "medium",
) -> AgentResult:
    """history（文章だけの user / assistant の並び）に続けて、1回分の回答を作る。"""
    messages = [dict(m) for m in history]
    by_name = {t.spec.name: t for t in tools}
    specs = [t.spec for t in tools]
    total = Usage(llm.model_id, 0, 0, 0, 0.0)
    log: list[dict[str, Any]] = []
    used = 0
    while True:
        try:
            turn, usage = await llm.converse(
                skill,
                context=context,
                messages=messages,
                tools=specs,
                allow_tools=used < max_tool_calls,
                effort=effort,
                max_tokens=max_tokens,
            )
        except BudgetExceededError:
            return AgentResult(text=LIMITED_TEXT, usage=total, tool_log=log, limited=True)
        total = _add(total, usage)
        if not turn.tool_calls:
            if not turn.text.strip():
                raise LlmFormatError("回答が空でした")
            return AgentResult(text=turn.text.strip(), usage=total, tool_log=log)
        # 考えたブロックを含む呼び出しの結果を、そのまま次へ渡す。ツールの結果は1つにまとめて返す
        messages.append({"role": "assistant", "content": turn.content})
        results: list[dict[str, Any]] = []
        for call in turn.tool_calls:
            if used >= max_tool_calls:
                output, failed = (
                    "ツールの回数の上限に達しました。これまでの情報で答えてください",
                    True,
                )
            else:
                output, failed = _execute(by_name.get(call.name), call.input)
                used += 1
                log.append({"name": call.name, "input": call.input})
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": call.id,
                    "content": output,
                    "is_error": failed,
                }
            )
        messages.append({"role": "user", "content": results})
