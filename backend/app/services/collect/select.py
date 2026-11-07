"""選定（採点済みの話題を、選定・重大ニュース・落選に振り分ける）。

しきい値以上（かつ関心が基準以上）を点数の高い順に最大 max_selected 件。
上限からあふれた話題のうち「新しさ・重要度」が5のものは、重大ニュースの候補に回す。
重大ニュースは最大 max_major 件。残りは落選。
"""

from dataclasses import dataclass
from datetime import datetime

from sqlmodel import Session, col, select

from app.models import Run, Score, Topic
from app.schemas.settings import Settings
from app.services.scoring import (
    MAJOR_FRESHNESS,
    OFFICIAL_BONUS,
    build_breakdown,
    compute_total,
    decide_selection,
)


@dataclass
class SelectReport:
    selected: int = 0
    major: int = 0
    rejected: int = 0


def _refresh_total(score: Score) -> None:
    """保存した内訳（5観点・そのときの重み）から、公式加点と合計点を計算し直す。"""
    score.official_bonus = OFFICIAL_BONUS if score.official_bonus > 0 else 0
    score.total = compute_total(
        {
            "interest": score.interest,
            "practical": score.practical,
            "freshness": score.freshness,
            "trust": score.trust,
            "depth": score.depth,
        },
        score.weights,  # type: ignore[arg-type]
        official=score.official_bonus > 0,
    )


def _decide_group(
    rows: list[tuple[Topic, Score]], settings: Settings
) -> tuple[set[int | None], set[int | None]]:
    """1回の更新で採点された話題から、選定と重大ニュースの話題 ID を決める。"""
    decided: dict[str, list[tuple[Topic, Score]]] = {"selected": [], "major": [], "rejected": []}
    for topic, score in rows:
        breakdown = build_breakdown(
            {
                "interest": score.interest,
                "practical": score.practical,
                "freshness": score.freshness,
                "trust": score.trust,
                "depth": score.depth,
            },
            score.weights,  # type: ignore[arg-type]
            article_type=score.article_type,  # type: ignore[arg-type]
            official=score.official_bonus > 0,
            reason=score.reason,
        )
        decided[decide_selection(breakdown, settings.threshold)].append((topic, score))

    def best_first(items: list[tuple[Topic, Score]]) -> list[tuple[Topic, Score]]:
        return sorted(items, key=lambda r: (-r[1].total, -r[1].freshness, r[0].id or 0))

    ranked = best_first(decided["selected"])
    chosen = ranked[: settings.max_selected]
    overflow = ranked[settings.max_selected :]
    major_pool = best_first(
        decided["major"] + [r for r in overflow if r[1].freshness >= MAJOR_FRESHNESS]
    )
    majors = major_pool[: settings.max_major]
    return {t.id for t, _ in chosen}, {t.id for t, _ in majors}


def select_scored(
    session: Session,
    *,
    run: Run | None,
    settings: Settings,
    now: datetime,
    recompute: bool = False,
    dry_run: bool = False,
) -> SelectReport:
    """採点済みで未判定（pending）の話題を振り分ける。

    recompute=True のときは、判定済みの話題も含めてすべてやり直す（重み・しきい値・公式加点・
    件数の上限を変えたとき用。Haiku は使わない）。保存した内訳から合計点も計算し直し、
    すでに選定されていた話題の選定日は変えない。dry_run=True なら、結果だけ返して保存しない。
    """
    stmt = select(Topic, Score).join(Score, col(Score.topic_id) == col(Topic.id))
    if not recompute:
        stmt = stmt.where(col(Topic.selection) == "pending")
    rows = session.exec(stmt).all()
    previous = {t.id: (t.selection, t.selected_at) for t, _ in rows}
    if recompute:
        for _topic, score in rows:
            _refresh_total(score)
            session.add(score)

    # 件数の上限は「1回の更新あたり」。採点した実行ごとに分けて適用する
    by_run: dict[int | None, list[tuple[Topic, Score]]] = {}
    for topic, score in rows:
        by_run.setdefault(score.run_id, []).append((topic, score))
    chosen_ids: set[int | None] = set()
    major_ids: set[int | None] = set()
    for group in by_run.values():
        chosen, majors = _decide_group(group, settings)
        chosen_ids |= chosen
        major_ids |= majors

    report = SelectReport()
    for topic, _score in rows:
        was, was_at = previous[topic.id]
        keep_at = was_at if was in ("selected", "major") and was_at else now
        if topic.id in chosen_ids:
            topic.selection, topic.selected_at = "selected", keep_at
            report.selected += 1
        elif topic.id in major_ids:
            topic.selection, topic.selected_at = "major", keep_at
            report.major += 1
        else:
            topic.selection = "rejected"
            report.rejected += 1
        session.add(topic)
    if run is not None:
        run.selected_count += report.selected + report.major
        session.add(run)
    if dry_run:
        session.rollback()
    else:
        session.commit()
    return report
