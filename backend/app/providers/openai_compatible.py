"""Cliente para qualquer API no padrão OpenAI.

Cobre: OpenRouter, DeepSeek, Nous, OMP (Oh-my-pi), OpenAI, Groq, Together,
Mistral, Fireworks, xAI, Cerebras, Perplexity, LM Studio, vLLM, llama.cpp
e endpoints personalizados.
"""

from __future__ import annotations

import json
import time
from typing import Any, AsyncIterator

import httpx

from app.core.logging import get_logger
from app.providers.base import (
    AIProvider,
    ChatMessage,
    ChatResult,
    HealthResult,
    ModelInfo,
    ProviderError,
)
from app.providers.catalog import estimate_cost

log = get_logger(__name__)

DEFAULT_TIMEOUT = httpx.Timeout(connect=10.0, read=300.0, write=60.0, pool=10.0)


class OpenAICompatibleProvider(AIProvider):
    def __init__(
        self,
        *,
        slug: str,
        label: str,
        base_url: str,
        api_key: str = "",
        default_model: str = "",
        extra_headers: dict[str, str] | None = None,
        is_local: bool = False,
        supports_model_listing: bool = True,
    ) -> None:
        self.slug = slug
        self.label = label
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.default_model = default_model
        self.extra_headers = extra_headers or {}
        self.is_local = is_local
        self.supports_model_listing = supports_model_listing

    # ------------------------------------------------------------------ #
    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", **self.extra_headers}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    # ------------------------------------------------------------------ #
    async def health(self) -> HealthResult:
        started = time.perf_counter()
        try:
            if self.supports_model_listing:
                models = await self.list_models()
                return HealthResult(
                    ok=True,
                    message=f"{len(models)} modelos disponíveis",
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    model_count=len(models),
                )
            result = await self.chat(
                [ChatMessage("user", "ping")], max_tokens=5, temperature=0.0
            )
            return HealthResult(
                ok=bool(result.text is not None),
                message="conexão ok",
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
        except Exception as exc:  # noqa: BLE001
            return HealthResult(
                ok=False,
                message=str(exc)[:400],
                latency_ms=int((time.perf_counter() - started) * 1000),
            )

    async def list_models(self) -> list[ModelInfo]:
        if not self.supports_model_listing:
            return [ModelInfo(id=self.default_model)] if self.default_model else []
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.get(self._url("models"), headers=self._headers())
            if resp.status_code >= 400:
                raise ProviderError(
                    f"{self.label}: {resp.status_code} {resp.text[:300]}",
                    status=resp.status_code,
                    slug=self.slug,
                )
            payload = resp.json()
        items = payload.get("data", payload if isinstance(payload, list) else [])
        models: list[ModelInfo] = []
        for item in items:
            if isinstance(item, str):
                models.append(ModelInfo(id=item, is_local=self.is_local))
                continue
            mid = item.get("id") or item.get("name") or ""
            if not mid:
                continue
            models.append(
                ModelInfo(
                    id=mid,
                    label=item.get("name") or mid,
                    context_length=int(
                        item.get("context_length")
                        or item.get("context_window")
                        or (item.get("top_provider") or {}).get("context_length")
                        or 0
                    ),
                    is_local=self.is_local,
                )
            )
        models.sort(key=lambda m: m.id)
        return models

    # ------------------------------------------------------------------ #
    def _payload(
        self,
        messages: list[ChatMessage],
        model: str | None,
        temperature: float,
        max_tokens: int,
        json_mode: bool,
        images: list[str] | None,
        stream: bool = False,
    ) -> dict[str, Any]:
        chosen = model or self.default_model
        if not chosen:
            raise ProviderError(f"{self.label}: nenhum modelo definido", slug=self.slug)

        msg_dicts: list[dict[str, Any]] = [m.to_dict() for m in messages]
        if images:
            content: list[dict[str, Any]] = [
                {"type": "text", "text": msg_dicts[-1]["content"]}
            ]
            for img in images:
                url = img if img.startswith(("http", "data:")) else f"data:image/jpeg;base64,{img}"
                content.append({"type": "image_url", "image_url": {"url": url}})
            msg_dicts[-1] = {"role": msg_dicts[-1]["role"], "content": content}

        payload: dict[str, Any] = {
            "model": chosen,
            "messages": msg_dicts,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if stream:
            payload["stream"] = True
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        return payload

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        json_mode: bool = False,
        images: list[str] | None = None,
    ) -> ChatResult:
        payload = self._payload(messages, model, temperature, max_tokens, json_mode, images)
        started = time.perf_counter()
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.post(
                self._url("chat/completions"), headers=self._headers(), json=payload
            )
            if resp.status_code >= 400:
                raise ProviderError(
                    f"{self.label} ({resp.status_code}): {resp.text[:400]}",
                    status=resp.status_code,
                    slug=self.slug,
                )
            data = resp.json()

        latency = int((time.perf_counter() - started) * 1000)
        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(
                f"{self.label}: resposta inesperada {json.dumps(data)[:300]}", slug=self.slug
            ) from exc

        usage = data.get("usage") or {}
        tin = int(usage.get("prompt_tokens", 0))
        tout = int(usage.get("completion_tokens", 0))
        used_model = data.get("model", payload["model"])
        return ChatResult(
            text=text.strip(),
            model=used_model,
            provider=self.slug,
            tokens_in=tin,
            tokens_out=tout,
            latency_ms=latency,
            cost_usd=0.0 if self.is_local else estimate_cost(used_model, tin, tout),
            raw=data,
        )

    async def stream_chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> AsyncIterator[str]:
        payload = self._payload(messages, model, temperature, max_tokens, False, None, stream=True)
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            async with client.stream(
                "POST", self._url("chat/completions"), headers=self._headers(), json=payload
            ) as resp:
                if resp.status_code >= 400:
                    body = await resp.aread()
                    raise ProviderError(
                        f"{self.label} ({resp.status_code}): {body[:300]!r}",
                        status=resp.status_code,
                        slug=self.slug,
                    )
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    chunk = line[5:].strip()
                    if chunk == "[DONE]":
                        break
                    try:
                        delta = json.loads(chunk)["choices"][0]["delta"].get("content")
                    except Exception:  # noqa: BLE001
                        continue
                    if delta:
                        yield delta

    async def embed(self, texts: list[str], *, model: str | None = None) -> list[list[float]]:
        chosen = model or "text-embedding-3-small"
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.post(
                self._url("embeddings"),
                headers=self._headers(),
                json={"model": chosen, "input": texts},
            )
            if resp.status_code >= 400:
                raise ProviderError(
                    f"{self.label} embeddings ({resp.status_code}): {resp.text[:300]}",
                    status=resp.status_code,
                    slug=self.slug,
                )
            data = resp.json()
        return [item["embedding"] for item in data.get("data", [])]
