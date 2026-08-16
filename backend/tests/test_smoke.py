"""Testes de fumaça — rodam sem GPU, sem chave de API e sem internet.

    cd backend && ../backend/.venv/bin/python -m pytest tests -q
    (ou simplesmente: python -m pytest tests -q  com o venv ativado)
"""

from __future__ import annotations

import os
import tempfile

os.environ.setdefault("CLOUDSENA_DATA_DIR", tempfile.mkdtemp(prefix="cloudsena-test-"))
os.environ.setdefault("CLOUDSENA_WORKER_CONCURRENCY", "0")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.services.chunking import chunk_segments, format_timestamp  # noqa: E402
from app.services.enrichment import parse_json  # noqa: E402
from app.services.rag import extract_citations  # noqa: E402
from app.services.search import fuse_rrf, sanitize_query  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_seeds_providers_and_routes(client):
    providers = client.get("/api/providers").json()
    slugs = {p["slug"] for p in providers}
    assert {"ollama", "omp", "openrouter", "deepseek", "nous", "gemini"} <= slugs
    # Motores locais vêm ligados por padrão; APIs externas, não.
    assert next(p for p in providers if p["slug"] == "ollama")["enabled"]
    assert not next(p for p in providers if p["slug"] == "openrouter")["enabled"]

    routes = {r["task"] for r in client.get("/api/providers/routing/rules").json()}
    assert {"summarize", "chat", "chat_complex", "embeddings"} <= routes


def test_default_library_exists(client):
    libraries = client.get("/api/libraries").json()
    assert len(libraries) >= 1


def test_provider_key_never_leaks(client):
    client.patch("/api/providers/openrouter", json={"api_key": "sk-or-v1-segredo-total"})
    provider = next(
        p for p in client.get("/api/providers").json() if p["slug"] == "openrouter"
    )
    assert provider["has_key"] is True
    assert "segredo" not in str(provider)
    assert "•" in provider["key_masked"]


def test_cannot_enable_provider_without_key(client):
    response = client.patch("/api/providers/deepseek", json={"enabled": True})
    assert response.status_code == 400


def test_search_on_empty_index_is_graceful(client):
    response = client.post("/api/search", json={"query": "qualquer coisa", "library_id": 1})
    assert response.status_code == 200
    assert response.json()["count"] == 0


def test_youtube_source_requires_url(client):
    """Fonte tipo YouTube sem URL não pode ser criada — sem isso, uma fonte
    'fantasma' entraria no banco e nunca teria o que varrer."""
    response = client.post(
        "/api/sources",
        json={"library_id": 1, "source_type": "youtube", "url": ""},
    )
    assert response.status_code == 400


def test_youtube_source_rejects_unreachable_playlist(client):
    """Playlist inválida/inacessível é rejeitada na criação, não descoberta
    silenciosamente depois na fila (onde o erro ficaria escondido num job
    falho em vez de um 400 imediato pro usuário)."""
    response = client.post(
        "/api/sources",
        json={
            "library_id": 1,
            "source_type": "youtube",
            "url": "https://www.youtube.com/playlist?list=isto-nao-existe-de-verdade",
        },
    )
    assert response.status_code == 400


def test_preview_playlist_returns_error_not_exception(client):
    """preview-playlist nunca deve estourar 500 por URL inválida — sempre
    responde 200 com exists=False e uma mensagem de erro legível."""
    response = client.post(
        "/api/sources/preview-playlist",
        json={"url": "https://www.youtube.com/playlist?list=isto-nao-existe-de-verdade"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["exists"] is False
    assert body.get("error")


def test_watch_status_survives_unrelated_edit_but_not_new_progress(client):
    """Regressão: um PATCH sem relação com o player não pode apagar um
    'revisitar' escolhido pelo usuário — mas reportar progresso de novo, sim,
    porque aí é o sinal legítimo de que o vídeo está sendo assistido de novo."""
    from app.db.session import session_scope
    from app.db.models import Video, VideoStatus

    with session_scope() as db:
        video = Video(
            library_id=1,
            title="Vídeo de teste",
            duration_seconds=100.0,
            watched_seconds=98.0,  # > 95%, dispararia auto-completar
            status=VideoStatus.ready,
        )
        db.add(video)
        db.flush()
        video_id = video.id

    r = client.patch(f"/api/videos/{video_id}", json={"watch_status": "revisit"})
    assert r.json()["watch_status"] == "revisit"

    r = client.patch(f"/api/videos/{video_id}", json={"is_favorite": True})
    assert r.json()["watch_status"] == "revisit", "PATCH não relacionado sobrescreveu o status"
    assert r.json()["is_favorite"] is True

    r = client.patch(f"/api/videos/{video_id}", json={"watched_seconds": 99.0})
    assert r.json()["watch_status"] == "completed", "progresso real deveria poder avançar o status"


# --------------------------------------------------------------------------- #
# Serviços puros
# --------------------------------------------------------------------------- #
def test_chunking_preserves_timestamps():
    segments = [
        {"start": i * 5.0, "end": i * 5.0 + 5.0, "text": f"Frase número {i} do conteúdo. " * 4}
        for i in range(40)
    ]
    chunks = chunk_segments(segments)
    assert len(chunks) > 1
    assert chunks[0].start == 0.0
    assert chunks[-1].end == segments[-1]["end"]
    # os trechos avançam no tempo e todo trecho tem texto
    for a, b in zip(chunks, chunks[1:]):
        assert b.start >= a.start
    assert all(c.text.strip() for c in chunks)


def test_format_timestamp():
    assert format_timestamp(65) == "1:05"
    assert format_timestamp(3725) == "1:02:05"


def test_rrf_prefers_agreement():
    lexical = [(1, 0.9), (2, 0.8), (3, 0.7)]
    semantic = [(3, 0.95), (1, 0.9), (9, 0.5)]
    fused = fuse_rrf(lexical, semantic)
    ids = [cid for cid, *_ in fused]
    # 1 e 3 aparecem nos dois rankings, então vêm antes de 2 e 9
    assert set(ids[:2]) == {1, 3}


def test_sanitize_query_blocks_fts_injection():
    assert '"drop"' in sanitize_query('drop table"; --')
    assert ";" not in sanitize_query("a; b")


def test_parse_json_survives_markdown_fence():
    assert parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json('texto antes {"b": 2} texto depois') == {"b": 2}


def test_citations_only_include_referenced_sources():
    from app.services.search import Hit

    hits = [
        Hit(chunk_id=i, video_id=i, video_title=f"Aula {i}", course="Curso",
            start=i * 60.0, end=i * 60.0 + 30, text="conteúdo")
        for i in (1, 2, 3)
    ]
    citations = extract_citations("A resposta está em [1] e também em [3].", hits)
    assert [c["marker"] for c in citations] == [1, 3]
    assert citations[0]["deep_link"] == "/video/1?t=60"
