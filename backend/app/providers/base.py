"""Contrato comum a todos os providers de IA."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Protocol


class ProviderError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None, slug: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.slug = slug


@dataclass
class ChatMessage:
    role: str  # system | user | assistant
    content: str

    def to_dict(self) -> dict[str, Any]:
        return {"role": self.role, "content": self.content}


@dataclass
class ChatResult:
    text: str
    model: str
    provider: str
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    cost_usd: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelInfo:
    id: str
    label: str = ""
    context_length: int = 0
    is_local: bool = False
    modality: str = "text"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label or self.id,
            "context_length": self.context_length,
            "is_local": self.is_local,
            "modality": self.modality,
        }


@dataclass
class HealthResult:
    ok: bool
    message: str = ""
    latency_ms: int = 0
    model_count: int = 0


class AIProvider(Protocol):
    slug: str
    label: str

    async def health(self) -> HealthResult: ...

    async def list_models(self) -> list[ModelInfo]: ...

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        json_mode: bool = False,
        images: list[str] | None = None,
    ) -> ChatResult: ...

    async def stream_chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> AsyncIterator[str]: ...

    async def embed(self, texts: list[str], *, model: str | None = None) -> list[list[float]]: ...
