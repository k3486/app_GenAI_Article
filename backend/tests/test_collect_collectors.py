import json
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

import pytest

from app.services.collect.collectors import (
    collect_source,
    discover,
    parse_feed,
    parse_hf_daily,
    parse_listing,
    parse_qiita,
    parse_sitemap,
    parse_zenn,
)
from app.services.collect.source_config import SourceConfig, load_sources
from tests.helpers import FakeWeb, make_fetcher

NOW = datetime(2026, 11, 7, 3, 0, tzinfo=UTC)
SINCE = NOW - timedelta(days=3)
ROBOTS = "User-agent: *\nAllow: /\n"

RSS = """<?xml version="1.0"?>
<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/"><channel><title>Blog</title>
<item><title>First &amp; best</title><link>https://example.com/p/1</link>
<pubDate>Thu, 05 Nov 2026 12:00:00 GMT</pubDate>
<description>&lt;p&gt;A &lt;b&gt;short&lt;/b&gt; summary.&lt;/p&gt;</description>
<media:thumbnail url="https://img.example.com/1.png"/></item>
<item><title>No date</title><link>https://example.com/p/2</link></item>
<item><title>No link</title></item>
</channel></rss>"""

ATOM = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>Blog</title>
<entry><title>Atom entry</title><link href="https://example.com/a/1"/>
<updated>2026-11-06T10:00:00+09:00</updated><summary>Summary text</summary></entry></feed>"""

SITEMAP = """<?xml version="1.0"?><urlset>
<url><loc>https://www.example.com/news/alpha</loc><lastmod>2026-11-06T10:22:49.000Z</lastmod></url>
<url><loc>https://www.example.com/news/beta?x=1&amp;y=2</loc></url>
<url><loc>https://www.example.com/about</loc><lastmod>2026-11-01</lastmod></url>
</urlset>"""


def qiita_url(tag: str) -> str:
    query = quote(f"tag:{tag} created:>={SINCE:%Y-%m-%d}")
    return f"https://qiita.com/api/v2/items?page=1&per_page=50&query={query}"


def source(**kwargs: object) -> SourceConfig:
    data: dict[str, object] = {"key": "s", "name": "S", "kind": "media", "fetch": "rss"}
    data.update(kwargs)
    return SourceConfig.model_validate(data)


def test_parse_feed_handles_rss_and_atom() -> None:
    items = parse_feed(RSS.encode(), "s")
    assert [i.url for i in items] == ["https://example.com/p/1", "https://example.com/p/2"]
    first = items[0]
    assert first.title == "First & best"
    assert first.summary == "A short summary."
    assert first.published_at == datetime(2026, 11, 5, 12, 0, tzinfo=UTC)
    assert first.image_url == "https://img.example.com/1.png"
    assert items[1].published_at is None

    atom = parse_feed(ATOM.encode(), "s")[0]
    assert atom.url == "https://example.com/a/1"
    assert atom.published_at == datetime(2026, 11, 6, 1, 0, tzinfo=UTC)  # UTC に直す


def test_parse_feed_survives_garbage() -> None:
    assert parse_feed(b"<html>not a feed</html>", "s") == []
    assert parse_feed(b"", "s") == []


def test_parse_sitemap_filters_by_pattern_and_marks_dates_as_estimates() -> None:
    items = parse_sitemap(SITEMAP, "s", r"^https://www\.example\.com/news/[a-z]+")
    assert [i.url for i in items] == [
        "https://www.example.com/news/alpha",
        "https://www.example.com/news/beta?x=1&y=2",
    ]
    assert items[0].published_at == datetime(2026, 11, 6, 10, 22, 49, tzinfo=UTC)
    assert items[1].published_at is None
    assert all(not i.date_is_reliable for i in items)


def test_parse_listing_resolves_links_and_deduplicates() -> None:
    html = """
    <a href="/blog/one/">One <span>post</span></a>
    <a href="https://ai.example.com/blog/two?utm=1#c">Two</a>
    <a href="/blog/one/">One again</a>
    <a href="/about">About</a>
    <a href="mailto:x@example.com">Mail</a>
    """
    items = parse_listing(
        html, "https://ai.example.com/blog/", "s", r"^https://ai\.example\.com/blog/[a-z]+/?$"
    )
    assert [i.url for i in items] == [
        "https://ai.example.com/blog/one/",
        "https://ai.example.com/blog/two",
    ]
    assert all(i.title == "" for i in items)  # リンク文字は見出しにしない


def test_parse_zenn_qiita_and_hf() -> None:
    zenn = parse_zenn(
        {
            "articles": [
                {
                    "title": "Z",
                    "path": "/u/articles/a",
                    "liked_count": 7,
                    "published_at": "2026-11-06T10:00:00.000+09:00",
                },
                {"title": "no path", "liked_count": 1},
            ]
        },
        "zenn",
    )
    assert len(zenn) == 1
    assert zenn[0].url == "https://zenn.dev/u/articles/a" and zenn[0].likes == 7
    assert zenn[0].published_at == datetime(2026, 11, 6, 1, 0, tzinfo=UTC)

    qiita = parse_qiita(
        [
            {
                "title": "Q",
                "url": "https://qiita.com/u/items/1",
                "likes_count": 3,
                "created_at": "2026-11-06T10:00:00+09:00",
                "body": "# body",
            }
        ],
        "qiita",
    )
    assert qiita[0].likes == 3 and qiita[0].summary == "# body"

    papers = [
        {
            "paper": {
                "id": "2611.00001",
                "title": "Low",
                "upvotes": 1,
                "summary": "abs",
                "publishedAt": "2026-11-05T00:00:00.000Z",
            }
        },
        {
            "paper": {
                "id": "2611.00002",
                "title": "High",
                "upvotes": 50,
                "summary": "abstract text",
                "publishedAt": "2026-11-05T00:00:00.000Z",
            }
        },
        {"paper": {"id": "2611.00003", "title": "Mid", "upvotes": 9}},
    ]
    top = parse_hf_daily(papers, "hf", top=2)
    assert [p.arxiv_id for p in top] == ["2611.00002", "2611.00003"]
    assert top[0].url == "https://arxiv.org/abs/2611.00002"
    assert top[0].is_paper and top[0].likes == 50 and top[0].summary == "abstract text"


async def test_collect_source_rss_over_http() -> None:
    web = FakeWeb()
    web.add("https://example.com/robots.txt", ROBOTS, content_type="text/plain")
    web.add("https://example.com/feed.xml", RSS, content_type="application/rss+xml")
    async with make_fetcher(web) as fetcher:
        result = await collect_source(
            fetcher, source(url="https://example.com/feed.xml"), since=SINCE, now=NOW
        )
    assert result.error is None and len(result.candidates) == 2


async def test_collect_source_reports_failure_instead_of_raising() -> None:
    web = FakeWeb()
    web.add("https://example.com/robots.txt", ROBOTS, content_type="text/plain")
    web.add("https://example.com/feed.xml", "", status=500, content_type="text/plain")
    async with make_fetcher(web) as fetcher:
        result = await collect_source(
            fetcher, source(url="https://example.com/feed.xml"), since=SINCE, now=NOW
        )
    assert result.candidates == [] and result.error_kind == "http"
    assert "500" in (result.error or "")


async def test_collect_source_reports_unexpected_data_shape() -> None:
    web = FakeWeb()
    web.add("https://zenn.dev/robots.txt", ROBOTS, content_type="text/plain")
    web.add(
        "https://zenn.dev/api/articles?topicname=llm&order=latest&count=50",
        json.dumps(["unexpected", "list"]),
        content_type="application/json",
    )
    config = source(key="zenn", fetch="zenn", options={"topics": ["llm"], "top": 5})
    async with make_fetcher(web) as fetcher:
        result = await collect_source(fetcher, config, since=SINCE, now=NOW)
    assert result.candidates == [] and result.error_kind == "parse"


async def test_zenn_returns_most_liked_recent_articles_across_topics() -> None:
    def article(path: str, likes: int, day: str) -> dict[str, object]:
        return {
            "title": path,
            "path": f"/{path}",
            "liked_count": likes,
            "published_at": f"{day}T10:00:00.000+09:00",
        }

    web = FakeWeb()
    web.add("https://zenn.dev/robots.txt", ROBOTS, content_type="text/plain")
    web.add(
        "https://zenn.dev/api/articles?topicname=llm&order=latest&count=50",
        json.dumps(
            {
                "articles": [
                    article("a", 5, "2026-11-06"),
                    article("old", 999, "2026-10-01"),
                    article("shared", 2, "2026-11-06"),
                ]
            }
        ),
        content_type="application/json",
    )
    web.add(
        "https://zenn.dev/api/articles?topicname=claude&order=latest&count=50",
        json.dumps(
            {"articles": [article("b", 9, "2026-11-07"), article("shared", 2, "2026-11-06")]}
        ),
        content_type="application/json",
    )
    config = source(key="zenn", fetch="zenn", options={"topics": ["llm", "claude"], "top": 2})
    async with make_fetcher(web) as fetcher:
        result = await collect_source(fetcher, config, since=SINCE, now=NOW)
    assert [c.url for c in result.candidates] == ["https://zenn.dev/b", "https://zenn.dev/a"]


async def test_qiita_queries_each_tag_and_keeps_the_top() -> None:
    def item(n: int, likes: int, created: str) -> dict[str, object]:
        return {
            "title": f"t{n}",
            "url": f"https://qiita.com/u/items/{n}",
            "likes_count": likes,
            "created_at": created,
            "body": "b",
        }

    web = FakeWeb()
    web.add("https://qiita.com/robots.txt", ROBOTS, content_type="text/plain")
    web.add(
        qiita_url("LLM"),
        json.dumps(
            [item(1, 4, "2026-11-06T10:00:00+09:00"), item(2, 50, "2026-09-01T10:00:00+09:00")]
        ),
        content_type="application/json",
    )
    web.add(
        qiita_url("生成AI"),
        json.dumps([item(3, 8, "2026-11-07T10:00:00+09:00")]),
        content_type="application/json",
    )
    config = source(key="qiita", fetch="qiita", options={"tags": ["LLM", "生成AI"], "top": 5})
    async with make_fetcher(web) as fetcher:
        result = await collect_source(fetcher, config, since=SINCE, now=NOW)
    assert [c.url for c in result.candidates] == [
        "https://qiita.com/u/items/3",
        "https://qiita.com/u/items/1",
    ]


async def test_hf_papers_takes_top_per_day_and_skips_days_without_data() -> None:
    def day(ids: list[tuple[str, int]]) -> str:
        return json.dumps(
            [{"paper": {"id": i, "title": i, "upvotes": u, "summary": "x" * 30}} for i, u in ids]
        )

    web = FakeWeb()
    web.add("https://huggingface.co/robots.txt", ROBOTS, content_type="text/plain")
    web.add(
        "https://huggingface.co/api/daily_papers?date=2026-11-07",
        day([("2611.1", 3), ("2611.2", 30), ("2611.3", 20)]),
        content_type="application/json",
    )
    web.add(
        "https://huggingface.co/api/daily_papers?date=2026-11-06",
        day([("2611.4", 9)]),
        content_type="application/json",
    )
    # 11-05 と 11-04 は 404（その日の分が無い）
    config = source(key="hf", kind="paper", fetch="hf_papers", options={"top": 2})
    async with make_fetcher(web) as fetcher:
        result = await collect_source(fetcher, config, since=SINCE, now=NOW)
    assert result.error is None
    assert [c.arxiv_id for c in result.candidates] == ["2611.2", "2611.3", "2611.4"]


async def test_one_failing_source_does_not_stop_the_others() -> None:
    web = FakeWeb()
    web.add("https://good.example.com/robots.txt", ROBOTS, content_type="text/plain")
    web.add("https://good.example.com/feed", RSS, content_type="application/rss+xml")
    web.add("https://bad.example.com/robots.txt", ROBOTS, content_type="text/plain")
    web.add("https://bad.example.com/feed", "", status=503, content_type="text/plain")
    sources = [
        source(key="good", url="https://good.example.com/feed"),
        source(key="bad", url="https://bad.example.com/feed"),
        source(key="off", url="https://off.example.com/feed", disabled_reason="使えない"),
    ]
    async with make_fetcher(web) as fetcher:
        results = await discover(fetcher, sources, since=SINCE, now=NOW)
    by_key = {r.source.key: r for r in results}
    assert set(by_key) == {"good", "bad"}  # 使えない情報源には問い合わせない
    assert len(by_key["good"].candidates) == 2 and by_key["bad"].error
    assert not any("off.example.com" in call for call in web.calls)


def test_the_real_sources_file_is_valid() -> None:
    config = load_sources()
    keys = [s.key for s in config.sources]
    assert len(keys) == len(set(keys))
    assert {"openai-news", "anthropic-news", "zenn", "qiita", "hf-papers"} <= set(keys)
    assert all(
        s.disabled_reason for s in config.sources if s.key in {"venturebeat-ai", "claude-blog"}
    )
    assert config.fetch.min_interval_seconds["arxiv.org"] >= 3.0
    official = [s for s in config.sources if s.kind == "official"]
    assert len(official) >= 10


def test_invalid_source_definitions_are_rejected() -> None:
    with pytest.raises(ValueError, match="url"):
        source(fetch="rss", url=None)
    with pytest.raises(ValueError, match="pattern"):
        source(fetch="sitemap", url="https://example.com/sitemap.xml")


def test_hf_daily_uses_the_day_it_was_listed_not_the_paper_date() -> None:
    items = [
        {
            "publishedAt": "2026-11-06T19:00:00.000Z",
            "paper": {
                "id": "2611.9",
                "title": "t",
                "upvotes": 3,
                "publishedAt": "2026-10-20T00:00:00.000Z",
            },
        }
    ]
    (paper,) = parse_hf_daily(items, "hf", top=5)
    assert paper.published_at == datetime(2026, 11, 6, 19, 0, tzinfo=UTC)
