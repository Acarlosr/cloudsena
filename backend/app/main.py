"""CloudSena — API principal.

Rodar em desenvolvimento:
    uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.deps import require_token
from app.api.routes import chat, libraries, providers, sources, system, videos
from app.config import settings
from app.core.events import bus
from app.core.logging import get_logger, setup_logging
from app.db.init_db import init_database
from app.db.session import session_scope
from app.providers.base import ProviderError
from app.services.media import ffmpeg_available
from app.services.transcription import whisper_available
from app.workers import queue, runner

log = get_logger(__name__)

_worker_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    log.info("Iniciando %s v%s (%s)", settings.app_name, settings.version, settings.environment)
    init_database()
    bus.bind_loop(asyncio.get_running_loop())

    with session_scope() as db:
        requeued = queue.requeue_stale(db)
    if requeued:
        log.info("%d job(s) recuperados após reinício", requeued)

    if not ffmpeg_available():
        log.warning("FFmpeg não encontrado — thumbnails e extração de áudio ficarão indisponíveis")
    if not whisper_available():
        log.warning(
            "faster-whisper não instalado — a transcrição local não vai funcionar "
            "(pip install faster-whisper)"
        )

    global _worker_task
    if settings.worker_concurrency > 0:
        _worker_task = asyncio.create_task(runner.loop())
        log.info("Worker embutido ativo (%d slot(s))", settings.worker_concurrency)

    yield

    if _worker_task:
        runner.request_shutdown()
        _worker_task.cancel()
        try:
            await _worker_task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
    log.info("CloudSena encerrado")


app = FastAPI(
    title="CloudSena API",
    description="Biblioteca inteligente de vídeos e cursos — busca, resumo e perguntas com citações.",
    version=settings.version,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ProviderError)
async def provider_error_handler(_: Request, exc: ProviderError) -> JSONResponse:
    return JSONResponse(
        status_code=502,
        content={"detail": str(exc), "provider": exc.slug, "type": "provider_error"},
    )


api = FastAPI  # alias para clareza nos imports abaixo

app.include_router(system.router, prefix="/api", dependencies=[Depends(require_token)])
app.include_router(libraries.router, prefix="/api", dependencies=[Depends(require_token)])
app.include_router(sources.router, prefix="/api", dependencies=[Depends(require_token)])
app.include_router(videos.router, prefix="/api", dependencies=[Depends(require_token)])
app.include_router(chat.router, prefix="/api", dependencies=[Depends(require_token)])
app.include_router(providers.router, prefix="/api", dependencies=[Depends(require_token)])


@app.get("/")
def root() -> dict:
    return {
        "app": settings.app_name,
        "version": settings.version,
        "docs": "/docs",
        "api": "/api",
    }


def run() -> None:
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_config=None,
    )


if __name__ == "__main__":
    run()
