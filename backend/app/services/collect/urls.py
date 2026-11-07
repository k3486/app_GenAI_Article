"""URL の正規化と、取りに行ってよい URL かの検査（SSRF 対策）。

SSRF: 外部から入ってきた URL（検索結果・記事内のリンク）を使って、サーバー内部の情報
（クラウドのメタデータ 169.254.169.254 など）を読まれてしまう攻撃。
②で AWS 上で動かすときに特に重要。
"""

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# 追跡用のパラメータ（同じ記事でも URL が変わってしまうので除く）
_TRACKING_PREFIXES = ("utm_", "mc_", "pk_", "hsa_")
_TRACKING_KEYS = frozenset(
    {
        "fbclid",
        "gclid",
        "yclid",
        "igshid",
        "ref",
        "ref_src",
        "ref_url",
        "cmpid",
        "ocid",
        "spm",
        "s_cid",
        "mkt_tok",
        "_hsenc",
        "_hsmi",
        "ito",
        "feature",
    }
)
_ALLOWED_PORTS = frozenset({80, 443})


class UnsafeUrlError(ValueError):
    """取りに行ってはいけない URL。"""


def normalize_url(url: str) -> str:
    """同じ記事なら同じ文字列になるようにそろえる。

    http → https／ホスト名は小文字／標準ポートを除く／断片（#…）と追跡用パラメータを除く／
    残りのパラメータは並べ替え／末尾のスラッシュをそろえる。
    """
    parts = urlsplit(url.strip())
    scheme = "https" if parts.scheme in ("http", "https", "") else parts.scheme
    host = (parts.hostname or "").lower()
    port = parts.port
    netloc = host if port in (None, 80, 443) else f"{host}:{port}"
    path = parts.path or "/"
    while "//" in path:
        path = path.replace("//", "/")
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    query = sorted(
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in _TRACKING_KEYS and not k.lower().startswith(_TRACKING_PREFIXES)
    )
    return urlunsplit((scheme, netloc, path, urlencode(query), ""))


Resolver = Callable[[str, int], Awaitable[list[str]]]


async def resolve_host(host: str, port: int) -> list[str]:
    """名前解決して、返ってきたすべてのアドレスを返す。"""
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeUrlError(f"名前解決できません: {host}") from exc
    return sorted({str(info[4][0]) for info in infos})


def _is_public(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%")[0])
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


async def ensure_public_url(url: str, resolver: Resolver = resolve_host) -> None:
    """http/https の公開アドレスだけを許す。内部アドレスは、名前解決後の IP でも拒否する。"""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise UnsafeUrlError(f"http/https 以外は取得しません: {parts.scheme or '(なし)'}")
    host = parts.hostname
    if not host:
        raise UnsafeUrlError("ホスト名がありません")
    if parts.username or parts.password:
        raise UnsafeUrlError("認証情報つきの URL は取得しません")
    port = parts.port or (443 if parts.scheme == "https" else 80)
    if port not in _ALLOWED_PORTS:
        raise UnsafeUrlError(f"許可していないポートです: {port}")
    try:
        addresses = [str(ipaddress.ip_address(host))]  # IP アドレスをそのまま書いた URL
    except ValueError:
        addresses = await resolver(host, port)
    if not addresses:
        raise UnsafeUrlError(f"名前解決の結果がありません: {host}")
    for address in addresses:
        if not _is_public(address):
            raise UnsafeUrlError(f"内部のアドレスへは接続しません: {host} → {address}")
