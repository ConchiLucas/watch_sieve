from watch_sieve.extract import extract_title, list_titles, list_topics, to_markdown


def test_extract_title_and_markdown() -> None:
    html = """
    <html>
      <head><title>Hello WatchSieve</title></head>
      <body>
        <nav>Home</nav>
        <article>
          <h1>News</h1>
          <p>Useful paragraph about a watched site.</p>
          <script>window.track = 1</script>
        </article>
        <footer>copyright</footer>
      </body>
    </html>
    """
    assert extract_title(html) == "Hello WatchSieve"
    markdown = to_markdown(html)
    assert "Useful paragraph" in markdown
    assert "window.track" not in markdown
    assert "copyright" not in markdown


def test_css_selector_limits_content() -> None:
    html = """
    <html><body>
      <p class="noise">ignore me</p>
      <p class="keep">keep this sentence for the selector test.</p>
    </body></html>
    """
    markdown = to_markdown(html, css_selector=".keep", main_content=False)
    assert "keep this sentence" in markdown
    assert "ignore me" not in markdown


def test_missing_selector_returns_empty() -> None:
    html = "<html><body><p>no quotes here yet</p></body></html>"
    assert to_markdown(html, css_selector=".quote") == ""


def test_list_titles_dedupes_and_strips() -> None:
    html = """
    <html><body>
      <span class="item_title"><a href="/t/1">  现在还适合转码吗？ </a></span>
      <span class="item_title"><a href="/t/2">现在还适合转码吗？</a></span>
      <span class="item_title"><a href="/t/3">GPT-6 Astra 建模大赛</a></span>
    </body></html>
    """
    assert list_titles(html, "span.item_title a") == ["现在还适合转码吗？", "GPT-6 Astra 建模大赛"]
    topics = list_topics(html, "span.item_title a", "https://v2ex.com/")
    assert topics[0].url == "https://v2ex.com/t/1"
