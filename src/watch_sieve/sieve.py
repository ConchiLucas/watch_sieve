from __future__ import annotations

import os

from watch_sieve.models import RawMessage, SievedMessage, SiteConfig


def sieve_message(site: SiteConfig, message: RawMessage) -> SievedMessage:
    """Keep a message when it looks relevant to the site interest.

    Replace this stub with a real LLM call (OpenAI-compatible) once keys are set.
    """
    if os.getenv("OPENAI_API_KEY"):
        return _llm_sieve(site, message)

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


def _llm_sieve(site: SiteConfig, message: RawMessage) -> SievedMessage:
    return SievedMessage(
        **message.model_dump(),
        keep=True,
        reason="LLM sieve not implemented yet; kept by default",
        score=0.5,
    )
