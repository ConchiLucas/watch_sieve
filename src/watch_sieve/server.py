from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from watch_sieve.classification import (
    ClassificationCatalog,
    ClassificationPage,
    classification_catalog,
    query_classifications,
)
from watch_sieve.store import get_store
from watch_sieve.titles import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    FilterMeta,
    TitlesResponse,
    TopicPage,
    filter_meta,
    query_topics,
    read_cached,
    start_refresh,
)
from watch_sieve.watch import router as watch_router

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
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> TopicPage:
    return query_topics(q=q, site_id=site_id, category=category, date=date, page=page, page_size=page_size)


@app.post("/api/refresh", response_model=TitlesResponse)
def post_refresh() -> TitlesResponse:
    return start_refresh()


@app.get("/api/classifications/catalog", response_model=ClassificationCatalog)
def get_classification_catalog(q: str = "", site_id: str = "") -> ClassificationCatalog:
    return classification_catalog(q=q, site_id=site_id)


@app.get("/api/classifications", response_model=ClassificationPage)
def get_classifications(
    topic: str = "",
    q: str = "",
    site_id: str = "",
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> ClassificationPage:
    return query_classifications(topic=topic, q=q, site_id=site_id, page=page, page_size=page_size)


app.include_router(watch_router)


@app.get("/topics")
def topics_page() -> FileResponse:
    index = WEB_DIST / "index.html"
    if not index.exists():
        raise HTTPException(status_code=404, detail="页面尚未构建，请先运行 npm --prefix web run build")
    return FileResponse(index)


@app.get("/watch")
def watch_page() -> FileResponse:
    index = WEB_DIST / "index.html"
    if not index.exists():
        raise HTTPException(status_code=404, detail="页面尚未构建，请先运行 npm --prefix web run build")
    return FileResponse(index)


if WEB_DIST.exists():
    app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")


def run() -> None:
    from dotenv import load_dotenv
    import uvicorn

    load_dotenv(ROOT / ".env")
    get_store()
    uvicorn.run("watch_sieve.server:app", host="127.0.0.1", port=8000, reload=False)
