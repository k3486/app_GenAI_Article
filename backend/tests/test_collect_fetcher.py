import asyncio

import httpx2
import pytest

from app.services.collect.fetcher import Fetcher, FetchError
from tests.helpers import FakeClock, FakeWeb, make_fetcher, public_resolver

ROBOTS_OPEN = "User-agent: *\nAllow: /\n"


def web_with(**pages: str) -> FakeWeb:
    web = FakeWeb()
    web.add("https://site.example.com/robots.txt", ROBOTS_OPEN, content_type="text/plain")
    for path, body in pages.items():
        web.add(f"https://site.example.com/{path}", body)
    return web


async def test_get_returns_body_and_decodes_charset() -> None:
    web = web_with()
    web.add(
        "https://site.example.com/sjis",
        "こんにちは".encode("shift_jis"),
        content_type="text/html; charset=Shift_JIS",
    )
    async with make_fetcher(web) as fetcher:
        result = await fetcher.get("https://site.example.com/sjis")
    assert result.status == 200
    assert result.text == "こんにちは"
    assert result.url == "https://site.example.com/sjis"


async def test_json_helper() -> None:
    web = web_with()
    web.add("https://site.example.com/api", '{"a": [1, 2]}', content_type="application/json")
    async with make_fetcher(web) as fetcher:
        assert (await fetcher.get("https://site.example.com/api")).json() == {"a": [1, 2]}


# --- robots.txt ----------------------------------------------------------------


async def test_robots_disallow_blocks_the_page_but_not_others() -> None:
    web = FakeWeb()
    web.add(
        "https://site.example.com/robots.txt",
        "User-agent: *\nDisallow: /private/\n",
        content_type="text/plain",
    )
    web.add("https://site.example.com/private/x", "secret")
    web.add("https://site.example.com/public/x", "ok")
    async with make_fetcher(web) as fetcher:
        with pytest.raises(FetchError) as blocked:
            await fetcher.get("https://site.example.com/private/x")
        assert blocked.value.kind == "robots"
        assert (await fetcher.get("https://site.example.com/public/x")).text == "ok"
    assert "https://site.example.com/private/x" not in web.calls  # 取りに行っていない


async def test_robots_for_our_own_agent_name_is_respected() -> None:
    web = FakeWeb()
    web.add(
        "https://site.example.com/robots.txt",
        "User-agent: ai-news-dashboard\nDisallow: /\n",
        content_type="text/plain",
    )
    web.add("https://site.example.com/x", "ok")
    async with make_fetcher(web) as fetcher:
        with pytest.raises(FetchError) as blocked:
            await fetcher.get("https://site.example.com/x")
    assert blocked.value.kind == "robots"


async def test_missing_robots_file_means_allowed() -> None:
    web = FakeWeb()  # robots.txt は 404
    web.add("https://site.example.com/x", "ok")
    async with make_fetcher(web) as fetcher:
        assert (await fetcher.get("https://site.example.com/x")).text == "ok"


@pytest.mark.parametrize("status", [500, 503, 429])
async def test_unreachable_robots_means_do_not_fetch(status: int) -> None:
    web = FakeWeb()
    web.add("https://site.example.com/robots.txt", "", status=status, content_type="text/plain")
    web.add("https://site.example.com/x", "ok")
    async with make_fetcher(web) as fetcher:
        with pytest.raises(FetchError) as blocked:
            await fetcher.get("https://site.example.com/x")
    assert blocked.value.kind == "robots"
    assert "https://site.example.com/x" not in web.calls


async def test_robots_is_fetched_once_per_site() -> None:
    web = web_with(a="1", b="2")
    async with make_fetcher(web) as fetcher:
        await asyncio.gather(
            fetcher.get("https://site.example.com/a"), fetcher.get("https://site.example.com/b")
        )
    assert web.calls.count("https://site.example.com/robots.txt") == 1


async def test_crawl_delay_is_followed_up_to_a_limit() -> None:
    web = FakeWeb()
    web.add(
        "https://site.example.com/robots.txt",
        "User-agent: *\nCrawl-delay: 4\n",
        content_type="text/plain",
    )
    web.add("https://site.example.com/a", "1")
    web.add("https://site.example.com/b", "2")
    clock = FakeClock()
    async with make_fetcher(web, clock=clock) as fetcher:
        await fetcher.get("https://site.example.com/a")
        await fetcher.get("https://site.example.com/b")
    assert any(abs(s - 4.0) < 0.01 for s in clock.sleeps)


# --- 内部アドレス・リダイレクト --------------------------------------------------


async def test_redirect_to_internal_address_is_refused_before_connecting() -> None:
    web = web_with()
    web.add(
        "https://site.example.com/go",
        "",
        status=302,
        headers={"location": "http://169.254.169.254/latest/meta-data/"},
    )
    async with make_fetcher(web) as fetcher:
        with pytest.raises(FetchError) as error:
            await fetcher.get("https://site.example.com/go")
    assert error.value.kind == "unsafe_url"
    assert not any("169.254" in call for call in web.calls)


