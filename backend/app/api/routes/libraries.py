from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.db.models import Library, PrivacyMode, Video, VideoStatus
from app.db.session import get_db
from app.schemas import LibraryCreate, LibraryOut, LibraryUpdate

router = APIRouter(prefix="/libraries", tags=["libraries"])


def _serialize(db: Session, library: Library) -> LibraryOut:
    total, ready, duration = db.execute(
        select(
            func.count(Video.id),
            func.coalesce(
                func.sum(case((Video.status == VideoStatus.ready, 1), else_=0)), 0
            ),
            func.coalesce(func.sum(Video.duration_seconds), 0.0),
        ).where(Video.library_id == library.id)
    ).one()
    out = LibraryOut.model_validate(library)
    out.privacy_mode = library.privacy_mode.value
    out.video_count = int(total or 0)
    out.ready_count = int(ready or 0)
    out.total_duration = float(duration or 0.0)
    return out


@router.get("", response_model=list[LibraryOut])
def list_libraries(db: Session = Depends(get_db)) -> list[LibraryOut]:
    libraries = db.scalars(select(Library).order_by(Library.id)).all()
    return [_serialize(db, lib) for lib in libraries]


@router.post("", response_model=LibraryOut, status_code=201)
def create_library(payload: LibraryCreate, db: Session = Depends(get_db)) -> LibraryOut:
    library = Library(
        name=payload.name,
        description=payload.description,
        color=payload.color,
        privacy_mode=PrivacyMode(payload.privacy_mode),
    )
    db.add(library)
    db.commit()
    db.refresh(library)
    return _serialize(db, library)


@router.get("/{library_id}", response_model=LibraryOut)
def get_library(library_id: int, db: Session = Depends(get_db)) -> LibraryOut:
    library = db.get(Library, library_id)
    if not library:
        raise HTTPException(404, "Biblioteca não encontrada")
    return _serialize(db, library)


@router.patch("/{library_id}", response_model=LibraryOut)
def update_library(
    library_id: int, payload: LibraryUpdate, db: Session = Depends(get_db)
) -> LibraryOut:
    library = db.get(Library, library_id)
    if not library:
        raise HTTPException(404, "Biblioteca não encontrada")
    data = payload.model_dump(exclude_unset=True)
    if "privacy_mode" in data and data["privacy_mode"]:
        library.privacy_mode = PrivacyMode(data.pop("privacy_mode"))
    for key, value in data.items():
        if value is not None:
            setattr(library, key, value)
    db.commit()
    db.refresh(library)
    return _serialize(db, library)


@router.delete("/{library_id}", status_code=204)
def delete_library(library_id: int, db: Session = Depends(get_db)) -> None:
    library = db.get(Library, library_id)
    if not library:
        raise HTTPException(404, "Biblioteca não encontrada")
    db.delete(library)
    db.commit()


@router.get("/{library_id}/courses")
def list_courses(library_id: int, db: Session = Depends(get_db)) -> list[dict]:
    rows = db.execute(
        select(
            Video.course,
            func.count(Video.id),
            func.coalesce(func.sum(Video.duration_seconds), 0.0),
        )
        .where(Video.library_id == library_id)
        .group_by(Video.course)
        .order_by(Video.course)
    ).all()
    return [
        {"course": course or "Sem curso", "videos": int(count), "duration": float(duration)}
        for course, count, duration in rows
    ]
