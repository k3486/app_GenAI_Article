"""候補の記事を集める（RSS・サイトマップ・一覧ページ・Zenn・Qiita・HF Daily Papers）。

ここで取るのは URL・題名・日付・概要だけ。本文は、絞り込みのあとの段階で取る。
"""

import asyncio
import html as html_lib
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote, urljoin, urlsplit, urlunsplit

import feedparser

from app.services.collect.extract import clean_summary
from app.services.collect.fetcher import Fetcher, FetchError
from app.services.collect.source_config import SourceConfig


@dataclass(frozen=True)
class Candidate:
    url: str
    source_key: str
    title: str = ""
    published_at: datetime | None = None
    # サイトマップの更新日のように、公開日そのものではないとき False（ページの日付を優先する）
    date_is_reliable: bool = True
    summary: str = ""
    image_url: str | None = None
    likes: int | None = None
    is_paper: bool = False
    arxiv_id: str | None = None


@dataclass
class SourceResult:
    source: SourceConfig
    candidates: list[Candidate]
    error: str | None = None
    error_kind: str | None = None


_SITEMAP_URL = re.compile(r"<url>\s*<loc>([^<]+)</loc>(?:\s*<lastmod>([^<]+)</lastmod>)?", re.S)
_ANCHOR = re.compile(r'<a\s[^>]*?href="([^"]+)"[^>]*>(.*?)</a>', re.S | re.I)
_IMAGE_TYPES = ("image/",)


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return _utc(datetime.fromisoformat(value.strip().replace("Z", "+00:00")))
    except ValueError:
        return None


def _from_struct_time(stamp: Any) -> datetime:
    year, month, day, hour, minute, second = stamp[:6]
    return datetime(year, month, day, hour, minute, second, tzinfo=UTC)


def parse_feed(content: bytes, source_key: str) -> list[Candidate]:
    candidates: list[Candidate] = []
    for entry in feedparser.parse(content).entries:
        link = str(entry.get("link") or "").strip()
        if not link:
            continue
        stamp = entry.get("published_parsed") or entry.get("updated_parsed")
        published = _from_struct_time(stamp) if stamp else None
        image: str | None = None
        for key in ("media_thumbnail", "media_content"):
            items = entry.get(key) or []
            if items and items[0].get("url"):
                image = str(items[0]["url"])
                break
        if image is None:
            for enclosure in entry.get("enclosures") or []:
                if str(enclosure.get("type", "")).startswith(_IMAGE_TYPES) and enclosure.get(
                    "href"
                ):
                    image = str(enclosure["href"])
                    break
        candidates.append(
            Candidate(
                url=link,
                source_key=source_key,
                title=clean_summary(str(entry.get("title") or ""), limit=300),
                published_at=published,
                summary=clean_summary(str(entry.get("summary") or entry.get("description") or "")),
                image_url=image,
            )
        )
    return candidates


def parse_sitemap(text: str, source_key: str, pattern: str) -> list[Candidate]:
    regex = re.compile(pattern)
    found: list[Candidate] = []
    for loc, lastmod in _SITEMAP_URL.findall(text):
        url = html_lib.unescape(loc.strip())
        if regex.search(url):
            found.append(
                Candidate(
                    url=url,
                    source_key=source_key,
                    published_at=_parse_iso(lastmod),
                    date_is_reliable=False,
                )
            )
    return found


def parse_listing(html: str, base_url: str, source_key: str, pattern: str) -> list[Candidate]:
    regex = re.compile(pattern)
    seen: dict[str, Candidate] = {}
    for href, inner in _ANCHOR.findall(html):
        absolute = urljoin(base_url, html_lib.unescape(href).strip())
        parts = urlsplit(absolute)
        url = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
        if regex.search(url) and url not in seen:
            seen[url] = Candidate(
                url=url, source_key=source_key, title=clean_summary(inner, limit=200)
            )
    return list(seen.values())


def parse_zenn(data: dict[str, Any], source_key: str) -> list[Candidate]:
    return [
        Candidate(
            url=f"https://zenn.dev{article['path']}",
            source_key=source_key,
            title=str(article.get("title", "")),
            published_at=_parse_iso(article.get("published_at")),
            likes=int(article.get("liked_count") or 0),
        )
        for article in data.get("articles", [])
        if article.get("path")
    ]


def parse_qiita(data: list[dict[str, Any]], source_key: str) -> list[Candidate]:
    return [
        Candidate(
            url=str(item["url"]),
            source_key=source_key,
            title=str(item.get("title", "")),
            published_at=_parse_iso(item.get("created_at")),
            summary=clean_summary(str(item.get("body", "")), limit=500),
            likes=int(item.get("likes_count") or 0),
        )
        for item in data
        if item.get("url")
    ]


