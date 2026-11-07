import pytest

from app.services.collect.urls import UnsafeUrlError, ensure_public_url, normalize_url


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("http://Example.com/a/b/", "https://example.com/a/b"),
        (
            "https://example.com/a?utm_source=x&b=2&a=1&fbclid=z#top",
            "https://example.com/a?a=1&b=2",
        ),
        ("https://example.com:443/a", "https://example.com/a"),
        ("https://example.com", "https://example.com/"),
        ("https://example.com//a///b", "https://example.com/a/b"),
        ("  https://example.com/x  ", "https://example.com/x"),
        ("https://example.com/p?id=3&utm_campaign=q", "https://example.com/p?id=3"),
        ("https://example.com:8443/a", "https://example.com:8443/a"),
    ],
)
def test_normalize_url(raw: str, expected: str) -> None:
    assert normalize_url(raw) == expected


def test_normalize_is_stable_and_merges_variants() -> None:
    variants = [
        "http://example.com/post/1/?utm_medium=rss",
        "https://example.com/post/1#comments",
        "https://EXAMPLE.com/post/1/",
    ]
    assert len({normalize_url(v) for v in variants}) == 1
    once = normalize_url(variants[0])
    assert normalize_url(once) == once


async def _resolve(host: str, port: int) -> list[str]:
    table = {
        "public.example.com": ["93.184.216.34"],
        "internal.example.com": ["10.0.0.8"],
        "mixed.example.com": ["93.184.216.34", "192.168.1.5"],
        "metadata.example.com": ["169.254.169.254"],
        "loop.example.com": ["127.0.0.1"],
        "empty.example.com": [],
    }
    return table[host]


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://public.example.com/x",
        "gopher://public.example.com/",
        "https://",
        "http://127.0.0.1/",
        "http://localhost.invalid:80/",
        "http://10.1.2.3/",
        "http://172.16.0.1/",
        "http://192.168.0.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://100.64.0.1/",
        "http://[::1]/",
        "http://[fe80::1]/",
        "http://[::ffff:10.0.0.1]/",
        "http://0.0.0.0/",
        "https://internal.example.com/",
        "https://mixed.example.com/",
        "https://metadata.example.com/",
        "https://loop.example.com/",
        "https://empty.example.com/",
        "https://public.example.com:8080/",
        "https://user:pass@public.example.com/",
    ],
)
async def test_unsafe_urls_are_refused(url: str) -> None:
    async def resolver(host: str, port: int) -> list[str]:
        if host == "localhost.invalid":
            return ["127.0.0.1"]
        return await _resolve(host, port)

    with pytest.raises(UnsafeUrlError):
        await ensure_public_url(url, resolver)


@pytest.mark.parametrize(
    "url",
    [
        "https://public.example.com/a",
        "http://public.example.com:80/a",
        "https://public.example.com:443/a",
        "https://93.184.216.34/a",
        "http://[2606:2800:220:1:248:1893:25c8:1946]/",
    ],
)
async def test_public_urls_are_allowed(url: str) -> None:
    await ensure_public_url(url, _resolve)
