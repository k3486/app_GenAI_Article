"""安全な取得。

- robots.txt を守る（取得できなかったときは、そのサイトは取りに行かない）
- 同じサイトへは間隔をあけ、同時接続も絞る（arXiv は規約で「3秒に1回・同時接続1つ」）
- 内部アドレスへは接続しない（リダイレクトの先も、1回ごとに検査する）
- 1回のダウンロードは 5MB・30 秒まで。リダイレクトは 5 回まで
- 一時的なエラー（タイムアウト・通信エラー・5xx・429）は、2 回まで取り直す
"""

import asyncio
import json
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx2

from app.services.collect.urls import Resolver, UnsafeUrlError, ensure_public_url, resolve_host

USER_AGENT = "ai-news-dashboard/0.1 (personal feed reader)"
ROBOTS_TOKEN = "ai-news-dashboard"
MAX_BYTES = 5_000_000
TIMEOUT_SECONDS = 30.0
MAX_REDIRECTS = 5
RETRIES = 2
_MAX_BACKOFF = 10.0
_TEXTUAL = (
    "text/",
    "application/xml",
    "application/json",
    "application/xhtml",
    "application/rss",
    "application/atom",
    "application/pdf",
)
_SERIAL_DOMAINS = frozenset({"arxiv.org", "export.arxiv.org"})