async def test_direct_internal_url_is_refused() -> None:
    web = FakeWeb()
    async with make_fetcher(web) as fetcher:
        for url in ("http://127.0.0.1/", "http://10.0.0.1/x", "file:///etc/passwd"):
            with pytest.raises(FetchError) as error:
                await fetcher.get(url)
            assert error.value.kind == "unsafe_url"
    assert web.calls == []


async def test_hostname_resolving_to_internal_address_is_refused() -> None:
    async def evil_resolver(host: str, port: int) -> list[str]:
        return ["10.0.0.5"]

    web = FakeWeb()
    fetcher = Fetcher(
        transport=web.transport(), resolver=evil_resolver, min_interval={"default": 0}
    )
    async with fetcher:
        with pytest.raises(FetchError) as error:
            await fetcher.get("https://rebind.example.com/")
    assert error.value.kind == "unsafe_url"


async def test_redirects_are_followed_and_final_url_returned() -> None:
    web = web_with(final="done")
    web.add("https://site.example.com/old", "", status=301, headers={"location": "/new"})
    web.add("https://site.example.com/new", "", status=302, headers={"location": "/final"})
    async with make_fetcher(web) as fetcher:
        result = await fetcher.get("https://site.example.com/old")
    assert result.url == "https://site.example.com/final"
    assert result.text == "done"


async def test_too_many_redirects() -> None:
    web = web_with()
    web.add("https://site.example.com/loop", "", status=302, headers={"location": "/loop"})
    async with make_fetcher(web) as fetcher:
        with pytest.raises(FetchError) as error:
            await fetcher.get("https://site.example.com/loop")
    assert error.value.kind == "redirects"


# --- サイズ・種類 ---------------------------------------------------------------


async def test_oversized_download_is_refused_by_header_and_by_stream() -> None:
    web = web_with()
    web.add(
        "https://site.example.com/declared",
        "x" * 10,
        headers={"content-length": "999999999"},
    )
    web.add("https://site.example.com/streamed", "y" * 5000)
    async with make_fetcher(web, max_bytes=1000) as fetcher:
        for path in ("declared", "streamed"):
            with pytest.raises(FetchError) as error:
                await fetcher.get(f"https://site.example.com/{path}")
            assert error.value.kind == "too_large"


async def test_non_text_content_is_refused() -> None:
    web = web_with()
    web.add("https://site.example.com/img", b"\x89PNG", content_type="image/png")
    web.add("https://site.example.com/zip", b"PK", content_type="application/zip")
    web.add("https://site.example.com/doc", b"%PDF", content_type="application/pdf")
    async with make_fetcher(web) as fetcher:
        for path in ("img", "zip"):
            with pytest.raises(FetchError) as error:
                await fetcher.get(f"https://site.example.com/{path}")
            assert error.value.kind == "content_type"
        assert (await fetcher.get("https://site.example.com/doc")).body == b"%PDF"


# --- 再試行 ---------------------------------------------------------------------


async def test_temporary_errors_are_retried_up_to_two_times() -> None:
    attempts = {"n": 0}

    def flaky(request: httpx2.Request) -> httpx2.Response:
        attempts["n"] += 1
        if attempts["n"] < 3:
            return httpx2.Response(503, content=b"busy", headers={"content-type": "text/plain"})
        return httpx2.Response(200, content=b"ok", headers={"content-type": "text/plain"})

    web = web_with()
    web.routes["https://site.example.com/flaky"] = flaky
    clock = FakeClock()
    async with make_fetcher(web, clock=clock) as fetcher:
        result = await fetcher.get("https://site.example.com/flaky")
    assert result.text == "ok"
    assert attempts["n"] == 3
    assert len(clock.sleeps) == 2  # 取り直しの前に待った


async def test_gives_up_after_the_last_retry() -> None:
    web = web_with()
    web.add("https://site.example.com/down", "", status=503, content_type="text/plain")
    async with make_fetcher(web) as fetcher:
        with pytest.raises(FetchError) as error:
            await fetcher.get("https://site.example.com/down")
    assert error.value.kind == "http" and error.value.status == 503
    assert web.calls.count("https://site.example.com/down") == 3


@pytest.mark.parametrize("status", [404, 403, 410])
async def test_client_errors_are_not_retried(status: int) -> None:
    web = web_with()
    web.add("https://site.example.com/gone", "", status=status, content_type="text/plain")
    async with make_fetcher(web) as fetcher:
        with pytest.raises(FetchError) as error:
            await fetcher.get("https://site.example.com/gone")
    assert error.value.status == status
    assert web.calls.count("https://site.example.com/gone") == 1


