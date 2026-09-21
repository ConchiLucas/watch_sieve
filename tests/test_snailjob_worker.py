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


def test_executor_result_mapping_and_stop_signal(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from watch_sieve import snailjob_worker as worker
    from watch_sieve.cancellation import RefreshCancelled

    sdk = SimpleNamespace(
        ThreadPoolCache=SimpleNamespace(event_is_set=Mock(return_value=True)),
        SnailLog=SimpleNamespace(REMOTE=Mock()),
        ExecuteResult=SimpleNamespace(success=lambda message: (True, message), failure=lambda message: (False, message)),
    )
    args = SimpleNamespace(job_params=None, task_batch_id=42)
    for summary, success in [
        (worker.RefreshSummary(2, 10, ()), True),
        (worker.RefreshSummary(2, 10, ("LINUX DO",)), False),
        (worker.RefreshSummary(2, 10, ("LINUX DO",), skipped=True), True),
    ]:
        monkeypatch.setattr(worker, "run_refresh", lambda *a, **kw: summary)
        assert worker.execute_refresh(args, sdk)[0] is success

    def stopped(*a, should_stop):
        assert should_stop()
        raise RefreshCancelled("抓取已停止")

    monkeypatch.setattr(worker, "run_refresh", stopped)
    assert worker.execute_refresh(args, sdk) == (False, "抓取已停止")
    sdk.ThreadPoolCache.event_is_set.assert_called_once_with(42)
    sdk.SnailLog.REMOTE.exception.assert_not_called()

    def broken(*a, **kw):
        raise ValueError("bad config")
    monkeypatch.setattr(worker, "run_refresh", broken)
    assert worker.execute_refresh(args, sdk) == (False, "WatchSieve 抓取异常：bad config")
    sdk.SnailLog.REMOTE.exception.assert_called_once()


def test_judge_executor_result_mapping(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from watch_sieve import snailjob_worker as worker
    from watch_sieve.cancellation import RefreshCancelled
    from watch_sieve.judge import JudgeSummary

    sdk = SimpleNamespace(
        ThreadPoolCache=SimpleNamespace(event_is_set=Mock(return_value=True)),
        SnailLog=SimpleNamespace(REMOTE=Mock()),
        ExecuteResult=SimpleNamespace(success=lambda message: (True, message), failure=lambda message: (False, message)),
    )
    args = SimpleNamespace(task_batch_id=7)
    summary = JudgeSummary(
        model="gemini-3.7-flash-high",
        classified=12,
        classify_remaining=40,
        scanned=8,
        kept=2,
        skipped=6,
        watch_remaining=4,
    )
    monkeypatch.setattr(worker, "run_judge", lambda *a, **kw: summary)
    assert worker.execute_judge(args, sdk) == (True, summary.message)

    def stopped(*a, should_stop):
        assert should_stop()
        raise RefreshCancelled("抓取已停止")

    monkeypatch.setattr(worker, "run_judge", stopped)
    assert worker.execute_judge(args, sdk) == (False, "抓取已停止")

    def broken(*a, **kw):
        raise ValueError("no model")
    monkeypatch.setattr(worker, "run_judge", broken)
    ok, message = worker.execute_judge(args, sdk)
    assert ok is False
    assert "分类筛选异常" in message


def test_main_loads_explicit_env_and_registers_before_client_start(monkeypatch, tmp_path):
    import sys
    from types import SimpleNamespace
    from watch_sieve import snailjob_worker as worker

    events = []
    names = []
    def decorate(name):
        names.append(name)
        return lambda fn: fn
    sdk = SimpleNamespace(
        job=decorate,
        ExecutorManager=SimpleNamespace(register=lambda fn: events.append("register")),
        client_main=lambda: events.append("start"),
    )
    monkeypatch.setitem(sys.modules, "snailjob", sdk)
    monkeypatch.setattr(worker, "load_dotenv", lambda path: events.append(path))
    for key in ("SNAIL_NAMESPACE", "SNAIL_GROUP_NAME", "SNAIL_TOKEN"):
        monkeypatch.setenv(key, "test")
    monkeypatch.chdir(tmp_path)
    worker.main()
    assert names == ["watchSieveRefresh", "watchSieveJudge"]
    assert events == [worker.ROOT / ".env", "register", "register", "start"]
