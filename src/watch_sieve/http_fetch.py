from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx

from watch_sieve.cancellation import check_cancelled
from watch_sieve.headers import decode_html, request_headers
from watch_sieve.models import FetchAttempt


@dataclass
class HttpFetch:
    html: str
    status_code: int
    final_url: str
    attempts: list[FetchAttempt]


def fetch_http(
    url: str,
    *,
    client: httpx.Client,
    timeout_seconds: int = 30,
    retries: int = 3,
    retry_interval: float = 0.8,
    should_stop: Callable[[], bool] | None = None,
) -> HttpFetch:
    last_error = "http fetch failed"
    attempts: list[FetchAttempt] = []
    timeout = httpx.Timeout(timeout_seconds, connect=min(10.0, timeout_seconds))

    for index in range(retries):
        check_cancelled(should_stop)
        try:
            response = client.get(
                url,
                headers=request_headers(url),
                timeout=timeout,
                follow_redirects=True,
            )
            check_cancelled(should_stop)
            html = decode_html(response.content, response.encoding)
            attempt = FetchAttempt(
                engine="http",
                status_code=response.status_code,
                final_url=str(response.url),
            )
            if not html.strip():
                attempt.error = "empty body"
                attempts.append(attempt)
                last_error = attempt.error
            else:
                attempts.append(attempt)
                return HttpFetch(
                    html=html,
                    status_code=response.status_code,
                    final_url=str(response.url),
                    attempts=attempts,
                )
        except httpx.HTTPError as exc:
            last_error = str(exc)
            attempts.append(FetchAttempt(engine="http", error=last_error))

        if index < retries - 1:
            time.sleep(retry_interval)

    raise HttpFetchError(last_error, attempts)


class HttpFetchError(RuntimeError):
    def __init__(self, message: str, attempts: list[FetchAttempt]):
        super().__init__(message)
        self.attempts = attempts
