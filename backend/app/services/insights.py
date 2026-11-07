"""分析シートの集計（トピックの内訳・話題の推移・バックログ・情報源・効き具合）。"""

from datetime import UTC, date, datetime, timedelta

from sqlmodel import Session, col, select

from app.models import Score, Topic
from app.schemas.insights import (
    BacklogPoint,
    CategoryCount,
    Effectiveness,
    Insights,
    ScoreBin,
    TrendPoint,
)
from app.services.sources import source_stats
from app.services.topics import auto_dismiss

_JST = timedelta(hours=9)
_BACKLOG_DAYS = 14
_BINS = ("60点未満", "60〜69点", "70〜79点", "80点以上")


def _jst_date(moment: datetime) -> date:
    return (moment + _JST).date()


def _bin_label(total: int) -> str:
    if total < 60:
        return _BINS[0]
    if total < 70:
        return _BINS[1]
    if total < 80:
        return _BINS[2]
    return _BINS[3]


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def get_insights(session: Session, now: datetime | None = None) -> Insights:
    now = now or datetime.now(UTC)
    auto_dismiss(session, now)
    rows = session.exec(
        select(Topic, Score)
        .join(Score, col(Score.topic_id) == col(Topic.id))
        .where(col(Topic.selection) != "pending")
    ).all()

    counts: dict[str, int] = {}
    trend: dict[tuple[date, str], int] = {}
    for topic, score in rows:
        counts[score.category] = counts.get(score.category, 0) + 1
        when = topic.selected_at or score.scored_at
        trend[(_jst_date(when), score.category)] = (
            trend.get((_jst_date(when), score.category), 0) + 1
        )

    # バックログの残数: その日の終わりの時点で「選定済みで、まだ読まれていない」記事の数
    selected = [t for t, _ in rows if t.selection != "rejected" and t.selected_at is not None]
    today = _jst_date(now)
    backlog: list[BacklogPoint] = []
    for offset in range(_BACKLOG_DAYS - 1, -1, -1):
        day = today - timedelta(days=offset)
        end = datetime(day.year, day.month, day.day, tzinfo=UTC) + timedelta(days=1) - _JST
        remaining = sum(
            1
            for t in selected
            if t.selected_at is not None
            and t.selected_at < end
            and (t.read_at is None or t.read_at >= end)
        )
        backlog.append(BacklogPoint(date=day, count=remaining))

    chosen = [(t, s) for t, s in rows if t.selection != "rejected"]
    rejected = [t for t, _ in rows if t.selection == "rejected"]
    rated = [(t, s) for t, s in chosen if t.rating is not None]
    bins: list[ScoreBin] = []
    for label in _BINS:
        in_bin = [(t, s) for t, s in chosen if _bin_label(s.total) == label]
        bin_rated = [t for t, _ in in_bin if t.rating is not None]
        bins.append(
            ScoreBin(
                label=label,
                topics=len(in_bin),
                like_rate=_rate(sum(1 for t in bin_rated if t.rating == "like"), len(bin_rated)),
            )
        )

    stats = sorted(source_stats(session).values(), key=lambda s: s.source_name)
    return Insights(
        categories=[
            CategoryCount.model_validate({"category": category, "count": count})
            for category, count in sorted(counts.items(), key=lambda item: -item[1])
        ],
        trend=[
            TrendPoint.model_validate({"date": d, "category": category, "count": n})
            for (d, category), n in sorted(trend.items())
        ],
        backlog=backlog,
        sources=stats,
        effectiveness=Effectiveness(
            selected_like_rate=_rate(sum(1 for t, _ in rated if t.rating == "like"), len(rated)),
            rejected_missed_rate=_rate(sum(1 for t in rejected if t.missed), len(rejected)),
            score_bins=bins,
        ),
    )
