"""収集の段階：絞り込み → 登録 → 本文の取得。

記事の「進み具合」（Article.stage）を DB に持つので、途中で止まっても続きから再開できる。
  discovered（登録済み・本文はこれから／失敗は次回再試行）→ fetched（本文あり）→ …
  （採点以降は段階5）
  skipped（言語・重複などで対象外）
並列に動くのは通信だけで、DB への書き込みは、結果を受け取る側（この関数）が1か所で行う。
"""

import asyncio
import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from sqlmodel import Session, col, select

from app.models import Article, ArticleText, Run, RunIssue, Source
from app.services.collect.browser import BrowserUnavailableError, Renderer
from app.services.collect.collectors import Candidate, SourceResult
from app.services.collect.extract import (
    Extracted,
    ExtractError,
    detect_language,
    extract_article,
    extract_pdf_text,
    find_arxiv_ids,
    is_substantial,
    paper_sections,
)
from app.services.collect.fetcher import Fetcher, FetchError
from app.services.collect.source_config import SourceConfig, is_excluded_title
from app.services.collect.urls import normalize_url

MAX_FETCH_ATTEMPTS = 3
_SUMMARY_MIN_CHARS = 100
_IN_CHUNK = 500
# 取れない理由が「ページ側の都合」のときは、概要で採点する（通信の一時的な失敗は、次回やり直す）
_SUMMARY_FALLBACK_KINDS = frozenset({"http", "robots", "content_type", "too_large"})


# --- 絞り込み -----------------------------------------------------------------


@dataclass
class FilterOutcome:
    kept: list[Candidate]
    dropped: dict[str, Counter[str]] = field(default_factory=dict)

    def drop(self, source_key: str, reason: str) -> None:
        self.dropped.setdefault(source_key, Counter())[reason] += 1


def compile_keywords(keywords: Iterable[str]) -> re.Pattern[str]:
    """英字だけで4文字以下の語は、単語として一致したときだけ当てる。

    （"AI" が "said" の中に当たらないようにするため）
    """
    parts = []
    for word in keywords:
        if word.isascii() and len(word) <= 4:
            parts.append(rf"(?<![A-Za-z0-9]){re.escape(word)}(?![A-Za-z0-9])")
        else:
            parts.append(re.escape(word))
    return re.compile("|".join(parts), re.IGNORECASE)


def _existing_urls(session: Session, urls: list[str]) -> set[str]:
    found: set[str] = set()
    for start in range(0, len(urls), _IN_CHUNK):
        chunk = urls[start : start + _IN_CHUNK]
        found.update(
            session.exec(
                select(Article.url_normalized).where(col(Article.url_normalized).in_(chunk))
            )
        )
    return found


def filter_candidates(
    session: Session,
    results: list[SourceResult],
    *,
    since: datetime,
    max_candidates: int,
    keywords: Iterable[str],
) -> FilterOutcome:
    """取得済みの除外・期間・AI 関連語・言語・件数の打ち切り。費用はかからない。"""
    outcome = FilterOutcome(kept=[])
    keyword_pattern = compile_keywords(keywords)
    pool: list[tuple[SourceConfig, Candidate, str]] = []
    batch_seen: set[str] = set()
    ordered = sorted(results, key=lambda r: (r.source.kind != "official", r.source.key))
    for result in ordered:
        for candidate in result.candidates:
            key = result.source.key
            url = normalize_url(candidate.url)
            if url in batch_seen:
                outcome.drop(key, "duplicate")
                continue
            batch_seen.add(url)
            if candidate.published_at is not None and candidate.published_at < since:
                outcome.drop(key, "old")
                continue
            if is_excluded_title(candidate.title):
                outcome.drop(key, "excluded")
                continue
            text = f"{candidate.title} {candidate.summary}"
            if result.source.ai_filter and not keyword_pattern.search(text):
                outcome.drop(key, "not_ai")
                continue
            if detect_language(text) == "other":
                outcome.drop(key, "language")
                continue
            pool.append((result.source, candidate, url))

    existing = _existing_urls(session, [url for _, _, url in pool])
    fresh: list[tuple[SourceConfig, Candidate]] = []
    for source, candidate, url in pool:
        if url in existing:
            outcome.drop(source.key, "already_seen")
        else:
            fresh.append((source, candidate))

    # 打ち切るときは「公式 → 新しい順」で残す
    fresh.sort(
        key=lambda item: (
            item[0].kind != "official",
            -(item[1].published_at.timestamp() if item[1].published_at else 0.0),
        )
    )
    for source, _candidate in fresh[max_candidates:]:
        outcome.drop(source.key, "over_cap")
    outcome.kept = [candidate for _, candidate in fresh[:max_candidates]]
    return outcome


