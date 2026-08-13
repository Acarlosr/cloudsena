"""Painel de conexões de IA: onde o usuário pluga OpenRouter, DeepSeek, Nous,
Ollama local, OMP e qualquer endpoint compatível.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.core.security import decrypt, encrypt, mask
from app.db.models import ProviderConfig, RoutingRule, utcnow
from app.db.session import get_db
from app.providers import registry
from app.providers.catalog import spec_for
from app.schemas import ProviderOut, ProviderUpdate, RoutingRuleOut, RoutingRuleUpdate

log = get_logger(__name__)
router = APIRouter(prefix="/providers", tags=["providers"])


def _serialize(cfg: ProviderConfig) -> ProviderOut:
    spec = spec_for(cfg.slug)
    options = cfg.options or {}
    key = decrypt(cfg.api_key_encrypted)
    return ProviderOut(
        slug=cfg.slug,
        label=cfg.label or (spec.label if spec else cfg.slug),
        kind=cfg.kind,
        base_url=cfg.base_url,
        default_model=cfg.default_model,
        enabled=cfg.enabled,
        is_local=cfg.is_local,
        requires_key=bool(options.get("requires_key", True)),
        has_key=bool(key),
        key_masked=mask(key),
        status=cfg.status,
        status_message=cfg.status_message,
        last_checked_at=cfg.last_checked_at,
        priority=cfg.priority,
        docs_url=options.get("docs_url", ""),
        api_key_url=options.get("api_key_url", ""),
        notes=options.get("notes", ""),
        suggested_models=options.get("suggested_models", []),
        supports_vision=bool(options.get("supports_vision", False)),
        supports_embeddings=bool(options.get("supports_embeddings", False)),
    )


@router.get("", response_model=list[ProviderOut])
def list_providers(db: Session = Depends(get_db)) -> list[ProviderOut]:
    configs = db.scalars(
        select(ProviderConfig).order_by(
            ProviderConfig.is_local.desc(), ProviderConfig.priority, ProviderConfig.slug
        )
    )
    return [_serialize(c) for c in configs]


@router.patch("/{slug}", response_model=ProviderOut)
def update_provider(
    slug: str, payload: ProviderUpdate, db: Session = Depends(get_db)
) -> ProviderOut:
    cfg = db.scalar(select(ProviderConfig).where(ProviderConfig.slug == slug))
    if not cfg:
        raise HTTPException(404, "Provider não encontrado")

    data = payload.model_dump(exclude_unset=True)
    if "api_key" in data:
        api_key = data.pop("api_key")
        cfg.api_key_encrypted = encrypt(api_key) if api_key else ""
        cfg.status = "unknown"
        cfg.status_message = ""
    for key, value in data.items():
        if value is not None:
            setattr(cfg, key, value)

    if cfg.enabled and (cfg.options or {}).get("requires_key", True) and not cfg.api_key_encrypted:
        raise HTTPException(400, f"{cfg.label} exige uma chave de API para ser ativado")

    db.commit()
    db.refresh(cfg)
    return _serialize(cfg)


@router.post("/{slug}/test")
async def test_provider(slug: str, db: Session = Depends(get_db)) -> dict:
    """Testa a conexão de verdade e guarda o resultado."""
    cfg = db.scalar(select(ProviderConfig).where(ProviderConfig.slug == slug))
    if not cfg:
        raise HTTPException(404, "Provider não encontrado")

    provider = registry.build_provider(cfg)
    health = await provider.health()

    cfg.status = "ok" if health.ok else "error"
    cfg.status_message = health.message
    cfg.last_checked_at = utcnow()
    if health.ok:
        try:
            models = await provider.list_models()
            cfg.models_cache = [m.to_dict() for m in models][:500]
        except Exception:  # noqa: BLE001
            cfg.models_cache = []
    db.commit()

    return {
        "slug": slug,
        "ok": health.ok,
        "message": health.message,
        "latency_ms": health.latency_ms,
        "model_count": health.model_count,
    }


@router.post("/test-all")
async def test_all(db: Session = Depends(get_db)) -> list[dict]:
    configs = list(db.scalars(select(ProviderConfig).where(ProviderConfig.enabled.is_(True))))

    async def check(cfg: ProviderConfig) -> dict:
        provider = registry.build_provider(cfg)
        health = await provider.health()
        return {
            "slug": cfg.slug,
            "label": cfg.label,
            "ok": health.ok,
            "message": health.message,
            "latency_ms": health.latency_ms,
        }

    results = await asyncio.gather(*(check(c) for c in configs), return_exceptions=True)
    out: list[dict] = []
    for cfg, result in zip(configs, results):
        if isinstance(result, Exception):
            result = {"slug": cfg.slug, "label": cfg.label, "ok": False, "message": str(result)}
        cfg.status = "ok" if result["ok"] else "error"
        cfg.status_message = result.get("message", "")
        cfg.last_checked_at = utcnow()
        out.append(result)
    db.commit()
    return out


@router.get("/{slug}/models")
async def list_models(slug: str, refresh: bool = False, db: Session = Depends(get_db)) -> dict:
    cfg = db.scalar(select(ProviderConfig).where(ProviderConfig.slug == slug))
    if not cfg:
        raise HTTPException(404, "Provider não encontrado")

    if cfg.models_cache and not refresh:
        return {"slug": slug, "cached": True, "models": cfg.models_cache}

    provider = registry.build_provider(cfg)
    try:
        models = await provider.list_models()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Não foi possível listar modelos: {exc}") from exc

    cfg.models_cache = [m.to_dict() for m in models][:500]
    cfg.last_checked_at = utcnow()
    db.commit()
    return {"slug": slug, "cached": False, "models": cfg.models_cache}


# --------------------------------------------------------------------------- #
# Roteamento por tarefa
# --------------------------------------------------------------------------- #
@router.get("/routing/rules", response_model=list[RoutingRuleOut])
def list_routes(db: Session = Depends(get_db)) -> list[RoutingRuleOut]:
    rules = db.scalars(select(RoutingRule).order_by(RoutingRule.task)).all()
    out: list[RoutingRuleOut] = []
    for rule in rules:
        item = RoutingRuleOut.model_validate(rule)
        item.label = registry.TASKS.get(rule.task, rule.task)
        out.append(item)
    return out


@router.patch("/routing/rules/{task}", response_model=RoutingRuleOut)
def update_route(
    task: str, payload: RoutingRuleUpdate, db: Session = Depends(get_db)
) -> RoutingRuleOut:
    rule = db.scalar(select(RoutingRule).where(RoutingRule.task == task))
    if not rule:
        if task not in registry.TASKS:
            raise HTTPException(404, "Tarefa desconhecida")
        rule = RoutingRule(task=task)
        db.add(rule)

    for key, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(rule, key, value)
    db.commit()
    db.refresh(rule)

    out = RoutingRuleOut.model_validate(rule)
    out.label = registry.TASKS.get(rule.task, rule.task)
    return out


@router.get("/routing/tasks")
def list_tasks() -> list[dict]:
    return [{"task": task, "label": label} for task, label in registry.TASKS.items()]
