"""Busca híbrida: lexical (FTS5/BM25) + semântica (embeddings), fundidas por RRF.

RRF (Reciprocal Rank Fusion) é robusto porque não exige normalizar escores de
sistemas diferentes — só as posições no ranking.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy import select, text as sql_text
from sqlalchemy.orm import Session

from app.config import settings
from app.core.logging import get_logger
from app.db.models import TranscriptChunk, Video, VideoStatus
from app.services import embeddings as emb

log = get_logger(__name__)

RRF_K = 60
_FTS_CLEAN = re.compile(r"[^\wÀ-ÿ\s]", re.UNICODE)


@dataclass
class Hit:
    chunk_id: int
    video_id: int
    video_title: str
    course: str
    start: float
    end: float
    text: str
    chapter: str = ""
    score: float = 0.0
    lexical_rank: int | None = None
    semantic_rank: int | None = None
    thumbnail: str = ""

    def to_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "video_id": self.video_id,
            "video_title": self.video_title,
            "course": self.course,
            "start": round(self.start, 2),
            "end": round(self.end, 2),
            "text": self.text,
            "chapter": self.chapter,
            "score": round(self.score, 5),
            "thumbnail": self.thumbnail,
        }


@dataclass
class SearchScope:
    library_id: int | None = None
    video_ids: list[int] = field(default_factory=list)
    course: str = ""


def fts_available(db: Session) -> bool:
    if not str(db.bind.url).startswith("sqlite"):
        return False
    try:
        row = db.execute(
            sql_text("SELECT name FROM sqlite_master WHERE type='table' AND name='chunks_fts'")
        ).first()
        return row is not None
    except Exception:  # noqa: BLE001
        return False


def sanitize_query(query: str) -> str:
    cleaned = _FTS_CLEAN.sub(" ", query)
    terms = [t for t in cleaned.split() if len(t) > 1]
    return " OR ".join(f'"{t}"' for t in terms[:20])


def _scope_video_ids(db: Session, scope: SearchScope) -> list[int]:
    if scope.video_ids:
        return scope.video_ids
    stmt = select(Video.id).where(Video.status == VideoStatus.ready)
    if scope.library_id is not None:
        stmt = stmt.where(Video.library_id == scope.library_id)
    if scope.course:
        stmt = stmt.where(Video.course == scope.course)
    return [row[0] for row in db.execute(stmt)]


def lexical_search(db: Session, query: str, scope: SearchScope, limit: int) -> list[tuple[int, float]]:
    video_ids = _scope_video_ids(db, scope)
    if not video_ids:
        return []

    if fts_available(db):
        match = sanitize_query(query)
        if not match:
            return []
        placeholders = ",".join(str(int(v)) for v in video_ids)
        rows = db.execute(
            sql_text(
                f"""
                SELECT f.rowid AS chunk_id, bm25(chunks_fts) AS rank
                FROM chunks_fts f
                JOIN transcript_chunks c ON c.id = f.rowid
                WHERE chunks_fts MATCH :match AND c.video_id IN ({placeholders})
                ORDER BY rank
                LIMIT :limit
                """
            ),
            {"match": match, "limit": limit},
        ).all()
        return [(int(r[0]), -float(r[1])) for r in rows]

    # Fallback portátil (PostgreSQL ou FTS indisponível)
    terms = [t for t in _FTS_CLEAN.sub(" ", query).split() if len(t) > 2][:6]
    if not terms:
        return []
    stmt = select(TranscriptChunk.id).where(TranscriptChunk.video_id.in_(video_ids))
    for term in terms:
        stmt = stmt.where(TranscriptChunk.text.ilike(f"%{term}%"))
    rows = db.execute(stmt.limit(limit)).all()
    return [(int(r[0]), 1.0) for r in rows]


async def semantic_search(
    db: Session, query: str, scope: SearchScope, limit: int
) -> list[tuple[int, float]]:
    if settings.embedding_provider == "none":
        return []
    try:
        vectors, _ = await emb.embed_texts(db, [query])
    except Exception as exc:  # noqa: BLE001
        log.warning("Busca semântica indisponível: %s", exc)
        return []
    if not vectors:
        return []
    matrix, ids = emb.load_matrix(
        db, library_id=scope.library_id, video_ids=_scope_video_ids(db, scope)
    )
    return emb.cosine_search(vectors[0], matrix, ids, limit)


def fuse_rrf(
    lexical: list[tuple[int, float]],
    semantic: list[tuple[int, float]],
    *,
    lexical_weight: float = 1.0,
    semantic_weight: float = 1.2,
) -> list[tuple[int, float, int | None, int | None]]:
    scores: dict[int, float] = {}
    lex_rank: dict[int, int] = {}
    sem_rank: dict[int, int] = {}

    for rank, (cid, _) in enumerate(lexical, start=1):
        scores[cid] = scores.get(cid, 0.0) + lexical_weight / (RRF_K + rank)
        lex_rank[cid] = rank
    for rank, (cid, _) in enumerate(semantic, start=1):
        scores[cid] = scores.get(cid, 0.0) + semantic_weight / (RRF_K + rank)
        sem_rank[cid] = rank

    ordered = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    return [(cid, score, lex_rank.get(cid), sem_rank.get(cid)) for cid, score in ordered]


def hydrate(db: Session, fused: list[tuple[int, float, int | None, int | None]]) -> list[Hit]:
    if not fused:
        return []
    ids = [cid for cid, *_ in fused]
    rows = db.execute(
        select(
            TranscriptChunk.id,
            TranscriptChunk.video_id,
            TranscriptChunk.start_seconds,
            TranscriptChunk.end_seconds,
            TranscriptChunk.text,
            TranscriptChunk.chapter,
            Video.title,
            Video.course,
            Video.thumbnail_path,
        )
        .join(Video, Video.id == TranscriptChunk.video_id)
        .where(TranscriptChunk.id.in_(ids))
    ).all()
    by_id = {r[0]: r for r in rows}

    hits: list[Hit] = []
    for cid, score, lrank, srank in fused:
        row = by_id.get(cid)
        if not row:
            continue
        hits.append(
            Hit(
                chunk_id=row[0],
                video_id=row[1],
                start=row[2],
                end=row[3],
                text=row[4],
                chapter=row[5],
                video_title=row[6],
                course=row[7],
                thumbnail=row[8],
                score=score,
                lexical_rank=lrank,
                semantic_rank=srank,
            )
        )
    return hits


async def hybrid_search(
    db: Session, query: str, scope: SearchScope, *, top_k: int | None = None
) -> list[Hit]:
    pool = top_k or settings.retrieval_top_k
    lexical = lexical_search(db, query, scope, pool)
    semantic = await semantic_search(db, query, scope, pool)
    fused = fuse_rrf(lexical, semantic)[:pool]
    return hydrate(db, fused)
