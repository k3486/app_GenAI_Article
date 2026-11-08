"""ツールを使う Haiku の往復（偽の Haiku を使う）。"""

from typing import Any

import pytest

from app.services.llm.agent import (
    LIMITED_TEXT,
    MAX_TOOL_CALLS,
    Tool,
    ToolError,
    run_agent,
)
from app.services.llm.backend import RawTurn, ToolCall, ToolSpec
from app.services.llm.budget import Budget
from app.services.llm.client import Llm
from app.services.llm.errors import LlmFormatError, LlmUnavailableError
from app.services.llm.skills import Skill
from tests.fake_llm import FakeBackend

SKILL = Skill(name="chat", text="指示文", version="v1")
HISTORY = [{"role": "user", "content": "質問です"}]


def turn(text: str = "", *calls: tuple[str, dict[str, Any]], tokens: int = 1000) -> RawTurn:
    tool_calls = [ToolCall(id=f"t{i}", name=n, input=a) for i, (n, a) in enumerate(calls)]
    content: list[Any] = [{"type": "thinking", "thinking": "", "signature": "sig"}]
    content += [
        {"type": "tool_use", "id": c.id, "name": c.name, "input": c.input} for c in tool_calls
    ]
    if text:
        content.append({"type": "text", "text": text})
    return RawTurn(
        content=content,
        text=text,
        tool_calls=tool_calls,
        input_tokens=tokens,
        output_tokens=100,
        stop_reason="tool_use" if tool_calls else "end_turn",
    )


def make(
    scripted: list[Any], run_limit: float = 0.5
) -> tuple[Llm, FakeBackend, list[dict[str, Any]]]:
    backend = FakeBackend(lambda *_: (_ for _ in ()).throw(AssertionError()), scripted=scripted)
    budget = Budget(run_limit_usd=run_limit, month_limit_usd=10.0, month_spent_usd=0.0)
    return Llm(backend, "claude-haiku-5-5", budget), backend, []


def echo_tool(seen: list[dict[str, Any]]) -> Tool:
    def run(arguments: dict[str, Any]) -> str:
        seen.append(arguments)
        return f"結果: {arguments}"

    spec = ToolSpec("lookup", "調べる", {"type": "object", "properties": {}})
    return Tool(spec, run)


async def test_tool_is_called_and_its_result_goes_back_in_one_user_message() -> None:
    llm, backend, _ = make([turn("", ("lookup", {"q": "a"})), turn("答えです")])
    seen: list[dict[str, Any]] = []
    result = await run_agent(llm, SKILL, context="記事", history=HISTORY, tools=[echo_tool(seen)])
    assert result.text == "答えです" and not result.limited
    assert seen == [{"q": "a"}]
    assert result.tool_log == [{"name": "lookup", "input": {"q": "a"}}]
    second = backend.converse_calls[1]["messages"]
    assert second[1]["role"] == "assistant"
    assert second[1]["content"][0]["type"] == "thinking"  # 考えたブロックをそのまま渡す
    assert second[2]["role"] == "user"
    assert second[2]["content"][0]["type"] == "tool_result"
    assert second[2]["content"][0]["tool_use_id"] == "t0"
    assert second[2]["content"][0]["is_error"] is False
    assert result.usage.cost_usd > 0 and result.usage.input_tokens == 2000  # 2回分を合算


async def test_parallel_tool_calls_return_all_results_in_a_single_user_message() -> None:
    llm, backend, _ = make([turn("", ("lookup", {"q": 1}), ("lookup", {"q": 2})), turn("答え")])
    seen: list[dict[str, Any]] = []
    await run_agent(llm, SKILL, context="", history=HISTORY, tools=[echo_tool(seen)])
    results = backend.converse_calls[1]["messages"][2]["content"]
    assert [r["tool_use_id"] for r in results] == ["t0", "t1"] and len(seen) == 2


