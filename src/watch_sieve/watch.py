from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from watch_sieve.cancellation import check_cancelled
from watch_sieve.gateway import ChatCompletionError, ChatCompletionResult, GatewayError, build_gateway_service
from watch_sieve.store import StoredTitleRow, TopicStore, get_store
from watch_sieve.titles import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE

BATCH_SIZE = 15
MAX_PER_RUN = 30
DEFAULT_INTERESTS_KEY = "default"
TOPIC_MARKERS = ("新闻", "大事件", "时事")
NEWS_EVENT_HINTS = (
    "战争",
    "关税",
    "制裁",
    "以色列",
    "俄乌",
    "乌克兰",
    "加沙",
    "哈马斯",
    "中东",
    "白宫",
    "北约",
    "联合国",
    "地震",
    "台风",
    "阅兵",
    "两会",
    "外交",
    "中美",
    "台海",
    "疫情",
    "美联储",
    "核反应堆",
    "核电",
    "选举",
    "冲突",
    "导弹",
    "停火",
    "峰会",
    "空袭",
    "政变",
    "空难",
    "海啸",
    "G7",
    "G20",
    "APEC",
)


class WatchInterestState(BaseModel):
    keywords: str
    revision: int


class WatchInterestUpdate(BaseModel):
    keywords: str = Field(default="", max_length=4000)


class WatchRow(BaseModel):
    title: str
    url: str
    site_id: str
    site_name: str
    interest: str
    reason: str
    fetched_at: datetime | None = None


class WatchPage(BaseModel):
    total: int
    page: int
    page_size: int
    keywords: str
    revision: int
    model: str
    running: bool = False
    items: list[WatchRow]


class WatchRunResult(BaseModel):
    ok: bool
    model: str
    provider_id: str
    scanned: int
    kept: int
    skipped: int
    remaining: int
    message: str


def parse_keywords(raw: str) -> list[str]:
    seen: set[str] = set()
    items: list[str] = []
    for part in re.split(r"[,，\n]", raw):
        token = part.strip()
        if not token or token.lower() in seen:
            continue
        seen.add(token.lower())
        items.append(token)
    return items


def is_topic_keyword(keyword: str) -> bool:
    return any(marker in keyword for marker in TOPIC_MARKERS)


def prefilter_titles(rows: list[StoredTitleRow], keywords: list[str]) -> list[StoredTitleRow]:
    if not keywords:
        return []
    name_needles = [item.lower() for item in keywords if not is_topic_keyword(item)]
    has_topic = any(is_topic_keyword(item) for item in keywords)
    hits: list[StoredTitleRow] = []
    for row in rows:
        haystack = row.title.lower()
        if name_needles and any(needle in haystack for needle in name_needles):
            hits.append(row)
            continue
        if has_topic and any(hint.lower() in haystack for hint in NEWS_EVENT_HINTS):
            hits.append(row)
    return hits


def parse_watch_payload(raw: str) -> list[dict[str, object]]:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    start = text.find("[")
    end = text.rfind("]")
    if start < 0 or end <= start:
        raise ValueError("模型没有返回数组")
    payload = json.loads(text[start : end + 1])
    if not isinstance(payload, list):
        raise ValueError("模型没有返回数组")
    return [item for item in payload if isinstance(item, dict)]


def build_watch_prompt(keywords: list[str], titles: list[tuple[int, str]]) -> str:
    numbered = "\n".join(f"{index}. {title}" for index, title in titles)
    return (
        "你是标题筛选器。兴趣："
        + "、".join(keywords)
        + "。\n只保留与兴趣相关的标题。"
        "「国际新闻大事件」「国内新闻大事件」只指公众时政与重大新闻，"
        "不要把技术论坛、代理、大模型、账号充值当成新闻。"
        "\n输出 JSON 数组，每项: "
        '{"id": n, "keep": true/false, "interest": "命中的兴趣", "reason": "简短中文原因"}。\n'
        "标题：\n"
        + numbered
    )


