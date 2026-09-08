from watch_sieve.quality import content_too_thin, needs_browser


def test_empty_html_needs_browser() -> None:
    blocked, reason = needs_browser(200, "<html></html>")
    assert blocked
    assert "empty" in reason or "body" in reason or "shell" in reason


def test_challenge_page_needs_browser() -> None:
    html = "<html><body><script src='/cdn-cgi/challenge-platform/x'></script></body></html>"
    blocked, reason = needs_browser(200, html)
    assert blocked
    assert "challenge" in reason


def test_forbidden_needs_browser() -> None:
    blocked, reason = needs_browser(403, "<html><body>nope</body></html>")
    assert blocked
    assert "403" in reason


def test_real_article_does_not_need_browser() -> None:
    html = """
    <html><body>
      <article>
        <h1>Stable fetch</h1>
        <p>This page has enough visible text and semantic tags for HTTP extraction.</p>
        <p>A second paragraph keeps the content above the thin-page threshold.</p>
      </article>
    </body></html>
    """
    blocked, reason = needs_browser(200, html)
    assert blocked is False
    assert reason == ""


def test_thin_markdown() -> None:
    assert content_too_thin("ok")
    assert content_too_thin("# Quotes to Scrape\n\n[Login](/login)")
    assert not content_too_thin(
        "This extracted markdown is long enough to keep after dropping navigation chrome."
    )
