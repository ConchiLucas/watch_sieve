from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from watch_sieve.titles import (
    DEFAULT_PAGE_SIZE,
    FilterMeta,
    TitlesResponse,
    TopicPage,
    filter_meta,
    query_topics,
    read_cached,
    refresh_titles,
)

ROOT = Path(__file__).resolve().parents[2]
WEB_DIST = ROOT / "web" / "dist"

app = FastAPI(title="WatchSieve")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/titles", response_model=TitlesResponse)
def get_titles() -> TitlesResponse:
    return read_cached()


@app.get("/api/filters", response_model=FilterMeta)
def get_filters() -> FilterMeta:
    return filter_meta()


@app.get("/api/topics", response_model=TopicPage)
def get_topics(
    q: str = "",
    site_id: str = "",
    category: str = "",
    date: str = "",
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=50),
) -> TopicPage:
    return query_topics(q=q, site_id=site_id, category=category, date=date, page=page, page_size=page_size)


@app.post("/api/refresh", response_model=TitlesResponse)
def post_refresh() -> TitlesResponse:
    return refresh_titles()


if WEB_DIST.exists():
    app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")


def run() -> None:
    import uvicorn

    uvicorn.run("watch_sieve.server:app", host="127.0.0.1", port=8000, reload=False)