# --- 登録 ---------------------------------------------------------------------


def register_candidates(
    session: Session,
    kept: list[Candidate],
    *,
    sources: dict[str, Source],
    configs: dict[str, SourceConfig],
    run_id: int,
    now: datetime,
) -> list[int]:
    """残った候補を、記事として DB に登録する（本文はこれから取る）。"""
    ids: list[int] = []
    for candidate in kept:
        config = configs[candidate.source_key]
        source = sources[candidate.source_key]
        estimated = candidate.published_at is None or not candidate.date_is_reliable
        article = Article(
            role="representative",
            source_id=source.id,
            domain=(urlsplit(candidate.url).hostname or "").lower(),
            url=candidate.url,
            url_normalized=normalize_url(candidate.url),
            title_original=candidate.title,
            language=config.language,
            published_at=candidate.published_at or now,
            published_estimated=estimated,
            discovered_at=now,
            run_id=run_id,
            image_url=candidate.image_url,
            summary=candidate.summary,
            stage="discovered",
            fetch_status="none",
            link_key=f"arxiv:{candidate.arxiv_id}" if candidate.arxiv_id else None,
            is_paper=candidate.is_paper,
        )
        session.add(article)
        session.flush()
        assert article.id is not None
        ids.append(article.id)
        if not config.fetch_body:
            _register_summary_only(session, article, now)
    session.commit()
    return ids


def _register_summary_only(session: Session, article: Article, now: datetime) -> None:
    """記事ページを取りに行かない情報源。概要を本文の代わりにして、取得済みにする。"""
    if len(article.summary) >= _SUMMARY_MIN_CHARS:
        outcome = FetchOutcome(status="partial", body=article.summary)
        _apply(session, article, outcome, now)
        return
    # 概要が短すぎて採点できない。取りに行く情報源ではないので、再試行の対象にもしない
    article.fetch_status = "failed"
    article.fetch_error = "no_summary"
    article.stage = "skipped"
    session.add(article)


# --- 本文の取得 ---------------------------------------------------------------


@dataclass(frozen=True)
class _Snapshot:
    id: int
    url: str
    summary: str
    is_paper: bool
    arxiv_id: str | None
    published_estimated: bool


@dataclass
class FetchOutcome:
    status: str  # full | partial | failed
    body: str = ""
    title: str = ""
    published_at: datetime | None = None
    image_url: str | None = None
    canonical_url: str | None = None
    arxiv_ids: list[str] = field(default_factory=list)
    used_browser: bool = False
    error: str | None = None


def _is_pdf(content_type: str, url: str) -> bool:
    return "pdf" in content_type.lower() or urlsplit(url).path.lower().endswith(".pdf")


async def _fetch_page(
    fetcher: Fetcher, browser: Renderer | None, snapshot: _Snapshot
) -> FetchOutcome:
    result = await fetcher.get(snapshot.url)
    if _is_pdf(result.content_type, result.url):
        text = extract_pdf_text(result.body)
        extracted = Extracted("", text, None, None, None)
        arxiv_ids = find_arxiv_ids(snapshot.url)
    else:
        extracted = extract_article(result.body, result.url)
        arxiv_ids = find_arxiv_ids(result.text)
    outcome = FetchOutcome(
        status="full",
        body=extracted.text,
        title=extracted.title,
        published_at=extracted.published_at,
        image_url=extracted.image_url,
        canonical_url=extracted.canonical_url or result.url,
        arxiv_ids=arxiv_ids,
    )
    if is_substantial(extracted.text):
        return outcome

    # 本文が空なら、ブラウザ（JavaScript の実行後）で取り直す
    if browser is not None and await fetcher.allowed(snapshot.url):
        try:
            rendered = extract_article(await browser.render(result.url), result.url)
            if is_substantial(rendered.text):
                outcome.body = rendered.text
                outcome.title = rendered.title or outcome.title
                outcome.published_at = rendered.published_at or outcome.published_at
                outcome.image_url = rendered.image_url or outcome.image_url
                outcome.used_browser = True
                return outcome
        except BrowserUnavailableError as error:
            outcome.error = f"browser_unavailable: {error}"
        except Exception as error:  # ブラウザ側の失敗は、概要にフォールバックする
            outcome.error = f"browser_failed: {type(error).__name__}"
    return _fallback_to_summary(outcome, snapshot)


