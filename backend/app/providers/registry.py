"""Registry: transforma configuração do banco em clientes prontos + roteamento por tarefa.

Fluxo:
    resolve("summarize") -> (provider, model, params)  segundo RoutingRule
    complete(...)        -> executa com fallback automático e registra uso
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.core.security import decrypt
from app.db.models import ProviderConfig, RoutingRule, UsageLog
from app.providers.anthropic import AnthropicProvider
from app.providers.base import AIProvider, ChatMessage, ChatResult, ProviderError
from app.providers.catalog import spec_for
from app.providers.gemini import GeminiProvider
from app.providers.ollama import OllamaProvider
from app.providers.openai_compatible import OpenAICompatibleProvider

log = get_logger(__name__)

# Tarefas roteáveis. Aparecem na tela de Providers da UI.
TASKS: dict[str, str] = {
    "transcribe_fallback": "Transcrição (fallback via API)",
    "summarize": "Resumos em lote",
    "chapters": "Capítulos e tópicos",
    "tags": "Tags e categorias",
    "chat": "Perguntas rápidas",
    "chat_complex": "Perguntas complexas / raciocínio",
    "rerank": "Reordenação de trechos",
    "vision": "Análise visual de slides e código",
    "embeddings": "Embeddings (busca semântica)",
    "title": "Títulos de conversa",
}

_BUILDERS = {
    "openai_compatible": OpenAICompatibleProvider,
    "ollama": OllamaProvider,
    "gemini": GeminiProvider,
    "anthropic": AnthropicProvider,
}


@dataclass
class Resolved:
    provider: AIProvider
    model: str
    temperature: float
    max_tokens: int
    slug: str


def build_provider(cfg: ProviderConfig) -> AIProvider:
    spec = spec_for(cfg.slug)
    builder = _BUILDERS.get(cfg.kind, OpenAICompatibleProvider)
    kwargs: dict[str, Any] = {
        "slug": cfg.slug,
        "label": cfg.label or cfg.slug,
        "base_url": cfg.base_url or (spec.base_url if spec else ""),
        "api_key": decrypt(cfg.api_key_encrypted),
        "default_model": cfg.default_model or (spec.default_model if spec else ""),
        "is_local": cfg.is_local,
    }
    if builder is OpenAICompatibleProvider:
        kwargs["extra_headers"] = cfg.extra_headers or (spec.extra_headers if spec else {}) or {}
        kwargs["supports_model_listing"] = (
            spec.supports_model_listing if spec else True
        ) and cfg.options.get("supports_model_listing", True)
    else:
        kwargs.pop("is_local", None)
    return builder(**kwargs)


def get_config(db: Session, slug: str) -> ProviderConfig | None:
    return db.scalar(select(ProviderConfig).where(ProviderConfig.slug == slug))


def get_provider(db: Session, slug: str) -> AIProvider:
    cfg = get_config(db, slug)
    if cfg is None:
        raise ProviderError(f"Provider '{slug}' não configurado", slug=slug)
    if not cfg.enabled:
        raise ProviderError(f"Provider '{cfg.label or slug}' está desativado", slug=slug)
    return build_provider(cfg)


def enabled_configs(db: Session) -> list[ProviderConfig]:
    return list(
        db.scalars(
            select(ProviderConfig)
            .where(ProviderConfig.enabled.is_(True))
            .order_by(ProviderConfig.priority)
        )
    )


def resolve(db: Session, task: str, *, override: dict | None = None) -> Resolved:
    """Descobre qual provider/modelo atende uma tarefa.

    Ordem: override (biblioteca) > RoutingRule > primeiro provider habilitado.
    """
    override = override or {}
    if task in override:
        slug = override[task].get("provider")
        model = override[task].get("model", "")
        if slug:
            return Resolved(get_provider(db, slug), model, 0.2, 2048, slug)

    rule = db.scalar(select(RoutingRule).where(RoutingRule.task == task))
    if rule and rule.provider_slug:
        try:
            provider = get_provider(db, rule.provider_slug)
            return Resolved(
                provider, rule.model, rule.temperature, rule.max_tokens, rule.provider_slug
            )
        except ProviderError as exc:
            log.warning("Rota principal de '%s' indisponível: %s", task, exc)
            if rule.fallback_provider_slug:
                provider = get_provider(db, rule.fallback_provider_slug)
                return Resolved(
                    provider,
                    rule.fallback_model,
                    rule.temperature,
                    rule.max_tokens,
                    rule.fallback_provider_slug,
                )
            raise

    configs = enabled_configs(db)
    if not configs:
        raise ProviderError(
            "Nenhum provider de IA habilitado. Configure em Ajustes › Providers."
        )
    cfg = configs[0]
    return Resolved(build_provider(cfg), cfg.default_model, 0.2, 2048, cfg.slug)


def _fallback_of(db: Session, task: str) -> Resolved | None:
    rule = db.scalar(select(RoutingRule).where(RoutingRule.task == task))
    if not rule or not rule.fallback_provider_slug:
        return None
    try:
        provider = get_provider(db, rule.fallback_provider_slug)
    except ProviderError:
        return None
    return Resolved(
        provider, rule.fallback_model, rule.temperature, rule.max_tokens,
        rule.fallback_provider_slug,
    )


async def complete(
    db: Session,
    task: str,
    messages: list[ChatMessage],
    *,
    override: dict | None = None,
    json_mode: bool = False,
    images: list[str] | None = None,
    video_id: int | None = None,
    max_tokens: int | None = None,
    temperature: float | None = None,
) -> ChatResult:
    """Executa uma tarefa de IA com fallback e log de uso."""
    started = time.perf_counter()
    resolved = resolve(db, task, override=override)
    attempts: list[Resolved] = [resolved]
    fb = _fallback_of(db, task)
    if fb and fb.slug != resolved.slug:
        attempts.append(fb)

    last_error: Exception | None = None
    for attempt in attempts:
        try:
            result = await attempt.provider.chat(
                messages,
                model=attempt.model or None,
                temperature=temperature if temperature is not None else attempt.temperature,
                max_tokens=max_tokens or attempt.max_tokens,
                json_mode=json_mode,
                images=images,
            )
            _log_usage(db, attempt.slug, result, task, video_id, True)
            return result
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            log.warning("Tarefa '%s' falhou em %s: %s", task, attempt.slug, exc)
            _log_usage(
                db,
                attempt.slug,
                ChatResult(
                    text="",
                    model=attempt.model,
                    provider=attempt.slug,
                    latency_ms=int((time.perf_counter() - started) * 1000),
                ),
                task,
                video_id,
                False,
            )

    raise ProviderError(f"Todas as rotas falharam para '{task}': {last_error}")


def _log_usage(
    db: Session,
    slug: str,
    result: ChatResult,
    task: str,
    video_id: int | None,
    success: bool,
) -> None:
    try:
        db.add(
            UsageLog(
                provider_slug=slug,
                model=result.model,
                task=task,
                video_id=video_id,
                tokens_in=result.tokens_in,
                tokens_out=result.tokens_out,
                cost_usd=result.cost_usd,
                latency_ms=result.latency_ms,
                success=success,
            )
        )
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
