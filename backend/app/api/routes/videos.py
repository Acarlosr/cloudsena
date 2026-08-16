from __future__ import annotations

import mimetypes
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import (
    Summary,
    TranscriptChunk,
    Transcript,
    Video,
    VideoStatus,
    WatchStatus,
)
from app.db.session import get_db
from app.schemas import SummaryOut, TranscriptOut, VideoDetail, VideoOut, VideoUpdate
from app.services import transcription
from app.workers import queue

router = APIRouter(prefix="/videos", tags=["videos"])

CHUNK = 1024 * 1024


def _to_out(video: Video) -> VideoOut:
    out = VideoOut.model_validate(video)
    out.status = video.status.value
    out.watch_status = video.watch_status.value
    return out


@router.get("", response_model=list[VideoOut])
def list_videos(
    library_id: int | None = None,
    course: str | None = None,
    status: str | None = None,
    watch_status: str | None = None,
    favorites: bool = False,
    q: str = "",
    sort: str = Query("recent", pattern="^(recent|title|duration|progress|course)$"),
    limit: int = Query(60, le=500),
    offset: int = 0,
    db: Session = Depends(get_db),
) -> list[VideoOut]:
    stmt = select(Video)
    if library_id:
        stmt = stmt.where(Video.library_id == library_id)
    if course:
        stmt = stmt.where(Video.course == course)
    if status:
        stmt = stmt.where(Video.status == VideoStatus(status))
    if watch_status:
        stmt = stmt.where(Video.watch_status == WatchStatus(watch_status))
    if favorites:
        stmt = stmt.where(Video.is_favorite.is_(True))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Video.title.ilike(like), Video.course.ilike(like)))

    order = {
        "recent": Video.created_at.desc(),
        "title": Video.title.asc(),
        "duration": Video.duration_seconds.desc(),
        "progress": Video.watched_seconds.desc(),
        "course": Video.course.asc(),
    }[sort]
    stmt = stmt.order_by(order, Video.order_index, Video.id).limit(limit).offset(offset)
    return [_to_out(v) for v in db.scalars(stmt)]


@router.get("/{video_id}", response_model=VideoDetail)
def get_video(video_id: int, db: Session = Depends(get_db)) -> VideoDetail:
    video = db.get(Video, video_id)
    if not video:
        raise HTTPException(404, "Vídeo não encontrado")

    detail = VideoDetail.model_validate(video)
    detail.status = video.status.value
    detail.watch_status = video.watch_status.value
    if video.summary:
        detail.summary = SummaryOut.model_validate(video.summary)
    detail.has_transcript = bool(
        db.scalar(
            select(func.count(Transcript.id)).where(
                Transcript.video_id == video_id, Transcript.is_active.is_(True)
            )
        )
    )
    detail.chunk_count = int(
        db.scalar(
            select(func.count(TranscriptChunk.id)).where(TranscriptChunk.video_id == video_id)
        )
        or 0
    )
    return detail


@router.patch("/{video_id}", response_model=VideoOut)
def update_video(video_id: int, payload: VideoUpdate, db: Session = Depends(get_db)) -> VideoOut:
    video = db.get(Video, video_id)
    if not video:
        raise HTTPException(404, "Vídeo não encontrado")
    data = payload.model_dump(exclude_unset=True)
    explicit_watch_status = bool(data.get("watch_status"))
    watched_seconds_changed = data.get("watched_seconds") is not None

    if explicit_watch_status:
        video.watch_status = WatchStatus(data.pop("watch_status"))
    for key, value in data.items():
        if value is not None:
            setattr(video, key, value)

    # Auto-avança o status de leitura conforme o progresso do player — mas só
    # quando esta requisição de fato reportou progresso, e nunca por cima de uma
    # escolha explícita do usuário (ex.: marcar "revisitar" num vídeo já visto).
    # Sem essas duas guardas, qualquer PATCH sem relação com o player — favoritar,
    # editar nota, renomear — reescreveria "revisitar" de volta para "concluído".
    if not explicit_watch_status and watched_seconds_changed:
        if video.duration_seconds and video.watched_seconds / video.duration_seconds > 0.95:
            video.watch_status = WatchStatus.completed
        elif video.watched_seconds > 30 and video.watch_status == WatchStatus.unwatched:
            video.watch_status = WatchStatus.in_progress

    db.commit()
    db.refresh(video)
    return _to_out(video)


