from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from watch_sieve.cancellation import check_cancelled
from watch_sieve.classification import (
    CLASSIFIER_REVISION,
    UNCATEGORIZED,
    build_classify_prompt,
    normalize_topic_id,
)
from watch_sieve.gateway import ChatCompletionResult, GatewayModel, build_gateway_service
from watch_sieve.store import TopicStore, get_store
from watch_sieve.watch import BATCH_SIZE, MAX_PER_RUN, execute_watch_run, parse_keywords, parse_watch_payload

CLASSIFY_MAX_PER_RUN = 45


class JudgeAiService(Protocol):
    def resolve_chat(self, *, refresh: bool = True) -> GatewayModel: ...

    def chat(self, prompt: str, provider_id: str = "") -> ChatCompletionResult: ...


@dataclass(frozen=True)
class JudgeSummary:
    model: str
    classified: int
    classify_remaining: int
    scanned: int
    kept: int
    skipped: int
    watch_remaining: int
    watch_skipped: bool = False

    @property
    def message(self) -> str:
        parts = [f"分类 {self.classified} 条（剩余 {self.classify_remaining}）"]
        if self.watch_skipped:
            parts.append("未填写兴趣，跳过关注")
        else:
            parts.append(f"关注筛了 {self.scanned} 条，留下 {self.kept} 条（剩余 {self.watch_remaining}）")
        return f"用 {self.model}：" + "；".join(parts)


def execute_classify_run(
    store: TopicStore,
    *,
    chat: Callable[[str, str], ChatCompletionResult],
    provider_id: str,
    model: str,
    revision: int = CLASSIFIER_REVISION,
    limit: int = CLASSIFY_MAX_PER_RUN,
    should_stop: Callable[[], bool] | None = None,
) -> tuple[int, int]:
    pending = store.pending_topic_titles(revision)[:limit]
    for offset in range(0, len(pending), BATCH_SIZE):
        check_cancelled(should_stop)
        batch = pending[offset : offset + BATCH_SIZE]
        numbered = [(index + 1, item.title) for index, item in enumerate(batch)]
        result = chat(build_classify_prompt(numbered), provider_id)
        judgements: dict[int, dict[str, object]] = {}
        for item in parse_watch_payload(result.content):
            try:
                judgements[int(item.get("id") or 0)] = item
            except (TypeError, ValueError):
                continue
        for index, row in enumerate(batch, start=1):
            judgement = judgements.get(index) or {}
            store.upsert_topic(
                row,
                topic_id=normalize_topic_id(str(judgement.get("topic_id") or UNCATEGORIZED)),
                reason=str(judgement.get("reason") or "")[:200],
                provider_id=provider_id,
                model=model,
                classifier_revision=revision,
            )
    return len(pending), len(store.pending_topic_titles(revision))


def run_judge(
    should_stop: Callable[[], bool] | None = None,
    *,
    store: TopicStore | None = None,
    service: JudgeAiService | None = None,
) -> JudgeSummary:
    store = store or get_store()
    service = service or build_gateway_service()
    chosen = service.resolve_chat(refresh=True)
    classified, classify_remaining = execute_classify_run(
        store,
        chat=service.chat,
        provider_id=chosen.id,
        model=chosen.id,
        should_stop=should_stop,
    )
    keywords_text, revision = store.get_watch_interests()
    keywords = parse_keywords(keywords_text)
    if not keywords:
        return JudgeSummary(
            model=chosen.id,
            classified=classified,
            classify_remaining=classify_remaining,
            scanned=0,
            kept=0,
            skipped=0,
            watch_remaining=0,
            watch_skipped=True,
        )
    watch = execute_watch_run(
        store,
        chat=service.chat,
        provider_id=chosen.id,
        model=chosen.id,
        keywords=keywords,
        revision=revision,
        limit=MAX_PER_RUN,
        should_stop=should_stop,
    )
    return JudgeSummary(
        model=chosen.id,
        classified=classified,
        classify_remaining=classify_remaining,
        scanned=watch.scanned,
        kept=watch.kept,
        skipped=watch.skipped,
        watch_remaining=watch.remaining,
    )
