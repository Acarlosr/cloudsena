"""Barramento de eventos em memória para progresso em tempo real (SSE)."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, AsyncIterator

from app.core.logging import get_logger

log = get_logger(__name__)


class EventBus:
    def __init__(self, history_size: int = 200) -> None:
        self._subscribers: set[asyncio.Queue] = set()
        self._history: list[dict[str, Any]] = []
        self._history_size = history_size
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    # -- publicação --------------------------------------------------
    def publish(self, kind: str, payload: dict[str, Any] | None = None) -> None:
        event = {"kind": kind, "ts": time.time(), "data": payload or {}}
        self._history.append(event)
        self._history = self._history[-self._history_size :]

        for q in list(self._subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:  # pragma: no cover
                pass

    def publish_threadsafe(self, kind: str, payload: dict[str, Any] | None = None) -> None:
        """Publicação a partir de threads de worker."""
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self.publish, kind, payload)
        else:
            self.publish(kind, payload)

    # -- consumo -----------------------------------------------------
    async def stream(self, replay: int = 0) -> AsyncIterator[str]:
        q: asyncio.Queue = asyncio.Queue(maxsize=500)
        self._subscribers.add(q)
        try:
            for event in self._history[-replay:] if replay else []:
                yield _sse(event)
            yield _sse({"kind": "connected", "ts": time.time(), "data": {}})
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=20.0)
                    yield _sse(event)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            self._subscribers.discard(q)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)


def _sse(event: dict[str, Any]) -> str:
    return f"event: {event['kind']}\ndata: {json.dumps(event, default=str)}\n\n"


bus = EventBus()