def parse_hf_daily(data: list[dict[str, Any]], source_key: str, top: int) -> list[Candidate]:
    """1日分の注目論文から、投票数の多い順に top 本。元の論文（arXiv）を指す。"""
    ranked = sorted(data, key=lambda item: -int(item.get("paper", {}).get("upvotes") or 0))
    candidates: list[Candidate] = []
    for item in ranked[:top]:
        paper = item.get("paper", {})
        arxiv_id = paper.get("id")
        if not arxiv_id:
            continue
        candidates.append(
            Candidate(
                url=f"https://arxiv.org/abs/{arxiv_id}",
                source_key=source_key,
                title=str(paper.get("title") or item.get("title") or ""),
                # 日次リストに載った日で見る（論文自体の投稿日は、数日前のことがある）
                published_at=_parse_iso(item.get("publishedAt") or paper.get("publishedAt")),
                summary=clean_summary(str(paper.get("summary") or item.get("summary") or "")),
                likes=int(paper.get("upvotes") or 0),
                is_paper=True,
                arxiv_id=str(arxiv_id),
            )
        )
    return candidates


def _recent_top(candidates: list[Candidate], since: datetime, top: int) -> list[Candidate]:
    recent = [c for c in candidates if c.published_at is None or c.published_at >= since]
    unique = {c.url: c for c in recent}
    return sorted(unique.values(), key=lambda c: -(c.likes or 0))[:top]


async def _collect(
    fetcher: Fetcher, source: SourceConfig, since: datetime, now: datetime
) -> list[Candidate]:
    options = source.options
    match source.fetch:
        case "rss":
            assert source.url
            return parse_feed((await fetcher.get(source.url)).body, source.key)
        case "sitemap":
            assert source.url and source.pattern
            result = await fetcher.get(source.url)
            return parse_sitemap(result.text, source.key, source.pattern)
        case "listing":
            assert source.url and source.pattern
            result = await fetcher.get(source.url)
            return parse_listing(result.text, result.url, source.key, source.pattern)
        case "zenn":
            gathered: list[Candidate] = []
            for topic in options.get("topics", []):
                url = f"https://zenn.dev/api/articles?topicname={quote(str(topic))}&order=latest&count=50"
                gathered += parse_zenn((await fetcher.get(url)).json(), source.key)
            return _recent_top(gathered, since, int(options.get("top", 10)))
        case "qiita":
            gathered = []
            for tag in options.get("tags", []):
                query = quote(f"tag:{tag} created:>={since:%Y-%m-%d}")
                url = f"https://qiita.com/api/v2/items?page=1&per_page=50&query={query}"
                gathered += parse_qiita((await fetcher.get(url)).json(), source.key)
            return _recent_top(gathered, since, int(options.get("top", 10)))
        case "hf_papers":
            top = int(options.get("top", 5))
            days = (now.date() - since.date()).days + 1
            found: list[Candidate] = []
            for offset in range(days):
                day = (now - timedelta(days=offset)).strftime("%Y-%m-%d")
                url = f"https://huggingface.co/api/daily_papers?date={day}"
                try:
                    data = (await fetcher.get(url)).json()
                except FetchError as error:
                    if error.kind == "http" and error.status == 404:
                        continue  # その日の分がまだ無い
                    raise
                found += parse_hf_daily(data, source.key, top)
            return found
    raise ValueError(f"未対応の取得方法です: {source.fetch}")


async def collect_source(
    fetcher: Fetcher, source: SourceConfig, *, since: datetime, now: datetime
) -> SourceResult:
    """1つの情報源の候補を集める。失敗しても例外にせず、理由を結果に入れる（他の情報源を止めない）。"""
    try:
        return SourceResult(source, await _collect(fetcher, source, since, now))
    except FetchError as error:
        return SourceResult(source, [], error=str(error), error_kind=error.kind)
    except (ValueError, KeyError, TypeError, AttributeError) as error:  # 想定外の形のデータ
        return SourceResult(
            source, [], error=f"データの形が想定と違います: {error}", error_kind="parse"
        )


async def discover(
    fetcher: Fetcher, sources: list[SourceConfig], *, since: datetime, now: datetime
) -> list[SourceResult]:
    """使える情報源すべてから、同時に候補を集める。"""
    return list(
        await asyncio.gather(
            *(collect_source(fetcher, s, since=since, now=now) for s in sources if s.usable)
        )
    )
