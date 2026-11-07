from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import Session, col, select

from app.models import Article, ArticleText, Run, RunIssue, Source
from app.services.collect.browser import BrowserUnavailableError
from app.services.collect.collectors import Candidate, SourceResult
from app.services.collect.pipeline import (
    MAX_FETCH_ATTEMPTS,
    FetchReport,
    compile_keywords,
    fetch_pending,
    filter_candidates,
    register_candidates,
)
from app.services.collect.run import CollectSummary, run_collection
from app.services.collect.source_config import (
    SourceConfig,
    SourcesFile,
    is_excluded_title,
    sync_sources,
)
from tests.helpers import (
    EN_SENTENCES,
    JA_SENTENCES,
    FakeWeb,
    article_html,
    make_fetcher,
    public_resolver,
)

NOW = datetime(2026, 11, 7, 3, 0, tzinfo=UTC)
SINCE = NOW - timedelta(days=3)
ROBOTS = "User-agent: *\nAllow: /\n"
LONG_SUMMARY = "A summary that is long enough to be used instead of the full text. " * 3
KEYWORDS = ["AI", "LLM", "生成AI"]


def cfg(key: str, kind: str = "media", **extra: object) -> SourceConfig:
    data: dict[str, object] = {
        "key": key,
        "name": key.upper(),
        "kind": kind,
        "fetch": "rss",
        "url": f"https://{key}.example.com/feed",
    }
    data.update(extra)
    return SourceConfig.model_validate(data)


def cand(
    url: str,
    source: str = "a",
    *,
    title: str = "AI news",
    published_at: datetime = NOW - timedelta(hours=5),
    undated: bool = False,
    date_is_reliable: bool = True,
    summary: str = "",
    image_url: str | None = None,
    is_paper: bool = False,
    arxiv_id: str | None = None,
) -> Candidate:
    return Candidate(
        url=url,
        source_key=source,
        title=title,
        published_at=None if undated else published_at,
        date_is_reliable=date_is_reliable,
        summary=summary,
        image_url=image_url,
        is_paper=is_paper,
        arxiv_id=arxiv_id,
    )


# --- 絞り込み -----------------------------------------------------------------


def test_keyword_matching_uses_word_boundaries_for_short_ascii_words() -> None:
    pattern = compile_keywords(KEYWORDS)
    assert pattern.search("A new AI model") and pattern.search("今日の生成AIニュース")
    assert pattern.search("Using an LLM in production")
    assert not pattern.search("He said it was fine")  # "said" の中の "ai" は数えない
    assert not pattern.search("Sustainability report")
    assert pattern.search("The (AI) boom")


def test_filter_drops_old_foreign_non_ai_seen_and_duplicate(session: Session) -> None:
    session.add(
        Article(
            url="https://a.example.com/seen",
            url_normalized="https://a.example.com/seen",
            published_at=NOW,
        )
    )
    session.commit()
    results = [
        SourceResult(
            cfg("a", ai_filter=True),
            [
                cand("https://a.example.com/ok"),
                cand("https://a.example.com/ok?utm_source=x"),  # 同じ記事（正規化すると重複）
                cand("https://a.example.com/seen"),
                cand("https://a.example.com/old", published_at=NOW - timedelta(days=9)),
                cand("https://a.example.com/not-ai", title="Cooking pasta", summary="Boil water."),
                cand(
                    "https://a.example.com/de",
                    title="Neue Modelle für Entwickler und Teams im AI Bereich heute",
                    summary="Das ist ein deutscher Text über neue Modelle und ihre Möglichkeiten. "
                    * 6,
                ),
                cand("https://a.example.com/undated", undated=True),
            ],
        )
    ]
    outcome = filter_candidates(
        session, results, since=SINCE, max_candidates=80, keywords=KEYWORDS
    )
    assert [c.url for c in outcome.kept] == [
        "https://a.example.com/ok",
        "https://a.example.com/undated",
    ]
    assert dict(outcome.dropped["a"]) == {
        "duplicate": 1,
        "already_seen": 1,
        "old": 1,
        "not_ai": 1,
        "language": 1,
    }


