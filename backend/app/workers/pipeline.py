"""Máquina de estados do processamento de vídeo.

discovered → queued → extracting → transcribing → summarizing → indexing → ready
                                        ↓
                                      failed

Cada etapa é idempotente e verifica se já foi concluída antes de rodar de novo.
Se a máquina desligar no meio, o job retoma do último estágio concluído.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.events import bus
from app.core.logging import get_logger
from app.db.models import (
    Job,
    Source,
    Transcript,
    TranscriptChunk,
    Video,
    VideoStatus,
    utcnow,
)
from app.services import chunking, embeddings, enrichment, media, scanner, transcription
from app.workers import queue

log = get_logger(__name__)


def _set_status(db: Session, video: Video, status: VideoStatus, progress: float = 0.0) -> None:
    video.status = status
    video.stage_progress = progress
    db.commit()
    bus.publish_threadsafe(
        "video.status",
        {
            "video_id": video.id,
            "library_id": video.library_id,
            "status": status.value,
            "progress": progress,
            "title": video.title,
        },
    )


# --------------------------------------------------------------------------- #
# Etapas
# --------------------------------------------------------------------------- #
def step_probe(db: Session, video: Video) -> None:
    """Metadados técnicos + thumbnail. Barato e sempre local."""
    path = Path(video.file_path)
    if not path.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {path}")

    if not video.duration_seconds:
        info = media.probe(path)
        video.duration_seconds = info.duration
        video.width = info.width
        video.height = info.height
        video.codec = info.codec
        video.file_size = info.size or video.file_size
        if not info.has_audio:
            raise ValueError("O arquivo não possui trilha de áudio para transcrever.")
        db.commit()

    if not video.thumbnail_path or not (settings.data_dir / video.thumbnail_path).exists():
        video.thumbnail_path = media.make_thumbnail(path, video.id)
        db.commit()


def step_transcribe(db: Session, job: Job, video: Video) -> Transcript:
    """Extrai áudio e transcreve. Reaproveita transcrição existente se houver."""
    existing = db.scalar(
        select(Transcript).where(
            Transcript.video_id == video.id, Transcript.is_active.is_(True)
        )
    )
    if existing and (settings.data_dir / existing.text_path).exists():
        log.info("Vídeo %s já transcrito — pulando etapa", video.id)
        return existing

    _set_status(db, video, VideoStatus.extracting, 0.05)
    audio_path = media.extract_audio(Path(video.file_path), video.id)

    _set_status(db, video, VideoStatus.transcribing, 0.10)

    # Whisper chama isso a cada segmento (podem ser centenas numa aula longa).
    # Persistimos no banco só a cada ~1,5s de trabalho real — o suficiente para a
    # barra de progresso parecer contínua sem martelar o SQLite com um commit por
    # segmento. O evento SSE, esse sim, é publicado sempre: é o que o usuário vê.
    last_persisted = {"at": time.monotonic()}

    def on_progress(ratio: float, _preview: str) -> None:
        overall = 0.10 + ratio * 0.55
        video.stage_progress = overall
        now = time.monotonic()
        if now - last_persisted["at"] >= 1.5:
            queue.heartbeat(db, job, progress=overall, stage="transcribing")
            last_persisted["at"] = now
        else:
            bus.publish_threadsafe(
                "job.progress",
                {"job_id": job.id, "video_id": video.id, "progress": overall, "stage": "transcribing"},
            )

    try:
        result = transcription.transcribe(
            audio_path,
            language=video.language or None,
            on_progress=on_progress,
        )
    finally:
        media.cleanup_temp(video.id)

    if not result.segments:
        raise ValueError("Transcrição vazia — o vídeo tem áudio audível?")

    json_path, txt_path = transcription.save_transcript(video.id, result)

    # desativa versões anteriores
    for old in db.scalars(select(Transcript).where(Transcript.video_id == video.id)):
        old.is_active = False

    transcript = Transcript(
        video_id=video.id,
        engine=result.engine,
        model=result.model,
        language=result.language,
        text_path=json_path,
        plain_path=txt_path,
        confidence=result.confidence,
        duration_processed=result.duration,
        version=1,
        is_active=True,
    )
    db.add(transcript)
    if not video.language:
        video.language = result.language
    db.commit()
    db.refresh(transcript)
    return transcript


async def step_enrich(db: Session, video: Video, transcript: Transcript) -> list[dict]:
    _set_status(db, video, VideoStatus.summarizing, 0.70)
    data = transcription.load_transcript(transcript.text_path)
    segments = data.get("segments", [])
    try:
        await enrichment.enrich_video(db, video, segments)
    except Exception as exc:  # noqa: BLE001
        # Resumo é valioso, mas não pode bloquear a indexação/busca.
        log.warning("Enriquecimento falhou no vídeo %s: %s", video.id, exc)
        video.error_message = f"Resumo indisponível: {exc}"[:1000]
        db.commit()
    return segments


async def step_index(db: Session, video: Video, transcript: Transcript, segments: list[dict]) -> int:
    _set_status(db, video, VideoStatus.indexing, 0.85)

    db.execute(delete(TranscriptChunk).where(TranscriptChunk.video_id == video.id))
    db.commit()

    chapters = video.summary.chapters if video.summary else []
    chunks = chunking.assign_chapters(chunking.chunk_segments(segments), chapters)

    rows = [
        TranscriptChunk(
            video_id=video.id,
            transcript_id=transcript.id,
            library_id=video.library_id,
            seq=c.seq,
            start_seconds=c.start,
            end_seconds=c.end,
            text=c.text,
            chapter=c.chapter,
            token_estimate=c.token_estimate,
        )
        for c in chunks
    ]
    db.add_all(rows)
    db.commit()

    chunk_ids = [r.id for r in rows]
    if settings.embedding_provider != "none" and chunk_ids:
        try:
            await embeddings.embed_chunks(db, chunk_ids)
        except Exception as exc:  # noqa: BLE001
            # Sem embeddings a busca lexical continua funcionando.
            log.warning("Embeddings falharam no vídeo %s: %s", video.id, exc)
    return len(rows)


# --------------------------------------------------------------------------- #
# Orquestração
# --------------------------------------------------------------------------- #
async def run_full_pipeline(db: Session, job: Job) -> None:
    video = db.get(Video, job.video_id)
    if video is None:
        raise ValueError(f"Vídeo {job.video_id} não existe mais")

    # step_probe (ffmpeg) e step_transcribe (faster-whisper) são bloqueantes e podem
    # levar minutos. Rodar em thread evita travar o event loop — e com ele a API,
    # o SSE de progresso e qualquer outro job, quando o worker roda embutido no
    # mesmo processo (padrão em `make dev`). db.get acima já resolveu `video`;
    # as duas chamadas usam a mesma sessão `db`, sempre de uma única thread por vez.
    queue.heartbeat(db, job, progress=0.02, stage="probe")
    await asyncio.to_thread(step_probe, db, video)

    queue.heartbeat(db, job, progress=0.05, stage="transcribe")
    transcript = await asyncio.to_thread(step_transcribe, db, job, video)

    queue.heartbeat(db, job, progress=0.70, stage="enrich")
    segments = await step_enrich(db, video, transcript)

    queue.heartbeat(db, job, progress=0.85, stage="index")
    count = await step_index(db, video, transcript, segments)

    video.processed_at = utcnow()
    video.error_message = video.error_message or ""
    _set_status(db, video, VideoStatus.ready, 1.0)
    log.info("Vídeo %s pronto (%d trechos indexados)", video.id, count)


def run_scan_source(db: Session, job: Job) -> None:
    source = db.get(Source, job.source_id)
    if source is None:
        raise ValueError(f"Fonte {job.source_id} não existe mais")
    source.sync_status = "syncing"
    db.commit()
    result = scanner.scan_source(db, source)
    bus.publish_threadsafe(
        "source.scanned",
        {
            "source_id": source.id,
            "library_id": source.library_id,
            "discovered": result.discovered,
            "skipped": result.skipped,
        },
    )


async def execute(db: Session, job: Job) -> None:
    """Ponto único de execução de qualquer job."""
    from app.db.models import TaskKind

    if job.kind == TaskKind.full_pipeline:
        await run_full_pipeline(db, job)
    elif job.kind == TaskKind.scan_source:
        await asyncio.to_thread(run_scan_source, db, job)
    elif job.kind == TaskKind.thumbnail:
        video = db.get(Video, job.video_id)
        if video:
            video.thumbnail_path = media.make_thumbnail(Path(video.file_path), video.id)
            db.commit()
    elif job.kind == TaskKind.embed:
        ids = [r[0] for r in db.execute(
            select(TranscriptChunk.id).where(
                TranscriptChunk.video_id == job.video_id,
                TranscriptChunk.embedding.is_(None),
            )
        )]
        if ids:
            await embeddings.embed_chunks(db, ids)
    else:
        raise ValueError(f"Tipo de job não suportado: {job.kind}")


def mark_video_failed(db: Session, job: Job, error: str) -> None:
    if not job.video_id:
        return
    video = db.get(Video, job.video_id)
    if video:
        video.status = VideoStatus.failed
        video.error_message = error[:2000]
        db.commit()
        bus.publish_threadsafe(
            "video.status",
            {"video_id": video.id, "status": "failed", "error": error[:300]},
        )
