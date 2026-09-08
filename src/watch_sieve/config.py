from __future__ import annotations

from pathlib import Path

import yaml

from watch_sieve.models import WatchConfig


def load_config(path: str | Path) -> WatchConfig:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return WatchConfig.model_validate(data)
