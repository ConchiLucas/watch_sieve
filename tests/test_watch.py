from watch_sieve.store import MemoryTopicStore, StoredTitleRow, TitleRecord
from watch_sieve.watch import parse_keywords, parse_watch_payload, prefilter_titles


def test_parse_keywords_splits_chinese_commas() -> None:
    assert parse_keywords("Agent 工作流，本地 GPU,秋招") == ["Agent 工作流", "本地 GPU", "秋招"]


def test_prefilter_keeps_interest_hits() -> None:
    rows = [
        StoredTitleRow(title="27届秋招", url="", site_id="v2ex", site_name="V2EX"),
        StoredTitleRow(title="想买一口铁锅", url="", site_id="v2ex", site_name="V2EX"),
    ]
    hits = prefilter_titles(rows, ["秋招", "Agent"])
    assert [row.title for row in hits] == ["27届秋招"]


def test_prefilter_news_topics_use_event_hints() -> None:
    rows = [
        StoredTitleRow(
            title="AI热潮推升韩国电力需求，或将增建20座核反应堆",
            url="",
            site_id="linux_do",
            site_name="LINUX DO",
        ),
        StoredTitleRow(
            title="国内大模型 API，你代码里锁的是具体版本号还是最新版别名？",
            url="",
            site_id="linux_do",
            site_name="LINUX DO",
        ),
        StoredTitleRow(title="公司研发说，token断供了就只能罢工了", url="", site_id="v2ex", site_name="V2EX"),
    ]
    hits = prefilter_titles(rows, ["国际新闻大事件", "国内新闻大事件"])
    assert [row.title for row in hits] == ["AI热潮推升韩国电力需求，或将增建20座核反应堆"]


def test_parse_watch_payload_reads_fenced_json() -> None:
    payload = parse_watch_payload('```json\n[{"id": 1, "keep": true, "interest": "秋招", "reason": "招聘"}]\n```')
    assert payload[0]["keep"] is True


def test_memory_store_roundtrip_watch() -> None:
    store = MemoryTopicStore()
    store.upsert_titles(
        [
            TitleRecord(
                site_id="v2ex",
                site_name="V2EX",
                site_url="https://v2ex.com/",
                category="forum",
                title="27届秋招",
                url="https://v2ex.com/t/1",
            )
        ]
    )
    keywords, revision = store.save_watch_interests("秋招")
    assert "秋招" in keywords
    pending = store.pending_watch_titles(revision)
    assert pending[0].title == "27届秋招"
    store.upsert_watch(
        pending[0],
        keep=True,
        interest="秋招",
        reason="招聘",
        provider_id="antigravity-gemini-3-7-flash-high",
        model="gemini-3.7-flash-high",
        interests_revision=revision,
    )
    kept = store.list_kept_watches()
    assert len(kept) == 1
    assert store.pending_watch_titles(revision) == []
