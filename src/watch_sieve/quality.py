from __future__ import annotations

import re

_CHALLENGE_MARKERS = (
    re.compile(r"/cdn-cgi/challenge-platform/", re.I),
    re.compile(r"__cf_chl", re.I),
    re.compile(r"<title>\s*Just a moment", re.I),
    re.compile(r"Checking your browser", re.I),
    re.compile(r"captcha-delivery\.com", re.I),
    re.compile(r"_Incapsula_Resource", re.I),
    re.compile(r"window\._pxAppId\s*=", re.I),
)

_SCRIPT_RE = re.compile(r"<script\b[\s\S]*?</script>", re.I)
_STYLE_RE = re.compile(r"<style\b[\s\S]*?</style>", re.I)
_TAG_RE = re.compile(r"<[^>]+>")
_BODY_RE = re.compile(r"<body\b", re.I)
_CONTENT_RE = re.compile(r"<(?:p|h[1-6]|article|section|li|td|a|pre)\b", re.I)

_EMPTY_BYTES = 120
_SHORT_PAGE = 10_000
_SHELL_PAGE = 50_000


def visible_text(html: str) -> str:
    stripped = _SCRIPT_RE.sub("", html or "")
    stripped = _STYLE_RE.sub("", stripped)
    return _TAG_RE.sub(" ", stripped)


def needs_browser(status_code: int | None, html: str) -> tuple[bool, str]:
    """Return True when HTTP HTML is blocked, empty, or a JS shell.

    False positives are cheap because Playwright can still recover.
    """
    html = html or ""
    html_len = len(html)

    if status_code == 429:
        return True, "HTTP 429"
    if status_code in {401, 403, 503}:
        return True, f"HTTP {status_code}"

    snippet = html[:20_000]
    for pattern in _CHALLENGE_MARKERS:
        if pattern.search(snippet):
            return True, f"challenge page ({pattern.pattern})"

    if status_code and status_code >= 400:
        return True, f"HTTP {status_code}"

    if html_len < _EMPTY_BYTES:
        return True, f"near-empty HTML ({html_len} bytes)"

    if html_len > _SHELL_PAGE:
        return False, ""

    if not _BODY_RE.search(html):
        return True, "no <body> tag"

    visible = visible_text(html).strip()
    content_tags = len(_CONTENT_RE.findall(html))
    script_heavy = html.lower().count("<script") >= 3
    if len(visible) < 80 and (content_tags == 0 or script_heavy or html_len < _SHORT_PAGE):
        return True, f"JS shell ({html_len} bytes, {len(visible)} visible chars)"

    return False, ""


def content_too_thin(markdown: str, *, min_chars: int = 80) -> bool:
    return len((markdown or "").strip()) < min_chars
