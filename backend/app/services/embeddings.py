"""Geração e armazenamento de embeddings.

Os vetores ficam no próprio banco como float32 bruto (LargeBinary). Para uma
biblioteca pessoal (dezenas de milhares de trechos) isso é rápido, portátil e
não exige um serviço externo de vetores. Se a biblioteca crescer muito, o
mesmo modelo de dados migra para pgvector/Qdrant sem alterar a API.
"""

from __future__ import annotations

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.logging import get_logger
from app.db.models import TranscriptChunk
from app.providers.base import ChatMessage, ProviderError  # noqa: F401
from app.providers import registry

log = get_logger(__name__)


def to_blob(vector: list[float]) -> bytes:
    return np.asarray(vector, dtype=np.float32).tobytes()


def from_blob(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)


def normalize(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=-1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


async def embed_texts(db: Session, texts: list[str]) -> tuple[list[list[float]], str]:
    """Gera embeddings usando a rota configurada para a tarefa 'embeddings'."""
    if not texts:
        return [], ""
    if settings.embedding_provider == "none":
        raise ProviderError("Embeddings desativados nas configurações")

    resolved = registry.resolve(db, "embeddings")
    model = resolved.model or settings.embedding_model
    vectors = await resolved.provider.embed(texts, model=model)
    if len(vectors) != len(texts):
        raise ProviderError(
            f"Provider retornou {len(vectors)} vetores para {len(texts)} textos"
        )
    return vectors, model


async def embed_chunks(db: Session, chunk_ids: list[int], batch_size: int = 32) -> int:
    """Preenche o embedding dos trechos informados. Retorna quantos foram indexados."""
    done = 0
    for i in range(0, len(chunk_ids), batch_size):
        batch_ids = chunk_ids[i : i + batch_size]
        chunks = list(
            db.scalars(select(TranscriptChunk).where(TranscriptChunk.id.in_(batch_ids)))
        )
        texts = [c.text for c in chunks]
        vectors, model = await embed_texts(db, texts)
        for chunk, vector in zip(chunks, vectors):
            chunk.embedding = to_blob(vector)
            chunk.embedding_model = model
            chunk.embedding_dim = len(vector)
        db.commit()
        done += len(chunks)
    return done


def load_matrix(
    db: Session, *, library_id: int | None = None, video_ids: list[int] | None = None
) -> tuple[np.ndarray, list[int]]:
    """Carrega os vetores do escopo pedido em uma matriz normalizada."""
    stmt = select(TranscriptChunk.id, TranscriptChunk.embedding).where(
        TranscriptChunk.embedding.is_not(None)
    )
    if library_id is not None:
        stmt = stmt.where(TranscriptChunk.library_id == library_id)
    if video_ids:
        stmt = stmt.where(TranscriptChunk.video_id.in_(video_ids))

    ids: list[int] = []
    vectors: list[np.ndarray] = []
    dim = 0
    for chunk_id, blob in db.execute(stmt):
        if not blob:
            continue
        vec = from_blob(blob)
        if dim == 0:
            dim = vec.shape[0]
        if vec.shape[0] != dim:
            continue  # modelo trocado: ignora vetores de dimensão diferente
        ids.append(chunk_id)
        vectors.append(vec)

    if not vectors:
        return np.zeros((0, 1), dtype=np.float32), []
    return normalize(np.vstack(vectors)), ids


def cosine_search(
    query_vector: list[float], matrix: np.ndarray, ids: list[int], top_k: int
) -> list[tuple[int, float]]:
    if matrix.shape[0] == 0:
        return []
    q = np.asarray(query_vector, dtype=np.float32)
    if q.shape[0] != matrix.shape[1]:
        log.warning(
            "Dimensão do embedding da pergunta (%d) difere do índice (%d)",
            q.shape[0],
            matrix.shape[1],
        )
        return []
    q = q / (np.linalg.norm(q) or 1.0)
    scores = matrix @ q
    k = min(top_k, scores.shape[0])
    top = np.argpartition(-scores, k - 1)[:k]
    top = top[np.argsort(-scores[top])]
    return [(ids[i], float(scores[i])) for i in top]
