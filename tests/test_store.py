from dataclasses import replace
from datetime import datetime, timezone

from watch_sieve.store import MemoryTopicStore, TitleRecord, canonical_key, canonical_url


def test_canonical_url_strips_fragment_and_slash():
    assert canonical_url("https://v2ex.com/t/1240256#reply84") == "https://v2ex.com/t/1240256"
    assert canonical_key("标题", "https://V2EX.com/t/1240256#reply90") == canonical_key(
        "标题", "https://v2ex.com/t/1240256"
    )


def test_same_url_is_not_inserted_twice():
    store = MemoryTopicStore()
    first = datetime(2026, 9, 8, 1, tzinfo=timezone.utc)
    second = datetime(2026, 9, 8, 2, tzinfo=timezone.utc)
    record = TitleRecord(
        site_id="v2ex",
        site_name="V2EX",
        site_url="https://v2ex.com/",
        category="forum",
        title="同一帖",
        url="https://v2ex.com/t/1#reply1",
        seen_at=first,
    )
    store.upsert_titles([record])
    store.upsert_titles(
        [replace(record, title="同一帖（改标题）", url="https://v2ex.com/t/1#reply9", seen_at=second)]
    )
    page = store.query_topics()
    assert page.total == 1
    assert page.items[0].title == "同一帖（改标题）"
    assert page.items[0].url == "https://v2ex.com/t/1"
    assert page.items[0].fetched_at == first
