from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl

FetchEngine = Literal["http", "browser"]
SiteCategory = Literal["forum", "news", "blog", "other"]

CATEGORY_LABELS: dict[str, str] = {
    "forum": "论坛",
    "news": "资讯",
    "blog": "博客",
    "other": "其他",
}


class SiteConfig(BaseModel):
    id: str
    name: str
    url: HttpUrl
    category: SiteCategory = "other"
    kind: Literal["html", "rss", "browser"] = "html"
    css_selector: str | None = None
    wait_for: str | None = None
    force_browser: bool = False
    timeout_seconds: int = 30
    poll_seconds: int = 300
    interest: str = ""


class WatchConfig(BaseModel):
    sites: list[SiteConfig]


class FetchAttempt(BaseModel):
    engine: FetchEngine
    status_code: int | None = None
    final_url: str = ""
    error: str = ""
    quality_reason: str = ""


class Topic(BaseModel):
    title: str
    url: str = ""


class FetchResult(BaseModel):
    ok: bool
    site_id: str = ""
    url: str
    final_url: str = ""
    status_code: int | None = None
    engine: FetchEngine | None = None
    title: str = ""
    html: str = ""
    markdown: str = ""
    text: str = ""
    items: list[Topic] = Field(default_factory=list)
    error: str = ""
    attempts: list[FetchAttempt] = Field(default_factory=list)
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def content(self) -> str:
        if self.items:
            return "\n".join(item.title for item in self.items)
        return self.markdown.strip() or self.text.strip()


class RawMessage(BaseModel):
    site_id: str
    url: str
    title: str = ""
    text: str
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SievedMessage(RawMessage):
    keep: bool
    reason: str
    score: float = 0.0
