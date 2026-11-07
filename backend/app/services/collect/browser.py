"""ブラウザ（Playwright）での取得。通常の取得で本文が空だったページの取り直し用。

重いので、ここに隔離して、無くても動くようにしてある（無ければ BrowserUnavailableError）。
使い捨ての状態で開き、画像・動画・フォントは読まず、内部アドレスへの通信は止める。
"""

import asyncio
from pathlib import Path
from typing import Any, Protocol

from app.services.collect.urls import UnsafeUrlError, ensure_public_url

_CHROME_CANDIDATES = (
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
)
_BLOCKED_TYPES = frozenset({"image", "media", "font"})
_NAVIGATION_TIMEOUT_MS = 30_000


class Renderer(Protocol):
    """ブラウザで開いて、JavaScript の実行後の HTML を返すもの（テストでは偽物に差し替える）。"""

    async def render(self, url: str) -> str: ...


class BrowserUnavailableError(RuntimeError):
    """Playwright かブラウザが使えない。"""


class BrowserFetcher:
    def __init__(self, *, max_concurrency: int = 2) -> None:
        self._sem = asyncio.Semaphore(max_concurrency)
        self._playwright: Any = None
        self._browser: Any = None
        self._lock = asyncio.Lock()

    async def _ensure(self) -> Any:
        async with self._lock:
            if self._browser is not None:
                return self._browser
            try:
                from playwright.async_api import async_playwright
            except ImportError as exc:
                raise BrowserUnavailableError("playwright が入っていません") from exc
            self._playwright = await async_playwright().start()
            executable = next((p for p in _CHROME_CANDIDATES if Path(p).exists()), None)
            try:
                self._browser = await self._playwright.chromium.launch(
                    executable_path=executable, headless=True
                )
            except Exception as exc:  # 起動の失敗はさまざま（ブラウザ無し・権限など）
                await self._playwright.stop()
                self._playwright = None
                raise BrowserUnavailableError(
                    f"ブラウザを起動できません: {type(exc).__name__}"
                ) from exc
            return self._browser

    async def render(self, url: str) -> str:
        """ページを開き、JavaScript の実行後の HTML を返す。"""
        browser = await self._ensure()
        async with self._sem:
            context = await browser.new_context(
                java_script_enabled=True,
                accept_downloads=False,
                service_workers="block",
                permissions=[],
            )
            try:
                await context.route("**/*", self._guard)
                page = await context.new_page()
                await page.goto(url, wait_until="networkidle", timeout=_NAVIGATION_TIMEOUT_MS)
                return str(await page.content())
            finally:
                await context.close()

    @staticmethod
    async def _guard(route: Any) -> None:
        request = route.request
        if request.resource_type in _BLOCKED_TYPES:
            await route.abort()
            return
        try:
            await ensure_public_url(request.url)
        except UnsafeUrlError:
            await route.abort()
            return
        await route.continue_()

    async def aclose(self) -> None:
        if self._browser is not None:
            await self._browser.close()
        if self._playwright is not None:
            await self._playwright.stop()
        self._browser = None
        self._playwright = None
