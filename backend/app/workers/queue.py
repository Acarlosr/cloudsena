"""Fila de trabalho persistida no banco — sobrevive a reinício da máquina.

Nenhuma dependência de Redis no MVP: o próprio banco é a fila, com claim
atômico por transação e heartbeat para recuperar jobs órfãos.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.events import bus
from app.core.logging import get_logger
from app.db.models import Job, JobStatus, TaskKind, Video, VideoStatus, utcnow

log = get_logger(__name__)

STALE_AFTER = timedelta(minutes=15)


def enqueue(
    db: Session,
    kind: TaskKind,
    *,
    video_id: int | None = None,
    library_id: int | None = None,
    source_id: int | None = None,
    payload: dict | None = None,
    priority: int = 100,
    max_attempts: int = 3,
) -> Job:
    job = Job(
        kind=kind,
        video_id=video_id,
        library_id=library_id,
        source_id=source_id,
        payload=payload or {},
        priority=priority,
        max_attempts=max_attempts,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    bus.publish_threadsafe(
        "job.created", {"job_id": job.id, "kind": kind.value, "video_id": video_id}
    )
    return job


def claim_next(db: Session, worker_id: str) -> Job | None:
    """Pega o próximo job pendente de forma segura para múltiplos workers."""
    stmt = (
        select(Job)
        .where(Job.status == JobStatus.pending)
        .order_by(Job.priority, Job.id)
        .limit(1)
    )
    # SQLite não suporta SELECT ... FOR UPDATE SKIP LOCKED; nele a corrida é
    # resolvida pelo UPDATE condicional abaixo.
    if db.bind.dialect.name != "sqlite":
        stmt = stmt.with_for_update(skip_locked=True)

    job = db.scalar(stmt)
    if job is None:
        return None

    updated = db.execute(
        update(Job)
        .where(Job.id == job.id, Job.status == JobStatus.pending)
        .values(
            status=JobStatus.running,
            worker_id=worker_id,
            attempts=Job.attempts + 1,
            started_at=utcnow(),
            heartbeat_at=utcnow(),
            error="",
        )
    )
    db.commit()
    if updated.rowcount == 0:
        return None  # outro worker pegou primeiro
    db.refresh(job)
    return job


def heartbeat(db: Session, job: Job, *, progress: float | None = None, stage: str = "") -> None:
    job.heartbeat_at = utcnow()
    if progress is not None:
        job.progress = max(0.0, min(1.0, progress))
    if stage:
        job.stage = stage
    db.commit()
    bus.publish_threadsafe(
        "job.progress",
        {
            "job_id": job.id,
            "video_id": job.video_id,
            "progress": job.progress,
            "stage": job.stage,
        },
    )


def finish(db: Session, job: Job, *, success: bool, error: str = "") -> None:
    job.status = JobStatus.done if success else JobStatus.failed
    job.finished_at = utcnow()
    job.progress = 1.0 if success else job.progress
    job.error = error[:2000]
    db.commit()
    bus.publish_threadsafe(
        "job.finished",
        {"job_id": job.id, "video_id": job.video_id, "success": success, "error": error[:300]},
    )


def retry(db: Session, job: Job, error: str) -> bool:
    """Devolve o job para a fila se ainda houver tentativas."""
    if job.attempts >= job.max_attempts:
        finish(db, job, success=False, error=error)
        return False
    job.status = JobStatus.pending
    job.error = error[:2000]
    job.heartbeat_at = None
    db.commit()
    log.warning("Job %s reagendado (tentativa %s/%s)", job.id, job.attempts, job.max_attempts)
    return True


def requeue_stale(db: Session) -> int:
    """Recupera jobs que ficaram 'running' após um desligamento abrupto."""
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - STALE_AFTER
    result = db.execute(
        update(Job)
        .where(
            Job.status == JobStatus.running,
            (Job.heartbeat_at.is_(None)) | (Job.heartbeat_at < cutoff),
        )
        .values(status=JobStatus.pending, worker_id="", stage="")
    )
    db.commit()
    if result.rowcount:
        log.info("%d job(s) órfãos devolvidos à fila", result.rowcount)
    return result.rowcount


def retry_video(db: Session, video_id: int) -> Job:
    """Reprocessa um vídeo específico (botão 'tentar novamente' da UI)."""
    video = db.get(Video, video_id)
    if video is None:
        raise ValueError(f"Vídeo {video_id} não encontrado")
    video.status = VideoStatus.queued
    video.error_message = ""
    db.commit()
    return enqueue(
        db,
        TaskKind.full_pipeline,
        video_id=video.id,
        library_id=video.library_id,
        priority=50,
    )


def stats(db: Session) -> dict:
    from sqlalchemy import func

    rows = db.execute(select(Job.status, func.count(Job.id)).group_by(Job.status)).all()
    counts = {status.value if hasattr(status, "value") else str(status): n for status, n in rows}
    return {
        "pending": counts.get("pending", 0),
        "running": counts.get("running", 0),
        "done": counts.get("done", 0),
        "failed": counts.get("failed", 0),
        "canceled": counts.get("canceled", 0),
    }
