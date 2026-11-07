from app.schemas.topics import CriterionKey, ScoreBreakdown
from app.services.scoring import (
    DEFAULT_THRESHOLD,
    DEFAULT_WEIGHTS,
    build_breakdown,
    compute_total,
    criterion_label,
    decide_selection,
)

Scores = dict[CriterionKey, int]


def _scores(interest: int, practical: int, freshness: int, trust: int, depth: int) -> Scores:
    return {
        "interest": interest,
        "practical": practical,
        "freshness": freshness,
        "trust": trust,
        "depth": depth,
    }


def _breakdown(scores: Scores) -> ScoreBreakdown:
    return build_breakdown(
        scores, DEFAULT_WEIGHTS, article_type="howto", official=False, reason="テスト"
    )


def test_compute_total_matches_the_agreed_example() -> None:
    # 関心4・実用4・新しさ3・信頼4・深さ3 → 65点（重み 20/25/25/15/15）
    assert compute_total(_scores(4, 4, 3, 4, 3), DEFAULT_WEIGHTS, official=False) == 65


def test_three_is_half_of_the_weight() -> None:
    assert compute_total(_scores(3, 3, 3, 3, 3), DEFAULT_WEIGHTS, official=False) == 50


def test_all_fives_is_100_and_official_adds_five() -> None:
    assert compute_total(_scores(5, 5, 5, 5, 5), DEFAULT_WEIGHTS, official=False) == 100
    assert compute_total(_scores(5, 5, 5, 5, 5), DEFAULT_WEIGHTS, official=True) == 105


def test_label_switches_for_paper_and_announcement() -> None:
    assert criterion_label("practical", "paper") == "実務・事業への示唆の大きさ"
    assert criterion_label("practical", "announcement") == "実務・事業への示唆の大きさ"
    assert criterion_label("practical", "howto") == "実用性（再現性・汎用性）"
    assert criterion_label("trust", "paper") == "信頼性"


def test_selected_needs_interest_three_and_threshold() -> None:
    ok = _breakdown(_scores(4, 4, 4, 4, 4))  # 75点（しきい値は 70）
    assert decide_selection(_breakdown(_scores(4, 4, 3, 4, 3)), DEFAULT_THRESHOLD) == "rejected"
    assert decide_selection(ok, DEFAULT_THRESHOLD) == "selected"
    # 合計は高くても、関心が2以下なら通常の選定に入れない
    low_interest = _breakdown(_scores(2, 5, 4, 5, 5))
    assert low_interest.total >= DEFAULT_THRESHOLD
    assert decide_selection(low_interest, DEFAULT_THRESHOLD) == "rejected"


def test_major_when_freshness_is_five_but_not_selected() -> None:
    major = _breakdown(_scores(1, 1, 5, 3, 1))
    assert decide_selection(major, DEFAULT_THRESHOLD) == "major"


def test_below_threshold_is_rejected() -> None:
    low = _breakdown(_scores(3, 2, 2, 3, 2))
    assert decide_selection(low, DEFAULT_THRESHOLD) == "rejected"


def test_rejection_reason_distinguishes_cap_overflow_from_low_score() -> None:
    from app.services.topics import rejection_reason

    assert "上限" in rejection_reason(90, 5, 60)  # 線を超えたが、件数の上限であふれた
    assert "届きませんでした" in rejection_reason(50, 4, 60)
    assert "関心" in rejection_reason(90, 2, 60)
