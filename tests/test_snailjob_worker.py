from __future__ import annotations

import json
from pathlib import Path

from watch_sieve.models import Topic
from watch_sieve.snailjob_worker import _config_path, _summarize
from watch_sieve.titles import SiteTitles, TitlesResponse


def test_summarize_marks_failed_sites() -> None:
    payload = TitlesResponse(
        sites=[
            SiteTitles(
                id="ok",
                name="正常站点",
                url="https://example.com",
                items=[Topic(title="一"), Topic(title="二")],
            ),
            SiteTitles(
                id="failed",
                name="失败站点",
                url="https://example.org",
                ok=False,
                error="抓取失败",
            ),
        ]
    )

    summary = _summarize(payload)

    assert summary.site_count == 2
    assert summary.topic_count == 2
    assert summary.failed_sites == ("失败站点",)
    assert "失败站点" in summary.message


def test_config_path_accepts_snailjob_json_params() -> None:
    path = _config_path(json.dumps({"config": "configs/sites.example.yaml"}))

    assert path == Path(__file__).resolve().parents[1] / "configs" / "sites.example.yaml"
