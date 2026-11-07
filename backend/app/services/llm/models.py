"""使う Haiku の選択。常に最新の Haiku を使い、使えないときは前回のモデルで続ける。"""

from dataclasses import dataclass

from app.services.llm.backend import LlmBackend
from app.services.llm.errors import LlmError, LlmUnavailableError
from app.services.llm.pricing import price_of

HAIKU_PREFIX = "claude-haiku-"


@dataclass(frozen=True)
class ModelChoice:
    model_id: str
    note: str | None = None  # 最新を使えなかった理由（実行履歴に残す）


async def resolve_haiku(backend: LlmBackend, previous: str | None) -> ModelChoice:
    """最新の有効な Haiku を選ぶ。

    料金表にない新しいモデルは費用を計算できないので使わない。
    一覧を取れないときも、前回のモデル（料金表にあるもの）で続ける。
    """
    try:
        entries = await backend.list_models()
    except LlmError as error:
        return _fallback(previous, f"モデル一覧を取得できませんでした（{error}）")
    haikus = sorted(
        (e for e in entries if e.id.startswith(HAIKU_PREFIX) and e.active),
        key=lambda e: e.created_at,
        reverse=True,
    )
    if haikus and price_of(haikus[0].id):
        return ModelChoice(haikus[0].id)
    note = (
        f"最新の Haiku（{haikus[0].id}）は料金表にないため使いませんでした"
        if haikus
        else "有効な Haiku が見つかりませんでした"
    )
    return _fallback(previous, note)


def _fallback(previous: str | None, note: str) -> ModelChoice:
    if previous and price_of(previous):
        return ModelChoice(previous, f"{note}。前回のモデル（{previous}）で続けます")
    raise LlmUnavailableError(f"{note}。前回のモデルも無いため処理できません")
