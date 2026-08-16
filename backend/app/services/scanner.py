"""Varredura de pastas locais: descobre vídeos, evita reprocessar duplicados."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.logging import get_logger
from app.core.security import file_fingerprint
from app.db.models import Job, JobStatus, Source, TaskKind, Video, VideoStatus
from app.services import youtube

log = get_logger(__name__)

_ORDER_RE = re.compile(r"^\s*(\d{1,3})[\s._\-)]+")
_NOISE_RE = re.compile(r"[_\-]+")


@dataclass
class ScanResult:
    discovered: int = 0
    skipped: int = 0
    errors: int = 0
    files_seen: int = 0


def humanize(name: str) -> str:
    """'03 - aula_02_pool-de-liquidez.mp4' -> 'Aula 02 Pool De Liquidez'"""
    stem = Path(name).stem
    stem = _ORDER_RE.sub("", stem)
    stem = _NOISE_RE.sub(" ", stem)
    stem = re.sub(r"\s+", " ", stem).strip()
    return stem.title() if stem.islower() or stem.isupper() else stem


def order_index(name: str) -> int:
    m = _ORDER_RE.match(Path(name).stem)
    return int(m.group(1)) if m else 0


def iter_video_files(root: Path) -> list[Path]:
    exts = settings.video_ext_set
    files: list[Path] = []
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in exts and not path.name.startswith("."):
            files.append(path)
    return sorted(files)


def scan_source(db: Session, source: Source, *, auto_queue: bool = True) -> ScanResult:
    """Varre a pasta de uma fonte e cria os registros de vídeo faltantes."""
    result = ScanResult()
    root = Path(source.root_path).expanduser()
    if not root.exists() or not root.is_dir():
        raise FileNotFoundError(f"Pasta não encontrada: {root}")

    files = iter_video_files(root)
    result.files_seen = len(files)
    log.info("Scan '%s': %d arquivos de vídeo em %s", source.title, len(files), root)

    for path in files:
        try:
            existing_by_path = db.scalar(
                select(Video).where(
                    Video.library_id == source.library_id, Video.file_path == str(path)
                )
            )
            if existing_by_path:
                result.skipped += 1
                continue

            fingerprint = file_fingerprint(path)
            duplicate = db.scalar(
                select(Video).where(
                    Video.library_id == source.library_id, Video.file_hash == fingerprint
                )
            )
            if duplicate:
                # Mesmo conteúdo em outro caminho: atualiza o caminho, não reprocessa.
                duplicate.file_path = str(path)
                db.commit()
                result.skipped += 1
                continue

            rel = path.relative_to(root)
            parts = rel.parts[:-1]
            video = Video(
                library_id=source.library_id,
                source_id=source.id,
                title=humanize(path.name),
                course=parts[0] if parts else source.title or root.name,
                module=parts[1] if len(parts) > 1 else "",
                order_index=order_index(path.name),
                file_path=str(path),
                file_hash=fingerprint,
                file_size=path.stat().st_size,
                status=VideoStatus.discovered,
            )
            db.add(video)
            db.flush()

            if auto_queue:
                db.add(
                    Job(
                        kind=TaskKind.full_pipeline,
                        status=JobStatus.pending,
                        video_id=video.id,
                        library_id=source.library_id,
                        source_id=source.id,
                        priority=100 + video.order_index,
                        max_attempts=settings.job_max_attempts,
                    )
                )
                video.status = VideoStatus.queued
            db.commit()
            result.discovered += 1
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            result.errors += 1
            log.exception("Erro ao registrar %s: %s", path, exc)

    source.stats = {
        "files_seen": result.files_seen,
        "discovered": result.discovered,
        "skipped": result.skipped,
        "errors": result.errors,
    }
    source.sync_status = "idle"
    db.commit()
    return result


def scan_youtube_source(db: Session, source: Source, *, auto_queue: bool = True) -> ScanResult:
    """Lista uma playlist do YouTube (só metadados) e cria os vídeos faltantes.

    Espelha `scan_source`, mas sem tocar em disco: dedupe é por `youtube_id`
    em vez de hash de arquivo, e nenhum download acontece aqui — só na hora de
    transcrever cada vídeo (ver `youtube.download_audio_wav`, chamado pelo
    worker em `workers/pipeline.step_transcribe`).
    """
    result = ScanResult()
    playlist_title, entries = youtube.extract_playlist(source.url)
    result.files_seen = len(entries)
    log.info("Scan YouTube '%s': %d vídeos em %s", source.title, len(entries), source.url)

    course_name = source.title or playlist_title

    for entry in entries:
        try:
            existing = db.scalar(
                select(Video).where(
                    Video.library_id == source.library_id, Video.youtube_id == entry.youtube_id
                )
            )
            if existing:
                result.skipped += 1
                continue

            video = Video(
                library_id=source.library_id,
                source_id=source.id,
                title=entry.title,
                course=course_name,
                order_index=entry.playlist_index,
                youtube_id=entry.youtube_id,
                url=entry.url,
                channel=entry.channel,
                duration_seconds=entry.duration_seconds,
                # dedupe por hash não se aplica aqui (nada baixado ainda); usa o
                # próprio id do YouTube, que já é globalmente único.
                file_hash=f"youtube:{entry.youtube_id}",
                status=VideoStatus.discovered,
            )
            db.add(video)
            db.flush()

            if auto_queue:
                db.add(
                    Job(
                        kind=TaskKind.full_pipeline,
                        status=JobStatus.pending,
                        video_id=video.id,
                        library_id=source.library_id,
                        source_id=source.id,
                        priority=100 + video.order_index,
                        max_attempts=settings.job_max_attempts,
                    )
                )
                video.status = VideoStatus.queued
            db.commit()
            result.discovered += 1
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            result.errors += 1
            log.exception("Erro ao registrar vídeo %s da playlist: %s", entry.youtube_id, exc)

    source.title = source.title or playlist_title
    source.stats = {
        "files_seen": result.files_seen,
        "discovered": result.discovered,
        "skipped": result.skipped,
        "errors": result.errors,
    }
    source.sync_status = "idle"
    db.commit()
    return result


def preview_playlist(url: str, limit: int = 200) -> dict:
    """Pré-visualização usada pela UI antes de confirmar a importação de uma
    playlist — espelha `preview_folder`, mas sem tocar em disco."""
    try:
        playlist_title, entries = youtube.extract_playlist(url)
    except youtube.YoutubeError as exc:
        return {"exists": False, "error": str(exc), "count": 0, "courses": [], "files": []}

    return {
        "exists": True,
        "count": len(entries),
        "total_bytes": 0,  # não baixamos nada na prévia — não há tamanho pra estimar
        "courses": [playlist_title],
        "files": [
            {
                "path": e.url,
                "name": e.title,
                "title": e.title,
                "size": 0,
                "course": playlist_title,
                "duration": e.duration_seconds,
                "thumbnail": e.thumbnail,
            }
            for e in entries[:limit]
        ],
    }


def preview_folder(root_path: str, limit: int = 200) -> dict:
    """Pré-visualização usada pela UI antes de confirmar a importação."""
    root = Path(root_path).expanduser()
    if not root.exists():
        return {"exists": False, "files": [], "count": 0, "courses": []}
    files = iter_video_files(root)
    courses = sorted({(f.relative_to(root).parts[:-1] or (root.name,))[0] for f in files})
    return {
        "exists": True,
        "count": len(files),
        "total_bytes": sum(f.stat().st_size for f in files[:limit]),
        "courses": courses,
        "files": [
            {
                "path": str(f),
                "name": f.name,
                "title": humanize(f.name),
                "size": f.stat().st_size,
                "course": (f.relative_to(root).parts[:-1] or (root.name,))[0],
            }
            for f in files[:limit]
        ],
    }
