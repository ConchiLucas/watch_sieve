from __future__ import annotations

import os
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Protocol
from urllib.parse import urlsplit, urlunsplit

from pathlib import Path

from dotenv import load_dotenv

from watch_sieve.models import CATEGORY_LABELS

ROOT = Path(__file__).resolve().parents[2]

BEIJING = timezone(timedelta(hours=8))

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS site_status (
  site_id TEXT PRIMARY KEY,
  site_name TEXT NOT NULL,
  site_url TEXT NOT NULL,
  category TEXT NOT NULL DEFAULT 'other',
  ok BOOLEAN NOT NULL DEFAULT TRUE,
  error TEXT NOT NULL DEFAULT '',
  fetched_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS titles (
  id BIGSERIAL PRIMARY KEY,
  site_id TEXT NOT NULL,
  site_name TEXT NOT NULL,
  site_url TEXT NOT NULL,
  category TEXT NOT NULL DEFAULT 'other',
  title TEXT NOT NULL,
  url TEXT NOT NULL DEFAULT '',
  canonical_key TEXT NOT NULL,
  first_seen_at TIMESTAMPTZ NOT NULL,
  last_seen_at TIMESTAMPTZ NOT NULL,
  UNIQUE (site_id, canonical_key)
);

CREATE INDEX IF NOT EXISTS titles_first_seen_idx ON titles (first_seen_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS titles_site_id_idx ON titles (site_id);
CREATE INDEX IF NOT EXISTS titles_category_idx ON titles (category);

CREATE TABLE IF NOT EXISTS shared_ai_defaults (
  defaults_key TEXT PRIMARY KEY,
  default_provider_id TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT ck_shared_ai_defaults_key CHECK (defaults_key = 'default'),
  CONSTRAINT ck_shared_ai_defaults_provider CHECK (length(default_provider_id) > 0),
  CONSTRAINT ck_shared_ai_defaults_revision CHECK (revision >= 1)
);

CREATE TABLE IF NOT EXISTS watch_interests (
  interests_key TEXT PRIMARY KEY,
  keywords TEXT NOT NULL DEFAULT '',
  revision INTEGER NOT NULL DEFAULT 1,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT ck_watch_interests_key CHECK (interests_key = 'default'),
  CONSTRAINT ck_watch_interests_revision CHECK (revision >= 1)
);

CREATE TABLE IF NOT EXISTS title_watches (
  id BIGSERIAL PRIMARY KEY,
  site_id TEXT NOT NULL,
  canonical_key TEXT NOT NULL,
  title TEXT NOT NULL,
  url TEXT NOT NULL DEFAULT '',
  site_name TEXT NOT NULL,
  keep BOOLEAN NOT NULL,
  interest TEXT NOT NULL DEFAULT '',
  reason TEXT NOT NULL DEFAULT '',
  provider_id TEXT NOT NULL DEFAULT '',
  model TEXT NOT NULL DEFAULT '',
  interests_revision INTEGER NOT NULL DEFAULT 1,
  fetched_at TIMESTAMPTZ,
  judged_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (site_id, canonical_key)
);

CREATE INDEX IF NOT EXISTS title_watches_keep_idx ON title_watches (keep, judged_at DESC);

CREATE TABLE IF NOT EXISTS title_topics (
  id BIGSERIAL PRIMARY KEY,
  site_id TEXT NOT NULL,
  canonical_key TEXT NOT NULL,
  title TEXT NOT NULL,
  url TEXT NOT NULL DEFAULT '',
  site_name TEXT NOT NULL,
  topic_id TEXT NOT NULL,
  reason TEXT NOT NULL DEFAULT '',
  provider_id TEXT NOT NULL DEFAULT '',
  model TEXT NOT NULL DEFAULT '',
  classifier_revision INTEGER NOT NULL DEFAULT 1,
  fetched_at TIMESTAMPTZ,
  judged_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (site_id, canonical_key)
);

CREATE INDEX IF NOT EXISTS title_topics_topic_idx ON title_topics (topic_id, judged_at DESC);
"""


def normalize_title(title: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", title).split())


def canonical_url(url: str) -> str:
    parts = urlsplit(url.strip())
    path = parts.path.rstrip("/") or "/"
    if not parts.scheme and not parts.netloc:
        return url.strip()
    return urlunsplit((parts.scheme, parts.netloc.lower(), path, parts.query, ""))


def canonical_key(title: str, url: str = "") -> str:
    cleaned = canonical_url(url) if url.strip() else ""
    if cleaned:
        return "u:" + cleaned
    return "t:" + normalize_title(title)


@dataclass(frozen=True)
class SiteStatus:
    site_id: str
    site_name: str
    site_url: str
    category: str
    ok: bool
    error: str = ""
    fetched_at: datetime | None = None


@dataclass(frozen=True)
class TitleRecord:
    site_id: str
    site_name: str
    site_url: str
    category: str
    title: str
    url: str = ""
    seen_at: datetime | None = None


@dataclass(frozen=True)
class StoredTitleRow:
    title: str
    url: str
    site_id: str
    site_name: str
    fetched_at: datetime | None = None


class TopicStore(Protocol):
    def upsert_site(self, status: SiteStatus) -> None: ...

    def upsert_titles(self, records: list[TitleRecord]) -> None: ...

    def query_topics(
        self,
        *,
        q: str = "",
        site_id: str = "",
        category: str = "",
        date: str = "",
        page: int = 1,
        page_size: int = 50,
        refreshing: bool = False,
    ): ...

    def list_title_rows(self) -> list[StoredTitleRow]: ...

    def get_watch_interests(self) -> tuple[str, int]: ...

    def save_watch_interests(self, keywords: str) -> tuple[str, int]: ...

    def list_kept_watches(self) -> list[dict]: ...

    def pending_watch_titles(self, interests_revision: int) -> list[StoredTitleRow]: ...

    def upsert_watch(
        self,
        row: StoredTitleRow,
        *,
        keep: bool,
        interest: str,
        reason: str,
        provider_id: str,
        model: str,
        interests_revision: int,
    ) -> None: ...

    def list_title_topic_ids(self) -> dict[tuple[str, str], str]: ...

    def pending_topic_titles(self, classifier_revision: int) -> list[StoredTitleRow]: ...

    def upsert_topic(
        self,
        row: StoredTitleRow,
        *,
        topic_id: str,
        reason: str,
        provider_id: str,
        model: str,
        classifier_revision: int,
    ) -> None: ...


@dataclass
class MemoryTopicStore:
    titles: dict[tuple[str, str], dict] = field(default_factory=dict)
    sites: dict[str, SiteStatus] = field(default_factory=dict)
    watches: dict[tuple[str, str], dict] = field(default_factory=dict)
    topics: dict[tuple[str, str], dict] = field(default_factory=dict)
    watch_keywords: str = ""
    watch_revision: int = 1
    next_id: int = 1

    def upsert_site(self, status: SiteStatus) -> None:
        self.sites[status.site_id] = status

    def upsert_titles(self, records: list[TitleRecord]) -> None:
        for record in records:
            key = (record.site_id, canonical_key(record.title, record.url))
            seen_at = record.seen_at or datetime.now(timezone.utc)
            existing = self.titles.get(key)
            if existing is None:
                self.titles[key] = {
                    "id": self.next_id,
                    "site_id": record.site_id,
                    "site_name": record.site_name,
                    "site_url": record.site_url,
                    "category": record.category,
                    "title": record.title,
                    "url": canonical_url(record.url) if record.url.strip() else "",
                    "first_seen_at": seen_at,
                    "last_seen_at": seen_at,
                }
                self.next_id += 1
            else:
                existing["last_seen_at"] = seen_at
                existing["title"] = record.title
                existing["site_name"] = record.site_name
                existing["site_url"] = record.site_url
                existing["category"] = record.category
                if record.url.strip():
                    existing["url"] = canonical_url(record.url)

    def query_topics(
        self,
        *,
        q: str = "",
        site_id: str = "",
        category: str = "",
        date: str = "",
        page: int = 1,
        page_size: int = 50,
        refreshing: bool = False,
    ):
        from watch_sieve.titles import TopicPage, TopicRow

        rows = [self._row(item) for item in self.titles.values()]
        keyword = q.strip().lower()
        if keyword:
            rows = [row for row in rows if keyword in row.title.lower()]
        if site_id:
            rows = [row for row in rows if row.site_id == site_id]
        if category:
            rows = [row for row in rows if row.category == category]
        if date:
            rows = [row for row in rows if _day(row.fetched_at) == date]
        rows.sort(key=lambda row: (row.fetched_at or datetime.min.replace(tzinfo=timezone.utc),), reverse=True)
        page_size = max(page_size, 1)
        total = len(rows)
        last_page = max(1, (total + page_size - 1) // page_size) if total else 1
        page = min(max(page, 1), last_page)
        start = (page - 1) * page_size
        fetched_at = max((site.fetched_at for site in self.sites.values() if site.fetched_at), default=None)
        failed = [site.site_name for site in self.sites.values() if not site.ok]
        return TopicPage(
            total=total,
            page=page,
            page_size=page_size,
            fetched_at=fetched_at,
            refreshing=refreshing,
            failed_sites=failed,
            items=rows[start : start + page_size],
        )

    def list_title_rows(self) -> list[StoredTitleRow]:
        return [
            StoredTitleRow(
                title=item["title"],
                url=item["url"],
                site_id=item["site_id"],
                site_name=item["site_name"],
                fetched_at=item["first_seen_at"],
            )
            for item in self.titles.values()
        ]

    def get_watch_interests(self) -> tuple[str, int]:
        return self.watch_keywords, self.watch_revision

    def save_watch_interests(self, keywords: str) -> tuple[str, int]:
        self.watch_keywords = keywords.strip()
        self.watch_revision += 1
        return self.watch_keywords, self.watch_revision

    def list_kept_watches(self) -> list[dict]:
        rows = [item for item in self.watches.values() if item["keep"]]
        rows.sort(key=lambda item: item["fetched_at"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        return rows

    def pending_watch_titles(self, interests_revision: int) -> list[StoredTitleRow]:
        pending = []
        for item in self.titles.values():
            key = (item["site_id"], canonical_key(item["title"], item["url"]))
            existing = self.watches.get(key)
            if existing is not None and existing["interests_revision"] == interests_revision:
                continue
            pending.append(
                StoredTitleRow(
                    title=item["title"],
                    url=item["url"],
                    site_id=item["site_id"],
                    site_name=item["site_name"],
                    fetched_at=item["first_seen_at"],
                )
            )
        return pending

    def upsert_watch(
        self,
        row: StoredTitleRow,
        *,
        keep: bool,
        interest: str,
        reason: str,
        provider_id: str,
        model: str,
        interests_revision: int,
    ) -> None:
        key = (row.site_id, canonical_key(row.title, row.url))
        self.watches[key] = {
            "title": row.title,
            "url": row.url,
            "site_id": row.site_id,
            "site_name": row.site_name,
            "keep": keep,
            "interest": interest,
            "reason": reason,
            "provider_id": provider_id,
            "model": model,
            "interests_revision": interests_revision,
            "fetched_at": row.fetched_at,
        }

    def list_title_topic_ids(self) -> dict[tuple[str, str], str]:
        return {key: str(item["topic_id"]) for key, item in self.topics.items()}

    def pending_topic_titles(self, classifier_revision: int) -> list[StoredTitleRow]:
        pending = []
        for item in self.titles.values():
            key = (item["site_id"], canonical_key(item["title"], item["url"]))
            existing = self.topics.get(key)
            if existing is not None and existing["classifier_revision"] == classifier_revision:
                continue
            pending.append(
                StoredTitleRow(
                    title=item["title"],
                    url=item["url"],
                    site_id=item["site_id"],
                    site_name=item["site_name"],
                    fetched_at=item["first_seen_at"],
                )
            )
        return pending

    def upsert_topic(
        self,
        row: StoredTitleRow,
        *,
        topic_id: str,
        reason: str,
        provider_id: str,
        model: str,
        classifier_revision: int,
    ) -> None:
        key = (row.site_id, canonical_key(row.title, row.url))
        self.topics[key] = {
            "topic_id": topic_id,
            "reason": reason,
            "provider_id": provider_id,
            "model": model,
            "classifier_revision": classifier_revision,
        }

    def _row(self, item: dict):
        from watch_sieve.titles import TopicRow

        return TopicRow(
            title=item["title"],
            url=item["url"],
            site_id=item["site_id"],
            site_name=item["site_name"],
            site_url=item["site_url"],
            category=item["category"],
            category_label=CATEGORY_LABELS.get(item["category"], item["category"]),
            fetched_at=item["first_seen_at"],
        )


class PostgresTopicStore:
    def __init__(self, database_url: str) -> None:
        from psycopg_pool import ConnectionPool

        self._pool = ConnectionPool(conninfo=database_url, min_size=1, max_size=4, open=True)
        self.ensure_schema()

    @classmethod
    def from_env(cls) -> PostgresTopicStore:
        load_dotenv(ROOT / ".env")
        url = os.getenv("WATCH_SIEVE_DATABASE_URL", "").strip()
        if not url:
            raise RuntimeError("缺少 WATCH_SIEVE_DATABASE_URL。请在 .env 中填写本机 postgres16 的 watch_sieve 库连接串。")
        return cls(url)

    def ensure_schema(self) -> None:
        with self._pool.connection() as conn:
            for statement in SCHEMA_SQL.split(";"):
                sql = statement.strip()
                if sql:
                    conn.execute(sql)
            conn.commit()

    def upsert_site(self, status: SiteStatus) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO site_status (site_id, site_name, site_url, category, ok, error, fetched_at)
                VALUES (%(site_id)s, %(site_name)s, %(site_url)s, %(category)s, %(ok)s, %(error)s, %(fetched_at)s)
                ON CONFLICT (site_id) DO UPDATE SET
                  site_name = EXCLUDED.site_name,
                  site_url = EXCLUDED.site_url,
                  category = EXCLUDED.category,
                  ok = EXCLUDED.ok,
                  error = EXCLUDED.error,
                  fetched_at = EXCLUDED.fetched_at
                """,
                {
                    "site_id": status.site_id,
                    "site_name": status.site_name,
                    "site_url": status.site_url,
                    "category": status.category,
                    "ok": status.ok,
                    "error": status.error,
                    "fetched_at": status.fetched_at,
                },
            )
            conn.commit()

    def upsert_titles(self, records: list[TitleRecord]) -> None:
        if not records:
            return
        payload = []
        for record in records:
            seen_at = record.seen_at or datetime.now(timezone.utc)
            url = canonical_url(record.url) if record.url.strip() else ""
            payload.append(
                {
                    "site_id": record.site_id,
                    "site_name": record.site_name,
                    "site_url": record.site_url,
                    "category": record.category,
                    "title": record.title,
                    "url": url,
                    "canonical_key": canonical_key(record.title, record.url),
                    "seen_at": seen_at,
                }
            )
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.executemany(
                    """
                    INSERT INTO titles (
                      site_id, site_name, site_url, category, title, url, canonical_key, first_seen_at, last_seen_at
                    ) VALUES (
                      %(site_id)s, %(site_name)s, %(site_url)s, %(category)s, %(title)s, %(url)s, %(canonical_key)s,
                      %(seen_at)s, %(seen_at)s
                    )
                    ON CONFLICT (site_id, canonical_key) DO UPDATE SET
                      last_seen_at = EXCLUDED.last_seen_at,
                      title = EXCLUDED.title,
                      site_name = EXCLUDED.site_name,
                      site_url = EXCLUDED.site_url,
                      category = EXCLUDED.category,
                      url = EXCLUDED.url
                    """,
                    payload,
                )
            conn.commit()

    def query_topics(
        self,
        *,
        q: str = "",
        site_id: str = "",
        category: str = "",
        date: str = "",
        page: int = 1,
        page_size: int = 50,
        refreshing: bool = False,
    ):
        from watch_sieve.titles import TopicPage, TopicRow

        filters = ["TRUE"]
        params: dict[str, object] = {}
        keyword = q.strip()
        if keyword:
            filters.append("LOWER(title) LIKE %(keyword)s")
            params["keyword"] = f"%{keyword.lower()}%"
        if site_id:
            filters.append("site_id = %(site_id)s")
            params["site_id"] = site_id
        if category:
            filters.append("category = %(category)s")
            params["category"] = category
        if date:
            filters.append("(first_seen_at AT TIME ZONE 'Asia/Shanghai')::date = %(date)s::date")
            params["date"] = date
        where = " AND ".join(filters)
        page_size = max(page_size, 1)
        with self._pool.connection() as conn:
            total = conn.execute(f"SELECT COUNT(*) FROM titles WHERE {where}", params).fetchone()[0]
            last_page = max(1, (total + page_size - 1) // page_size) if total else 1
            page = min(max(page, 1), last_page)
            params["limit"] = page_size
            params["offset"] = (page - 1) * page_size
            rows = conn.execute(
                f"""
                SELECT title, url, site_id, site_name, site_url, category, first_seen_at
                FROM titles
                WHERE {where}
                ORDER BY first_seen_at DESC, id DESC
                LIMIT %(limit)s OFFSET %(offset)s
                """,
                params,
            ).fetchall()
            status_rows = conn.execute(
                "SELECT site_name, ok, fetched_at FROM site_status"
            ).fetchall()
        fetched_at = max((row[2] for row in status_rows if row[2] is not None), default=None)
        failed = [row[0] for row in status_rows if not row[1]]
        items = [
            TopicRow(
                title=row[0],
                url=row[1],
                site_id=row[2],
                site_name=row[3],
                site_url=row[4],
                category=row[5],
                category_label=CATEGORY_LABELS.get(row[5], row[5]),
                fetched_at=row[6],
            )
            for row in rows
        ]
        return TopicPage(
            total=total,
            page=page,
            page_size=page_size,
            fetched_at=fetched_at,
            refreshing=refreshing,
            failed_sites=failed,
            items=items,
        )

    def list_title_rows(self) -> list[StoredTitleRow]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT title, url, site_id, site_name, first_seen_at
                FROM titles
                ORDER BY first_seen_at DESC, id DESC
                """
            ).fetchall()
        return [
            StoredTitleRow(
                title=row[0],
                url=row[1],
                site_id=row[2],
                site_name=row[3],
                fetched_at=row[4],
            )
            for row in rows
        ]

    def get_watch_interests(self) -> tuple[str, int]:
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                INSERT INTO watch_interests (interests_key, keywords)
                VALUES ('default', '')
                ON CONFLICT (interests_key) DO NOTHING
                RETURNING keywords, revision
                """
            ).fetchone()
            if row is None:
                row = conn.execute(
                    "SELECT keywords, revision FROM watch_interests WHERE interests_key = 'default'"
                ).fetchone()
            conn.commit()
        if row is None:
            return "", 1
        return str(row[0]), int(row[1])

    def save_watch_interests(self, keywords: str) -> tuple[str, int]:
        clean = keywords.strip()
        with self._pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO watch_interests (interests_key, keywords)
                VALUES ('default', %s)
                ON CONFLICT (interests_key) DO NOTHING
                """,
                (clean,),
            )
            row = conn.execute(
                """
                UPDATE watch_interests
                SET keywords = %s, revision = revision + 1, updated_at = CURRENT_TIMESTAMP
                WHERE interests_key = 'default'
                RETURNING keywords, revision
                """,
                (clean,),
            ).fetchone()
            conn.commit()
        if row is None:
            raise RuntimeError("兴趣关键词保存失败")
        return str(row[0]), int(row[1])

    def list_kept_watches(self) -> list[dict]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT title, url, site_id, site_name, interest, reason, model, fetched_at
                FROM title_watches
                WHERE keep = TRUE
                ORDER BY judged_at DESC, id DESC
                """
            ).fetchall()
        return [
            {
                "title": row[0],
                "url": row[1],
                "site_id": row[2],
                "site_name": row[3],
                "interest": row[4],
                "reason": row[5],
                "model": row[6],
                "fetched_at": row[7],
            }
            for row in rows
        ]

    def pending_watch_titles(self, interests_revision: int) -> list[StoredTitleRow]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT t.title, t.url, t.site_id, t.site_name, t.first_seen_at
                FROM titles t
                LEFT JOIN title_watches w
                  ON t.site_id = w.site_id AND t.canonical_key = w.canonical_key
                WHERE w.id IS NULL OR w.interests_revision <> %s
                ORDER BY t.first_seen_at DESC, t.id DESC
                """,
                (interests_revision,),
            ).fetchall()
        return [
            StoredTitleRow(
                title=row[0],
                url=row[1],
                site_id=row[2],
                site_name=row[3],
                fetched_at=row[4],
            )
            for row in rows
        ]

    def upsert_watch(
        self,
        row: StoredTitleRow,
        *,
        keep: bool,
        interest: str,
        reason: str,
        provider_id: str,
        model: str,
        interests_revision: int,
    ) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO title_watches (
                  site_id, canonical_key, title, url, site_name, keep, interest, reason,
                  provider_id, model, interests_revision, fetched_at
                ) VALUES (
                  %(site_id)s, %(canonical_key)s, %(title)s, %(url)s, %(site_name)s, %(keep)s,
                  %(interest)s, %(reason)s, %(provider_id)s, %(model)s, %(interests_revision)s, %(fetched_at)s
                )
                ON CONFLICT (site_id, canonical_key) DO UPDATE SET
                  title = EXCLUDED.title,
                  url = EXCLUDED.url,
                  site_name = EXCLUDED.site_name,
                  keep = EXCLUDED.keep,
                  interest = EXCLUDED.interest,
                  reason = EXCLUDED.reason,
                  provider_id = EXCLUDED.provider_id,
                  model = EXCLUDED.model,
                  interests_revision = EXCLUDED.interests_revision,
                  fetched_at = EXCLUDED.fetched_at,
                  judged_at = CURRENT_TIMESTAMP
                """,
                {
                    "site_id": row.site_id,
                    "canonical_key": canonical_key(row.title, row.url),
                    "title": row.title,
                    "url": row.url,
                    "site_name": row.site_name,
                    "keep": keep,
                    "interest": interest,
                    "reason": reason,
                    "provider_id": provider_id,
                    "model": model,
                    "interests_revision": interests_revision,
                    "fetched_at": row.fetched_at,
                },
            )
            conn.commit()

    def list_title_topic_ids(self) -> dict[tuple[str, str], str]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT site_id, canonical_key, topic_id FROM title_topics"
            ).fetchall()
        return {(row[0], row[1]): str(row[2]) for row in rows}

    def pending_topic_titles(self, classifier_revision: int) -> list[StoredTitleRow]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT t.title, t.url, t.site_id, t.site_name, t.first_seen_at
                FROM titles t
                LEFT JOIN title_topics c
                  ON t.site_id = c.site_id AND t.canonical_key = c.canonical_key
                WHERE c.id IS NULL OR c.classifier_revision <> %s
                ORDER BY t.first_seen_at DESC, t.id DESC
                """,
                (classifier_revision,),
            ).fetchall()
        return [
            StoredTitleRow(
                title=row[0],
                url=row[1],
                site_id=row[2],
                site_name=row[3],
                fetched_at=row[4],
            )
            for row in rows
        ]

    def upsert_topic(
        self,
        row: StoredTitleRow,
        *,
        topic_id: str,
        reason: str,
        provider_id: str,
        model: str,
        classifier_revision: int,
    ) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO title_topics (
                  site_id, canonical_key, title, url, site_name, topic_id, reason,
                  provider_id, model, classifier_revision, fetched_at
                ) VALUES (
                  %(site_id)s, %(canonical_key)s, %(title)s, %(url)s, %(site_name)s, %(topic_id)s,
                  %(reason)s, %(provider_id)s, %(model)s, %(classifier_revision)s, %(fetched_at)s
                )
                ON CONFLICT (site_id, canonical_key) DO UPDATE SET
                  title = EXCLUDED.title,
                  url = EXCLUDED.url,
                  site_name = EXCLUDED.site_name,
                  topic_id = EXCLUDED.topic_id,
                  reason = EXCLUDED.reason,
                  provider_id = EXCLUDED.provider_id,
                  model = EXCLUDED.model,
                  classifier_revision = EXCLUDED.classifier_revision,
                  fetched_at = EXCLUDED.fetched_at,
                  judged_at = CURRENT_TIMESTAMP
                """,
                {
                    "site_id": row.site_id,
                    "canonical_key": canonical_key(row.title, row.url),
                    "title": row.title,
                    "url": row.url,
                    "site_name": row.site_name,
                    "topic_id": topic_id,
                    "reason": reason,
                    "provider_id": provider_id,
                    "model": model,
                    "classifier_revision": classifier_revision,
                    "fetched_at": row.fetched_at,
                },
            )
            conn.commit()


_store: TopicStore | None = None


def get_store() -> TopicStore:
    global _store
    if _store is None:
        _store = PostgresTopicStore.from_env()
    return _store


def set_store(store: TopicStore | None) -> None:
    global _store
    _store = store


def _day(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(BEIJING).date().isoformat()
