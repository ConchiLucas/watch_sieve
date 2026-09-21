from __future__ import annotations

import json
from collections.abc import Callable

from watch_sieve.gateway import GatewayError
from watch_sieve.models import RawMessage, SievedMessage, SiteConfig


def sieve_message(
    site: SiteConfig,
    message: RawMessage,
    *,
    complete: Callable[[str], str] | None = None,
) -> SievedMessage:
    """Keep a message when it looks relevant to the site interest."""
    completer = complete if complete is not None else _shared_chat_completer()
    if completer is not None:
        return _llm_sieve(site, message, completer)
    return _keyword_sieve(site, message)


def _keyword_sieve(site: SiteConfig, message: RawMessage) -> SievedMessage:
    interest = (site.interest or "").strip()
    haystack = f"{message.title}\n{message.text}".lower()
    keep = True
    reason = "no LLM key; kept pending review"
    score = 0.5
    if interest:
        tokens = [token.lower() for token in interest.replace("，", ",").split(",") if token.strip()]
        hits = [token for token in tokens if token and token in haystack]
        keep = bool(hits)
        reason = f"keyword hits: {hits}" if hits else "no interest keywords matched"
        score = min(1.0, len(hits) / max(len(tokens), 1))
    return SievedMessage(**message.model_dump(), keep=keep, reason=reason, score=score)


def _llm_sieve(site: SiteConfig, message: RawMessage, complete: Callable[[str], str]) -> SievedMessage:
    interest = (site.interest or "").strip() or "未指定"
    prompt = (
        "你是标题筛选器。只根据兴趣判断是否保留。\n"
        f"兴趣：{interest}\n"
        f"标题：{message.title.strip()}\n"
        f"正文：{message.text.strip()[:2000]}\n"
        '只输出 JSON：{"keep": true 或 false, "reason": "简短中文原因", "score": 0 到 1 的小数}'
    )
    try:
        raw = complete(prompt)
        parsed = _parse_sieve_payload(raw)
    except (GatewayError, TimeoutError, ValueError, json.JSONDecodeError):
        return SievedMessage(
            **message.model_dump(),
            keep=False,
            reason="LLM 筛选失败，已跳过",
            score=0.0,
        )
    return SievedMessage(
        **message.model_dump(),
        keep=bool(parsed.get("keep")),
        reason=str(parsed.get("reason") or "模型未给出原因")[:200],
        score=_score(parsed.get("score")),
    )


def _shared_chat_completer() -> Callable[[str], str] | None:
    try:
        from watch_sieve.gateway import build_gateway_service

        service = build_gateway_service()
        service.resolve_chat()
    except Exception:
        return None
    return lambda prompt: service.chat(prompt).content


def _parse_sieve_payload(raw: str) -> dict[str, object]:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("模型没有返回 JSON")
    payload = json.loads(text[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("模型没有返回 JSON 对象")
    return payload


def _score(value: object) -> float:
    try:
        score = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.5
    return max(0.0, min(1.0, score))
