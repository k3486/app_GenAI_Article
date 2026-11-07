"""Anthropic の料金表（100万トークンあたりの米ドル）。費用の上限の判定と記録に使う。

料金表にないモデルは費用を計算できないので、使わない（models.py が前回のモデルで続ける）。
Haiku 5.5 の料金は、プロンプトが 10万トークン以下のとき。このアプリのプロンプトは最大でも
約 2 万字の本文なので、この範囲に収まる。
"""

from dataclasses import dataclass

CACHE_WRITE_MULTIPLIER = 1.25  # 5 分キャッシュの書き込み
CACHE_READ_MULTIPLIER = 0.10


@dataclass(frozen=True)
class Price:
    input_per_mtok: float
    output_per_mtok: float


PRICES: dict[str, Price] = {
    "claude-haiku-5-5": Price(input_per_mtok=0.10, output_per_mtok=0.50),
}


def price_of(model_id: str) -> Price | None:
    return PRICES.get(model_id)


def cost_usd(
    model_id: str,
    *,
    input_tokens: int,
    output_tokens: int,
    cache_write_tokens: int = 0,
    cache_read_tokens: int = 0,
) -> float:
    """実費。input_tokens はキャッシュに関係しない入力（API の usage.input_tokens）。"""
    price = PRICES[model_id]
    per_input = price.input_per_mtok / 1_000_000
    return (
        input_tokens * per_input
        + cache_write_tokens * per_input * CACHE_WRITE_MULTIPLIER
        + cache_read_tokens * per_input * CACHE_READ_MULTIPLIER
        + output_tokens * price.output_per_mtok / 1_000_000
    )


def estimate_usd(model_id: str, *, input_chars: int, max_output_tokens: int) -> float:
    """呼ぶ前の見込み（多めに見る）。1 文字 = 1 トークンとして数え、出力は上限いっぱい。"""
    return cost_usd(
        model_id,
        input_tokens=input_chars,
        output_tokens=max_output_tokens,
    )