async def test_retry_after_is_honoured_with_a_cap() -> None:
    web = web_with()
    web.add(
        "https://site.example.com/limited",
        "",
        status=429,
        content_type="text/plain",
        headers={"retry-after": "120"},
    )
    clock = FakeClock()
    async with make_fetcher(web, clock=clock) as fetcher:
        with pytest.raises(FetchError):
            await fetcher.get("https://site.example.com/limited")
    assert clock.sleeps and max(clock.sleeps) <= 10.0


async def test_timeouts_and_network_errors_are_retried_then_reported() -> None:
    calls = {"n": 0}

    def broken(request: httpx2.Request) -> httpx2.Response:
        calls["n"] += 1
        raise httpx2.ConnectError("boom")

    def slow(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ReadTimeout("slow")

    web = web_with()
    web.routes["https://site.example.com/broken"] = broken
    web.routes["https://site.example.com/slow"] = slow
    async with make_fetcher(web) as fetcher:
        with pytest.raises(FetchError) as network:
            await fetcher.get("https://site.example.com/broken")
        with pytest.raises(FetchError) as timeout:
            await fetcher.get("https://site.example.com/slow")
    assert network.value.kind == "network" and calls["n"] == 3
    assert timeout.value.kind == "timeout"


async def test_total_time_limit() -> None:
    async def never(request: httpx2.Request) -> httpx2.Response:
        await asyncio.sleep(5)
        return httpx2.Response(200)

    web = web_with()
    web.routes["https://site.example.com/hang"] = never
    fetcher = Fetcher(
        transport=web.transport(),
        resolver=public_resolver,
        min_interval={"default": 0},
        timeout=0.05,
        sleep=FakeClock().sleep,
    )
    async with fetcher:
        with pytest.raises(FetchError) as error:
            await fetcher.get("https://site.example.com/hang", robots=False)
    assert error.value.kind == "timeout"


# --- 間隔と同時接続 -------------------------------------------------------------


async def test_requests_to_the_same_site_are_spaced_out() -> None:
    web = web_with(a="1", b="2", c="3")
    clock = FakeClock()
    async with make_fetcher(web, clock=clock, min_interval={"default": 1.0}) as fetcher:
        for name in "abc":
            await fetcher.get(f"https://site.example.com/{name}")
    # robots.txt を含めて4回の取得。2回目以降は、直前から1秒あけている
    assert sum(clock.sleeps) >= 3.0 - 0.01


async def test_per_site_interval_overrides_default() -> None:
    web = FakeWeb()
    for host in ("arxiv.org", "other.example.com"):
        web.add(f"https://{host}/robots.txt", ROBOTS_OPEN, content_type="text/plain")
        web.add(f"https://{host}/a", "1")
        web.add(f"https://{host}/b", "2")
    arxiv_clock, other_clock = FakeClock(), FakeClock()
    intervals = {"default": 0.5, "arxiv.org": 3.0}
    async with make_fetcher(web, clock=arxiv_clock, min_interval=intervals) as fetcher:
        await fetcher.get("https://arxiv.org/a")
        await fetcher.get("https://arxiv.org/b")
    async with make_fetcher(web, clock=other_clock, min_interval=intervals) as fetcher:
        await fetcher.get("https://other.example.com/a")
        await fetcher.get("https://other.example.com/b")
    assert max(arxiv_clock.sleeps) >= 3.0 - 0.01
    assert max(other_clock.sleeps) < 3.0


async def test_arxiv_is_limited_to_one_connection_at_a_time() -> None:
    active = {"now": 0, "max": 0}

    async def slow_page(request: httpx2.Request) -> httpx2.Response:
        active["now"] += 1
        active["max"] = max(active["max"], active["now"])
        await asyncio.sleep(0.01)
        active["now"] -= 1
        return httpx2.Response(200, content=b"ok", headers={"content-type": "text/plain"})

    web = FakeWeb()
    web.add("https://arxiv.org/robots.txt", ROBOTS_OPEN, content_type="text/plain")
    web.add("https://normal.example.com/robots.txt", ROBOTS_OPEN, content_type="text/plain")
    for i in range(4):
        web.routes[f"https://arxiv.org/p{i}"] = slow_page
        web.routes[f"https://normal.example.com/p{i}"] = slow_page

    async with make_fetcher(web, per_domain_limit=2) as fetcher:
        await asyncio.gather(*(fetcher.get(f"https://arxiv.org/p{i}") for i in range(4)))
        assert active["max"] == 1
        active["max"] = 0
        await asyncio.gather(*(fetcher.get(f"https://normal.example.com/p{i}") for i in range(4)))
        assert active["max"] == 2


async def test_robots_can_be_turned_off_for_checks_that_need_it() -> None:
    web = FakeWeb()
    web.add("https://site.example.com/x", "ok")
    async with make_fetcher(web, respect_robots=False) as fetcher:
        assert (await fetcher.get("https://site.example.com/x")).text == "ok"
        assert await fetcher.allowed("https://site.example.com/x") is True
    assert "https://site.example.com/robots.txt" not in web.calls
