from __future__ import annotations

import shutil
import subprocess
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.events import bus
from app.db.models import (
    Job,
    Library,
    ProviderConfig,
    TranscriptChunk,
    UsageLog,
    Video,
    VideoStatus,
)
from app.db.session import get_db
from app.schemas import JobOut, StatsOut, SystemStatus
from app.services import media, transcription
from app.workers import queue

router = APIRouter(tags=["system"])


def gpu_info() -> dict:
    if not shutil.which("nvidia-smi"):
        return {"available": False, "name": "", "memory_total_mb": 0, "memory_used_mb": 0}
    try:
        out = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.used,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        name, total, used, util = [p.strip() for p in out.stdout.strip().split(",")]
        return {
            "available": True,
            "name": name,
            "memory_total_mb": int(total),
            "memory_used_mb": int(used),
            "utilization": int(util),
        }
    except Exception:  # noqa: BLE001
        return {"available": False, "name": "", "memory_total_mb": 0, "memory_used_mb": 0}


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "app": settings.app_name, "version": settings.version}


@router.get("/system/status", response_model=SystemStatus)
def system_status(db: Session = Depends(get_db)) -> SystemStatus:
    providers = list(db.scalars(select(ProviderConfig)))
    counts = {
        "videos": int(db.scalar(select(func.count(Video.id))) or 0),
        "ready": int(
            db.scalar(select(func.count(Video.id)).where(Video.status == VideoStatus.ready)) or 0
        ),
        "libraries": int(db.scalar(select(func.count(Library.id))) or 0),
        "chunks": int(db.scalar(select(func.count(TranscriptChunk.id))) or 0),
    }
    return SystemStatus(
        app=settings.app_name,
        version=settings.version,
        environment=settings.environment,
        ffmpeg=media.ffmpeg_available(),
        whisper=transcription.whisper_available(),
        gpu=gpu_info(),
        database=settings.sqlalchemy_url.split("://")[0],
        data_dir=str(settings.data_dir),
        providers_enabled=sum(1 for p in providers if p.enabled),
        providers_ok=sum(1 for p in providers if p.enabled and p.status == "ok"),
        queue=queue.stats(db),
        counts=counts,
        embedding_provider=settings.embedding_provider,
    )


@router.get("/stats", response_model=StatsOut)
def stats(db: Session = Depends(get_db)) -> StatsOut:
    total, ready, failed, seconds = db.execute(
        select(
            func.count(Video.id),
            func.coalesce(func.sum(case((Video.status == VideoStatus.ready, 1), else_=0)), 0),
            func.coalesce(func.sum(case((Video.status == VideoStatus.failed, 1), else_=0)), 0),
            func.coalesce(func.sum(Video.duration_seconds), 0.0),
        )
    ).one()

    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=30)
    cost = float(
        db.scalar(select(func.coalesce(func.sum(UsageLog.cost_usd), 0.0)).where(UsageLog.created_at >= since))
        or 0.0
    )
    top = db.execute(
        select(
            UsageLog.provider_slug,
            func.count(UsageLog.id),
            func.coalesce(func.sum(UsageLog.cost_usd), 0.0),
        )
        .where(UsageLog.created_at >= since)
        .group_by(UsageLog.provider_slug)
        .order_by(func.count(UsageLog.id).desc())
        .limit(6)
    ).all()

    recent = db.scalars(
        select(Video).where(Video.status == VideoStatus.ready).order_by(Video.processed_at.desc()).limit(8)
    ).all()

    return StatsOut(
        videos_total=int(total or 0),
        videos_ready=int(ready or 0),
        videos_failed=int(failed or 0),
        hours_indexed=round(float(seconds or 0) / 3600, 2),
        chunks=int(db.scalar(select(func.count(TranscriptChunk.id))) or 0),
        libraries=int(db.scalar(select(func.count(Library.id))) or 0),
        courses=int(db.scalar(select(func.count(func.distinct(Video.course)))) or 0),
        cost_last_30d=round(cost, 4),
        top_providers=[
            {"provider": slug or "—", "calls": int(calls), "cost": round(float(c), 4)}
            for slug, calls, c in top
        ],
        recent_activity=[
            {
                "video_id": v.id,
                "title": v.title,
                "course": v.course,
                "processed_at": v.processed_at.isoformat() if v.processed_at else None,
            }
            for v in recent
        ],
    )


# --------------------------------------------------------------------------- #
# Fila
# --------------------------------------------------------------------------- #
@router.get("/jobs", response_model=list[JobOut])
def list_jobs(
    status: str | None = None, limit: int = 50, db: Session = Depends(get_db)
) -> list[JobOut]:
    from app.db.models import JobStatus

    stmt = select(Job).order_by(Job.id.desc()).limit(limit)
    if status:
        stmt = stmt.where(Job.status == JobStatus(status))
    jobs = db.scalars(stmt).all()

    titles = {}
    video_ids = [j.video_id for j in jobs if j.video_id]
    if video_ids:
        titles = {
            vid: title
            for vid, title in db.execute(
                select(Video.id, Video.title).where(Video.id.in_(video_ids))
            )
        }

    out: list[JobOut] = []
    for job in jobs:
        item = JobOut.model_validate(job)
        item.kind = job.kind.value
        item.status = job.status.value
        item.video_title = titles.get(job.video_id, "")
        out.append(item)
    return out


@router.get("/jobs/stats")
def job_stats(db: Session = Depends(get_db)) -> dict:
    return queue.stats(db)


@router.post("/jobs/{job_id}/retry", status_code=202)
def retry_job(job_id: int, db: Session = Depends(get_db)) -> dict:
    from fastapi import HTTPException

    from app.db.models import JobStatus

    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job não encontrado")
    job.status = JobStatus.pending
    job.attempts = 0
    job.error = ""
    db.commit()
    return {"job_id": job.id, "status": "pending"}


@router.post("/jobs/requeue-stale", status_code=202)
def requeue_stale(db: Session = Depends(get_db)) -> dict:
    return {"requeued": queue.requeue_stale(db)}


# --------------------------------------------------------------------------- #
# Eventos em tempo real
# --------------------------------------------------------------------------- #
@router.get("/events")
async def events(replay: int = 0) -> StreamingResponse:
    return StreamingResponse(
        bus.stream(replay=replay),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
