from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import httpx
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GATEWAY_BASE_URL = "http://127.0.0.1:18527"
DEFAULT_GATEWAY_AUTH = "local-gateway"
DEFAULT_TIMEOUT_SECONDS = 90.0


class GatewayError(RuntimeError):
    pass


class ChatCompletionError(GatewayError):
    pass


class ChatCompletionResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    ok: bool
    provider_id: str = Field(validation_alias="providerId")
    label: str
    model: str
    content: str
    duration_seconds: float = Field(validation_alias="durationSeconds")


class GatewayModel(BaseModel):
    id: str
    kind: str
    vendor: str = ""
    label: str = ""
    model: str = ""
    note: str = ""


class InvokeResult(BaseModel):
    kind: str
    model: str
    state: str
    text: str = ""
    assets: list[dict[str, Any]] = Field(default_factory=list)
    duration_seconds: float = 0.0


class GatewayClient:
    def __init__(
        self,
        base_url: str,
        auth: str,
        *,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._auth = auth
        self._timeout_seconds = timeout_seconds
        self._client = client

    @classmethod
    def from_env(cls, client: httpx.Client | None = None) -> GatewayClient:
        load_dotenv(ROOT / ".env")
        return cls(
            os.getenv("WATCH_SIEVE_GATEWAY_BASE_URL", DEFAULT_GATEWAY_BASE_URL).strip()
            or DEFAULT_GATEWAY_BASE_URL,
            os.getenv("WATCH_SIEVE_GATEWAY_AUTH", os.getenv("GATEWAY_AUTH", DEFAULT_GATEWAY_AUTH)).strip()
            or DEFAULT_GATEWAY_AUTH,
            timeout_seconds=_timeout_seconds(),
            client=client,
        )

    def list_models(self) -> list[GatewayModel]:
        payload = self._request("GET", "/v1/models", params={"auth": self._auth})
        raw = payload.get("models") if isinstance(payload, dict) else None
        if not isinstance(raw, list):
            raise GatewayError("网关没有返回模型清单")
        models: list[GatewayModel] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            model_id = str(item.get("id") or "").strip()
            kind = str(item.get("kind") or "").strip()
            if "/" not in model_id or not kind:
                continue
            models.append(
                GatewayModel(
                    id=model_id,
                    kind=kind,
                    vendor=str(item.get("vendor") or model_id.split("/", 1)[0]),
                    label=str(item.get("label") or ""),
                    model=str(item.get("model") or model_id.split("/", 1)[1]),
                    note=str(item.get("note") or ""),
                )
            )
        return models

    def resolve_model(self, kind: str, preferred: str = "") -> GatewayModel:
        wanted_kind = kind.strip()
        target = preferred.strip() or _preferred_model(wanted_kind)
        try:
            models = [item for item in self.list_models() if item.kind == wanted_kind]
        except GatewayError:
            if _looks_like_slug(target):
                return _model_from_slug(wanted_kind, target)
            raise
        if not models:
            if _looks_like_slug(target):
                return _model_from_slug(wanted_kind, target)
            raise GatewayError(f"网关没有可用的 {wanted_kind} 模型")
        if not target:
            return models[0]
        for item in models:
            if item.id == target:
                return item
        raise GatewayError(f"模型 {target} 当前不可用")

    def invoke(
        self,
        kind: str,
        model: str,
        input_payload: dict[str, Any],
        *,
        format: str | None = None,
    ) -> InvokeResult:
        started = time.monotonic()
        body: dict[str, Any] = {
            "auth": self._auth,
            "kind": kind,
            "model": model,
            "input": input_payload,
        }
        if format:
            body["format"] = format
        payload = self._request("POST", "/v1/invoke", json_body=body)
        run = payload.get("run") if isinstance(payload, dict) else None
        if not isinstance(run, dict):
            raise GatewayError("网关没有返回调用结果")
        state = str(run.get("state") or "")
        if state != "succeeded":
            raise GatewayError(_run_error(run) or "模型调用失败")
        outputs = run.get("outputs") if isinstance(run.get("outputs"), list) else []
        duration = (run.get("metrics") or {}).get("elapsedMs") if isinstance(run.get("metrics"), dict) else None
        seconds = round(float(duration) / 1000.0, 3) if duration is not None else round(time.monotonic() - started, 3)
        return InvokeResult(
            kind=kind,
            model=model,
            state=state,
            text=_text_from_outputs(outputs) if kind in {"chat", "transcribe"} else "",
            assets=_assets_from_outputs(outputs),
            duration_seconds=seconds,
        )

    def chat(self, prompt: str, model: str) -> ChatCompletionResult:
        text = prompt.strip()
        if not text:
            raise ValueError("请填写要执行的内容")
        result = self.invoke(
            "chat",
            model,
            {"messages": [{"role": "user", "content": text}]},
            format="json",
        )
        if not result.text.strip():
            raise GatewayError("模型没有返回文本")
        return ChatCompletionResult(
            ok=True,
            provider_id=model,
            label=model,
            model=model,
            content=result.text,
            duration_seconds=result.duration_seconds,
        )

    def generate_image(
        self,
        prompt: str,
        model: str,
        *,
        resolution: str = "",
        aspect: str = "",
    ) -> InvokeResult:
        payload: dict[str, Any] = {"prompt": prompt}
        if resolution:
            payload["resolution"] = resolution
        if aspect:
            payload["aspect"] = aspect
        result = self.invoke("image", model, payload)
        if not result.assets:
            raise GatewayError("模型没有返回图片")
        return result

    def synthesize_audio(self, text: str, model: str, *, voice: str = "") -> InvokeResult:
        payload: dict[str, Any] = {"text": text}
        if voice:
            payload["voice"] = voice
        result = self.invoke("audio", model, payload)
        if not result.assets:
            raise GatewayError("模型没有返回音频")
        return result

    def transcribe(self, filename: str, audio_base64: str, model: str) -> InvokeResult:
        result = self.invoke(
            "transcribe",
            model,
            {"filename": filename, "audioBase64": audio_base64},
        )
        if not result.text.strip():
            raise GatewayError("模型没有返回听写文本")
        return result

    def media_url(self, path: str) -> str:
        value = path.strip()
        if value.startswith("http://") or value.startswith("https://"):
            return value
        return urljoin(self._base_url + "/", value.lstrip("/"))

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self._base_url:
            raise GatewayError("本机网关地址尚未配置")
        timeout = httpx.Timeout(self._timeout_seconds, connect=min(10.0, self._timeout_seconds))
        own_client = self._client is None
        http = self._client or httpx.Client(timeout=timeout, trust_env=False)
        try:
            response = http.request(
                method,
                f"{self._base_url}{path}",
                params=params,
                json=json_body,
                headers={"Accept": "application/json", "Content-Type": "application/json"},
                timeout=timeout,
            )
        except httpx.TimeoutException as exc:
            raise TimeoutError(f"AI 调用超时: {int(self._timeout_seconds)} 秒") from exc
        except httpx.HTTPError as exc:
            raise GatewayError("无法调用本机网关") from exc
        finally:
            if own_client:
                http.close()
        payload = _json_object(response)
        if isinstance(payload.get("run"), dict):
            return payload
        if response.status_code == 401:
            raise GatewayError(str(payload.get("detail") or "鉴权不通过"))
        if response.status_code >= 400:
            raise GatewayError(_http_error(response.status_code, payload))
        if not isinstance(payload, dict):
            raise GatewayError("网关返回格式错误")
        return payload


class GatewayService:
    def __init__(self, client: GatewayClient) -> None:
        self._client = client

    def resolve_chat(self, *, refresh: bool = True) -> GatewayModel:
        return self._client.resolve_model("chat")

    def chat(self, prompt: str, provider_id: str = "") -> ChatCompletionResult:
        model = provider_id.strip() if "/" in provider_id else ""
        chosen = self._client.resolve_model("chat", model)
        return self._client.chat(prompt, chosen.id)

    def resolve_image(self) -> GatewayModel:
        return self._client.resolve_model("image")

    def resolve_audio(self) -> GatewayModel:
        return self._client.resolve_model("audio")

    def resolve_transcribe(self) -> GatewayModel:
        return self._client.resolve_model("transcribe")

    def generate_image(self, prompt: str, *, resolution: str = "", aspect: str = "") -> InvokeResult:
        model = self.resolve_image()
        return self._client.generate_image(prompt, model.id, resolution=resolution, aspect=aspect)

    def synthesize_audio(self, text: str, *, voice: str = "") -> InvokeResult:
        model = self.resolve_audio()
        return self._client.synthesize_audio(text, model.id, voice=voice)

    def transcribe(self, filename: str, audio_base64: str) -> InvokeResult:
        model = self.resolve_transcribe()
        return self._client.transcribe(filename, audio_base64, model.id)

    def media_url(self, path: str) -> str:
        return self._client.media_url(path)


def build_gateway_service(client: httpx.Client | None = None) -> GatewayService:
    return GatewayService(GatewayClient.from_env(client=client))


def _looks_like_slug(value: str) -> bool:
    vendor, sep, slug = value.partition("/")
    return bool(sep and vendor.strip() and slug.strip())


def _model_from_slug(kind: str, slug: str) -> GatewayModel:
    vendor, name = slug.split("/", 1)
    return GatewayModel(id=slug, kind=kind, vendor=vendor, label=name, model=name)


def _preferred_model(kind: str) -> str:
    load_dotenv(ROOT / ".env")
    env_name = {
        "chat": "WATCH_SIEVE_CHAT_MODEL",
        "image": "WATCH_SIEVE_IMAGE_MODEL",
        "audio": "WATCH_SIEVE_AUDIO_MODEL",
        "transcribe": "WATCH_SIEVE_TRANSCRIBE_MODEL",
    }.get(kind, "")
    if not env_name:
        return ""
    return os.getenv(env_name, "").strip()


def _timeout_seconds() -> float:
    load_dotenv(ROOT / ".env")
    raw = os.getenv("WATCH_SIEVE_CHAT_TIMEOUT_SECONDS", str(int(DEFAULT_TIMEOUT_SECONDS)))
    try:
        value = float(raw or DEFAULT_TIMEOUT_SECONDS)
    except ValueError:
        return DEFAULT_TIMEOUT_SECONDS
    return value if value > 0 else DEFAULT_TIMEOUT_SECONDS


def _json_object(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        payload = None
    return payload if isinstance(payload, dict) else {}


def _http_error(status: int, payload: dict[str, Any]) -> str:
    detail = payload.get("detail") or payload.get("title")
    if isinstance(detail, str) and detail.strip():
        return detail.strip()
    return f"HTTP {status}"


def _run_error(run: dict[str, Any]) -> str:
    error = run.get("error")
    if isinstance(error, dict):
        message = error.get("safeMessage") or error.get("code")
        if isinstance(message, str) and message.strip():
            return message.strip()
    return ""


def _text_from_outputs(outputs: list[Any]) -> str:
    chunks: list[str] = []
    for block in outputs:
        if not isinstance(block, dict):
            continue
        text = str(block.get("text") or "").strip()
        if text:
            chunks.append(text)
            continue
        parsed = block.get("parsed")
        if parsed is not None:
            if isinstance(parsed, str) and parsed.strip():
                chunks.append(parsed.strip())
            else:
                chunks.append(json.dumps(parsed, ensure_ascii=False))
            continue
        raw = str(block.get("rawText") or "").strip()
        if raw:
            chunks.append(raw)
            continue
        transcript = str(block.get("transcript") or "").strip()
        if transcript:
            chunks.append(transcript)
    return "\n".join(chunks)


def _assets_from_outputs(outputs: list[Any]) -> list[dict[str, Any]]:
    assets: list[dict[str, Any]] = []
    for block in outputs:
        if not isinstance(block, dict):
            continue
        asset = block.get("asset")
        if isinstance(asset, dict):
            assets.append(asset)
        extra = block.get("assets")
        if isinstance(extra, list):
            assets.extend(item for item in extra if isinstance(item, dict))
    return assets
