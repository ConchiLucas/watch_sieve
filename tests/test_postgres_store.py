from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest
from dotenv import load_dotenv

from watch_sieve.store import PostgresTopicStore, SiteStatus, TitleRecord, ROOT, set_store


@pytest.mark.postgres
def test_postgres_dedup_keeps_first_seen():
    load_dotenv(ROOT / ".env")
    url = os.getenv("WATCH_SIEVE_DATABASE_URL", "").strip()
    if not url:
        pytest.skip("WATCH_SIEVE_DATABASE_URL is not set")
    store = PostgresTopicStore(url)
    set_store(store)
    site_id = "test_dedup_v2ex"
    try:
        first = datetime(2026, 9, 8, 1, tzinfo=timezone.utc)
        store.upsert_site(
            SiteStatus(site_id, "V2EX", "https://v2ex.com/", "forum", True, "", first)
        )
        store.upsert_titles(
            [
                TitleRecord(
                    site_id=site_id,
                    site_name="V2EX",
                    site_url="https://v2ex.com/",
                    category="forum",
                    title="测试去重",
                    url="https://v2ex.com/t/watch-sieve-dedup#reply1",
                    seen_at=first,
                )
            ]
        )
        store.upsert_titles(
            [
                TitleRecord(
                    site_id=site_id,
                    site_name="V2EX",
                    site_url="https://v2ex.com/",
                    category="forum",
                    title="测试去重",
                    url="https://v2ex.com/t/watch-sieve-dedup#reply8",
                    seen_at=datetime(2026, 9, 8, 2, tzinfo=timezone.utc),
                )
            ]
        )
        page = store.query_topics(site_id=site_id)
        assert page.total == 1
        assert page.items[0].url == "https://v2ex.com/t/watch-sieve-dedup"
        assert page.items[0].fetched_at == first
    finally:
        with store._pool.connection() as conn:
            conn.execute("DELETE FROM titles WHERE site_id = %s", (site_id,))
            conn.execute("DELETE FROM site_status WHERE site_id = %s", (site_id,))
            conn.commit()
        set_store(None)