async def test_after_the_tool_limit_the_answer_is_forced_without_tools() -> None:
    llm, backend, _ = make(
        [turn("", ("lookup", {"q": 1})), turn("", ("lookup", {"q": 2})), turn("最終回答")]
    )
    seen: list[dict[str, Any]] = []
    result = await run_agent(
        llm, SKILL, context="", history=HISTORY, tools=[echo_tool(seen)], max_tool_calls=2
    )
    assert result.text == "最終回答" and len(seen) == 2
    assert [c["allow_tools"] for c in backend.converse_calls] == [True, True, False]


async def test_default_limit_is_six_tool_calls() -> None:
    assert MAX_TOOL_CALLS == 6
    scripted = [turn("", ("lookup", {"q": i})) for i in range(6)] + [turn("おわり")]
    llm, backend, _ = make(scripted)
    seen: list[dict[str, Any]] = []
    result = await run_agent(llm, SKILL, context="", history=HISTORY, tools=[echo_tool(seen)])
    assert result.text == "おわり" and len(seen) == 6
    assert backend.converse_calls[-1]["allow_tools"] is False


async def test_extra_calls_in_one_turn_beyond_the_limit_are_refused_not_run() -> None:
    llm, backend, _ = make(
        [turn("", ("lookup", {"q": 1}), ("lookup", {"q": 2}), ("lookup", {"q": 3})), turn("答え")]
    )
    seen: list[dict[str, Any]] = []
    await run_agent(
        llm, SKILL, context="", history=HISTORY, tools=[echo_tool(seen)], max_tool_calls=2
    )
    results = backend.converse_calls[1]["messages"][2]["content"]
    assert len(seen) == 2
    assert [r["is_error"] for r in results] == [False, False, True]


async def test_unknown_tool_and_tool_error_become_error_results() -> None:
    def broken(_: dict[str, Any]) -> str:
        raise ToolError("話題がありません")

    spec = ToolSpec("broken", "壊れている", {"type": "object", "properties": {}})
    llm, backend, _ = make([turn("", ("nothing", {}), ("broken", {})), turn("答え")])
    result = await run_agent(llm, SKILL, context="", history=HISTORY, tools=[Tool(spec, broken)])
    results = backend.converse_calls[1]["messages"][2]["content"]
    assert [r["is_error"] for r in results] == [True, True]
    assert "話題がありません" in results[1]["content"]
    assert result.text == "答え"


async def test_tool_result_is_cut_to_the_size_limit() -> None:
    spec = ToolSpec("big", "大きい", {"type": "object", "properties": {}})
    llm, backend, _ = make([turn("", ("big", {})), turn("答え")])
    await run_agent(
        llm, SKILL, context="", history=HISTORY, tools=[Tool(spec, lambda _: "あ" * 50_000)]
    )
    assert len(backend.converse_calls[1]["messages"][2]["content"][0]["content"]) == 20_000


async def test_budget_limit_returns_a_limited_result_without_calling_haiku() -> None:
    llm, backend, _ = make([turn("答え")], run_limit=0.0000001)
    result = await run_agent(llm, SKILL, context="記事", history=HISTORY, tools=[])
    assert result.limited and result.text == LIMITED_TEXT
    assert backend.converse_calls == []


async def test_budget_is_settled_with_the_actual_cost_and_released_on_failure() -> None:
    llm, _, _ = make([turn("答え", tokens=2000)])
    await run_agent(llm, SKILL, context="", history=HISTORY, tools=[])
    assert llm.budget.run_spent == pytest.approx(2000 * 0.10 / 1e6 + 100 * 0.50 / 1e6)
    failing, _, _ = make([LlmUnavailableError("落ちた")])
    with pytest.raises(LlmUnavailableError):
        await run_agent(failing, SKILL, context="", history=HISTORY, tools=[])
    assert failing.budget.run_spent == 0.0  # 失敗したときは予約を外す（実費は 0）


async def test_empty_answer_is_an_error() -> None:
    llm, _, _ = make([turn("")])
    with pytest.raises(LlmFormatError):
        await run_agent(llm, SKILL, context="", history=HISTORY, tools=[])


async def test_system_order_is_skill_then_context() -> None:
    llm, backend, _ = make([turn("答え")])
    await run_agent(llm, SKILL, context="記事の文脈", history=HISTORY, tools=[])
    assert backend.converse_calls[0]["system"] == ["指示文", "記事の文脈"]
