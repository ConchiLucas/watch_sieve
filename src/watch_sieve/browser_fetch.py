from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from time import monotonic

_local_browsers = Path(__file__).resolve().parents[2] / ".playwright-browsers"
if _local_browsers.exists():
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(_local_browsers))

from playwright.sync_api import Browser, Playwright, TimeoutError as PlaywrightTimeout, sync_playwright

from watch_sieve.cancellation import RefreshCancelled, check_cancelled
from watch_sieve.headers import BROWSER_HEADERS
from watch_sieve.models import FetchAttempt


@dataclass
class BrowserFetch:
    html: str
    status_code: int | None
    final_url: str
    title: str
    attempt: FetchAttempt


class BrowserSession:
    def __init__(self) -> None:
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None

    def start(self) -> None:
        if self._browser is not None:
            return
        self._playwright = sync_playwright().start()
        launch_args = {
            "headless": True,
            "args": ["--disable-blink-features=AutomationControlled", "--headless=new"],
        }
        chrome = _chrome_executable()
        if chrome is not None:
            launch_args["executable_path"] = str(chrome)
        self._browser = self._playwright.chromium.launch(**launch_args)

    def close(self) -> None:
        if self._browser is not None:
            self._browser.close()
            self._browser = None
        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None

    def fetch(
        self,
        url: str,
        *,
        wait_for: str | None = None,
        timeout_seconds: int = 30,
        should_stop: Callable[[], bool] | None = None,
    ) -> BrowserFetch:
        check_cancelled(should_stop)
        self.start()
        assert self._browser is not None
        timeout_ms = timeout_seconds * 1000
        started = monotonic()
        context = self._browser.new_context(
            user_agent=BROWSER_HEADERS["User-Agent"],
            locale="zh-CN",
            viewport={"width": 1280, "height": 900},
            extra_http_headers={
                "Accept-Language": BROWSER_HEADERS["Accept-Language"],
                "Upgrade-Insecure-Requests": "1",
            },
        )
        page = context.new_page()
        status_code: int | None = None
        try:
            response = page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            check_cancelled(should_stop)
            status_code = response.status if response is not None else None
            page.wait_for_selector("body", timeout=min(_remaining_ms(started, timeout_ms), 10_000))
            check_cancelled(should_stop)
            _wait_out_challenge(page, _remaining_ms(started, timeout_ms))
            check_cancelled(should_stop)
            if wait_for:
                try:
                    page.wait_for_selector(
                        wait_for,
                        state="attached",
                        timeout=_remaining_ms(started, timeout_ms),
                    )
                except PlaywrightTimeout:
                    page.wait_for_timeout(2000)
            check_cancelled(should_stop)
            html = page.content()
            title = page.title()
            final_url = page.url
            return BrowserFetch(
                html=html,
                status_code=status_code,
                final_url=final_url,
                title=title,
                attempt=FetchAttempt(engine="browser", status_code=status_code, final_url=final_url),
            )
        except RefreshCancelled:
            raise
        except PlaywrightTimeout as exc:
            raise BrowserFetchError(f"browser timeout: {exc}", FetchAttempt(engine="browser", error=str(exc))) from exc
        except Exception as exc:
            raise BrowserFetchError(str(exc), FetchAttempt(engine="browser", error=str(exc))) from exc
        finally:
            context.close()


def _chrome_executable() -> Path | None:
    matches = sorted(
        _local_browsers.glob(
            "chromium-*/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"
        )
    )
    return matches[-1] if matches else None


def _wait_out_challenge(page, timeout_ms: float) -> None:
    title = (page.title() or "").strip()
    if title and "just a moment" not in title.lower():
        return
    try:
        page.wait_for_function(
            """() => {
                const title = (document.title || '').trim();
                return title.length > 3 && !/just a moment/i.test(title);
            }""",
            timeout=timeout_ms,
        )
    except PlaywrightTimeout:
        return


def _remaining_ms(started: float, timeout_ms: int) -> float:
    return max(1000.0, timeout_ms - (monotonic() - started) * 1000)


class BrowserFetchError(RuntimeError):
    def __init__(self, message: str, attempt: FetchAttempt):
        super().__init__(message)
        self.attempt = attempt
