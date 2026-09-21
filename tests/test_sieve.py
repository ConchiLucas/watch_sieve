from __future__ import annotations

from watch_sieve.models import RawMessage, SiteConfig
from watch_sieve.sieve import sieve_message


def _site() -> SiteConfig:
    return SiteConfig(
        id="v2ex",
        name="V2EX",
        url="https://www.v2ex.com/",
        interest="Agent,秋招",
    )


def test_keyword_sieve_keeps_interest_hit(monkeypatch) -> None:
    monkeypatch.setattr("watch_sieve.sieve._shared_chat_completer", lambda: None)
    message = RawMessage(site_id="v2ex", url="https://example.com/1", title="27届秋招", text="")
    result = sieve_message(_site(), message)
    assert result.keep is True
    assert "秋招" in result.reason


def test_keyword_sieve_drops_unrelated(monkeypatch) -> None:
    monkeypatch.setattr("watch_sieve.sieve._shared_chat_completer", lambda: None)
    message = RawMessage(site_id="v2ex", url="https://example.com/1", title="想买一口铁锅", text="")
    result = sieve_message(_site(), message)
    assert result.keep is False


def test_injected_llm_keep() -> None:
    message = RawMessage(site_id="v2ex", url="https://example.com/1", title="铁锅", text="")
    result = sieve_message(
        _site(),
        message,
        complete=lambda prompt: '{"keep": false, "reason": "与兴趣无关", "score": 0.1}',
    )
    assert result.keep is False
    assert result.reason == "与兴趣无关"
    assert result.score == 0.1


def test_injected_llm_json_fence() -> None:
    message = RawMessage(site_id="v2ex", url="https://example.com/1", title="Agent 工作流", text="")
    result = sieve_message(
        _site(),
        message,
        complete=lambda prompt: '```json\n{"keep": true, "reason": "命中 Agent", "score": 0.9}\n```',
    )
    assert result.keep is True
    assert "Agent" in result.reason