def test_filter_keeps_official_first_then_newest_when_capping(session: Session) -> None:
    def day(n: int) -> datetime:
        return NOW - timedelta(days=n)

    results = [
        SourceResult(
            cfg("media", kind="media"),
            [
                cand("https://m.example.com/new", "media", published_at=day(0)),
                cand("https://m.example.com/mid", "media", published_at=day(1)),
            ],
        ),
        SourceResult(
            cfg("lab", kind="official"),
            [
                cand("https://l.example.com/old", "lab", published_at=day(2)),
                cand("https://l.example.com/new", "lab", published_at=day(1)),
            ],
        ),
    ]
    outcome = filter_candidates(session, results, since=SINCE, max_candidates=3, keywords=KEYWORDS)
    assert [c.url for c in outcome.kept] == [
        "https://l.example.com/new",
        "https://l.example.com/old",
        "https://m.example.com/new",
    ]
    assert dict(outcome.dropped["media"]) == {"over_cap": 1}


def test_filter_does_not_drop_when_language_cannot_be_told(session: Session) -> None:
    results = [SourceResult(cfg("a"), [cand("https://a.example.com/x", title="OK", summary="")])]
    outcome = filter_candidates(session, results, since=SINCE, max_candidates=5, keywords=KEYWORDS)
    assert len(outcome.kept) == 1


# --- 登録 ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("title", "excluded"),
    [
        ("Open call for guest investigators in the life sciences", True),
        ("Call for Papers: Agents workshop", True),
        ("We're hiring research engineers", True),
        ("研究者を募集します", True),
        ("Anthropic特集記事一覧", True),
        ("AI関連の一覧表を作る方法と注意点", False),  # 末尾が「一覧」ではない
        ("Introducing a new model with open weights", False),
        ("OpenAI valued at $1.25 trillion", False),
        ("", False),
    ],
)
def test_announcements_and_listing_titles_are_excluded(title: str, excluded: bool) -> None:
    assert is_excluded_title(title) is excluded


def test_filter_drops_excluded_titles(session: Session) -> None:
    results = [
        SourceResult(
            cfg("a"),
            [
                cand("https://a.example.com/ok"),
                cand("https://a.example.com/x", title="公募のお知らせ"),
            ],
        )
    ]
    outcome = filter_candidates(
        session, results, since=SINCE, max_candidates=10, keywords=KEYWORDS
    )
    assert [c.url for c in outcome.kept] == ["https://a.example.com/ok"]


async def test_page_title_is_checked_after_fetch_for_untitled_candidates(
    session: Session,
) -> None:
    """サイトマップ・一覧ページ由来の候補は、取得するまで見出しが分からない。"""
    article = add_article(session, "https://site.example.com/call")
    await run_fetch(
        session, web_for(("call", article_html(title="Open call for guest investigators")))
    )
    session.refresh(article)
    assert article.stage == "skipped" and article.fetch_error == "excluded"


def test_source_without_body_fetch_is_registered_from_the_summary_only(session: Session) -> None:
    config = SourcesFile(sources=[cfg("oa", kind="official", fetch_body=False)])
    sources = sync_sources(session, config)
    kept = [
        cand("https://oa.example.com/long", "oa", summary=LONG_SUMMARY),
        cand("https://oa.example.com/short", "oa", summary="too short"),
    ]
    run = Run(trigger="manual")
    session.add(run)
    session.commit()
    register_candidates(
        session,
        kept,
        sources=sources,
        configs={s.key: s for s in config.sources},
        run_id=run.id or 0,
        now=NOW,
    )
    rows = {a.url: a for a in session.exec(select(Article)).all()}
    long = rows["https://oa.example.com/long"]
    assert (long.stage, long.fetch_status) == ("fetched", "partial")
    text = session.get(ArticleText, long.id)
    assert text is not None and text.body == LONG_SUMMARY
    short = rows["https://oa.example.com/short"]
    assert (short.stage, short.fetch_status) == ("skipped", "failed")  # 再試行しない


def test_register_marks_estimated_dates_and_paper_keys(session: Session) -> None:
    config = SourcesFile(
        sources=[cfg("a", language="ja"), cfg("hf", kind="paper", fetch="hf_papers")]
    )
    sources = sync_sources(session, config)
    kept = [
        cand("https://a.example.com/dated"),
        cand("https://a.example.com/sitemap", date_is_reliable=False),
        cand("https://a.example.com/undated", undated=True, image_url="https://i/x.png"),
        cand("https://arxiv.org/abs/2611.00001", "hf", is_paper=True, arxiv_id="2611.00001"),
    ]
    run = Run(trigger="manual")
    session.add(run)
    session.commit()
    ids = register_candidates(
        session,
        kept,
        sources=sources,
        configs={s.key: s for s in config.sources},
        run_id=run.id or 0,
        now=NOW,
    )
    rows = {a.url: a for a in session.exec(select(Article)).all()}
    assert len(ids) == 4
    assert rows["https://a.example.com/dated"].published_estimated is False
    assert rows["https://a.example.com/sitemap"].published_estimated is True
    undated = rows["https://a.example.com/undated"]
    assert undated.published_estimated is True and undated.published_at == NOW
    assert undated.image_url == "https://i/x.png" and undated.language == "ja"
    paper = rows["https://arxiv.org/abs/2611.00001"]
    assert paper.is_paper and paper.link_key == "arxiv:2611.00001"
    assert all(a.stage == "discovered" and a.fetch_status == "none" for a in rows.values())
    assert all(a.domain for a in rows.values())