def _fallback_to_summary(outcome: FetchOutcome, snapshot: _Snapshot) -> FetchOutcome:
    """全文が取れなかった。概要が十分あれば「全文未取得」として概要で採点する。"""
    reason = outcome.error or "empty_body"
    if len(snapshot.summary) >= _SUMMARY_MIN_CHARS:
        outcome.status = "partial"
        outcome.body = snapshot.summary
    else:
        outcome.status = "failed"
        outcome.body = ""
    outcome.error = reason
    return outcome


async def _fetch_paper(fetcher: Fetcher, snapshot: _Snapshot) -> FetchOutcome:
    """論文: HTML 版 → PDF → 概要（要旨）の順。採点には要旨・序論・結論を使う。"""
    paper_id = snapshot.arxiv_id
    assert paper_id is not None
    html_error: FetchError | None = None
    try:
        result = await fetcher.get(f"https://arxiv.org/html/{paper_id}")
        extracted = extract_article(result.body, result.url)
        if is_substantial(extracted.text):
            return FetchOutcome(
                status="full",
                body=paper_sections(extracted.text),
                title=extracted.title,
                published_at=extracted.published_at,
                arxiv_ids=[paper_id],
            )
    except FetchError as error:
        html_error = error
    try:
        pdf = await fetcher.get(f"https://arxiv.org/pdf/{paper_id}")
        text = extract_pdf_text(pdf.body)
        if is_substantial(text):
            return FetchOutcome(status="full", body=paper_sections(text), arxiv_ids=[paper_id])
    except FetchError as error:
        html_error = html_error or error
    except ExtractError as error:
        html_error = html_error or FetchError("parse", str(error))
    outcome = FetchOutcome(status="failed", arxiv_ids=[paper_id])
    outcome.error = f"{html_error.kind}: {html_error}" if html_error else "empty_body"
    return _fallback_to_summary(outcome, snapshot)


async def _fetch_one(
    fetcher: Fetcher, browser: Renderer | None, snapshot: _Snapshot
) -> FetchOutcome:
    try:
        if snapshot.is_paper and snapshot.arxiv_id:
            return await _fetch_paper(fetcher, snapshot)
        return await _fetch_page(fetcher, browser, snapshot)
    except FetchError as error:
        outcome = FetchOutcome(status="failed", error=f"{error.kind}: {error}")
        return (
            _fallback_to_summary(outcome, snapshot)
            if error.kind in _SUMMARY_FALLBACK_KINDS
            else outcome
        )
    except ExtractError as error:
        return _fallback_to_summary(
            FetchOutcome(status="failed", error=f"parse: {error}"), snapshot
        )


