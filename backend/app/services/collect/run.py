"""収集の実行（候補を集める → 絞る → 登録 → 本文を取る）。段階 5・6 で、採点以降をここにつなぐ。"""

from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime

import httpx2
from sqlalchemy import func
from sqlmodel import Session, col, select

from app.models import Article, ArticleText, Run, RunIssue, Source
from app.services.app_settings import load_settings
from app.services.collect.browser import BrowserFetcher, Renderer
from app.services.collect.collectors import Candidate, SourceResult, discover
from app.services.collect.fetcher import Fetcher
from app.services.collect.pipeline import (
    FetchReport,
    fetch_pending,
    filter_candidates,
    record_fetch_issues,
    register_candidates,
    window_start,
)
from app.services.collect.source_config import (
    SourcesFile,
    load_ai_keywords,
    sync_sources,
)
from app.services.collect.urls import Resolver, resolve_host


@dataclass
class SourceLine:
    key: str
    name: str
    candidates: int
    kept: int
    dropped: Counter[str] = field(default_factory=Counter)
    error: str | None = None


@dataclass
class CollectSummary:
    run_id: int | None
    sources: list[SourceLine]
    discovered: int
    kept: int
    registered: int
    fetch: FetchReport
    status: str


async def run_collection(
    session: Session,
    config: SourcesFile,
    *,
    only_keys: set[str] | None = None,
    since_days: int = 3,
    max_candidates: int | None = None,
    use_browser: bool = True,
    dry_run: bool = False,
    now: datetime | None = None,
    transport: httpx2.AsyncBaseTransport | None = None,
    resolver: Resolver = resolve_host,
    browser: Renderer | None = None,
) -> CollectSummary:
    now = now or datetime.now(UTC)
    since = window_start(now, since_days)
    chosen = [s for s in config.sources if only_keys is None or s.key in only_keys]
    limit = max_candidates or load_settings(session).max_candidates

    db_sources = {} if dry_run else sync_sources(session, config)
    if db_sources:
        chosen = [s for s in chosen if db_sources[s.key].enabled]
    run: Run | None = None
    if not dry_run:
        run = Run(trigger="manual", started_at=now, heartbeat_at=now)
        session.add(run)
        session.commit()
        session.refresh(run)

    owned = browser is None and use_browser and not dry_run
    renderer: Renderer | None = browser
    own_browser = BrowserFetcher() if owned else None
    if own_browser is not None:
        renderer = own_browser
    try:
        async with Fetcher(
            transport=transport,
            resolver=resolver,
            min_interval=config.fetch.min_interval_seconds,
        ) as fetcher:
            results = await discover(fetcher, chosen, since=since, now=now)
            if run is not None:
                _record_source_errors(session, run, results)
            outcome = filter_candidates(
                session,
                results,
                since=since,
                max_candidates=limit,
                keywords=load_ai_keywords(),
            )
            lines = _lines(results, outcome.kept, outcome.dropped)
            registered: list[int] = []
            fetch = FetchReport()
            if run is not None:
                assert run.id is not None
                registered = register_candidates(
                    session,
                    outcome.kept,
                    sources=db_sources,
                    configs={s.key: s for s in config.sources},
                    run_id=run.id,
                    now=now,
                )
                fetch = await fetch_pending(session, fetcher, renderer, run=run, now=now)
                record_fetch_issues(session, run)
    finally:
        if own_browser is not None:
            await own_browser.aclose()

    status = "succeeded"
    if run is not None:
        has_issue = session.exec(
            select(func.count()).select_from(RunIssue).where(col(RunIssue.run_id) == run.id)
        ).one()
        status = "partial" if has_issue else "succeeded"
        run.status = status
        run.new_count = len(registered)
        run.finished_at = datetime.now(UTC)
        run.heartbeat_at = run.finished_at
        session.add(run)
        session.commit()
    return CollectSummary(
        run_id=run.id if run else None,
        sources=lines,
        discovered=sum(len(r.candidates) for r in results),
        kept=len(outcome.kept),
        registered=len(registered),
        fetch=fetch,
        status=status,
    )


def _record_source_errors(session: Session, run: Run, results: list[SourceResult]) -> None:
    assert run.id is not None
    for result in results:
        if result.error:
            session.add(
                RunIssue(
                    run_id=run.id,
                    source_name=result.source.name,
                    stage="候補の取得",
                    message=result.error,
                )
            )
    session.commit()


def _lines(
    results: list[SourceResult], kept: list[Candidate], dropped: dict[str, Counter[str]]
) -> list[SourceLine]:
    kept_by_source = Counter(c.source_key for c in kept)
    return [
        SourceLine(
            key=r.source.key,
            name=r.source.name,
            candidates=len(r.candidates),
            kept=kept_by_source[r.source.key],
            dropped=dropped.get(r.source.key, Counter()),
            error=r.error,
        )
        for r in sorted(results, key=lambda r: r.source.key)
    ]


@dataclass
class FetchStat:
    source: str
    total: int
    full: int
    partial: int
    failed: int
    skipped: int
    avg_chars: int
    reasons: Counter[str]


def fetch_stats(session: Session, run_id: int) -> list[FetchStat]:
    """この実行で登録した記事の、本文の取得結果を情報源ごとに集計する（G2 の確認用）。"""
    rows = session.exec(
        select(Article, Source, ArticleText)
        .join(Source, col(Source.id) == col(Article.source_id), isouter=True)
        .join(ArticleText, col(ArticleText.article_id) == col(Article.id), isouter=True)
        .where(col(Article.run_id) == run_id)
    ).all()
    grouped: dict[str, list[tuple[Article, ArticleText | None]]] = {}
    for article, source, text in rows:
        grouped.setdefault(source.name if source else article.domain, []).append((article, text))
    stats: list[FetchStat] = []
    for name, items in sorted(grouped.items()):
        lengths = [t.length for a, t in items if t is not None and a.fetch_status == "full"]
        stats.append(
            FetchStat(
                source=name,
                total=len(items),
                full=sum(1 for a, _ in items if a.fetch_status == "full" and a.stage != "skipped"),
                partial=sum(1 for a, _ in items if a.fetch_status == "partial"),
                failed=sum(1 for a, _ in items if a.fetch_status == "failed"),
                skipped=sum(1 for a, _ in items if a.stage == "skipped"),
                avg_chars=int(sum(lengths) / len(lengths)) if lengths else 0,
                reasons=Counter(
                    (a.fetch_error or "").split(":")[0] for a, _ in items if a.fetch_error
                ),
            )
        )
    return stats
