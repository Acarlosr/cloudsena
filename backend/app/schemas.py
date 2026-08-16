"""Contratos de entrada e saída da API (Pydantic v2)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --------------------------------------------------------------------------- #
# Bibliotecas
# --------------------------------------------------------------------------- #
class LibraryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    color: str = "#6366f1"
    privacy_mode: Literal["local", "hybrid", "cloud"] = "hybrid"


class LibraryUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    color: str | None = None
    privacy_mode: Literal["local", "hybrid", "cloud"] | None = None
    routing_override: dict | None = None


class LibraryOut(ORMModel):
    id: int
    name: str
    description: str
    color: str
    privacy_mode: str
    created_at: datetime
    video_count: int = 0
    ready_count: int = 0
    total_duration: float = 0.0


# --------------------------------------------------------------------------- #
# Fontes
# --------------------------------------------------------------------------- #
class SourceCreate(BaseModel):
    library_id: int
    source_type: Literal["local_folder", "youtube", "manual"]
    title: str = ""
    root_path: str = ""
    url: str = ""
    auto_sync: bool = False
    scan_now: bool = True


class SourceOut(ORMModel):
    id: int
    library_id: int
    source_type: str
    title: str
    root_path: str
    url: str
    auto_sync: bool
    sync_status: str
    last_synced_at: datetime | None
    stats: dict


class FolderPreviewRequest(BaseModel):
    path: str


class PlaylistPreviewRequest(BaseModel):
    url: str


# --------------------------------------------------------------------------- #
# Vídeos
# --------------------------------------------------------------------------- #
class ChapterOut(BaseModel):
    title: str
    start: float
    end: float


class SummaryOut(ORMModel):
    short_summary: str = ""
    long_summary: str = ""
    topics: list = []
    chapters: list = []
    keywords: list = []
    entities: list = []
    suggested_questions: list = []
    category: str = ""
    model: str = ""


class VideoOut(ORMModel):
    id: int
    library_id: int
    title: str
    course: str
    module: str
    order_index: int
    duration_seconds: float
    thumbnail_path: str
    status: str
    stage_progress: float
    watch_status: str
    watched_seconds: float
    is_favorite: bool
    rating: int
    tags: list
    language: str
    error_message: str = ""
    youtube_id: str = ""
    created_at: datetime


class VideoDetail(VideoOut):
    description: str = ""
    file_path: str = ""
    file_size: int = 0
    width: int = 0
    height: int = 0
    codec: str = ""
    notes: str = ""
    url: str = ""
    channel: str = ""
    summary: SummaryOut | None = None
    has_transcript: bool = False
    chunk_count: int = 0


class VideoUpdate(BaseModel):
    title: str | None = None
    notes: str | None = None
    is_favorite: bool | None = None
    rating: int | None = Field(default=None, ge=0, le=5)
    watch_status: Literal["unwatched", "in_progress", "completed", "revisit"] | None = None
    watched_seconds: float | None = None
    tags: list[str] | None = None
    course: str | None = None


class TranscriptSegment(BaseModel):
    start: float
    end: float
    text: str


class TranscriptOut(BaseModel):
    video_id: int
    language: str
    engine: str
    model: str
    confidence: float
    segments: list[TranscriptSegment]


# --------------------------------------------------------------------------- #
# Busca e chat
# --------------------------------------------------------------------------- #
class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    library_id: int | None = None
    course: str = ""
    video_ids: list[int] = []
    top_k: int = 20


class AskRequest(BaseModel):
    question: str = Field(min_length=1)
    library_id: int | None = None
    course: str = ""
    video_ids: list[int] = []
    conversation_id: int | None = None
    deep_reasoning: bool = False
    rerank: bool = True


class MessageOut(ORMModel):
    id: int
    role: str
    content: str
    citations: list
    model: str
    provider: str
    cost_usd: float
    latency_ms: int
    created_at: datetime


class ConversationOut(ORMModel):
    id: int
    title: str
    scope_type: str
    scope_id: str
    created_at: datetime
    updated_at: datetime
    message_count: int = 0


# --------------------------------------------------------------------------- #
# Providers
# --------------------------------------------------------------------------- #
class ProviderOut(BaseModel):
    slug: str
    label: str
    kind: str
    base_url: str
    default_model: str
    enabled: bool
    is_local: bool
    requires_key: bool = True
    has_key: bool = False
    key_masked: str = ""
    status: str = "unknown"
    status_message: str = ""
    last_checked_at: datetime | None = None
    priority: int = 100
    docs_url: str = ""
    api_key_url: str = ""
    notes: str = ""
    suggested_models: list[str] = []
    supports_vision: bool = False
    supports_embeddings: bool = False


class ProviderUpdate(BaseModel):
    label: str | None = None
    base_url: str | None = None
    api_key: str | None = None      # "" limpa a chave
    default_model: str | None = None
    enabled: bool | None = None
    priority: int | None = None
    extra_headers: dict | None = None


class RoutingRuleOut(ORMModel):
    task: str
    label: str = ""
    provider_slug: str
    model: str
    fallback_provider_slug: str
    fallback_model: str
    temperature: float
    max_tokens: int


class RoutingRuleUpdate(BaseModel):
    provider_slug: str | None = None
    model: str | None = None
    fallback_provider_slug: str | None = None
    fallback_model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None


# --------------------------------------------------------------------------- #
# Jobs e sistema
# --------------------------------------------------------------------------- #
class JobOut(ORMModel):
    id: int
    kind: str
    status: str
    video_id: int | None
    library_id: int | None
    progress: float
    stage: str
    attempts: int
    max_attempts: int
    error: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    video_title: str = ""


class SystemStatus(BaseModel):
    app: str
    version: str
    environment: str
    ffmpeg: bool
    whisper: bool
    gpu: dict[str, Any]
    database: str
    data_dir: str
    providers_enabled: int
    providers_ok: int
    queue: dict[str, int]
    counts: dict[str, int]
    embedding_provider: str


class StatsOut(BaseModel):
    videos_total: int
    videos_ready: int
    videos_failed: int
    hours_indexed: float
    chunks: int
    libraries: int
    courses: int
    cost_last_30d: float
    top_providers: list[dict]
    recent_activity: list[dict]
