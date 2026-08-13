"""Anthropic Messages API."""

from __future__ import annotations

import json
import time
from typing import Any, AsyncIterator

import httpx

from app.providers.base import (
    AIProvider,
    ChatMessage,
    ChatResult,
    HealthResult,
    ModelInfo,
    ProviderError,
)
from app.providers.catalog import estimate_cost

TIMEOUT = httpx.Timeout(connect=10.0, read=300.0, write=60.0, pool=10.0)


class AnthropicProvider(AIProvider):
    def __init__(
        self,
        *,
        slug: str = "anthropic",
        label: str = "Anthropic",
        base_url: str = "https://api.anthropic.com/v1",
        api_key: str = "",
        default_model: str = "claude-sonnet-4-20250514",
        **_: Any,
    ) -> None:
        self.slug = slug
        self.label = label
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.default_model = default_model
        self.is_local = False

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    async def health(self) -> HealthResult:
        started = time.perf_counter()
        try:
            models = await self.list_models()
            return HealthResult(
                ok=True,
                message=f"{len(models)} modelos",
                latency_ms=int((time.perf_counter() - started) * 1000),
                model_count=len(models),
            )
        except Exception as exc:  # noqa: BLE001
            return HealthResult(ok=False, message=str(exc)[:400])

    async def list_models(self) -> list[ModelInfo]:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(self._url("models"), headers=self._headers())
            if resp.status_code >= 400:
                raise ProviderError(
                    f"Anthropic ({resp.status_code}): {resp.text[:300]}", slug=self.slug
                )
            data = resp.json()
        return [
            ModelInfo(id=m["id"], label=m.get("display_name", m["id"]))
            for m in data.get("data", [])
        ]

    @staticmethod
    def _split(messages: list[ChatMessage]) -> tuple[str, list[dict[str, Any]]]:
        system = "\n\n".join(m.content for m in messages if m.role == "system")
        rest = [m.to_dict() for m in messages if m.role != "system"]
        return system, rest

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
        chosen = model or self.default_model
        system, msgs = self._split(messages)
        if images and msgs:
            content: list[dict[str, Any]] = [{"type": "text", "text": msgs[-1]["content"]}]
            for img in images:
                b64 = img.split(",", 1)[1] if img.startswith("data:") else img
                content.append(
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": "image/jpeg", "data": b64},
                    }
                )
            msgs[-1] = {"role": msgs[-1]["role"], "content": content}

        body: dict[str, Any] = {
            "model": chosen,
            "messages": msgs,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system:
            body["system"] = system

        started = time.perf_counter()
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(self._url("messages"), headers=self._headers(), json=body)
            if resp.status_code >= 400:
                raise ProviderError(
                    f"Anthropic ({resp.status_code}): {resp.text[:400]}",
                    status=resp.status_code,
                    slug=self.slug,
                )
            data = resp.json()

        text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        usage = data.get("usage") or {}
        tin = int(usage.get("input_tokens", 0))
        tout = int(usage.get("output_tokens", 0))
        return ChatResult(
            text=text.strip(),
            model=chosen,
            provider=self.slug,
            tokens_in=tin,
            tokens_out=tout,
            latency_ms=int((time.perf_counter() - started) * 1000),
            cost_usd=estimate_cost(chosen, tin, tout),
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
        system, msgs = self._split(messages)
        body: dict[str, Any] = {
            "model": model or self.default_model,
            "messages": msgs,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }
        if system:
            body["system"] = system
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            async with client.stream(
                "POST", self._url("messages"), headers=self._headers(), json=body
            ) as resp:
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    try:
                        event = json.loads(line[5:].strip())
                    except json.JSONDecodeError:
                        continue
                    if event.get("type") == "content_block_delta":
                        piece = (event.get("delta") or {}).get("text")
                        if piece:
                            yield piece

    async def embed(self, texts: list[str], *, model: str | None = None) -> list[list[float]]:
        raise ProviderError("Anthropic não oferece embeddings", slug=self.slug)
