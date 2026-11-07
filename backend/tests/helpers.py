"""収集のテスト用の補助：擬似の通信相手・テスト用の HTML・時計。"""

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

import httpx2

from app.services.collect.fetcher import Fetcher

PUBLIC_IP = "93.184.216.34"

EN_SENTENCES = (
    "The team announced that the new model is now available for all developers through the API. "
    "It is designed to follow instructions more closely and to work with the tools that are "
    "already part of the stack. Early testers said that the results were better than expected "
    "for the tasks that they cared about. The company plans to share more details about the "
    "training process in the coming weeks and to publish the evaluation results for the public. "
)
JA_SENTENCES = (
    "新しいモデルが公開され、開発者はすべての API からすぐに利用できるようになった。"
    "指示への従い方が改善され、既存のツールともそのまま組み合わせて使える設計になっている。"
    "先行して試した利用者からは、期待以上の結果が得られたという声が寄せられている。"
    "運営会社は、学習の過程や評価の結果について、今後数週間のうちに詳細を公開する予定だ。"
)


def article_html(
    title: str = "A new model for developers",
    *,
    sentences: str = EN_SENTENCES,
    repeat: int = 3,
    date: str | None = "2026-11-05",
    canonical: str | None = None,
    image: str | None = "https://img.example.com/hero.png",
    extra_body: str = "",
    lang: str = "en",
) -> str:
    head = [f"<title>{title}</title>"]
    if date:
        head.append(f'<meta property="article:published_time" content="{date}T09:00:00Z">')
    if canonical:
        head.append(f'<link rel="canonical" href="{canonical}">')
    if image:
        head.append(f'<meta property="og:image" content="{image}">')
    paragraphs = "".join(f"<p>[{i + 1}] {sentences}</p>" for i in range(repeat))
    return (
        f'<!doctype html><html lang="{lang}"><head>{"".join(head)}</head><body>'
        f"<nav><a href='/'>Home</a></nav><article><h1>{title}</h1>{paragraphs}{extra_body}"
        "</article><footer>Copyright</footer></body></html>"
    )


Handler = Callable[[httpx2.Request], httpx2.Response | Awaitable[httpx2.Response]]


@dataclass
class FakeWeb:
    """URL → 応答 の表。呼ばれた URL を記録する。表に無い URL は 404。"""

    routes: dict[str, httpx2.Response | Handler] = field(default_factory=dict)
    calls: list[str] = field(default_factory=list)

    def add(
        self,
        url: str,
        content: str | bytes = b"",
        *,
        status: int = 200,
        content_type: str = "text/html; charset=utf-8",
        headers: dict[str, str] | None = None,
    ) -> None:
        body = content.encode() if isinstance(content, str) else content
        merged = {"content-type": content_type, **(headers or {})}
        self.routes[url] = httpx2.Response(status, content=body, headers=merged)

    async def handler(self, request: httpx2.Request) -> httpx2.Response:
        url = str(request.url)
        self.calls.append(url)
        target = self.routes.get(url)
        if target is None:
            return httpx2.Response(
                404, content=b"not found", headers={"content-type": "text/plain"}
            )
        if isinstance(target, httpx2.Response):
            return target
        result = target(request)
        return await result if inspect.isawaitable(result) else result

    def transport(self) -> httpx2.MockTransport:
        return httpx2.MockTransport(self.handler)


async def public_resolver(host: str, port: int) -> list[str]:
    return [PUBLIC_IP]


class FakeClock:
    """待ち時間を実際には待たず、時計だけを進める。"""

    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def make_fetcher(
    web: FakeWeb,
    *,
    clock: FakeClock | None = None,
    min_interval: dict[str, float] | None = None,
    max_bytes: int = 5_000_000,
    max_concurrency: int = 8,
    per_domain_limit: int = 2,
    respect_robots: bool = True,
) -> Fetcher:
    clock = clock or FakeClock()
    return Fetcher(
        transport=web.transport(),
        resolver=public_resolver,
        min_interval=min_interval if min_interval is not None else {"default": 0.0},
        max_bytes=max_bytes,
        max_concurrency=max_concurrency,
        per_domain_limit=per_domain_limit,
        respect_robots=respect_robots,
        sleep=clock.sleep,
        clock=clock,
    )
