import json
from pathlib import Path

from watch_sieve.titles import TitlesResponse, _write_cache, empty_response, query_topics

CACHE = Path(__file__).resolve().parents[1] / "data" / "latest.json"


def test_empty_response_has_configured_sites() -> None:
    payload = empty_response()
    ids = [site.id for site in payload.sites]
    assert ids == ["v2ex", "linux_do"]
    assert payload.fetched_at is None
    assert payload.sites[0].items == []


def test_query_filters_and_pagination(memory_store) -> None:
    from datetime import datetime, timezone
    from watch_sieve.store import SiteStatus, TitleRecord

    seen = datetime(2026, 9, 7, 1, tzinfo=timezone.utc)
    memory_store.upsert_site(SiteStatus("v2ex", "V2EX", "https://v2ex.com/", "forum", True, "", seen))
    memory_store.upsert_site(SiteStatus("linux_do", "LINUX DO", "https://linux.do/", "forum", True, "", seen))
    memory_store.upsert_titles(
        [
            TitleRecord("v2ex", "V2EX", "https://v2ex.com/", "forum", "现在还适合转码吗？", "https://v2ex.com/t/1", seen),
            TitleRecord("v2ex", "V2EX", "https://v2ex.com/", "forum", "GPT-6 Astra 建模大赛", "https://v2ex.com/t/2", seen),
            TitleRecord("linux_do", "LINUX DO", "https://linux.do/", "forum", "请不要把互联网上的戾气带来这里！", "https://linux.do/t/3", seen),
        ]
    )

    all_rows = query_topics()
    assert all_rows.total == 3
    assert all_rows.page_size == 50
    assert all_rows.items[0].category_label == "论坛"

    v2ex = query_topics(site_id="v2ex")
    assert v2ex.total == 2
    assert {row.site_id for row in v2ex.items} == {"v2ex"}

    keyword = query_topics(q="转码")
    assert keyword.total == 1
    assert keyword.items[0].title == "现在还适合转码吗？"

    paged = query_topics(page=2, page_size=2)
    assert paged.total == 3
    assert paged.page == 2
    assert len(paged.items) == 1


def test_cache_write_replaces_file_atomically(tmp_path, monkeypatch) -> None:
    from watch_sieve import titles as titles_mod

    cache = tmp_path / "latest.json"
    cache.write_text("old", encoding="utf-8")
    monkeypatch.setattr(titles_mod, "CACHE_PATH", cache)

    payload = TitlesResponse(fetched_at=None, sites=[])
    _write_cache(payload)

    assert json.loads(cache.read_text(encoding="utf-8")) == {
        "fetched_at": None,
        "refreshing": False,
        "sites": [],
    }
    assert not cache.with_suffix(".json.tmp").exists()


def test_busy_refresh_returns_cache_without_crawling(tmp_path, monkeypatch):
    from watch_sieve import titles

    monkeypatch.setattr(titles, "CACHE_PATH", tmp_path / "latest.json")
    with titles._process_refresh_lock() as acquired:
        assert acquired
        assert titles.read_cached().refreshing
        monkeypatch.setattr(titles, "WatchCrawler", lambda **kw: (_ for _ in ()).throw(AssertionError("duplicate fetch")))
        assert titles.refresh_titles().refreshing
    assert not titles.read_cached().refreshing


def test_start_refresh_returns_without_waiting(tmp_path, monkeypatch):
    import threading
    from watch_sieve import titles

    monkeypatch.setattr(titles, "CACHE_PATH", tmp_path / "latest.json")
    titles._write_cache(titles.empty_response())
    entered = threading.Event()
    release = threading.Event()

    def blocked(*args, **kwargs):
        entered.set()
        release.wait(timeout=2)
        return titles.empty_response()

    monkeypatch.setattr(titles, "refresh_titles", blocked)
    payload = titles.start_refresh()
    assert entered.wait(timeout=1)
    assert payload.fetched_at is None
    release.set()