def _apply(session: Session, article: Article, outcome: FetchOutcome, now: datetime) -> None:
    article.fetch_attempts += 1
    article.fetch_error = outcome.error
    article.fetch_status = outcome.status
    if outcome.status == "failed":
        session.add(article)
        return
    if is_excluded_title(outcome.title) or is_excluded_title(article.title_original):
        article.stage = "skipped"
        article.fetch_error = "excluded"
        session.add(article)
        return

    # 公開日: ページに日付があり、いまの日付が推定なら、ページの日付を使う
    if outcome.published_at and article.published_estimated:
        article.published_at = outcome.published_at
        article.published_estimated = False
    if outcome.image_url and not article.image_url:
        article.image_url = outcome.image_url
    if outcome.title and not article.title_original:
        article.title_original = outcome.title
    if outcome.arxiv_ids and not article.link_key:
        article.link_key = f"arxiv:{outcome.arxiv_ids[0]}"

    language = detect_language(outcome.body)
    if language in ("ja", "en"):
        article.language = language
    if language == "other":
        article.stage = "skipped"
        article.fetch_error = "language"
        session.add(article)
        return

    canonical = normalize_url(outcome.canonical_url) if outcome.canonical_url else None
    if canonical and canonical != article.url_normalized:
        clash = session.exec(
            select(Article.id).where(col(Article.url_normalized) == canonical)
        ).first()
        if clash is not None and clash != article.id:
            article.stage = "skipped"
            article.fetch_error = "duplicate"
            session.add(article)
            return
        article.url_normalized = canonical

    article.stage = "fetched"
    session.add(article)
    existing = session.get(ArticleText, article.id)
    if existing is None:
        assert article.id is not None
        session.add(
            ArticleText(article_id=article.id, body=outcome.body, length=len(outcome.body))
        )
    else:
        existing.body = outcome.body
        existing.length = len(outcome.body)
        session.add(existing)


@dataclass
class FetchReport:
    attempted: int = 0
    full: int = 0
    partial: int = 0
    failed: int = 0
    skipped: int = 0
    browser_used: int = 0


async def fetch_pending(
    session: Session,
    fetcher: Fetcher,
    browser: Renderer | None,
    *,
    run: Run,
    now: datetime,
    only_ids: list[int] | None = None,
) -> FetchReport:
    """本文がまだの記事（新規＋前回までの失敗で試行回数が残っているもの）を、同時に取る。"""
    stmt = select(Article).where(
        col(Article.stage) == "discovered", col(Article.fetch_attempts) < MAX_FETCH_ATTEMPTS
    )
    if only_ids is not None:
        stmt = stmt.where(col(Article.id).in_(only_ids))
    articles = {a.id: a for a in session.exec(stmt.order_by(col(Article.discovered_at))).all()}
    report = FetchReport(attempted=len(articles))

    async def work(article: Article) -> tuple[int, FetchOutcome]:
        assert article.id is not None
        arxiv_id = article.link_key.removeprefix("arxiv:") if article.link_key else None
        snapshot = _Snapshot(
            id=article.id,
            url=article.url,
            summary=article.summary,
            is_paper=article.is_paper,
            arxiv_id=arxiv_id if article.is_paper else None,
            published_estimated=article.published_estimated,
        )
        return article.id, await _fetch_one(fetcher, browser, snapshot)

    tasks = [asyncio.create_task(work(a)) for a in articles.values()]
    for finished in asyncio.as_completed(tasks):
        article_id, outcome = await finished
        article = articles[article_id]
        _apply(session, article, outcome, now)
        if article.stage == "skipped":
            report.skipped += 1
        elif outcome.status == "full":
            report.full += 1
        elif outcome.status == "partial":
            report.partial += 1
        else:
            report.failed += 1
        report.browser_used += int(outcome.used_browser)
        run.heartbeat_at = datetime.now(UTC)
        session.add(run)
        session.commit()  # 1件ごとに保存する（止まっても、ここまでは残る）
    return report


def record_fetch_issues(session: Session, run: Run) -> None:
    """取得の失敗を、情報源ごとにまとめて実行履歴の「問題」に残す。"""
    rows = session.exec(
        select(Article, Source)
        .join(Source, col(Source.id) == col(Article.source_id), isouter=True)
        .where(col(Article.run_id) == run.id, col(Article.fetch_status) == "failed")
    ).all()
    by_source: dict[str, list[Article]] = {}
    for article, source in rows:
        by_source.setdefault(source.name if source else article.domain, []).append(article)
    assert run.id is not None
    for name, articles in by_source.items():
        reasons = Counter((a.fetch_error or "unknown").split(":")[0] for a in articles)
        detail = "、".join(f"{reason} {count}件" for reason, count in reasons.most_common(3))
        session.add(
            RunIssue(
                run_id=run.id,
                source_name=name,
                stage="本文の取得",
                message=f"{len(articles)}件の本文を取得できませんでした（{detail}）。次回の更新で再試行します",
            )
        )
    session.commit()


def window_start(now: datetime, days: int) -> datetime:
    return now - timedelta(days=days)