# --- 本文の取得 ---------------------------------------------------------------


class FakeBrowser:
    def __init__(self, html: str | None = None, error: Exception | None = None) -> None:
        self.html = html
        self.error = error
        self.opened: list[str] = []

    async def render(self, url: str) -> str:
        self.opened.append(url)
        if self.error:
            raise self.error
        assert self.html is not None
        return self.html


def add_article(
    session: Session,
    url: str,
    *,
    domain: str = "site.example.com",
    published_at: datetime = NOW,
    published_estimated: bool = True,
    summary: str = "",
    language: str = "en",
    is_paper: bool = False,
    link_key: str | None = None,
) -> Article:
    run = session.exec(select(Run)).first()
    if run is None:
        run = Run(trigger="manual", started_at=NOW)
        session.add(run)
        session.commit()
    article = Article(
        url=url,
        url_normalized=url,
        domain=domain,
        published_at=published_at,
        published_estimated=published_estimated,
        run_id=run.id,
        stage="discovered",
        summary=summary,
        language=language,
        is_paper=is_paper,
        link_key=link_key,
    )
    session.add(article)
    session.commit()
    session.refresh(article)
    return article


def web_for(*pages: tuple[str, str]) -> FakeWeb:
    web = FakeWeb()
    web.add("https://site.example.com/robots.txt", ROBOTS, content_type="text/plain")
    web.add("https://arxiv.org/robots.txt", ROBOTS, content_type="text/plain")
    for path, html in pages:
        web.add(f"https://site.example.com/{path}", html)
    return web


async def run_fetch(
    session: Session, web: FakeWeb, browser: FakeBrowser | None = None
) -> tuple[Run, FetchReport]:
    run = session.exec(select(Run)).one()
    async with make_fetcher(web) as fetcher:
        report = await fetch_pending(session, fetcher, browser, run=run, now=NOW)
    return run, report


async def test_full_text_is_saved_and_page_date_replaces_the_estimate(session: Session) -> None:
    article = add_article(session, "https://site.example.com/a?utm_source=rss")
    page = article_html("The title", canonical="https://site.example.com/a", date="2026-11-04")
    web = web_for(("a?utm_source=rss", page))
    await run_fetch(session, web)

    session.refresh(article)
    text = session.get(ArticleText, article.id)
    assert article.stage == "fetched" and article.fetch_status == "full"
    assert article.fetch_attempts == 1 and article.fetch_error is None
    assert text is not None and "new model" in text.body and text.length == len(text.body)
    assert article.published_at == datetime(2026, 11, 4, tzinfo=UTC)
    assert article.published_estimated is False
    assert article.title_original == "The title"
    assert article.image_url == "https://img.example.com/hero.png"
    assert article.url_normalized == "https://site.example.com/a"  # 正規の URL に置き換わる
    assert article.language == "en"


async def test_reliable_date_from_the_feed_is_kept(session: Session) -> None:
    article = add_article(
        session,
        "https://site.example.com/a",
        published_at=NOW - timedelta(days=1),
        published_estimated=False,
    )
    await run_fetch(session, web_for(("a", article_html(date="2026-10-01"))))
    session.refresh(article)
    assert article.published_at == NOW - timedelta(days=1)


async def test_japanese_article_is_detected(session: Session) -> None:
    article = add_article(session, "https://site.example.com/j", language="en")
    html = article_html("日本語の記事", sentences=JA_SENTENCES, lang="ja")
    await run_fetch(session, web_for(("j", html)))
    session.refresh(article)
    assert article.language == "ja" and article.stage == "fetched"