def test_partial_failure_keeps_old_titles_and_timestamp(tmp_path, monkeypatch, memory_store):
    from datetime import datetime, timezone
    from watch_sieve import titles
    from watch_sieve.models import FetchResult, Topic
    from watch_sieve.store import SiteStatus, TitleRecord

    monkeypatch.setattr(titles, "CACHE_PATH", tmp_path / "latest.json")
    old_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    old = titles.empty_response()
    old.fetched_at = old_time
    old.sites[1].items = [Topic(title="旧标题")]
    titles._write_cache(old)
    memory_store.upsert_site(SiteStatus("linux_do", "LINUX DO", "https://linux.do/", "forum", True, "", old_time))
    memory_store.upsert_titles(
        [TitleRecord("linux_do", "LINUX DO", "https://linux.do/", "forum", "旧标题", "", old_time)]
    )

    class Crawler:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def fetch_site(self, site):
            return FetchResult(ok=site.id == "v2ex", url=str(site.url), engine="http", items=[Topic(title="新标题")] if site.id == "v2ex" else [])

    monkeypatch.setattr(titles, "WatchCrawler", Crawler)
    for _ in range(2):
        payload = titles.refresh_titles()
        assert not payload.sites[1].ok
        assert payload.sites[1].fetched_at == old_time
        page = titles.query_topics()
        assert page.failed_sites == ["LINUX DO"]
        assert [(row.title, row.fetched_at) for row in page.items if row.site_id == "linux_do"] == [("旧标题", old_time)]


def test_stop_after_site_does_not_fetch_next_or_write_cache(tmp_path, monkeypatch):
    import pytest
    from watch_sieve import titles
    from watch_sieve.cancellation import RefreshCancelled
    from watch_sieve.models import FetchResult

    monkeypatch.setattr(titles, "CACHE_PATH", tmp_path / "latest.json")
    titles._write_cache(titles.empty_response())
    before = titles.CACHE_PATH.read_bytes()
    fetched = []

    class Crawler:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def fetch_site(self, site):
            fetched.append(site.id)
            return FetchResult(ok=True, url=str(site.url), engine="http")

    monkeypatch.setattr(titles, "WatchCrawler", Crawler)
    with pytest.raises(RefreshCancelled):
        titles.refresh_titles(should_stop=lambda: bool(fetched))
    assert fetched == ["v2ex"]
    assert titles.CACHE_PATH.read_bytes() == before
    assert not titles.is_refreshing()


def test_other_process_lock_is_visible_and_released_on_exit(tmp_path, monkeypatch):
    import subprocess
    import sys
    from watch_sieve import titles

    monkeypatch.setattr(titles, "CACHE_PATH", tmp_path / "latest.json")
    child = subprocess.Popen(
        [sys.executable, "-c", "import fcntl,sys; f=open(sys.argv[1],'a+'); fcntl.flock(f,fcntl.LOCK_EX); print('locked',flush=True); sys.stdin.read()", str(titles.CACHE_PATH.with_suffix(".lock"))],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
    )
    try:
        assert child.stdout.readline().strip() == "locked"
        assert titles.read_cached().refreshing
        assert titles.refresh_titles().refreshing
    finally:
        try:
            child.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()
            child.communicate()
    assert not titles.read_cached().refreshing


def test_refresh_recovers_corrupt_cache(tmp_path, monkeypatch):
    from watch_sieve import titles
    from watch_sieve.models import FetchResult

    monkeypatch.setattr(titles, "CACHE_PATH", tmp_path / "latest.json")
    titles.CACHE_PATH.write_text("broken json")

    class Crawler:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def fetch_site(self, site):
            return FetchResult(ok=True, url=str(site.url), engine="http")

    monkeypatch.setattr(titles, "WatchCrawler", Crawler)
    assert all(site.ok for site in titles.refresh_titles().sites)
    assert len(titles.read_cached().sites) == 2
