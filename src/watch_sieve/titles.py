from __future__ import annotations

import json
import os
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

import fcntl

from pydantic import BaseModel, Field

from watch_sieve.config import load_config
from watch_sieve.crawler import WatchCrawler
from watch_sieve.models import CATEGORY_LABELS, SiteConfig, Topic

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "configs" / "sites.yaml"
CACHE_PATH = ROOT / "data" / "latest.json"
BEIJING = timezone(timedelta(hours=8))
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 50
_LOCK = threading.Lock()
_REFRESHING = False


class SiteTitles(BaseModel):
    id: str
    name: str
    url: str
    category: str = "other"
    ok: bool = True
    error: str = ""
    items: list[Topic] = Field(default_factory=list)


class TitlesResponse(BaseModel):
    fetched_at: datetime | None = None
    refreshing: bool = False
    sites: list[SiteTitles]


class NamedOption(BaseModel):
    id: str
    name: str


class FilterMeta(BaseModel):
    sites: list[NamedOption]
    categories: list[NamedOption]


class TopicRow(BaseModel):
    title: str
    url: str = ""
    site_id: str
    site_name: str
    site_url: str
    category: str
    category_label: str
    fetched_at: datetime | None = None


class TopicPage(BaseModel):
    total: int
    page: int
    page_size: int
    fetched_at: datetime | None = None
    refreshing: bool = False
    failed_sites: list[str] = Field(default_factory=list)
    items: list[TopicRow]


def empty_response(config_path: Path = DEFAULT_CONFIG) -> TitlesResponse:
    config = load_config(config_path)
    return TitlesResponse(refreshing=_REFRESHING, sites=[_shell(site) for site in config.sites])


def read_cached(config_path: Path = DEFAULT_CONFIG) -> TitlesResponse:
    if not CACHE_PATH.exists():
        return empty_response(config_path)
    data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    cached = TitlesResponse.model_validate(data)
    cached.refreshing = _REFRESHING
    _fill_categories(cached, config_path)
    return cached


def refresh_titles(config_path: Path = DEFAULT_CONFIG) -> TitlesResponse:
    global _REFRESHING
    with _LOCK:
        with _process_refresh_lock():
            _REFRESHING = True
            try:
                config = load_config(config_path)
                sites: list[SiteTitles] = []
                with WatchCrawler() as crawler:
                    for site in config.sites:
                        result = crawler.fetch_site(site)
                        sites.append(
                            SiteTitles(
                                id=site.id,
                                name=site.name,
                                url=str(site.url),
                                category=site.category,
                                ok=result.ok,
                                error=_public_error(result.error) if not result.ok else "",
                                items=result.items,
                            )
                        )
                payload = TitlesResponse(
                    fetched_at=datetime.now(timezone.utc),
                    refreshing=False,
                    sites=sites,
                )
                _write_cache(payload)
                return payload
            finally:
                _REFRESHING = False


@contextmanager
def _process_refresh_lock() -> Iterator[None]:
    """Prevent the web process and SnailJob worker from refreshing together."""
    lock_path = CACHE_PATH.with_suffix(".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _write_cache(payload: TitlesResponse) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = CACHE_PATH.with_suffix(".json.tmp")
    temporary.write_text(payload.model_dump_json(indent=2), encoding="utf-8")
    os.replace(temporary, CACHE_PATH)


def filter_meta(config_path: Path = DEFAULT_CONFIG) -> FilterMeta:
    config = load_config(config_path)
    return FilterMeta(
        sites=[NamedOption(id=site.id, name=site.name) for site in config.sites],
        categories=[NamedOption(id=key, name=label) for key, label in CATEGORY_LABELS.items()],
    )


def query_topics(
    *,
    q: str = "",
    site_id: str = "",
    category: str = "",
    date: str = "",
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    config_path: Path = DEFAULT_CONFIG,
) -> TopicPage:
    cached = read_cached(config_path)
    rows = _flatten(cached)
    keyword = q.strip().lower()
    if keyword:
        rows = [row for row in rows if keyword in row.title.lower()]
    if site_id:
        rows = [row for row in rows if row.site_id == site_id]
    if category:
        rows = [row for row in rows if row.category == category]
    if date:
        rows = [row for row in rows if _day(row.fetched_at) == date]
    page_size = min(max(page_size, 1), MAX_PAGE_SIZE)
    total = len(rows)
    last_page = max(1, (total + page_size - 1) // page_size) if total else 1
    page = min(max(page, 1), last_page)
    start = (page - 1) * page_size
    failed = [site.name for site in cached.sites if not site.ok]
    return TopicPage(
        total=total,
        page=page,
        page_size=page_size,
        fetched_at=cached.fetched_at,
        refreshing=cached.refreshing,
        failed_sites=failed,
        items=rows[start : start + page_size],
    )


def _flatten(cached: TitlesResponse) -> list[TopicRow]:
    rows: list[TopicRow] = []
    for site in cached.sites:
        if not site.ok:
            continue
        for item in site.items:
            rows.append(
                TopicRow(
                    title=item.title,
                    url=item.url,
                    site_id=site.id,
                    site_name=site.name,
                    site_url=site.url,
                    category=site.category,
                    category_label=CATEGORY_LABELS.get(site.category, site.category),
                    fetched_at=cached.fetched_at,
                )
            )
    return rows


def _fill_categories(cached: TitlesResponse, config_path: Path) -> None:
    config = {site.id: site for site in load_config(config_path).sites}
    for site in cached.sites:
        if site.category and site.category != "other":
            continue
        mapped = config.get(site.id)
        if mapped is not None:
            site.category = mapped.category


def _day(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(BEIJING).date().isoformat()


def _shell(site: SiteConfig) -> SiteTitles:
    return SiteTitles(id=site.id, name=site.name, url=str(site.url), category=site.category)


def _public_error(error: str) -> str:
    return "抓取失败"
