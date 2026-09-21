from watch_sieve.classification import CLASSIFIER_REVISION, UNCATEGORIZED, build_classify_prompt, query_classifications
from watch_sieve.judge import execute_classify_run, run_judge
from watch_sieve.gateway import ChatCompletionResult, GatewayModel
from watch_sieve.store import TitleRecord, canonical_key
from watch_sieve.watch import execute_watch_run


def _chat_result(content: str) -> ChatCompletionResult:
    return ChatCompletionResult.model_validate(
        {
            "ok": True,
            "providerId": "aurora/auto",
            "label": "aurora/auto",
            "model": "aurora/auto",
            "content": content,
            "durationSeconds": 0.1,
        }
    )


class FakeService:
    def __init__(self, replies: list[str]) -> None:
        self.replies = list(replies)
        self.prompts: list[str] = []

    def resolve_chat(self, *, refresh: bool = True) -> GatewayModel:
        return GatewayModel(id="aurora/auto", kind="chat", vendor="aurora", label="Auto", model="auto")

    def chat(self, prompt: str, provider_id: str = "") -> ChatCompletionResult:
        self.prompts.append(prompt)
        return _chat_result(self.replies.pop(0))


def _seed_title(memory_store, title: str, url: str = "https://v2ex.com/t/1") -> None:
    memory_store.upsert_titles(
        [
            TitleRecord(
                site_id="v2ex",
                site_name="V2EX",
                site_url="https://v2ex.com/",
                category="forum",
                title=title,
                url=url,
            )
        ]
    )


def test_build_classify_prompt_lists_labels_not_keywords() -> None:
    prompt = build_classify_prompt([(1, "鹈鹕测试")])
    assert "model-eval 模型测评 / 降智" in prompt
    assert "uncategorized 未分类" in prompt
    assert "鹈鹕测试" in prompt
    assert "富可敌国" not in prompt


def test_memory_store_roundtrip_topic(memory_store) -> None:
    _seed_title(memory_store, "中英文之间加空格吗")
    pending = memory_store.pending_topic_titles(CLASSIFIER_REVISION)
    assert pending[0].title == "中英文之间加空格吗"
    memory_store.upsert_topic(
        pending[0],
        topic_id="community",
        reason="站务闲聊",
        provider_id="aurora/auto",
        model="aurora/auto",
        classifier_revision=CLASSIFIER_REVISION,
    )
    key = ("v2ex", canonical_key(pending[0].title, pending[0].url))
    assert memory_store.list_title_topic_ids()[key] == "community"
    assert memory_store.pending_topic_titles(CLASSIFIER_REVISION) == []
    assert memory_store.pending_topic_titles(CLASSIFIER_REVISION + 1)[0].title == "中英文之间加空格吗"


def test_classify_page_prefers_stored_llm_topic(memory_store) -> None:
    _seed_title(memory_store, "中英文之间加空格吗")
    assert query_classifications(topic=UNCATEGORIZED).total == 1
    pending = memory_store.pending_topic_titles(CLASSIFIER_REVISION)[0]
    memory_store.upsert_topic(
        pending,
        topic_id="community",
        reason="站务",
        provider_id="aurora/auto",
        model="aurora/auto",
        classifier_revision=CLASSIFIER_REVISION,
    )
    assert query_classifications(topic="community").total == 1
    assert query_classifications(topic=UNCATEGORIZED).total == 0


def test_execute_classify_run_persists_model_topic(memory_store) -> None:
    _seed_title(memory_store, "中英文之间加空格吗")
    classified, remaining = execute_classify_run(
        memory_store,
        chat=lambda prompt, provider_id: _chat_result(
            '[{"id": 1, "topic_id": "community", "reason": "站务闲聊"}]'
        ),
        provider_id="aurora/auto",
        model="aurora/auto",
    )
    assert classified == 1
    assert remaining == 0
    assert query_classifications(topic="community").items[0].title == "中英文之间加空格吗"


def test_run_judge_classifies_then_watches(memory_store) -> None:
    _seed_title(memory_store, "Grok 4.7 发布了", "https://v2ex.com/t/2")
    memory_store.save_watch_interests("grok")
    service = FakeService(
        [
            '[{"id": 1, "topic_id": "model-news", "reason": "新模型"}]',
            '[{"id": 1, "keep": true, "interest": "grok", "reason": "提到 grok"}]',
        ]
    )
    summary = run_judge(store=memory_store, service=service)
    assert summary.classified == 1
    assert summary.kept == 1
    assert summary.watch_skipped is False
    assert "分类 1 条" in summary.message
    assert query_classifications(topic="model-news").total == 1
    assert memory_store.list_kept_watches()[0]["title"] == "Grok 4.7 发布了"
    assert len(service.prompts) == 2


def test_run_judge_skips_watch_without_keywords(memory_store) -> None:
    _seed_title(memory_store, "随便看看")
    service = FakeService(['[{"id": 1, "topic_id": "uncategorized", "reason": "闲聊"}]'])
    summary = run_judge(store=memory_store, service=service)
    assert summary.watch_skipped is True
    assert summary.scanned == 0
    assert "跳过关注" in summary.message
    assert len(service.prompts) == 1


def test_unknown_topic_id_becomes_uncategorized(memory_store) -> None:
    _seed_title(memory_store, "27届秋招")
    assert query_classifications(topic="career").total == 1
    execute_classify_run(
        memory_store,
        chat=lambda prompt, provider_id: _chat_result(
            '[{"id": 1, "topic_id": "not-a-topic", "reason": "乱填"}]'
        ),
        provider_id="aurora/auto",
        model="aurora/auto",
    )
    assert query_classifications(topic=UNCATEGORIZED).total == 1
    assert query_classifications(topic="career").total == 0


def test_execute_watch_run_still_prefilters(memory_store) -> None:
    _seed_title(memory_store, "想买一口铁锅", "https://v2ex.com/t/3")
    _seed_title(memory_store, "27届秋招", "https://v2ex.com/t/4")
    _keywords, revision = memory_store.save_watch_interests("秋招")
    result = execute_watch_run(
        memory_store,
        chat=lambda prompt, provider_id: _chat_result(
            '[{"id": 1, "keep": true, "interest": "秋招", "reason": "招聘"}]'
        ),
        provider_id="aurora/auto",
        model="aurora/auto",
        keywords=["秋招"],
        revision=revision,
    )
    assert result.scanned == 1
    assert result.kept == 1
    assert memory_store.list_kept_watches()[0]["title"] == "27届秋招"