async def test_short_page_falls_back_to_the_summary_and_is_marked_partial(
    session: Session,
) -> None:
    article = add_article(session, "https://site.example.com/s", summary=LONG_SUMMARY)
    await run_fetch(session, web_for(("s", "<html><body><div id='root'></div></body></html>")))
    session.refresh(article)
    text = session.get(ArticleText, article.id)
    assert article.fetch_status == "partial" and article.stage == "fetched"
    assert article.fetch_error == "empty_body"
    assert text is not None and text.body == LONG_SUMMARY


async def test_page_gone_with_summary_is_partial_and_without_summary_is_failed(
    session: Session,
) -> None:
    with_summary = add_article(session, "https://site.example.com/gone1", summary=LONG_SUMMARY)
    without = add_article(session, "https://site.example.com/gone2", summary="short")
    await run_fetch(session, web_for())  # どちらも 404
    session.refresh(with_summary)
    session.refresh(without)
    assert (with_summary.fetch_status, with_summary.stage) == ("partial", "fetched")
    assert with_summary.fetch_error is not None and with_summary.fetch_error.startswith("http")
    assert (without.fetch_status, without.stage) == ("failed", "discovered")
    assert without.fetch_attempts == 1 and session.get(ArticleText, without.id) is None


async def test_robots_disallowed_page_uses_the_summary(session: Session) -> None:
    article = add_article(session, "https://site.example.com/private/x", summary=LONG_SUMMARY)
    web = FakeWeb()
    web.add(
        "https://site.example.com/robots.txt",
        "User-agent: *\nDisallow: /private/\n",
        content_type="text/plain",
    )
    web.add("https://site.example.com/private/x", article_html())
    await run_fetch(session, web)
    session.refresh(article)
    assert article.fetch_status == "partial" and (article.fetch_error or "").startswith("robots")
    assert "https://site.example.com/private/x" not in web.calls


async def test_failed_articles_are_retried_until_the_attempt_limit(session: Session) -> None:
    article = add_article(session, "https://site.example.com/flaky", summary="")
    web = web_for()
    web.add("https://site.example.com/flaky", "", status=503, content_type="text/plain")
    for expected in range(1, MAX_FETCH_ATTEMPTS + 1):
        await run_fetch(session, web)
        session.refresh(article)
        assert article.fetch_attempts == expected and article.fetch_status == "failed"
    calls_before = len(web.calls)
    await run_fetch(session, web)  # 上限に達したので、もう取りに行かない
    assert len(web.calls) == calls_before
    # 一時的な不調が直れば、上限の前なら取れる
    other = add_article(session, "https://site.example.com/recovers", summary="")
    web.add("https://site.example.com/recovers", "", status=503, content_type="text/plain")
    await run_fetch(session, web)
    web.add("https://site.example.com/recovers", article_html())
    await run_fetch(session, web)
    session.refresh(other)
    assert other.fetch_status == "full" and other.fetch_attempts == 2


async def test_foreign_language_article_is_skipped(session: Session) -> None:
    german = "Das ist ein langer deutscher Text über neue Modelle für Entwickler und Teams. "
    article = add_article(session, "https://site.example.com/de")
    await run_fetch(session, web_for(("de", article_html(sentences=german * 3))))
    session.refresh(article)
    assert article.stage == "skipped" and article.fetch_error == "language"


async def test_two_urls_with_the_same_canonical_page_keep_only_one(session: Session) -> None:
    first = add_article(session, "https://site.example.com/x1")
    second = add_article(session, "https://site.example.com/x2")
    page = article_html(canonical="https://site.example.com/original")
    await run_fetch(session, web_for(("x1", page), ("x2", page)))
    session.refresh(first)
    session.refresh(second)
    stages = sorted([first.stage, second.stage])
    assert stages == ["fetched", "skipped"]
    skipped = first if first.stage == "skipped" else second
    assert skipped.fetch_error == "duplicate"


async def test_arxiv_links_in_the_page_become_the_link_key(session: Session) -> None:
    article = add_article(session, "https://site.example.com/blog")
    extra = '<p>Read the paper at <a href="https://arxiv.org/abs/2611.12345v2">arXiv</a>.</p>'
    await run_fetch(session, web_for(("blog", article_html(extra_body=extra))))
    session.refresh(article)
    assert article.link_key == "arxiv:2611.12345"


