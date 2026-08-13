"""Configuração central do CloudSena.

Todas as opções podem ser sobrescritas por variáveis de ambiente (prefixo CLOUDSENA_)
ou por um arquivo .env na raiz do repositório.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CLOUDSENA_",
        env_file=(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---------- identidade ----------
    app_name: str = "CloudSena"
    version: str = "0.1.0"
    environment: str = "local"  # local | production
    debug: bool = True

    # ---------- rede ----------
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # ---------- dados ----------
    data_dir: Path = ROOT_DIR / "data"
    database_url: str = ""  # vazio => sqlite em data/database/cloudsena.db

    # ---------- segurança ----------
    # Chave usada para criptografar credenciais de provider no banco.
    # Gere com: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    secret_key: str = ""
    api_token: str = ""  # se definido, exige header X-CloudSena-Token

    # ---------- mídia ----------
    ffmpeg_bin: str = "ffmpeg"
    ffprobe_bin: str = "ffprobe"
    video_extensions: str = ".mp4,.mkv,.avi,.mov,.webm,.m4v,.flv,.wmv,.ts"
    thumbnail_width: int = 640

    # ---------- transcrição ----------
    whisper_model: str = "large-v3"          # tiny | base | small | medium | large-v3
    whisper_device: str = "auto"             # auto | cuda | cpu
    whisper_compute_type: str = "float16"    # float16 (GPU) | int8 (CPU)
    whisper_beam_size: int = 5
    transcription_language: str = ""         # "" = detectar automaticamente

    # ---------- chunking / RAG ----------
    chunk_target_chars: int = 1100
    chunk_overlap_chars: int = 180
    retrieval_top_k: int = 40
    rerank_top_k: int = 8
    max_context_chars: int = 14000

    # ---------- embeddings ----------
    embedding_provider: str = "ollama"        # ollama | openai_compatible | none
    embedding_model: str = "nomic-embed-text"
    embedding_dim: int = 768

    # ---------- workers ----------
    worker_concurrency: int = 1
    worker_poll_seconds: float = 2.0
    job_max_attempts: int = 3

    # ---------- endpoints locais padrão ----------
    ollama_base_url: str = "http://localhost:11434"
    omp_base_url: str = "http://localhost:8080/v1"

    # ---------- privacidade ----------
    default_privacy_mode: str = "hybrid"  # local | hybrid | cloud

    # ---------- derivados ----------
    @property
    def db_dir(self) -> Path:
        return self.data_dir / "database"

    @property
    def sqlalchemy_url(self) -> str:
        if self.database_url:
            return self.database_url
        self.db_dir.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{self.db_dir / 'cloudsena.db'}"

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def video_ext_set(self) -> set[str]:
        return {e.strip().lower() for e in self.video_extensions.split(",") if e.strip()}

    def path(self, *parts: str) -> Path:
        p = self.data_dir.joinpath(*parts)
        p.mkdir(parents=True, exist_ok=True)
        return p

    def ensure_dirs(self) -> None:
        for sub in (
            "database",
            "thumbnails",
            "transcripts",
            "summaries",
            "frames",
            "temp",
            "logs",
            "backups",
        ):
            (self.data_dir / sub).mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.ensure_dirs()
    return s


settings = get_settings()
