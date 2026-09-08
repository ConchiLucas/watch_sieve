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


def test_query_filters_and_pagination(tmp_path, monkeypatch) -> None:
    from watch_sieve import titles as titles_mod

    cache = tmp_path / "latest.json"
    cache.write_text(
        json.dumps(
            {
                "fetched_at": "2026-09-07T01:00:00+00:00",
                "sites": [
                    {
                        "id": "v2ex",
                        "name": "V2EX",
                        "url": "https://v2ex.com/",
                        "category": "forum",
                        "ok": True,
                        "items": [
                            {"title": "现在还适合转码吗？", "url": "https://v2ex.com/t/1"},
                            {"title": "GPT-6 Astra 建模大赛", "url": "https://v2ex.com/t/2"},
                        ],
                    },
                    {
                        "id": "linux_do",
                        "name": "LINUX DO",
                        "url": "https://linux.do/",
                        "category": "forum",
                        "ok": True,
                        "items": [{"title": "请不要把互联网上的戾气带来这里！", "url": "https://linux.do/t/3"}],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(titles_mod, "CACHE_PATH", cache)

    all_rows = query_topics()
    assert all_rows.total == 3
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
