"""Google Gemini — Generative Language API (útil para visão em slides/código)."""

from __future__ import annotations

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


class GeminiProvider(AIProvider):
    def __init__(
        self,
        *,
        slug: str = "gemini",
        label: str = "Google Gemini",
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
        api_key: str = "",
        default_model: str = "gemini-2.5-flash",
        **_: Any,
    ) -> None:
        self.slug = slug
        self.label = label
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.default_model = default_model
        self.is_local = False

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    def _params(self) -> dict[str, str]:
        return {"key": self.api_key}

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
            resp = await client.get(self._url("models"), params=self._params())
            if resp.status_code >= 400:
                raise ProviderError(
                    f"Gemini ({resp.status_code}): {resp.text[:300]}", slug=self.slug
                )
            data = resp.json()
        out: list[ModelInfo] = []
        for m in data.get("models", []):
            mid = m.get("name", "").replace("models/", "")
            methods = m.get("supportedGenerationMethods", [])
            if "generateContent" not in methods and "embedContent" not in methods:
                continue
            out.append(
                ModelInfo(
                    id=mid,
                    label=m.get("displayName", mid),
                    context_length=int(m.get("inputTokenLimit", 0)),
                    modality="embedding" if "embedContent" in methods else "text",
                )
            )
        return sorted(out, key=lambda m: m.id)

    @staticmethod
    def _to_contents(messages: list[ChatMessage], images: list[str] | None) -> dict[str, Any]:
        system_parts = [m.content for m in messages if m.role == "system"]
        contents: list[dict[str, Any]] = []
        for m in messages:
            if m.role == "system":
                continue
            parts: list[dict[str, Any]] = [{"text": m.content}]
            contents.append({"role": "model" if m.role == "assistant" else "user", "parts": parts})
        if images and contents:
            for img in images:
                b64 = img.split(",", 1)[1] if img.startswith("data:") else img
                contents[-1]["parts"].append(
                    {"inline_data": {"mime_type": "image/jpeg", "data": b64}}
                )
        body: dict[str, Any] = {"contents": contents}
        if system_parts:
            body["systemInstruction"] = {"parts": [{"text": "\n\n".join(system_parts)}]}
        return body

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
        body = self._to_contents(messages, images)
        body["generationConfig"] = {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
            **({"responseMimeType": "application/json"} if json_mode else {}),
        }
        started = time.perf_counter()
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(
                self._url(f"models/{chosen}:generateContent"), params=self._params(), json=body
            )
            if resp.status_code >= 400:
                raise ProviderError(
                    f"Gemini ({resp.status_code}): {resp.text[:400]}",
                    status=resp.status_code,
                    slug=self.slug,
                )
            data = resp.json()

        try:
            parts = data["candidates"][0]["content"]["parts"]
            text = "".join(p.get("text", "") for p in parts)
        except (KeyError, IndexError):
            text = ""
        usage = data.get("usageMetadata") or {}
        tin = int(usage.get("promptTokenCount", 0))
        tout = int(usage.get("candidatesTokenCount", 0))
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
        result = await self.chat(
            messages, model=model, temperature=temperature, max_tokens=max_tokens
        )
        yield result.text

    async def embed(self, texts: list[str], *, model: str | None = None) -> list[list[float]]:
        chosen = model or "text-embedding-004"
        out: list[list[float]] = []
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            for text in texts:
                resp = await client.post(
                    self._url(f"models/{chosen}:embedContent"),
                    params=self._params(),
                    json={"model": f"models/{chosen}", "content": {"parts": [{"text": text}]}},
                )
                if resp.status_code >= 400:
                    raise ProviderError(
                        f"Gemini embeddings ({resp.status_code}): {resp.text[:200]}",
                        slug=self.slug,
                    )
                out.append(resp.json()["embedding"]["values"])
        return out
