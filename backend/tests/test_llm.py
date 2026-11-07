from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.schemas.analysis import GroupOutput, ScoreOutput
from app.services.llm.backend import ModelEntry
from app.services.llm.budget import Budget
from app.services.llm.client import Llm
from app.services.llm.errors import (
    BudgetExceededError,
    LlmFormatError,
    LlmRefusedError,
    LlmUnavailableError,
)
from app.services.llm.models import resolve_haiku
from app.services.llm.pricing import cost_usd, estimate_usd
from app.services.llm.skills import load_skill
from tests.fake_llm import FakeBackend, score_output


def budget(run: float = 0.5, month: float = 10.0, spent: float = 0.0) -> Budget:
    return Budget(run_limit_usd=run, month_limit_usd=month, month_spent_usd=spent)


# --- 料金 ---


def test_cost_uses_haiku_5_5_prices() -> None:
    assert cost_usd("claude-haiku-5-5", input_tokens=1_000_000, output_tokens=0) == pytest.approx(
        0.10
    )
    assert cost_usd("claude-haiku-5-5", input_tokens=0, output_tokens=1_000_000) == pytest.approx(
        0.50
    )


def test_cache_read_is_a_tenth_and_cache_write_is_1_25x() -> None:
    read = cost_usd(
        "claude-haiku-5-5", input_tokens=0, output_tokens=0, cache_read_tokens=1_000_000
    )
    write = cost_usd(
        "claude-haiku-5-5", input_tokens=0, output_tokens=0, cache_write_tokens=1_000_000
    )
    assert read == pytest.approx(0.01)
    assert write == pytest.approx(0.125)


def test_estimate_is_at_least_the_output_cap() -> None:
    assert estimate_usd(
        "claude-haiku-5-5", input_chars=0, max_output_tokens=4000
    ) == pytest.approx(0.002)


# --- 予算 ---


def test_budget_blocks_when_the_run_limit_would_be_exceeded() -> None:
    b = budget(run=0.01)
    b.reserve(0.006)
    with pytest.raises(BudgetExceededError):
        b.reserve(0.006)  # 予約中の分も数える（並列でも超えない）


def test_budget_settle_frees_the_reservation_and_counts_actual_cost() -> None:
    b = budget(run=0.01)
    b.reserve(0.006)
    b.settle(0.006, 0.001)
    b.reserve(0.006)  # 実費 0.001 だけが残るので、また予約できる
    assert b.run_spent == pytest.approx(0.001)


def test_budget_blocks_when_the_month_limit_would_be_exceeded() -> None:
    b = budget(month=10.0, spent=9.999)
    with pytest.raises(BudgetExceededError):
        b.reserve(0.01)


# --- モデルの選択 ---


def entry(model_id: str, day: int, active: bool = True) -> ModelEntry:
    return ModelEntry(model_id, datetime(2026, 10, day, tzinfo=UTC), active)


async def test_picks_the_newest_priced_haiku() -> None:
    backend = FakeBackend(
        lambda *_: score_output(),
        models=[entry("claude-haiku-4-5", 1), entry("claude-haiku-5-5", 5), entry("claude-x", 9)],
    )
    choice = await resolve_haiku(backend, None)
    assert choice.model_id == "claude-haiku-5-5" and choice.note is None


async def test_a_newer_haiku_without_a_price_is_not_used() -> None:
    backend = FakeBackend(
        lambda *_: score_output(),
        models=[entry("claude-haiku-5-5", 5), entry("claude-haiku-6", 9)],
    )
    choice = await resolve_haiku(backend, "claude-haiku-5-5")
    assert choice.model_id == "claude-haiku-5-5"
    assert choice.note and "claude-haiku-6" in choice.note


async def test_falls_back_to_the_previous_model_when_the_list_fails() -> None:
    backend = FakeBackend(lambda *_: score_output(), models=LlmUnavailableError("down"))
    choice = await resolve_haiku(backend, "claude-haiku-5-5")
    assert choice.model_id == "claude-haiku-5-5" and choice.note


async def test_fails_when_nothing_usable_and_no_previous_model() -> None:
    backend = FakeBackend(lambda *_: score_output(), models=LlmUnavailableError("down"))
    with pytest.raises(LlmUnavailableError):
        await resolve_haiku(backend, None)


# --- スキル ---


def test_real_skills_load_with_their_rubric() -> None:
    score = load_skill("score")
    assert "採点基準" in score.text and "name: score" not in score.text
    assert load_skill("group").text and len(score.version) == 12


def test_skill_version_changes_with_content(tmp_path: Path) -> None:
    folder = tmp_path / "demo"
    folder.mkdir()
    (folder / "SKILL.md").write_text("---\nname: demo\n---\n本文", encoding="utf-8")
    first = load_skill("demo", tmp_path)
    (folder / "extra.md").write_text("追加", encoding="utf-8")
    second = load_skill("demo", tmp_path)
    assert first.text == "本文" and second.text == "本文\n\n追加"
    assert first.version != second.version


def test_missing_skill_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_skill("nothing", tmp_path)


# --- 呼び出しの口 ---


async def run_score(llm: Llm) -> ScoreOutput:
    result = await llm.run(
        load_skill("score"), context="プロファイル", user="記事", output_type=ScoreOutput
    )
    return result.parsed


async def test_run_returns_result_and_settles_the_actual_cost() -> None:
    backend = FakeBackend(lambda *_: score_output())
    b = budget()
    llm = Llm(backend, "claude-haiku-5-5", b)
    result = await llm.run(
        load_skill("score"), context="C", user="U", output_type=ScoreOutput, effort="low"
    )
    assert result.usage.cost_usd == pytest.approx(1000 * 0.1e-6 + 200 * 0.5e-6)
    assert b.run_spent == pytest.approx(result.usage.cost_usd)
    call = backend.calls[0]
    assert call.system[1] == "C" and call.user == "U" and call.effort == "low"


async def test_format_error_is_retried_once() -> None:
    answers: list[ScoreOutput | LlmFormatError] = [LlmFormatError("bad"), score_output()]
    backend = FakeBackend(lambda *_: answers.pop(0))
    llm = Llm(backend, "claude-haiku-5-5", budget())
    assert (await run_score(llm)).title_ja == "テストの記事"
    assert len(backend.calls) == 2


async def test_second_format_error_is_raised() -> None:
    backend = FakeBackend(lambda *_: LlmFormatError("bad"))
    llm = Llm(backend, "claude-haiku-5-5", budget())
    with pytest.raises(LlmFormatError):
        await run_score(llm)
    assert len(backend.calls) == 2


async def test_refusal_is_not_retried_and_frees_the_reservation() -> None:
    backend = FakeBackend(lambda *_: LlmRefusedError("no"))
    b = budget(run=0.01)
    llm = Llm(backend, "claude-haiku-5-5", b)
    with pytest.raises(LlmRefusedError):
        await run_score(llm)
    assert len(backend.calls) == 1
    b.reserve(0.006)  # 失敗した呼び出しの予約が残っていない


async def test_no_call_is_made_when_the_budget_is_exhausted() -> None:
    backend = FakeBackend(lambda *_: GroupOutput(joins=[], same_topic_sets=[]))
    llm = Llm(backend, "claude-haiku-5-5", budget(run=0.0001))
    with pytest.raises(BudgetExceededError):
        await llm.run(load_skill("group"), context="", user="U", output_type=GroupOutput)
    assert backend.calls == []
