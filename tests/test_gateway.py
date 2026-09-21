from __future__ import annotations

import json

import httpx
import pytest

from watch_sieve.gateway import GatewayClient, GatewayError, GatewayService


@pytest.fixture(autouse=True)
def clear_model_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WATCH_SIEVE_CHAT_MODEL", "")
    monkeypatch.setenv("WATCH_SIEVE_IMAGE_MODEL", "")
    monkeypatch.setenv("WATCH_SIEVE_AUDIO_MODEL", "")
    monkeypatch.setenv("WATCH_SIEVE_TRANSCRIBE_MODEL", "")



def _models_payload() -> dict[str, object]:
    return {
        "models": [
            {"id": "aurora/auto", "kind": "chat", "vendor": "aurora", "label": "Auto", "model": "auto"},
            {"id": "antigravity/gemini-3-pro-image", "kind": "image", "vendor": "antigravity", "label": "Image", "model": "gemini-3-pro-image"},
            {"id": "mimo/mimo-v2.5-tts", "kind": "audio", "vendor": "mimo", "label": "TTS", "model": "mimo-v2.5-tts"},
            {"id": "aurora/transcribe", "kind": "transcribe", "vendor": "aurora", "label": "听写", "model": "transcribe"},
        ]
    }


def _run(text: str = "pong", state: str = "succeeded", error: dict[str, str] | None = None) -> dict[str, object]:
    payload: dict[str, object] = {
        "run": {
            "state": state,
            "outputs": [{"kind": "text", "text": text}] if text else [],
            "metrics": {"elapsedMs": 120},
            "error": error,
        }
    }
    return payload


def _client(handler) -> GatewayClient:
    transport = httpx.MockTransport(handler)
    http = httpx.Client(transport=transport, trust_env=False)
    return GatewayClient("http://127.0.0.1:18527", "local-gateway", timeout_seconds=5, client=http)


def test_list_models_uses_auth_query() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json=_models_payload())

    models = _client(handler).list_models()
    assert captured["url"] == "http://127.0.0.1:18527/v1/models?auth=local-gateway"
    assert [item.id for item in models] == [
        "aurora/auto",
        "antigravity/gemini-3-pro-image",
        "mimo/mimo-v2.5-tts",
        "aurora/transcribe",
    ]


def test_resolve_model_uses_live_catalog_not_stale_list() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"models": [{"id": "grok/grok-4", "kind": "chat", "vendor": "grok", "label": "Grok", "model": "grok-4"}]},
        )

    chosen = _client(handler).resolve_model("chat")
    assert chosen.id == "grok/grok-4"


def test_resolve_model_honors_env_slug(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WATCH_SIEVE_CHAT_MODEL", "aurora/auto")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_models_payload())

    chosen = _client(handler).resolve_model("chat")
    assert chosen.id == "aurora/auto"


def test_resolve_model_uses_env_slug_when_catalog_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WATCH_SIEVE_CHAT_MODEL", "aurora/auto")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<!doctype html>")

    chosen = _client(handler).resolve_model("chat")
    assert chosen.id == "aurora/auto"
    assert chosen.vendor == "aurora"


def test_chat_posts_invoke_contract() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return httpx.Response(200, json=_models_payload())
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=_run())

    service = GatewayService(_client(handler))
    result = service.chat("你好")
    assert result.ok is True
    assert result.content == "pong"
    assert result.model == "aurora/auto"
    assert captured["url"] == "http://127.0.0.1:18527/v1/invoke"
    assert captured["body"] == {
        "auth": "local-gateway",
        "kind": "chat",
        "model": "aurora/auto",
        "format": "json",
        "input": {"messages": [{"role": "user", "content": "你好"}]},
    }


def test_failed_run_uses_safe_message() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return httpx.Response(200, json=_models_payload())
        return httpx.Response(
            502,
            json=_run(text="", state="failed", error={"safeMessage": "上游暂时不可用", "code": "UPSTREAM_ERROR"}),
        )

    with pytest.raises(GatewayError, match="上游暂时不可用"):
        GatewayService(_client(handler)).chat("你好")


def test_unauthorized_uses_http_detail() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "鉴权不通过", "code": "UNAUTHORIZED"})

    with pytest.raises(GatewayError, match="鉴权不通过"):
        _client(handler).list_models()


def test_image_audio_transcribe_payloads() -> None:
    bodies: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return httpx.Response(200, json=_models_payload())
        body = json.loads(request.content)
        bodies.append(body)
        kind = body["kind"]
        if kind == "transcribe":
            return httpx.Response(200, json=_run("听写结果"))
        return httpx.Response(
            200,
            json={
                "run": {
                    "state": "succeeded",
                    "outputs": [{"kind": "asset", "asset": {"access": {"path": "/v1/media/abc"}}}],
                }
            },
        )

    service = GatewayService(_client(handler))
    image = service.generate_image("深海蓝控制台", resolution="2k", aspect="16x9")
    audio = service.synthesize_audio("你好", voice="冰糖")
    transcribe = service.transcribe("a.wav", "ZGF0YQ==")
    assert image.assets[0]["access"]["path"] == "/v1/media/abc"
    assert audio.assets[0]["access"]["path"] == "/v1/media/abc"
    assert transcribe.text == "听写结果"
    assert bodies[0]["kind"] == "image"
    assert bodies[0]["model"] == "antigravity/gemini-3-pro-image"
    assert bodies[0]["input"] == {"prompt": "深海蓝控制台", "resolution": "2k", "aspect": "16x9"}
    assert bodies[1]["kind"] == "audio"
    assert bodies[1]["input"] == {"text": "你好", "voice": "冰糖"}
    assert bodies[2]["kind"] == "transcribe"
    assert bodies[2]["input"] == {"filename": "a.wav", "audioBase64": "ZGF0YQ=="}
