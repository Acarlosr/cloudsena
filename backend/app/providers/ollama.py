"""Cliente nativo do Ollama (execução 100% local)."""

from __future__ import annotations

import base64
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

TIMEOUT = httpx.Timeout(connect=5.0, read=600.0, write=60.0, pool=5.0)


class OllamaProvider(AIProvider):
    def __init__(
        self,
        *,
        slug: str = "ollama",
        label: str = "Ollama (local)",
        base_url: str = "http://localhost:11434",
        default_model: str = "qwen2.5:7b-instruct",
        **_: Any,
    ) -> None:
        self.slug = slug
        self.label = label
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self.is_local = True

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    # ------------------------------------------------------------------ #
    async def health(self) -> HealthResult:
        started = time.perf_counter()
        try:
            models = await self.list_models()
            running = await self.running_models()
            msg = f"{len(models)} modelos instalados"
            if running:
                msg += f" · carregados: {', '.join(running)}"
            return HealthResult(
                ok=True,
                message=msg,
                latency_ms=int((time.perf_counter() - started) * 1000),
                model_count=len(models),
            )
        except Exception as exc:  # noqa: BLE001
            return HealthResult(ok=False, message=str(exc)[:400])

    async def list_models(self) -> list[ModelInfo]:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(self._url("api/tags"))
            if resp.status_code >= 400:
                raise ProviderError(f"Ollama: {resp.status_code}", slug=self.slug)
            data = resp.json()
        out: list[ModelInfo] = []
        for m in data.get("models", []):
            details = m.get("details") or {}
            out.append(
                ModelInfo(
                    id=m.get("name", ""),
                    label=f"{m.get('name','')} · {details.get('parameter_size','')}".strip(" ·"),
                    is_local=True,
                    modality="vision" if "llava" in m.get("name", "").lower() else "text",
                )
            )
        return sorted(out, key=lambda m: m.id)

    async def running_models(self) -> list[str]:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
                resp = await client.get(self._url("api/ps"))
                if resp.status_code >= 400:
                    return []
                return [m.get("name", "") for m in resp.json().get("models", [])]
        except Exception:  # noqa: BLE001
            return []

    # ------------------------------------------------------------------ #
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
        msgs = [m.to_dict() for m in messages]
        if images:
            msgs[-1]["images"] = [
                img if not img.startswith("data:") else img.split(",", 1)[1] for img in images
            ]
        payload: dict[str, Any] = {
            "model": chosen,
            "messages": msgs,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        if json_mode:
            payload["format"] = "json"

        started = time.perf_counter()
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(self._url("api/chat"), json=payload)
            if resp.status_code >= 400:
                raise ProviderError(
                    f"Ollama ({resp.status_code}): {resp.text[:300]}",
                    status=resp.status_code,
                    slug=self.slug,
                )
            data = resp.json()

        return ChatResult(
            text=(data.get("message") or {}).get("content", "").strip(),
            model=chosen,
            provider=self.slug,
            tokens_in=int(data.get("prompt_eval_count", 0)),
            tokens_out=int(data.get("eval_count", 0)),
            latency_ms=int((time.perf_counter() - started) * 1000),
            cost_usd=0.0,
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
        payload = {
            "model": model or self.default_model,
            "messages": [m.to_dict() for m in messages],
            "stream": True,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            async with client.stream("POST", self._url("api/chat"), json=payload) as resp:
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    piece = (data.get("message") or {}).get("content")
                    if piece:
                        yield piece
                    if data.get("done"):
                        break

    async def embed(self, texts: list[str], *, model: str | None = None) -> list[list[float]]:
        chosen = model or "nomic-embed-text"
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(
                self._url("api/embed"), json={"model": chosen, "input": texts}
            )
            if resp.status_code == 404:
                # Ollama antigo: endpoint singular
                out = []
                for text in texts:
                    r = await client.post(
                        self._url("api/embeddings"), json={"model": chosen, "prompt": text}
                    )
                    r.raise_for_status()
                    out.append(r.json()["embedding"])
                return out
            if resp.status_code >= 400:
                raise ProviderError(
                    f"Ollama embeddings ({resp.status_code}): {resp.text[:300]}", slug=self.slug
                )
            return resp.json().get("embeddings", [])

    async def pull_model(self, name: str) -> AsyncIterator[dict[str, Any]]:
        """Baixa um modelo, emitindo o progresso."""
        async with httpx.AsyncClient(timeout=httpx.Timeout(None)) as client:
            async with client.stream(
                "POST", self._url("api/pull"), json={"model": name, "stream": True}
            ) as resp:
                async for line in resp.aiter_lines():
                    if line.strip():
                        try:
                            yield json.loads(line)
                        except json.JSONDecodeError:
                            continue


def encode_image(path: str) -> str:
    with open(path, "rb") as fh:
        return base64.b64encode(fh.read()).decode()