async def test_browser_is_used_only_when_the_plain_fetch_is_empty(session: Session) -> None:
    shell = "<html><head><title>App</title></head><body><div id='root'></div></body></html>"
    needs_browser = add_article(session, "https://site.example.com/spa")
    plain = add_article(session, "https://site.example.com/plain")
    browser = FakeBrowser(html=article_html("Rendered"))
    web = web_for(("spa", shell), ("plain", article_html("Plain")))
    _, report = await run_fetch(session, web, browser)
    session.refresh(needs_browser)
    session.refresh(plain)
    assert browser.opened == ["https://site.example.com/spa"]
    assert needs_browser.fetch_status == "full" and needs_browser.title_original == "Rendered"
    assert plain.fetch_status == "full"
    assert report.browser_used == 1


async def test_unavailable_browser_degrades_to_the_summary(session: Session) -> None:
    shell = "<html><body><div id='root'></div></body></html>"
    article = add_article(session, "https://site.example.com/spa", summary=LONG_SUMMARY)
    browser = FakeBrowser(error=BrowserUnavailableError("ブラウザを起動できません"))
    await run_fetch(session, web_for(("spa", shell)), browser)
    session.refresh(article)
    assert article.fetch_status == "partial"
    assert (article.fetch_error or "").startswith("browser_unavailable")


async def test_paper_uses_arxiv_html_sections(session: Session) -> None:
    filler = "Experiments and related work are described here in detail. " * 30
    html = article_html(
        "Paper title",
        extra_body=(
            "<h2>Abstract</h2><p>" + EN_SENTENCES + "</p>"
            "<h2>1 Introduction</h2><p>" + EN_SENTENCES + "</p>"
            f"<h2>2 Experiments</h2><p>{filler}</p>"
            "<h2>5 Conclusion</h2><p>" + EN_SENTENCES + "</p>"
        ),
        repeat=0,
    )
    article = add_article(
        session,
        "https://arxiv.org/abs/2611.00001",
        domain="arxiv.org",
        is_paper=True,
        link_key="arxiv:2611.00001",
        summary=LONG_SUMMARY,
    )
    web = web_for()
    web.add("https://arxiv.org/html/2611.00001", html)
    await run_fetch(session, web)
    session.refresh(article)
    text = session.get(ArticleText, article.id)
    assert article.fetch_status == "full"
    assert text is not None and "Experiments and related work" not in text.body
    assert "Conclusion" in text.body
    assert "https://arxiv.org/pdf/2611.00001" not in web.calls  # HTML があれば PDF は取らない


async def test_paper_without_html_or_pdf_falls_back_to_the_abstract(session: Session) -> None:
    article = add_article(
        session,
        "https://arxiv.org/abs/2611.00002",
        domain="arxiv.org",
        is_paper=True,
        link_key="arxiv:2611.00002",
        summary=LONG_SUMMARY,
    )
    web = web_for()
    web.add("https://arxiv.org/pdf/2611.00002", b"not a pdf", content_type="application/pdf")
    await run_fetch(session, web)
    session.refresh(article)
    assert article.fetch_status == "partial" and article.stage == "fetched"
    text = session.get(ArticleText, article.id)
    assert text is not None and text.body == LONG_SUMMARY


async def test_each_article_is_saved_as_soon_as_it_finishes(session: Session) -> None:
    articles = [add_article(session, f"https://site.example.com/p{i}") for i in range(3)]
    web = web_for(*[(f"p{i}", article_html(f"Post {i}")) for i in range(3)])
    run, report = await run_fetch(session, web)
    assert report.full == 3
    assert run.heartbeat_at >= NOW  # 生きている印も更新される
    for article in articles:
        session.refresh(article)
        assert article.stage == "fetched"


# --- 全体 ---------------------------------------------------------------------

FEED = """<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>
<item><title>AI agents ship</title><link>https://good.example.com/p/1</link>
<pubDate>Fri, 06 Nov 2026 12:00:00 GMT</pubDate>
<description>About AI agents. {summary}</description></item>
<item><title>Old AI post</title><link>https://good.example.com/p/old</link>
<pubDate>Mon, 01 Sep 2026 12:00:00 GMT</pubDate></item>
<item><title>Gardening tips</title><link>https://good.example.com/p/garden</link>
<pubDate>Fri, 06 Nov 2026 12:00:00 GMT</pubDate><description>Plants.</description></item>
</channel></rss>"""


def end_to_end_web() -> FakeWeb:
    web = FakeWeb()
    for host in ("good", "bad"):
        web.add(f"https://{host}.example.com/robots.txt", ROBOTS, content_type="text/plain")
    web.add(
        "https://good.example.com/feed",
        FEED.format(summary=LONG_SUMMARY),
        content_type="application/rss+xml",
    )
    web.add("https://good.example.com/p/1", article_html("AI agents ship", date="2026-11-06"))
    web.add("https://bad.example.com/feed", "", status=500, content_type="text/plain")
    return web


