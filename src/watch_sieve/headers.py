from __future__ import annotations

import re
from urllib.parse import urlparse

from charset_normalizer import from_bytes

BROWSER_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
}

_META_CHARSET_RE = re.compile(
    rb'<meta[^>]+charset=["\']?\s*([a-zA-Z0-9_\-]+)',
    re.I,
)


def request_headers(url: str) -> dict[str, str]:
    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else ""
    headers = dict(BROWSER_HEADERS)
    if origin:
        headers["Referer"] = origin + "/"
    return headers


def decode_html(raw: bytes, header_charset: str | None = None) -> str:
    if header_charset:
        try:
            return raw.decode(header_charset, errors="replace")
        except LookupError:
            pass

    match = _META_CHARSET_RE.search(raw[:4096] if raw else b"")
    if match:
        charset = match.group(1).decode("ascii", errors="ignore")
        try:
            return raw.decode(charset, errors="replace")
        except LookupError:
            pass

    best = from_bytes(raw).best() if raw else None
    if best:
        return str(best)
    return (raw or b"").decode("utf-8", errors="replace")
