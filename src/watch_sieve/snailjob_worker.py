from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from watch_sieve.titles import DEFAULT_CONFIG, TitlesResponse, refresh_titles

EXECUTOR_NAME = "watchSieveRefresh"


@dataclass(frozen=True)
class RefreshSummary:
    site_count: int
    topic_count: int
    failed_sites: tuple[str, ...]

    @property
    def message(self) -> str:
        message = f"抓取完成：{self.site_count} 个站点，{self.topic_count} 条标题"
        if self.failed_sites:
            message += f"；失败站点：{', '.join(self.failed_sites)}"
        return message


def run_refresh(job_params: Any = None) -> RefreshSummary:
    config_path = _config_path(job_params)
    payload = refresh_titles(config_path)
    return _summarize(payload)


def _summarize(payload: TitlesResponse) -> RefreshSummary:
    return RefreshSummary(
        site_count=len(payload.sites),
        topic_count=sum(len(site.items) for site in payload.sites if site.ok),
        failed_sites=tuple(site.name for site in payload.sites if not site.ok),
    )


def _config_path(job_params: Any) -> Path:
    value = job_params
    if isinstance(value, str) and value.strip().startswith("{"):
        value = json.loads(value)
    if isinstance(value, dict):
        value = value.get("config")
    if not value:
        return DEFAULT_CONFIG
    path = Path(str(value)).expanduser()
    if not path.is_absolute():
        path = DEFAULT_CONFIG.parents[1] / path
    return path


def _validate_environment() -> None:
    required = ("SNAIL_NAMESPACE", "SNAIL_GROUP_NAME", "SNAIL_TOKEN")
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        names = ", ".join(missing)
        raise SystemExit(f"SnailJob 配置缺失：{names}。请从 .env.example 复制 .env 并填写控制台中的值。")


def main() -> None:
    load_dotenv()
    _validate_environment()
    try:
        import snailjob as sj
    except ModuleNotFoundError as exc:
        raise SystemExit('缺少 SnailJob 客户端，请运行 pip install -e ".[snailjob]"') from exc

    @sj.job(EXECUTOR_NAME)
    def refresh_executor(args: sj.JobArgs) -> sj.ExecuteResult:
        try:
            summary = run_refresh(args.job_params)
        except Exception as exc:
            message = f"WatchSieve 抓取异常：{exc}"
            sj.SnailLog.REMOTE.exception(message)
            return sj.ExecuteResult.failure(message)

        if summary.failed_sites:
            sj.SnailLog.REMOTE.error(summary.message)
            return sj.ExecuteResult.failure(summary.message)
        sj.SnailLog.REMOTE.info(summary.message)
        return sj.ExecuteResult.success(summary.message)

    sj.ExecutorManager.register(refresh_executor)
    sj.client_main()


if __name__ == "__main__":
    main()