@router.delete("/{video_id}", status_code=204)
def delete_video(video_id: int, db: Session = Depends(get_db)) -> None:
    video = db.get(Video, video_id)
    if not video:
        raise HTTPException(404, "Vídeo não encontrado")
    db.delete(video)  # o arquivo original NUNCA é apagado
    db.commit()


@router.post("/{video_id}/retry", status_code=202)
def retry_video(video_id: int, db: Session = Depends(get_db)) -> dict:
    job = queue.retry_video(db, video_id)
    return {"job_id": job.id, "status": "queued"}


@router.get("/{video_id}/transcript", response_model=TranscriptOut)
def get_transcript(video_id: int, db: Session = Depends(get_db)) -> TranscriptOut:
    transcript = db.scalar(
        select(Transcript).where(
            Transcript.video_id == video_id, Transcript.is_active.is_(True)
        )
    )
    if not transcript:
        raise HTTPException(404, "Transcrição ainda não disponível")
    data = transcription.load_transcript(transcript.text_path)
    return TranscriptOut(
        video_id=video_id,
        language=transcript.language,
        engine=transcript.engine,
        model=transcript.model,
        confidence=transcript.confidence,
        segments=data.get("segments", []),
    )


@router.get("/{video_id}/thumbnail")
def get_thumbnail(video_id: int, db: Session = Depends(get_db)) -> Response:
    video = db.get(Video, video_id)
    if not video or not video.thumbnail_path:
        raise HTTPException(404, "Sem thumbnail")
    path = settings.data_dir / video.thumbnail_path
    if not path.exists():
        raise HTTPException(404, "Sem thumbnail")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "max-age=86400"})


@router.get("/{video_id}/stream")
def stream_video(video_id: int, request: Request, db: Session = Depends(get_db)) -> Response:
    """Streaming com suporte a Range — permite pular direto para um minuto."""
    video = db.get(Video, video_id)
    if not video:
        raise HTTPException(404, "Vídeo não encontrado")
    if video.youtube_id:
        raise HTTPException(
            400, "Vídeo do YouTube não é servido por aqui — use o player embutido do YouTube."
        )
    if not video.file_path:
        raise HTTPException(404, "Vídeo não encontrado")
    path = Path(video.file_path)
    if not path.exists():
        raise HTTPException(410, f"Arquivo indisponível: {path}")

    file_size = path.stat().st_size
    media_type = mimetypes.guess_type(str(path))[0] or "video/mp4"
    range_header = request.headers.get("range")

    if not range_header:
        return FileResponse(path, media_type=media_type)

    try:
        units, _, range_spec = range_header.partition("=")
        start_str, _, end_str = range_spec.partition("-")
        start = int(start_str) if start_str else 0
        end = int(end_str) if end_str else min(start + CHUNK * 8, file_size - 1)
    except ValueError:
        raise HTTPException(416, "Range inválido")

    start = max(0, min(start, file_size - 1))
    end = max(start, min(end, file_size - 1))
    length = end - start + 1

    def iterator():
        with path.open("rb") as fh:
            fh.seek(start)
            remaining = length
            while remaining > 0:
                data = fh.read(min(CHUNK, remaining))
                if not data:
                    break
                remaining -= len(data)
                yield data

    return StreamingResponse(
        iterator(),
        status_code=206,
        media_type=media_type,
        headers={
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(length),
        },
    )


@router.get("/{video_id}/chunks")
def list_chunks(video_id: int, db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(
        select(TranscriptChunk)
        .where(TranscriptChunk.video_id == video_id)
        .order_by(TranscriptChunk.seq)
    )
    return [
        {
            "id": c.id,
            "seq": c.seq,
            "start": c.start_seconds,
            "end": c.end_seconds,
            "text": c.text,
            "chapter": c.chapter,
            "indexed": c.embedding is not None,
        }
        for c in rows
    ]
