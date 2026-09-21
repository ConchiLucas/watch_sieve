from __future__ import annotations

import json
import logging
import os
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator

import fcntl

from pydantic import BaseModel, Field, ValidationError

from watch_sieve.cancellation import check_cancelled
from watch_sieve.config import load_config
from watch_sieve.crawler import WatchCrawler
from watch_sieve.models import CATEGORY_LABELS, SiteConfig, Topic
from watch_sieve.store import SiteStatus, TitleRecord, get_store

_log = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "configs" / "sites.yaml"
CACHE_PATH = ROOT / "data" / "latest.json"
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 50


class SiteTitles(BaseModel):
    id: str
    name: str
    url: str
    category: str = "other"
    ok: bool = True
    error: str = ""
    fetched_at: datetime | None = None
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
    return TitlesResponse(refreshing=is_refreshing(), sites=[_shell(site) for site in config.sites])


def read_cached(config_path: Path = DEFAULT_CONFIG) -> TitlesResponse:
    if not CACHE_PATH.exists():
        return empty_response(config_path)
    data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    cached = TitlesResponse.model_validate(data)
    cached.refreshing = is_refreshing()
    _fill_categories(cached, config_path)
    return cached


def refresh_titles(
    config_path: Path = DEFAULT_CONFIG,
    *,
    should_stop: Callable[[], bool] | None = None,
) -> TitlesResponse:
    check_cancelled(should_stop)
    with _process_refresh_lock() as acquired:
        if not acquired:
            payload = read_cached(config_path)
            payload.refreshing = True
            return payload
        config = load_config(config_path)
        try:
            previous = read_cached(config_path)
        except (json.JSONDecodeError, ValidationError):
            # A damaged old cache must not prevent a fresh successful crawl.
            previous = empty_response(config_path)
        old_sites = {site.id: site for site in previous.sites}
        sites: list[SiteTitles] = []
        with WatchCrawler(should_stop=should_stop) as crawler:
            for site in config.sites:
                check_cancelled(should_stop)
                result = crawler.fetch_site(site)
                check_cancelled(should_stop)
                old = old_sites.get(site.id)
                # Never reuse data if the configured source URL has changed.
                if old is not None and old.url != str(site.url):
                    old = None
                fetched_at = datetime.now(timezone.utc) if result.ok else None
                if not result.ok and old is not None:
                    fetched_at = old.fetched_at or previous.fetched_at
                sites.append(
                    SiteTitles(
                        id=site.id,
                        name=site.name,
                        url=str(site.url),
                        category=site.category,
                        ok=result.ok,
                        error=_public_error(result.error) if not result.ok else "",
                        items=result.items if result.ok else (old.items if old else []),
                        fetched_at=fetched_at,
                    )
                )
        payload = TitlesResponse(
            fetched_at=datetime.now(timezone.utc), refreshing=False, sites=sites,
        )
        check_cancelled(should_stop)
        _persist(payload)
        _write_cache(payload)
        return payload


def start_refresh(config_path: Path = DEFAULT_CONFIG) -> TitlesResponse:
    thread = threading.Thread(
        target=_refresh_in_background,
        args=(config_path,),
        daemon=True,
        name="watch-sieve-refresh",
    )
    thread.start()
    return read_cached(config_path)


def _refresh_in_background(config_path: Path) -> None:
    try:
        refresh_titles(config_path)
    except Exception:
        _log.exception("后台抓取失败")


@contextmanager
def _process_refresh_lock() -> Iterator[bool]:
    """Try the shared lock without queuing another refresh behind its owner."""
    lock_path = CACHE_PATH.with_suffix(".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+") as lock_file:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def is_refreshing() -> bool:
    with _process_refresh_lock() as acquired:
        return not acquired


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
    del config_path
    return get_store().query_topics(
        q=q,
        site_id=site_id,
        category=category,
        date=date,
        page=page,
        page_size=min(max(page_size, 1), MAX_PAGE_SIZE),
        refreshing=is_refreshing(),
    )


def _persist(payload: TitlesResponse) -> None:
    store = get_store()
    seen_at = payload.fetched_at or datetime.now(timezone.utc)
    for site in payload.sites:
        store.upsert_site(
            SiteStatus(
                site_id=site.id,
                site_name=site.name,
                site_url=site.url,
                category=site.category,
                ok=site.ok,
                error=site.error,
                fetched_at=site.fetched_at or (seen_at if site.ok else None),
            )
        )
        if not site.ok:
            continue
        store.upsert_titles(
            [
                TitleRecord(
                    site_id=site.id,
                    site_name=site.name,
                    site_url=site.url,
                    category=site.category,
                    title=item.title,
                    url=item.url,
                    seen_at=site.fetched_at or seen_at,
                )
                for item in site.items
            ]
        )


def _fill_categories(cached: TitlesResponse, config_path: Path) -> None:
    config = {site.id: site for site in load_config(config_path).sites}
    for site in cached.sites:
        if site.category and site.category != "other":
            continue
        mapped = config.get(site.id)
        if mapped is not None:
            site.category = mapped.category


def _shell(site: SiteConfig) -> SiteTitles:
    return SiteTitles(id=site.id, name=site.name, url=str(site.url), category=site.category)


def _public_error(error: str) -> str:
    return "抓取失败"
