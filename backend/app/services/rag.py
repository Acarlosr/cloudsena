"""RAG com citações rastreáveis: cada resposta aponta vídeo + minuto exato."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.config import settings
from app.core.logging import get_logger
from app.db.models import Library, Video
from app.providers import registry
from app.providers.base import ChatMessage
from app.services import prompts
from app.services.chunking import format_timestamp
from app.services.enrichment import parse_json
from app.services.search import Hit, SearchScope, hybrid_search

log = get_logger(__name__)

_CITATION_RE = re.compile(r"\[(\d{1,2})\]")


@dataclass
class Answer:
    text: str
    citations: list[dict] = field(default_factory=list)
    model: str = ""
    provider: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    grounded: bool = True
    scope: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "citations": self.citations,
            "model": self.model,
            "provider": self.provider,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "cost_usd": round(self.cost_usd, 6),
            "latency_ms": self.latency_ms,
            "grounded": self.grounded,
            "scope": self.scope,
        }


NOT_FOUND = (
    "Não encontrei esse assunto nos vídeos desta biblioteca. "
    "Tente reformular com outras palavras, ou verifique se os vídeos relevantes "
    "já terminaram de ser processados."
)


def build_context(hits: list[Hit], max_chars: int | None = None) -> tuple[str, list[Hit]]:
    """Monta o contexto numerado e devolve apenas os trechos que couberam."""
    budget = max_chars or settings.max_context_chars
    parts: list[str] = []
    used: list[Hit] = []
    total = 0

    for idx, hit in enumerate(hits, start=1):
        header = (
            f"[{idx}] Curso: {hit.course or '—'} | Vídeo: {hit.video_title} | "
            f"Trecho: {format_timestamp(hit.start)}–{format_timestamp(hit.end)}"
        )
        if hit.chapter:
            header += f" | Capítulo: {hit.chapter}"
        block = f"{header}\n{hit.text}\n"
        if total + len(block) > budget and used:
            break
        parts.append(block)
        used.append(hit)
        total += len(block)

    return "\n".join(parts), used


async def rerank(db: Session, question: str, hits: list[Hit], top_k: int) -> list[Hit]:
    """Reordena por relevância usando o modelo configurado para 'rerank'.

    Falha de rerank nunca derruba a busca — cai no ranking original.
    """
    if len(hits) <= top_k:
        return hits[:top_k]

    candidates = "\n".join(
        f"id={h.chunk_id} | {h.video_title} | {h.text[:400]}" for h in hits[:24]
    )
    try:
        result = await registry.complete(
            db,
            "rerank",
            [
                ChatMessage("system", prompts.RERANK_SYSTEM),
                ChatMessage(
                    "user", prompts.RERANK_USER.format(question=question, candidates=candidates)
                ),
            ],
            json_mode=True,
            max_tokens=1200,
            temperature=0.0,
        )
        data = parse_json(result.text)
        scores = {int(r["id"]): float(r.get("score", 0)) for r in data.get("ranking", [])}
    except Exception as exc:  # noqa: BLE001
        log.info("Rerank indisponível (%s); usando ordem híbrida", exc)
        return hits[:top_k]

    ranked = sorted(hits, key=lambda h: scores.get(h.chunk_id, -1.0), reverse=True)
    kept = [h for h in ranked if scores.get(h.chunk_id, 0) >= 3.0] or ranked
    return kept[:top_k]


def extract_citations(answer_text: str, used: list[Hit]) -> list[dict]:
    """Devolve apenas as fontes realmente citadas — com deep link para o minuto."""
    referenced = {int(n) for n in _CITATION_RE.findall(answer_text)}
    citations: list[dict] = []
    for idx, hit in enumerate(used, start=1):
        if referenced and idx not in referenced:
            continue
        citations.append(
            {
                "marker": idx,
                "video_id": hit.video_id,
                "video_title": hit.video_title,
                "course": hit.course,
                "chapter": hit.chapter,
                "start": round(hit.start, 2),
                "end": round(hit.end, 2),
                "start_label": format_timestamp(hit.start),
                "end_label": format_timestamp(hit.end),
                "thumbnail": hit.thumbnail,
                "excerpt": hit.text[:320],
                "deep_link": f"/video/{hit.video_id}?t={int(hit.start)}",
            }
        )
    return citations


async def answer_question(
    db: Session,
    question: str,
    *,
    library_id: int | None = None,
    video_ids: list[int] | None = None,
    course: str = "",
    task: str = "chat",
    use_rerank: bool = True,
) -> Answer:
    scope = SearchScope(library_id=library_id, video_ids=video_ids or [], course=course)
    hits = await hybrid_search(db, question, scope)

    scope_info = {
        "library_id": library_id,
        "course": course,
        "video_ids": video_ids or [],
        "candidates": len(hits),
    }

    if not hits:
        return Answer(text=NOT_FOUND, grounded=False, scope=scope_info)

    if use_rerank:
        hits = await rerank(db, question, hits, settings.rerank_top_k)
    else:
        hits = hits[: settings.rerank_top_k]

    context, used = build_context(hits)
    if not used:
        return Answer(text=NOT_FOUND, grounded=False, scope=scope_info)

    library = db.get(Library, library_id) if library_id else None
    override = (library.routing_override or {}) if library else {}

    result = await registry.complete(
        db,
        task,
        [
            ChatMessage("system", prompts.RAG_SYSTEM),
            ChatMessage("user", prompts.RAG_USER.format(question=question, context=context)),
        ],
        override=override,
        max_tokens=2000,
    )

    citations = extract_citations(result.text, used)
    grounded = bool(citations) and "não encontrei" not in result.text.lower()[:120]

    return Answer(
        text=result.text,
        citations=citations,
        model=result.model,
        provider=result.provider,
        tokens_in=result.tokens_in,
        tokens_out=result.tokens_out,
        cost_usd=result.cost_usd,
        latency_ms=result.latency_ms,
        grounded=grounded,
        scope=scope_info,
    )


async def suggest_title(db: Session, question: str) -> str:
    try:
        result = await registry.complete(
            db,
            "title",
            [ChatMessage("system", prompts.TITLE_SYSTEM), ChatMessage("user", question)],
            max_tokens=30,
        )
        return result.text.strip().strip('"')[:80] or question[:60]
    except Exception:  # noqa: BLE001
        return question[:60]


def video_scope_ids(db: Session, library_id: int | None, course: str) -> list[int]:
    from sqlalchemy import select

    stmt = select(Video.id)
    if library_id:
        stmt = stmt.where(Video.library_id == library_id)
    if course:
        stmt = stmt.where(Video.course == course)
    return [r[0] for r in db.execute(stmt)]
