"""Criação do schema, índice FTS5 e seed inicial (providers + roteamento)."""

from __future__ import annotations

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import settings
from app.core.logging import get_logger
from app.db.models import Base, Library, PrivacyMode, ProviderConfig, RoutingRule
from app.db.session import engine, session_scope
from app.providers.catalog import CATALOG

log = get_logger(__name__)

FTS_SQL = [
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts
    USING fts5(text, tokenize='unicode61 remove_diacritics 2');
    """,
    """
    CREATE TRIGGER IF NOT EXISTS chunks_fts_ai AFTER INSERT ON transcript_chunks BEGIN
        INSERT INTO chunks_fts(rowid, text) VALUES (new.id, new.text);
    END;
    """,
    """
    CREATE TRIGGER IF NOT EXISTS chunks_fts_ad AFTER DELETE ON transcript_chunks BEGIN
        INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES('delete', old.id, old.text);
    END;
    """,
    """
    CREATE TRIGGER IF NOT EXISTS chunks_fts_au AFTER UPDATE ON transcript_chunks BEGIN
        INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES('delete', old.id, old.text);
        INSERT INTO chunks_fts(rowid, text) VALUES (new.id, new.text);
    END;
    """,
]

# Roteamento padrão. A regra aqui é: o primeiro boot tem que FUNCIONAR sem nenhuma
# chave de API e sem nenhum serviço extra no ar — só Ollama, que é o mínimo que a
# instalação já exige. Por isso todo primário remoto abaixo tem `ollama`/`qwen2.5:7b`
# como fallback: sem chave, o provider fica "disabled" (ver seed_providers) e
# `registry.resolve()` já cai pro fallback sozinho — sem essa rede de segurança,
# um primário remoto sem chave quebraria o primeiro import (foi exatamente o bug
# corrigido nesta mesma revisão, com OMP no lugar de OpenRouter).
#
# Divisão de tarefas via OpenRouter, pensada pro plano DeepSeek V4 que o projeto
# usa: tarefa de volume alto e formato fechado (resumo/capítulos/tags/rerank/
# título, roda em todo vídeo importado) vai no Flash — rápido e ~5x mais barato.
# A pergunta do usuário (`chat`/`chat_complex`) é o produto em si — é a citação
# `[n]` que sustenta a promessa de "não inventar" — então vai no Pro, onde o
# raciocínio mais forte compensa o custo maior (ainda assim, poucos centavos por
# milhares de perguntas). Sem chave do OpenRouter, tudo cai pro Ollama local.
#
# `nomic-embed-text` fica sempre local (não é escolha de custo): toda busca gera
# um embedding da pergunta, e latência de rede em toda busca seria sentida;
# trocar de modelo de embedding também obriga reindexar a biblioteca inteira, já
# que vetores de dimensão diferente são descartados (ver services/embeddings.py).
#
# Quer outro modelo, outro provider ou trocar Flash/Pro por tarefa? Ligue em
# *Conexões de IA* e ajuste a rota por lá — nada aqui precisa mudar.
_OPENROUTER_FLASH = "deepseek/deepseek-v4-flash-0731"
_OPENROUTER_PRO = "deepseek/deepseek-v4-pro-0813"
_OLLAMA_MODEL = "qwen2.5:7b"

DEFAULT_ROUTES = [
    ("summarize", "openrouter", _OPENROUTER_FLASH, "ollama", _OLLAMA_MODEL, 0.2, 4000),
    ("chapters", "openrouter", _OPENROUTER_FLASH, "ollama", _OLLAMA_MODEL, 0.2, 3000),
    ("tags", "openrouter", _OPENROUTER_FLASH, "ollama", _OLLAMA_MODEL, 0.1, 1200),
    ("chat", "openrouter", _OPENROUTER_PRO, "ollama", _OLLAMA_MODEL, 0.2, 2000),
    ("chat_complex", "openrouter", _OPENROUTER_PRO, "ollama", _OLLAMA_MODEL, 0.3, 3000),
    ("rerank", "openrouter", _OPENROUTER_FLASH, "ollama", _OLLAMA_MODEL, 0.0, 1200),
    # Visão é opcional: só roda na análise de frames. Sem chave do Gemini a rota
    # simplesmente não é usada — não quebra nada no pipeline principal.
    ("vision", "gemini", "gemini-2.5-flash", "", "", 0.2, 2000),
    ("embeddings", "ollama", "nomic-embed-text", "", "", 0.0, 512),
    ("title", "openrouter", _OPENROUTER_FLASH, "ollama", _OLLAMA_MODEL, 0.4, 40),
    ("transcribe_fallback", "", "", "", "", 0.0, 2000),
]


def create_schema() -> None:
    Base.metadata.create_all(engine)
    if str(engine.url).startswith("sqlite"):
        with engine.begin() as conn:
            for stmt in FTS_SQL:
                conn.execute(text(stmt))
        log.info("Índice FTS5 pronto")


def seed_providers(db: Session) -> None:
    existing = {p.slug for p in db.scalars(select(ProviderConfig))}
    for spec in CATALOG:
        if spec.slug in existing:
            continue
        base_url = spec.base_url
        if spec.slug == "ollama":
            base_url = settings.ollama_base_url
        elif spec.slug == "omp":
            base_url = settings.omp_base_url

        db.add(
            ProviderConfig(
                slug=spec.slug,
                label=spec.label,
                kind=spec.kind,
                base_url=base_url,
                default_model=spec.default_model,
                extra_headers=dict(spec.extra_headers),
                options={
                    "requires_key": spec.requires_key,
                    "supports_vision": spec.supports_vision,
                    "supports_embeddings": spec.supports_embeddings,
                    "supports_model_listing": spec.supports_model_listing,
                    "docs_url": spec.docs_url,
                    "api_key_url": spec.api_key_url,
                    "suggested_models": spec.suggested_models,
                    "notes": spec.notes,
                },
                # Providers locais já vêm ligados: não custam nada e não exigem chave.
                enabled=spec.is_local and spec.slug in {"ollama", "omp"},
                is_local=spec.is_local,
                priority=10 if spec.is_local else 100,
            )
        )
    db.commit()


def seed_routes(db: Session) -> None:
    existing = {r.task for r in db.scalars(select(RoutingRule))}
    for task, slug, model, fb_slug, fb_model, temp, max_tokens in DEFAULT_ROUTES:
        if task in existing:
            continue
        db.add(
            RoutingRule(
                task=task,
                provider_slug=slug,
                model=model,
                fallback_provider_slug=fb_slug,
                fallback_model=fb_model,
                temperature=temp,
                max_tokens=max_tokens,
            )
        )
    db.commit()


def seed_default_library(db: Session) -> None:
    if db.scalar(select(Library).limit(1)):
        return
    db.add(
        Library(
            name="Minha biblioteca",
            description="Biblioteca padrão criada na primeira execução.",
            privacy_mode=PrivacyMode(settings.default_privacy_mode),
        )
    )
    db.commit()


def init_database() -> None:
    settings.ensure_dirs()
    create_schema()
    with session_scope() as db:
        seed_providers(db)
        seed_routes(db)
        seed_default_library(db)
    log.info("Banco de dados pronto em %s", settings.sqlalchemy_url)


def rebuild_fts() -> None:
    """Reconstrói o índice lexical (útil após importar dados por fora)."""
    if not str(engine.url).startswith("sqlite"):
        return
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM chunks_fts"))
        conn.execute(
            text("INSERT INTO chunks_fts(rowid, text) SELECT id, text FROM transcript_chunks")
        )
    log.info("FTS reconstruído")


if __name__ == "__main__":
    init_database()