def end_to_end_config() -> SourcesFile:
    return SourcesFile.model_validate(
        {
            "fetch": {"min_interval_seconds": {"default": 0}},
            "sources": [
                {
                    "key": "good",
                    "name": "Good",
                    "kind": "official",
                    "fetch": "rss",
                    "url": "https://good.example.com/feed",
                    "ai_filter": True,
                },
                {
                    "key": "bad",
                    "name": "Bad",
                    "kind": "media",
                    "fetch": "rss",
                    "url": "https://bad.example.com/feed",
                },
            ],
        }
    )


async def collect(session: Session, web: FakeWeb) -> CollectSummary:
    return await run_collection(
        session,
        end_to_end_config(),
        now=NOW,
        transport=web.transport(),
        resolver=public_resolver,
        use_browser=False,
        use_llm=False,
    )


async def test_end_to_end_run_records_everything(session: Session) -> None:
    web = end_to_end_web()
    summary = await run_collection(
        session,
        end_to_end_config(),
        now=NOW,
        transport=web.transport(),
        resolver=public_resolver,
        use_browser=False,
        use_llm=False,
    )
    assert (summary.discovered, summary.kept, summary.registered) == (3, 1, 1)
    assert summary.fetch.full == 1 and summary.status == "partial"

    run = session.exec(select(Run)).one()
    assert run.status == "partial" and run.new_count == 1 and run.finished_at is not None
    issues = session.exec(select(RunIssue)).all()
    assert [(i.source_name, i.stage) for i in issues] == [("Bad", "候補の取得")]
    assert "500" in issues[0].message
    article = session.exec(select(Article)).one()
    assert article.stage == "fetched" and article.run_id == run.id
    assert article.published_at == datetime(2026, 11, 6, 12, 0, tzinfo=UTC)  # フィードの日付
    assert {s.key for s in session.exec(select(Source)).all()} == {"good", "bad"}


async def test_second_run_does_not_register_the_same_articles_again(session: Session) -> None:
    web = end_to_end_web()
    await collect(session, web)
    again = await collect(session, web)
    assert again.registered == 0
    assert len(session.exec(select(Article)).all()) == 1
    good = next(line for line in again.sources if line.key == "good")
    assert dict(good.dropped) == {"already_seen": 1, "old": 1, "not_ai": 1}


async def test_dry_run_writes_nothing(session: Session) -> None:
    web = end_to_end_web()
    summary = await run_collection(
        session,
        end_to_end_config(),
        now=NOW,
        transport=web.transport(),
        resolver=public_resolver,
        dry_run=True,
        use_llm=False,
    )
    assert summary.run_id is None and summary.kept == 1 and summary.registered == 0
    for model in (Run, Article, Source, RunIssue):
        assert session.exec(select(model)).first() is None
    assert "https://good.example.com/p/1" not in web.calls  # 本文は取りに行かない


async def test_sources_turned_off_in_the_database_are_skipped(session: Session) -> None:
    web = end_to_end_web()
    config = end_to_end_config()
    sync_sources(session, config)
    good = session.exec(select(Source).where(col(Source.key) == "good")).one()
    good.enabled = False
    session.add(good)
    session.commit()
    summary = await run_collection(
        session,
        config,
        now=NOW,
        transport=web.transport(),
        resolver=public_resolver,
        use_browser=False,
        use_llm=False,
    )
    assert {line.key for line in summary.sources} == {"bad"}
    assert not any("good.example.com" in call for call in web.calls)


async def test_only_selected_sources_are_collected(session: Session) -> None:
    web = end_to_end_web()
    summary = await run_collection(
        session,
        end_to_end_config(),
        only_keys={"good"},
        now=NOW,
        transport=web.transport(),
        resolver=public_resolver,
        use_browser=False,
        use_llm=False,
    )
    assert [line.key for line in summary.sources] == ["good"] and summary.status == "succeeded"


@pytest.mark.parametrize("hours", [0, 71])
def test_window_boundaries_are_inclusive(session: Session, hours: int) -> None:
    results = [
        SourceResult(
            cfg("a"), [cand("https://a.example.com/x", published_at=NOW - timedelta(hours=hours))]
        )
    ]
    outcome = filter_candidates(session, results, since=SINCE, max_candidates=5, keywords=KEYWORDS)
    assert len(outcome.kept) == 1
