"""Modelo de dados do CloudSena.

Desenhado para SQLite no MVP e PostgreSQL em produção sem mudança de código:
sem tipos específicos de dialeto, JSON portátil, ids inteiros.
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #
class VideoStatus(str, enum.Enum):
    discovered = "discovered"
    queued = "queued"
    extracting = "extracting"
    transcribing = "transcribing"
    summarizing = "summarizing"
    indexing = "indexing"
    ready = "ready"
    failed = "failed"
    skipped = "skipped"


class WatchStatus(str, enum.Enum):
    unwatched = "unwatched"
    in_progress = "in_progress"
    completed = "completed"
    revisit = "revisit"


class SourceType(str, enum.Enum):
    local_folder = "local_folder"
    youtube = "youtube"
    manual = "manual"


class PrivacyMode(str, enum.Enum):
    local = "local"       # tudo roda na máquina
    hybrid = "hybrid"     # transcrição local, texto selecionado vai para API
    cloud = "cloud"       # processamento remoto autorizado


class JobStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    done = "done"
    failed = "failed"
    canceled = "canceled"


class TaskKind(str, enum.Enum):
    scan_source = "scan_source"
    probe = "probe"
    thumbnail = "thumbnail"
    extract_audio = "extract_audio"
    transcribe = "transcribe"
    enrich = "enrich"
    embed = "embed"
    full_pipeline = "full_pipeline"


# --------------------------------------------------------------------------- #
# Bibliotecas e fontes
# --------------------------------------------------------------------------- #
class Library(Base):
    __tablename__ = "libraries"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    color: Mapped[str] = mapped_column(String(16), default="#6366f1")
    icon: Mapped[str] = mapped_column(String(40), default="library")
    privacy_mode: Mapped[PrivacyMode] = mapped_column(
        Enum(PrivacyMode, native_enum=False), default=PrivacyMode.hybrid
    )
    # Sobrescreve o roteamento global de modelos para esta biblioteca.
    routing_override: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    sources: Mapped[list["Source"]] = relationship(
        back_populates="library", cascade="all, delete-orphan"
    )
    videos: Mapped[list["Video"]] = relationship(
        back_populates="library", cascade="all, delete-orphan"
    )


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    library_id: Mapped[int] = mapped_column(
        ForeignKey("libraries.id", ondelete="CASCADE"), index=True
    )
    source_type: Mapped[SourceType] = mapped_column(Enum(SourceType, native_enum=False))
    title: Mapped[str] = mapped_column(String(300), default="")
    root_path: Mapped[str] = mapped_column(Text, default="")     # pasta local
    url: Mapped[str] = mapped_column(Text, default="")           # playlist / vídeo
    external_id: Mapped[str] = mapped_column(String(120), default="")
    auto_sync: Mapped[bool] = mapped_column(Boolean, default=False)
    sync_status: Mapped[str] = mapped_column(String(40), default="idle")
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    stats: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    library: Mapped[Library] = relationship(back_populates="sources")
    videos: Mapped[list["Video"]] = relationship(back_populates="source")


# --------------------------------------------------------------------------- #
# Vídeos
# --------------------------------------------------------------------------- #
class Video(Base):
    __tablename__ = "videos"
    __table_args__ = (
        UniqueConstraint("library_id", "file_hash", name="uq_video_library_hash"),
        Index("ix_video_status", "status"),
        Index("ix_video_course", "course"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    library_id: Mapped[int] = mapped_column(
        ForeignKey("libraries.id", ondelete="CASCADE"), index=True
    )
    source_id: Mapped[int | None] = mapped_column(
        ForeignKey("sources.id", ondelete="SET NULL"), nullable=True, index=True
    )

    title: Mapped[str] = mapped_column(String(500), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    course: Mapped[str] = mapped_column(String(300), default="")  # derivado da pasta/playlist
    module: Mapped[str] = mapped_column(String(300), default="")
    order_index: Mapped[int] = mapped_column(Integer, default=0)

    # origem
    file_path: Mapped[str] = mapped_column(Text, default="")
    youtube_id: Mapped[str] = mapped_column(String(40), default="", index=True)
    url: Mapped[str] = mapped_column(Text, default="")
    channel: Mapped[str] = mapped_column(String(300), default="")

    # mídia
    file_hash: Mapped[str] = mapped_column(String(64), default="", index=True)
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    duration_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    codec: Mapped[str] = mapped_column(String(40), default="")
    thumbnail_path: Mapped[str] = mapped_column(Text, default="")
    language: Mapped[str] = mapped_column(String(10), default="")

    # estado
    status: Mapped[VideoStatus] = mapped_column(
        Enum(VideoStatus, native_enum=False), default=VideoStatus.discovered
    )
    stage_progress: Mapped[float] = mapped_column(Float, default=0.0)
    error_message: Mapped[str] = mapped_column(Text, default="")

    # uso
    watch_status: Mapped[WatchStatus] = mapped_column(
        Enum(WatchStatus, native_enum=False), default=WatchStatus.unwatched
    )
    watched_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    rating: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[list] = mapped_column(JSON, default=list)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    library: Mapped[Library] = relationship(back_populates="videos")
    source: Mapped[Source | None] = relationship(back_populates="videos")
    transcripts: Mapped[list["Transcript"]] = relationship(
        back_populates="video", cascade="all, delete-orphan"
    )
    chunks: Mapped[list["TranscriptChunk"]] = relationship(
        back_populates="video", cascade="all, delete-orphan"
    )
    summary: Mapped["Summary | None"] = relationship(
        back_populates="video", cascade="all, delete-orphan", uselist=False
    )


class Transcript(Base):
    __tablename__ = "transcripts"

    id: Mapped[int] = mapped_column(primary_key=True)
    video_id: Mapped[int] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"), index=True
    )
    engine: Mapped[str] = mapped_column(String(80), default="faster-whisper")
    model: Mapped[str] = mapped_column(String(80), default="")
    language: Mapped[str] = mapped_column(String(10), default="")
    text_path: Mapped[str] = mapped_column(Text, default="")     # .json com segmentos
    plain_path: Mapped[str] = mapped_column(Text, default="")    # .txt legível
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    duration_processed: Mapped[float] = mapped_column(Float, default=0.0)
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    video: Mapped[Video] = relationship(back_populates="transcripts")


class TranscriptChunk(Base):
    __tablename__ = "transcript_chunks"
    __table_args__ = (Index("ix_chunk_video_start", "video_id", "start_seconds"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    video_id: Mapped[int] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"), index=True
    )
    transcript_id: Mapped[int] = mapped_column(
        ForeignKey("transcripts.id", ondelete="CASCADE"), index=True
    )
    library_id: Mapped[int] = mapped_column(Integer, index=True, default=0)
    seq: Mapped[int] = mapped_column(Integer, default=0)
    start_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    end_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    text: Mapped[str] = mapped_column(Text, default="")
    chapter: Mapped[str] = mapped_column(String(300), default="")
    token_estimate: Mapped[int] = mapped_column(Integer, default=0)

    # embedding armazenado como float32 bruto (portátil e rápido com numpy)
    embedding: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    embedding_model: Mapped[str] = mapped_column(String(120), default="")
    embedding_dim: Mapped[int] = mapped_column(Integer, default=0)

    video: Mapped[Video] = relationship(back_populates="chunks")


class Summary(Base):
    __tablename__ = "summaries"

    id: Mapped[int] = mapped_column(primary_key=True)
    video_id: Mapped[int] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"), unique=True, index=True
    )
    short_summary: Mapped[str] = mapped_column(Text, default="")
    long_summary: Mapped[str] = mapped_column(Text, default="")
    topics: Mapped[list] = mapped_column(JSON, default=list)
    chapters: Mapped[list] = mapped_column(JSON, default=list)   # [{title,start,end}]
    keywords: Mapped[list] = mapped_column(JSON, default=list)
    entities: Mapped[list] = mapped_column(JSON, default=list)
    suggested_questions: Mapped[list] = mapped_column(JSON, default=list)
    category: Mapped[str] = mapped_column(String(120), default="")
    model: Mapped[str] = mapped_column(String(160), default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    video: Mapped[Video] = relationship(back_populates="summary")


# --------------------------------------------------------------------------- #
# Conversas
# --------------------------------------------------------------------------- #
class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(300), default="Nova conversa")
    scope_type: Mapped[str] = mapped_column(String(30), default="library")  # library|course|video|all
    scope_id: Mapped[str] = mapped_column(String(80), default="")
    model_profile: Mapped[str] = mapped_column(String(60), default="chat")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="Message.id"
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(20), default="user")
    content: Mapped[str] = mapped_column(Text, default="")
    citations: Mapped[list] = mapped_column(JSON, default=list)
    model: Mapped[str] = mapped_column(String(160), default="")
    provider: Mapped[str] = mapped_column(String(60), default="")
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


# --------------------------------------------------------------------------- #
# Providers de IA
# --------------------------------------------------------------------------- #
class ProviderConfig(Base):
    """Uma linha por conexão configurada (OpenRouter, DeepSeek, Ollama, OMP...)."""

    __tablename__ = "provider_configs"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(60), unique=True, index=True)  # openrouter, ollama...
    label: Mapped[str] = mapped_column(String(120), default="")
    kind: Mapped[str] = mapped_column(String(40), default="openai_compatible")
    base_url: Mapped[str] = mapped_column(Text, default="")
    api_key_encrypted: Mapped[str] = mapped_column(Text, default="")
    default_model: Mapped[str] = mapped_column(String(160), default="")
    extra_headers: Mapped[dict] = mapped_column(JSON, default=dict)
    options: Mapped[dict] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    is_local: Mapped[bool] = mapped_column(Boolean, default=False)
    priority: Mapped[int] = mapped_column(Integer, default=100)

    status: Mapped[str] = mapped_column(String(30), default="unknown")  # ok|error|unknown
    status_message: Mapped[str] = mapped_column(Text, default="")
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    models_cache: Mapped[list] = mapped_column(JSON, default=list)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class RoutingRule(Base):
    """Qual provider/modelo usa cada tarefa. Editável na UI."""

    __tablename__ = "routing_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    task: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    provider_slug: Mapped[str] = mapped_column(String(60), default="")
    model: Mapped[str] = mapped_column(String(160), default="")
    fallback_provider_slug: Mapped[str] = mapped_column(String(60), default="")
    fallback_model: Mapped[str] = mapped_column(String(160), default="")
    temperature: Mapped[float] = mapped_column(Float, default=0.2)
    max_tokens: Mapped[int] = mapped_column(Integer, default=2048)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class UsageLog(Base):
    __tablename__ = "usage_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    provider_slug: Mapped[str] = mapped_column(String(60), index=True, default="")
    model: Mapped[str] = mapped_column(String(160), default="")
    task: Mapped[str] = mapped_column(String(60), default="")
    video_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


# --------------------------------------------------------------------------- #
# Fila de trabalho (retomável)
# --------------------------------------------------------------------------- #
class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (Index("ix_job_status_priority", "status", "priority"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[TaskKind] = mapped_column(Enum(TaskKind, native_enum=False))
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, native_enum=False), default=JobStatus.pending
    )
    video_id: Mapped[int | None] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"), nullable=True, index=True
    )
    source_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    library_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    priority: Mapped[int] = mapped_column(Integer, default=100)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    stage: Mapped[str] = mapped_column(String(60), default="")
    error: Mapped[str] = mapped_column(Text, default="")
    worker_id: Mapped[str] = mapped_column(String(80), default="")
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
