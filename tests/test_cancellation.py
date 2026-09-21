from unittest.mock import Mock

import httpx
import pytest

from watch_sieve.cancellation import RefreshCancelled
from watch_sieve.http_fetch import fetch_http


def test_cancelled_http_does_not_retry():
    stopped = False
    calls = []

    def handle(request):
        nonlocal stopped
        calls.append(request)
        stopped = True
        raise httpx.ReadTimeout("timeout", request=request)

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(RefreshCancelled):
            fetch_http("https://example.com", client=client, retry_interval=0, should_stop=lambda: stopped)
    assert len(calls) == 1


def test_cancelled_browser_closes_context_and_propagates():
    from watch_sieve.browser_fetch import BrowserSession

    session = BrowserSession()
    session._browser = Mock()
    context = session._browser.new_context.return_value
    page = context.new_page.return_value
    stopped = False

    def navigate(*args, **kwargs):
        nonlocal stopped
        stopped = True
        return None

    page.goto.side_effect = navigate
    with pytest.raises(RefreshCancelled):
        session.fetch("https://example.com", should_stop=lambda: stopped)
    context.close.assert_called_once()
    page.wait_for_selector.assert_not_called()


def test_cancelled_crawler_does_not_fall_back_to_browser(monkeypatch):
    from watch_sieve import crawler

    def cancelled(*args, **kwargs):
        raise RefreshCancelled("stopped")

    monkeypatch.setattr(crawler, "fetch_http", cancelled)
    with crawler.WatchCrawler() as worker:
        worker._browser = Mock()
        with pytest.raises(RefreshCancelled):
            worker.fetch("https://example.com")
        worker._browser.fetch.assert_not_called()
