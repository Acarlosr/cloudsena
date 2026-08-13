from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from app.config import settings

_CONFIGURED = False

_REDACT_KEYS = ("api_key", "authorization", "token", "secret", "password")


class RedactFilter(logging.Filter):
    """Evita que chaves de API vazem para os logs."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = str(record.getMessage())
        except Exception:  # pragma: no cover
            return True
        low = msg.lower()
        if any(k in low for k in _REDACT_KEYS):
            import re

            record.msg = re.sub(
                r"(sk-[A-Za-z0-9_\-]{6})[A-Za-z0-9_\-]+", r"\1***", msg
            )
            record.args = ()
        return True


def setup_logging() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    level = logging.DEBUG if settings.debug else logging.INFO
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)-28s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(fmt)
    stream.addFilter(RedactFilter())

    logs_dir = settings.data_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        logs_dir / "cloudsena.log", maxBytes=8_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    file_handler.addFilter(RedactFilter())

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers = [stream, file_handler]

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    return logging.getLogger(name)
