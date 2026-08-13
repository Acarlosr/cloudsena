"""Criptografia de credenciais e autenticação simples do backend.

Princípio do projeto: a chave de API nunca sai do backend em texto claro.
O frontend só recebe uma máscara (ex.: sk-or-...9f2a).
"""

from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

_KEY_FILE = settings.data_dir / "database" / ".secret.key"


def _load_or_create_key() -> bytes:
    if settings.secret_key:
        raw = settings.secret_key.encode()
        try:
            Fernet(raw)
            return raw
        except Exception:
            # Aceita uma frase secreta qualquer: deriva uma chave Fernet válida.
            digest = hashlib.sha256(raw).digest()
            return base64.urlsafe_b64encode(digest)

    if _KEY_FILE.exists():
        return _KEY_FILE.read_bytes().strip()

    key = Fernet.generate_key()
    _KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    _KEY_FILE.write_bytes(key)
    try:
        os.chmod(_KEY_FILE, 0o600)
    except OSError:  # pragma: no cover - Windows
        pass
    log.warning("Nova chave de criptografia gerada em %s (faça backup)", _KEY_FILE)
    return key


_fernet = Fernet(_load_or_create_key())


def encrypt(value: str) -> str:
    if not value:
        return ""
    return _fernet.encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    if not value:
        return ""
    try:
        return _fernet.decrypt(value.encode()).decode()
    except InvalidToken:
        log.error("Falha ao descriptografar credencial (chave trocada?)")
        return ""


def mask(value: str) -> str:
    """Máscara segura para exibir no frontend."""
    if not value:
        return ""
    if len(value) <= 10:
        return value[:2] + "•" * 6
    return f"{value[:6]}{'•' * 6}{value[-4:]}"


def file_fingerprint(path: Path, sample_bytes: int = 4 * 1024 * 1024) -> str:
    """Hash rápido e estável para arquivos grandes.

    Lê o início, o meio e o fim do arquivo + tamanho. Suficiente para detectar
    duplicados e mudanças sem ler 4 GB de vídeo.
    """
    size = path.stat().st_size
    h = hashlib.blake2b(digest_size=20)
    h.update(str(size).encode())
    with path.open("rb") as fh:
        h.update(fh.read(sample_bytes))
        if size > sample_bytes * 2:
            fh.seek(size // 2)
            h.update(fh.read(sample_bytes))
            fh.seek(max(0, size - sample_bytes))
            h.update(fh.read(sample_bytes))
    return h.hexdigest()
