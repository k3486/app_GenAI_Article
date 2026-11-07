"""点数の計算と選定の判定（Haiku を呼ばずにできる部分）。

Haiku は 5観点を 1〜5 で評価するだけで、合計点・選定はここで計算する。
重みやしきい値を変えても、保存した内訳から Haiku なしで計算し直せる。
"""

import math
from collections.abc import Mapping

from app.schemas.topics import (
    ArticleType,
    CriterionKey,
    CriterionScore,
    ScoreBreakdown,
    Selection,
)

CRITERIA: tuple[CriterionKey, ...] = ("interest", "practical", "freshness", "trust", "depth")

DEFAULT_WEIGHTS: dict[CriterionKey, int] = {
    "interest": 20,
    "practical": 25,
    "freshness": 25,
    "trust": 15,
    "depth": 15,
}
DEFAULT_THRESHOLD = 70
OFFICIAL_BONUS = 5
# 関心との一致がこの点以下の記事は、通常の選定に入れない
MIN_INTEREST = 3
# 「新しさ・重要度」がこの点なら、関心が低くても重大ニュースの候補にする
MAJOR_FRESHNESS = 5

_LABELS: dict[CriterionKey, str] = {
    "interest": "関心との一致",
    "practical": "実用性（再現性・汎用性）",
    "freshness": "新しさ・重要度",
    "trust": "信頼性",
    "depth": "内容の深さ",
}
# 論文・発表は「実用性」の代わりに「実務や事業への示唆の大きさ」で評価する
_INSIGHT_LABEL = "実務・事業への示唆の大きさ"
_INSIGHT_TYPES: frozenset[ArticleType] = frozenset({"paper", "announcement"})


def criterion_label(key: CriterionKey, article_type: ArticleType) -> str:
    if key == "practical" and article_type in _INSIGHT_TYPES:
        return _INSIGHT_LABEL
    return _LABELS[key]


def compute_total(
    scores: Mapping[CriterionKey, int],
    weights: Mapping[CriterionKey, int],
    *,
    official: bool,
) -> int:
    """各観点を (点数−1)÷4 にして重みを掛けて合計し、公式記事は OFFICIAL_BONUS を足す。"""
    weighted = sum(weights[key] * (scores[key] - 1) / 4 for key in CRITERIA)
    bonus = OFFICIAL_BONUS if official else 0
    return math.floor(weighted + 0.5) + bonus


def build_breakdown(
    scores: Mapping[CriterionKey, int],
    weights: Mapping[CriterionKey, int],
    *,
    article_type: ArticleType,
    official: bool,
    reason: str,
) -> ScoreBreakdown:
    return ScoreBreakdown(
        criteria=[
            CriterionScore(
                key=key,
                label=criterion_label(key, article_type),
                score=scores[key],
                weight=weights[key],
            )
            for key in CRITERIA
        ],
        official_bonus=OFFICIAL_BONUS if official else 0,
        total=compute_total(scores, weights, official=official),
        reason=reason,
    )


def decide_selection(breakdown: ScoreBreakdown, threshold: int) -> Selection:
    """選定・重大ニュース・落選を決める（件数の上限は呼び出し側で適用する）。"""
    by_key = {c.key: c.score for c in breakdown.criteria}
    if by_key["interest"] >= MIN_INTEREST and breakdown.total >= threshold:
        return "selected"
    if by_key["freshness"] >= MAJOR_FRESHNESS:
        return "major"
    return "rejected"
