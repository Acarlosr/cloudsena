export type VideoStatus =
  | "discovered"
  | "queued"
  | "extracting"
  | "transcribing"
  | "summarizing"
  | "indexing"
  | "ready"
  | "failed"
  | "skipped";

export type WatchStatus = "unwatched" | "in_progress" | "completed" | "revisit";

export interface Library {
  id: number;
  name: string;
  description: string;
  color: string;
  privacy_mode: "local" | "hybrid" | "cloud";
  created_at: string;
  video_count: number;
  ready_count: number;
  total_duration: number;
}

export interface Video {
  id: number;
  library_id: number;
  title: string;
  course: string;
  module: string;
  order_index: number;
  duration_seconds: number;
  thumbnail_path: string;
  status: VideoStatus;
  stage_progress: number;
  watch_status: WatchStatus;
  watched_seconds: number;
  is_favorite: boolean;
  rating: number;
  tags: string[];
  language: string;
  error_message?: string;
  youtube_id?: string;
  created_at: string;
}

export interface Summary {
  short_summary: string;
  long_summary: string;
  topics: string[];
  chapters: { title: string; start: number; end: number }[];
  keywords: string[];
  entities: string[];
  suggested_questions: string[];
  category: string;
  model: string;
}

export interface VideoDetail extends Video {
  description: string;
  file_path: string;
  file_size: number;
  width: number;
  height: number;
  codec: string;
  notes: string;
  url: string;
  channel: string;
  summary: Summary | null;
  has_transcript: boolean;
  chunk_count: number;
}

export interface Segment {
  start: number;
  end: number;
  text: string;
}

export interface TranscriptData {
  video_id: number;
  language: string;
  engine: string;
  model: string;
  confidence: number;
  segments: Segment[];
}

export interface Citation {
  marker: number;
  video_id: number;
  video_title: string;
  course: string;
  chapter: string;
  start: number;
  end: number;
  start_label: string;
  end_label: string;
  thumbnail: string;
  excerpt: string;
  deep_link: string;
}

export interface AnswerResponse {
  conversation_id: number;
  conversation_title: string;
  message_id: number;
  text: string;
  citations: Citation[];
  model: string;
  provider: string;
  cost_usd: number;
  latency_ms: number;
  grounded: boolean;
  scope: Record<string, unknown>;
}

export interface SearchHit {
  chunk_id: number;
  video_id: number;
  video_title: string;
  course: string;
  start: number;
  end: number;
  text: string;
  chapter: string;
  score: number;
  thumbnail: string;
}

export interface Provider {
  slug: string;
  label: string;
  kind: string;
  base_url: string;
  default_model: string;
  enabled: boolean;
  is_local: boolean;
  requires_key: boolean;
  has_key: boolean;
  key_masked: string;
  status: "ok" | "error" | "unknown";
  status_message: string;
  last_checked_at: string | null;
  priority: number;
  docs_url: string;
  api_key_url: string;
  notes: string;
  suggested_models: string[];
  supports_vision: boolean;
  supports_embeddings: boolean;
}

export interface RoutingRule {
  task: string;
  label: string;
  provider_slug: string;
  model: string;
  fallback_provider_slug: string;
  fallback_model: string;
  temperature: number;
  max_tokens: number;
}

export interface Job {
  id: number;
  kind: string;
  status: "pending" | "running" | "done" | "failed" | "canceled";
  video_id: number | null;
  library_id: number | null;
  progress: number;
  stage: string;
  attempts: number;
  max_attempts: number;
  error: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  video_title: string;
}

export interface SystemStatus {
  app: string;
  version: string;
  environment: string;
  ffmpeg: boolean;
  whisper: boolean;
  gpu: {
    available: boolean;
    name: string;
    memory_total_mb: number;
    memory_used_mb: number;
    utilization?: number;
  };
  database: string;
  data_dir: string;
  providers_enabled: number;
  providers_ok: number;
  queue: Record<string, number>;
  counts: Record<string, number>;
  embedding_provider: string;
}

export interface Stats {
  videos_total: number;
  videos_ready: number;
  videos_failed: number;
  hours_indexed: number;
  chunks: number;
  libraries: number;
  courses: number;
  cost_last_30d: number;
  top_providers: { provider: string; calls: number; cost: number }[];
  recent_activity: { video_id: number; title: string; course: string; processed_at: string }[];
}

export interface Source {
  id: number;
  library_id: number;
  source_type: string;
  title: string;
  root_path: string;
  url: string;
  auto_sync: boolean;
  sync_status: string;
  last_synced_at: string | null;
  stats: Record<string, number>;
}

export interface FolderPreview {
  exists: boolean;
  count: number;
  total_bytes?: number;
  courses: string[];
  files: { path: string; name: string; title: string; size: number; course: string }[];
}

export interface PlaylistPreview {
  exists: boolean;
  error?: string;
  count: number;
  courses: string[];
  files: {
    path: string;
    name: string;
    title: string;
    size: number;
    course: string;
    duration: number;
    thumbnail: string;
  }[];
}