class FetchError(Exception):
    """取得の失敗。

    kind: unsafe_url / robots / timeout / network / http / too_large / redirects / content_type
    """

    def __init__(
        self,
        kind: str,
        message: str,
        status: int | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.status = status
        self.retry_after = retry_after

    @property
    def retryable(self) -> bool:
        if self.kind in ("timeout", "network"):
            return True
        return (
            self.kind == "http"
            and self.status is not None
            and (self.status == 429 or self.status >= 500)
        )


@dataclass(frozen=True)
class FetchResult:
    url: str  # リダイレクトをたどった後の URL
    status: int
    content_type: str
    body: bytes

    @property
    def text(self) -> str:
        charset = "utf-8"
        for part in self.content_type.split(";")[1:]:
            key, _, value = part.strip().partition("=")
            if key.lower() == "charset" and value:
                charset = value.strip("\"'")
        try:
            return self.body.decode(charset, errors="replace")
        except LookupError:
            return self.body.decode("utf-8", errors="replace")

    def json(self) -> Any:
        return json.loads(self.body)


@dataclass
class _Robots:
    parser: RobotFileParser | None  # None のときは allow_all で決まる
    allow_all: bool

    def allows(self, url: str) -> bool:
        if self.parser is None:
            return self.allow_all
        return self.parser.can_fetch(ROBOTS_TOKEN, url)


class Fetcher:
    def __init__(
        self,
        *,
        transport: httpx2.AsyncBaseTransport | None = None,
        resolver: Resolver = resolve_host,
        min_interval: Mapping[str, float] | None = None,
        max_concurrency: int = 8,
        per_domain_limit: int = 2,
        max_bytes: int = MAX_BYTES,
        timeout: float = TIMEOUT_SECONDS,
        respect_robots: bool = True,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client = httpx2.AsyncClient(
            transport=transport,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "ja,en;q=0.8"},
            follow_redirects=False,
        )
        self._resolver = resolver
        self._intervals = dict(min_interval or {"default": 1.0})
        self._global = asyncio.Semaphore(max_concurrency)
        self._per_domain_limit = per_domain_limit
        self._max_bytes = max_bytes
        self._timeout = timeout
        self._respect_robots = respect_robots
        self._sleep = sleep
        self._clock = clock
        self._domain_sems: dict[str, asyncio.Semaphore] = {}
        self._turn_locks: dict[str, asyncio.Lock] = {}
        self._next_at: dict[str, float] = {}
        self._robots: dict[str, _Robots] = {}
        self._robots_locks: dict[str, asyncio.Lock] = {}
        self._crawl_delay: dict[str, float] = {}

    async def __aenter__(self) -> "Fetcher":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._client.aclose()

    # --- 公開 ---------------------------------------------------------------

    async def get(self, url: str, *, robots: bool = True) -> FetchResult:
        """取得する。一時的なエラーは取り直し、それ以外の失敗は FetchError を投げる。"""
        for attempt in range(RETRIES + 1):
            try:
                return await self._fetch(url, robots=robots)
            except FetchError as error:
                if not error.retryable or attempt == RETRIES:
                    raise
                await self._sleep(min(error.retry_after or 2.0**attempt, _MAX_BACKOFF))
        raise AssertionError("到達しない")

    async def allowed(self, url: str) -> bool:
        """robots.txt が許しているか（ブラウザで開く前の確認用）。"""
        if not self._respect_robots:
            return True
        return await self._robots_allow(url)

    # --- 内部 ---------------------------------------------------------------

    def _interval(self, host: str) -> float:
        base = self._intervals.get("default", 1.0)
        for domain, value in self._intervals.items():
            if domain != "default" and (host == domain or host.endswith("." + domain)):
                base = value
        return max(base, self._crawl_delay.get(host, 0.0))

    def _domain_sem(self, host: str) -> asyncio.Semaphore:
        if host not in self._domain_sems:
            serial = host in _SERIAL_DOMAINS or any(
                host.endswith("." + d) for d in _SERIAL_DOMAINS
            )
            self._domain_sems[host] = asyncio.Semaphore(1 if serial else self._per_domain_limit)
        return self._domain_sems[host]

    async def _wait_turn(self, host: str) -> None:
        lock = self._turn_locks.setdefault(host, asyncio.Lock())
        async with lock:
            wait = self._next_at.get(host, 0.0) - self._clock()
            if wait > 0:
                await self._sleep(wait)
            self._next_at[host] = self._clock() + self._interval(host)

    async def _fetch(self, url: str, *, robots: bool) -> FetchResult:
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            try:
                await ensure_public_url(current, self._resolver)
            except UnsafeUrlError as exc:
                raise FetchError("unsafe_url", str(exc)) from exc
            if robots and self._respect_robots and not await self._robots_allow(current):
                raise FetchError("robots", f"robots.txt で許可されていません: {current}")
            status, headers, body = await self._request(current)
            location = headers.get("location")
            if 300 <= status < 400 and location:
                current = urljoin(current, location)
                continue
            if status >= 400:
                retry_after = _seconds(headers.get("retry-after"))
                raise FetchError("http", f"HTTP {status}", status=status, retry_after=retry_after)
            return FetchResult(
                url=current,
                status=status,
                content_type=headers.get("content-type", ""),
                body=body,
            )
        raise FetchError("redirects", f"リダイレクトが {MAX_REDIRECTS} 回を超えました")

    async def _request(self, url: str) -> tuple[int, Mapping[str, str], bytes]:
        host = (urlsplit(url).hostname or "").lower()
        async with self._domain_sem(host):
            await self._wait_turn(host)
            async with self._global:
                try:
                    async with asyncio.timeout(self._timeout):
                        return await self._stream(url)
                except TimeoutError as exc:
                    raise FetchError(
                        "timeout", f"{self._timeout:.0f} 秒以内に終わりませんでした"
                    ) from exc
                except httpx2.TimeoutException as exc:
                    raise FetchError("timeout", "接続がタイムアウトしました") from exc
                except httpx2.HTTPError as exc:
                    raise FetchError("network", f"通信エラー: {type(exc).__name__}") from exc

    async def _stream(self, url: str) -> tuple[int, Mapping[str, str], bytes]:
        async with self._client.stream("GET", url) as response:
            headers = {k.lower(): v for k, v in response.headers.items()}
            status = response.status_code
            if status >= 400 or 300 <= status < 400:
                return status, headers, b""
            kind = headers.get("content-type", "").split(";")[0].strip().lower()
            if kind and not kind.startswith(_TEXTUAL):
                raise FetchError("content_type", f"対象外の種類です: {kind}")
            declared = _seconds(headers.get("content-length"))
            if declared is not None and declared > self._max_bytes:
                raise FetchError("too_large", f"{declared:.0f} バイトで大きすぎます")
            chunks: list[bytes] = []
            total = 0
            async for chunk in response.aiter_bytes():
                total += len(chunk)
                if total > self._max_bytes:
                    raise FetchError("too_large", f"{self._max_bytes} バイトを超えました")
                chunks.append(chunk)
            return status, headers, b"".join(chunks)

    async def _robots_allow(self, url: str) -> bool:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._robots:
            lock = self._robots_locks.setdefault(origin, asyncio.Lock())
            async with lock:
                if origin not in self._robots:
                    self._robots[origin] = await self._load_robots(origin)
        return self._robots[origin].allows(url)

    async def _load_robots(self, origin: str) -> _Robots:
        """4xx（429 を除く）は「制限なし」。5xx・429・通信エラーは、安全のため取りに行かない。"""
        try:
            result = await self._fetch(f"{origin}/robots.txt", robots=False)
        except FetchError as error:
            allow_all = (
                error.kind == "http"
                and error.status is not None
                and (error.status < 500 and error.status != 429)
            )
            return _Robots(parser=None, allow_all=allow_all)
        parser = RobotFileParser()
        parser.parse(result.text.splitlines())
        host = (urlsplit(origin).hostname or "").lower()
        delay = parser.crawl_delay(ROBOTS_TOKEN) or parser.crawl_delay("*")
        if delay:
            self._crawl_delay[host] = min(float(delay), 10.0)
        return _Robots(parser=parser, allow_all=True)


def _seconds(value: str | None) -> float | None:
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None
