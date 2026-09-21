from __future__ import annotations

from collections.abc import Callable

import httpx

from watch_sieve.cancellation import check_cancelled
from watch_sieve.browser_fetch import BrowserFetchError, BrowserSession
from watch_sieve.extract import extract_title, list_topics, to_markdown, to_text
from watch_sieve.http_fetch import HttpFetchError, fetch_http
from watch_sieve.models import FetchResult, SiteConfig
from watch_sieve.quality import content_too_thin, needs_browser


class WatchCrawler:
    def __init__(self, *, should_stop: Callable[[], bool] | None = None) -> None:
        self._should_stop = should_stop
        self._http = httpx.Client(follow_redirects=True)
        self._browser = BrowserSession()

    def close(self) -> None:
        self._http.close()
        self._browser.close()

    def __enter__(self) -> WatchCrawler:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def fetch_site(self, site: SiteConfig) -> FetchResult:
        result = self.fetch(
            str(site.url),
            css_selector=site.css_selector or site.wait_for,
            wait_for=site.wait_for or site.css_selector,
            force_browser=site.force_browser or site.kind == "browser",
            timeout_seconds=site.timeout_seconds,
        )
        result.site_id = site.id
        if not result.title:
            result.title = site.name
        return result

    def fetch(
        self,
        url: str,
        *,
        css_selector: str | None = None,
        wait_for: str | None = None,
        force_browser: bool = False,
        timeout_seconds: int = 30,
    ) -> FetchResult:
        check_cancelled(self._should_stop)
        attempts = []
        html = ""
        status_code: int | None = None
        final_url = url
        escalate_reason = "force_browser" if force_browser else ""

        if not force_browser:
            try:
                http_result = fetch_http(url, client=self._http, timeout_seconds=timeout_seconds, should_stop=self._should_stop)
                attempts.extend(http_result.attempts)
                html = http_result.html
                status_code = http_result.status_code
                final_url = http_result.final_url
                blocked, reason = needs_browser(status_code, html)
                payload = _payload(html, css_selector, str(final_url))
                if blocked or _payload_too_thin(payload, css_selector):
                    escalate_reason = reason or "extracted content too thin"
                    if attempts:
                        attempts[-1].quality_reason = escalate_reason
                else:
                    return _ok_result(
                        url=url,
                        final_url=final_url,
                        status_code=status_code,
                        engine="http",
                        html=html,
                        payload=payload,
                        attempts=attempts,
                    )
            except HttpFetchError as exc:
                attempts.extend(exc.attempts)
                escalate_reason = str(exc)

        last_error = ""
        for _ in range(2):
            check_cancelled(self._should_stop)
            try:
                browser_result = self._browser.fetch(
                    url,
                    wait_for=wait_for,
                    timeout_seconds=max(timeout_seconds, 45),
                    should_stop=self._should_stop,
                )
                attempts.append(browser_result.attempt)
                html = browser_result.html
                status_code = browser_result.status_code
                final_url = browser_result.final_url
                payload = _payload(html, css_selector, str(final_url))
                if not _payload_too_thin(payload, css_selector):
                    result = _ok_result(
                        url=url,
                        final_url=final_url,
                        status_code=status_code,
                        engine="browser",
                        html=html,
                        payload=payload,
                        attempts=attempts,
                    )
                    result.title = browser_result.title or result.title
                    return result
                last_error = escalate_reason or "extracted content too thin"
                if browser_result.attempt:
                    browser_result.attempt.quality_reason = last_error
            except BrowserFetchError as exc:
                attempts.append(exc.attempt)
                last_error = str(exc)

        return FetchResult(
            ok=False,
            url=url,
            final_url=final_url,
            status_code=status_code,
            engine="browser",
            html=html,
            error=last_error or escalate_reason,
            attempts=attempts,
        )


def _payload(html: str, css_selector: str | None, base_url: str = "") -> dict:
    items = list_topics(html, css_selector, base_url) if css_selector else []
    if items:
        markdown = "\n".join(f"- {item.title}" for item in items)
    else:
        markdown = to_markdown(html, css_selector=css_selector, main_content=True)
        if content_too_thin(markdown):
            markdown = to_markdown(html, css_selector=css_selector, main_content=False)
    return {
        "items": items,
        "markdown": markdown,
        "text": to_text(markdown),
        "title": extract_title(html),
    }


def _payload_too_thin(payload: dict, css_selector: str | None) -> bool:
    if css_selector:
        return len(payload["items"]) < 1
    return content_too_thin(payload["markdown"])


def _ok_result(*, url: str, final_url: str, status_code: int | None, engine: str, html: str, payload: dict, attempts) -> FetchResult:
    return FetchResult(
        ok=True,
        url=url,
        final_url=final_url,
        status_code=status_code,
        engine=engine,
        title=payload["title"],
        html=html,
        markdown=payload["markdown"],
        text=payload["text"],
        items=payload["items"],
        attempts=attempts,
    )
