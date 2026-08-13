from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Library, Source, SourceType, TaskKind
from app.db.session import get_db
from app.schemas import FolderPreviewRequest, SourceCreate, SourceOut
from app.services import scanner
from app.workers import queue

router = APIRouter(prefix="/sources", tags=["sources"])


def _serialize(source: Source) -> SourceOut:
    out = SourceOut.model_validate(source)
    out.source_type = source.source_type.value
    return out


@router.get("", response_model=list[SourceOut])
def list_sources(library_id: int | None = None, db: Session = Depends(get_db)) -> list[SourceOut]:
    stmt = select(Source).order_by(Source.id)
    if library_id:
        stmt = stmt.where(Source.library_id == library_id)
    return [_serialize(s) for s in db.scalars(stmt)]


@router.post("/preview-folder")
def preview_folder(payload: FolderPreviewRequest) -> dict:
    """Mostra o que será importado antes de confirmar."""
    return scanner.preview_folder(payload.path)


@router.post("", response_model=SourceOut, status_code=201)
def create_source(payload: SourceCreate, db: Session = Depends(get_db)) -> SourceOut:
    if not db.get(Library, payload.library_id):
        raise HTTPException(404, "Biblioteca não encontrada")

    source_type = SourceType(payload.source_type)
    if source_type == SourceType.local_folder:
        preview = scanner.preview_folder(payload.root_path)
        if not preview["exists"]:
            raise HTTPException(400, f"Pasta não encontrada: {payload.root_path}")

    source = Source(
        library_id=payload.library_id,
        source_type=source_type,
        title=payload.title or payload.root_path.rstrip("/").split("/")[-1] or payload.url,
        root_path=payload.root_path,
        url=payload.url,
        auto_sync=payload.auto_sync,
    )
    db.add(source)
    db.commit()
    db.refresh(source)

    if payload.scan_now and source_type == SourceType.local_folder:
        queue.enqueue(
            db,
            TaskKind.scan_source,
            source_id=source.id,
            library_id=source.library_id,
            priority=10,
        )
        source.sync_status = "queued"
        db.commit()

    return _serialize(source)


@router.post("/{source_id}/scan", response_model=SourceOut)
def scan_source(source_id: int, db: Session = Depends(get_db)) -> SourceOut:
    source = db.get(Source, source_id)
    if not source:
        raise HTTPException(404, "Fonte não encontrada")
    queue.enqueue(
        db, TaskKind.scan_source, source_id=source.id, library_id=source.library_id, priority=10
    )
    source.sync_status = "queued"
    db.commit()
    db.refresh(source)
    return _serialize(source)


@router.delete("/{source_id}", status_code=204)
def delete_source(source_id: int, db: Session = Depends(get_db)) -> None:
    source = db.get(Source, source_id)
    if not source:
        raise HTTPException(404, "Fonte não encontrada")
    db.delete(source)
    db.commit()