def execute_watch_run(
    store: TopicStore,
    *,
    chat: Callable[[str, str], ChatCompletionResult],
    provider_id: str,
    model: str,
    keywords: list[str],
    revision: int,
    limit: int = MAX_PER_RUN,
    should_stop: Callable[[], bool] | None = None,
) -> WatchRunResult:
    pending = store.pending_watch_titles(revision)
    candidates = prefilter_titles(pending, keywords)[:limit]
    kept = 0
    skipped = 0
    for offset in range(0, len(candidates), BATCH_SIZE):
        check_cancelled(should_stop)
        batch = candidates[offset : offset + BATCH_SIZE]
        numbered = [(index + 1, item.title) for index, item in enumerate(batch)]
        result = chat(build_watch_prompt(keywords, numbered), provider_id)
        judgements: dict[int, dict[str, object]] = {}
        for item in parse_watch_payload(result.content):
            try:
                judgements[int(item.get("id") or 0)] = item
            except (TypeError, ValueError):
                continue
        for index, row in enumerate(batch, start=1):
            judgement = judgements.get(index) or {}
            keep = bool(judgement.get("keep"))
            store.upsert_watch(
                row,
                keep=keep,
                interest=str(judgement.get("interest") or "")[:80],
                reason=str(judgement.get("reason") or "")[:200],
                provider_id=provider_id,
                model=model,
                interests_revision=revision,
            )
            if keep:
                kept += 1
            else:
                skipped += 1
    remaining = max(0, len(prefilter_titles(store.pending_watch_titles(revision), keywords)))
    return WatchRunResult(
        ok=True,
        model=model,
        provider_id=provider_id,
        scanned=len(candidates),
        kept=kept,
        skipped=skipped,
        remaining=remaining,
        message=f"用 {model} 筛了 {len(candidates)} 条，留下 {kept} 条",
    )


router = APIRouter(prefix="/api/watches", tags=["watches"])


def _interest_state(pair: tuple[str, int]) -> WatchInterestState:
    return WatchInterestState(keywords=pair[0], revision=pair[1])


@router.get("/interests", response_model=WatchInterestState)
def get_watch_interests() -> WatchInterestState:
    return _interest_state(get_store().get_watch_interests())


@router.put("/interests", response_model=WatchInterestState)
def save_watch_interests(payload: WatchInterestUpdate) -> WatchInterestState:
    return _interest_state(get_store().save_watch_interests(payload.keywords))


@router.get("", response_model=WatchPage)
def get_watches(
    q: str = "",
    site_id: str = "",
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> WatchPage:
    keywords, revision = get_store().get_watch_interests()
    rows = get_store().list_kept_watches()
    needle = q.strip().lower()
    if needle:
        rows = [row for row in rows if needle in str(row["title"]).lower()]
    if site_id:
        rows = [row for row in rows if row["site_id"] == site_id]
    page_size = max(page_size, 1)
    total = len(rows)
    last_page = max(1, (total + page_size - 1) // page_size) if total else 1
    page = min(max(page, 1), last_page)
    start = (page - 1) * page_size
    model = next((str(row.get("model") or "") for row in rows if row.get("model")), "")
    items = [
        WatchRow(
            title=row["title"],
            url=row["url"],
            site_id=row["site_id"],
            site_name=row["site_name"],
            interest=row.get("interest") or "",
            reason=row.get("reason") or "",
            fetched_at=row.get("fetched_at"),
        )
        for row in rows[start : start + page_size]
    ]
    return WatchPage(
        total=total,
        page=page,
        page_size=page_size,
        keywords=keywords,
        revision=revision,
        model=model,
        items=items,
    )


@router.post("/run", response_model=WatchRunResult)
def run_watches(response: Response) -> WatchRunResult:
    response.headers["Cache-Control"] = "no-store"
    keywords_text, revision = get_store().get_watch_interests()
    keywords = parse_keywords(keywords_text)
    if not keywords:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="请先填写兴趣关键词")
    try:
        service = build_gateway_service()
        chosen = service.resolve_chat(refresh=True)
    except GatewayError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    try:
        return execute_watch_run(
            get_store(),
            chat=service.chat,
            provider_id=chosen.id,
            model=chosen.id,
            keywords=keywords,
            revision=revision,
        )
    except TimeoutError as exc:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(exc)) from exc
    except (ChatCompletionError, GatewayError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
