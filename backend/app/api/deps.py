from __future__ import annotations

from fastapi import Header, HTTPException, status

from app.config import settings


async def require_token(x_cloudsena_token: str | None = Header(default=None)) -> None:
    """Proteção opcional. Ative definindo CLOUDSENA_API_TOKEN no .env.

    Útil quando o servidor for exposto na rede local ou atrás de um túnel.
    """
    if not settings.api_token:
        return
    if x_cloudsena_token != settings.api_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido"
        )
