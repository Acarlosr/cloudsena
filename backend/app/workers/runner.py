"""Worker: consome a fila. Roda embutido no servidor ou como processo separado.

Uso separado (recomendado quando a GPU estiver ocupada com transcrição):
    python -m app.workers.runner
"""

from __future__ import annotations

import asyncio
import os
import signal
import socket
import uuid

from app.config import settings
from app.core.logging import get_logger, setup_logging
from app.db.init_db import init_database
from app.db.session import session_scope
from app.workers import pipeline, queue

log = get_logger(__name__)

_shutdown = asyncio.Event()


def worker_id() -> str:
    return f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:6]}"


async def work_once(wid: str) -> bool:
    """Processa no máximo um job. Retorna True se havia trabalho."""
    with session_scope() as db:
        queue.requeue_stale(db)
        job = queue.claim_next(db, wid)
        if job is None:
            return False

        log.info("Job %s (%s) iniciado por %s", job.id, job.kind.value, wid)
        try:
            await pipeline.execute(db, job)
            queue.finish(db, job, success=True)
            log.info("Job %s concluído", job.id)
        except Exception as exc:  # noqa: BLE001
            log.exception("Job %s falhou: %s", job.id, exc)
            requeued = queue.retry(db, job, str(exc))
            if not requeued:
                pipeline.mark_video_failed(db, job, str(exc))
        return True


async def loop(concurrency: int | None = None) -> None:
    setup_logging()
    init_database()
    workers = concurrency or settings.worker_concurrency
    log.info("Worker CloudSena iniciado (%d slot(s))", workers)

    async def slot(index: int) -> None:
        wid = f"{worker_id()}#{index}"
        while not _shutdown.is_set():
            try:
                busy = await work_once(wid)
            except Exception as exc:  # noqa: BLE001
                log.exception("Erro no loop do worker: %s", exc)
                busy = False
            if not busy:
                try:
                    await asyncio.wait_for(
                        _shutdown.wait(), timeout=settings.worker_poll_seconds
                    )
                except asyncio.TimeoutError:
                    pass

    await asyncio.gather(*(slot(i) for i in range(workers)))
    log.info("Worker encerrado")


def request_shutdown(*_: object) -> None:
    log.info("Sinal recebido — finalizando o job atual antes de sair")
    _shutdown.set()


def main() -> None:
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, request_shutdown)
        except ValueError:  # pragma: no cover
            pass
    asyncio.run(loop())


if __name__ == "__main__":
    main()
