"""Enriquecimento com IA: resumos, capítulos, tópicos, tags e categoria."""

from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy.orm import Session

from app.config import settings
from app.core.logging import get_logger
from app.db.models import Library, PrivacyMode, Summary, Video
from app.providers import registry
from app.providers.base import ChatMessage
from app.services import prompts
from app.services.chunking import format_timestamp

log = get_logger(__name__)

_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


def parse_json(text: str) -> dict[str, Any]:
    """Modelos às vezes embrulham o JSON em markdown. Aqui a gente resolve."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = _JSON_BLOCK.search(text)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    raise ValueError(f"Resposta não é JSON válido: {text[:300]}")


def build_transcript_text(segments: list[dict], max_chars: int = 45_000) -> str:
    """Transcrição com timestamps, truncada de forma inteligente para caber no contexto."""
    lines = [f"[{format_timestamp(s['start'])}] {s['text'].strip()}" for s in segments]
    full = "\n".join(lines)
    if len(full) <= max_chars:
        return full
    # Mantém começo e fim — onde normalmente estão introdução e conclusão.
    head = full[: int(max_chars * 0.65)]
    tail = full[-int(max_chars * 0.3) :]
    return f"{head}\n\n[... trecho intermediário omitido por tamanho ...]\n\n{tail}"


def privacy_allows_remote(library: Library | None) -> bool:
    if library is None:
        return True
    return library.privacy_mode != PrivacyMode.local


async def enrich_video(
    db: Session, video: Video, segments: list[dict]
) -> Summary:
    """Gera e persiste o resumo completo de um vídeo."""
    library = db.get(Library, video.library_id)
    override = (library.routing_override or {}) if library else {}

    transcript = build_transcript_text(segments)
    messages = [
        ChatMessage("system", prompts.ENRICH_SYSTEM),
        ChatMessage(
            "user",
            prompts.ENRICH_USER.format(
                title=video.title,
                course=video.course or "—",
                duration=format_timestamp(video.duration_seconds),
                transcript=transcript,
            ),
        ),
    ]

    result = await registry.complete(
        db,
        "summarize",
        messages,
        override=override,
        json_mode=True,
        video_id=video.id,
        max_tokens=4000,
    )
    data = parse_json(result.text)

    chapters = _clean_chapters(data.get("chapters"), video.duration_seconds)

    summary = video.summary or Summary(video_id=video.id)
    summary.short_summary = str(data.get("short_summary", "")).strip()
    summary.long_summary = str(data.get("long_summary", "")).strip()
    summary.topics = _as_list(data.get("topics"))
    summary.chapters = chapters
    summary.keywords = _as_list(data.get("keywords"))
    summary.entities = _as_list(data.get("entities"))
    summary.suggested_questions = _as_list(data.get("suggested_questions"))
    summary.category = str(data.get("category", "")).strip()[:120]
    summary.model = f"{result.provider}:{result.model}"
    summary.version = (summary.version or 0) + 1

    if not video.language:
        video.language = str(data.get("language", "") or "")[:10]
    if summary.keywords and not video.tags:
        video.tags = summary.keywords[:12]

    db.add(summary)
    db.commit()
    db.refresh(summary)
    log.info("Vídeo %s enriquecido por %s", video.id, summary.model)
    return summary


async def summarize_course(db: Session, library_id: int, course: str) -> str:
    """Resumo de um curso inteiro a partir dos resumos das aulas."""
    from sqlalchemy import select

    rows = db.execute(
        select(Video.title, Summary.short_summary)
        .join(Summary, Summary.video_id == Video.id)
        .where(Video.library_id == library_id, Video.course == course)
        .order_by(Video.order_index, Video.id)
    ).all()
    if not rows:
        return "Nenhuma aula processada neste curso ainda."

    body = "\n\n".join(f"### {title}\n{summary}" for title, summary in rows)
    body = body[: settings.max_context_chars]
    result = await registry.complete(
        db,
        "chat_complex",
        [
            ChatMessage("system", prompts.COURSE_SUMMARY_SYSTEM),
            ChatMessage("user", f"CURSO: {course}\n\nRESUMOS DAS AULAS:\n{body}"),
        ],
        max_tokens=2500,
    )
    return result.text


def _as_list(value: Any) -> list:
    if isinstance(value, list):
        return [v for v in value if v not in (None, "")]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _clean_chapters(value: Any, duration: float) -> list[dict]:
    chapters: list[dict] = []
    if not isinstance(value, list):
        return chapters
    for item in value:
        if not isinstance(item, dict):
            continue
        try:
            start = float(item.get("start", 0) or 0)
            end = float(item.get("end", 0) or 0)
        except (TypeError, ValueError):
            continue
        title = str(item.get("title", "")).strip()
        if not title:
            continue
        if duration and start > duration:
            continue
        chapters.append({"title": title[:300], "start": round(start, 1), "end": round(end, 1)})
    chapters.sort(key=lambda c: c["start"])
    return chapters
