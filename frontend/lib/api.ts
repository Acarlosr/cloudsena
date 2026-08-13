import type {
  AnswerResponse,
  FolderPreview,
  Job,
  Library,
  Provider,
  RoutingRule,
  SearchHit,
  Source,
  Stats,
  SystemStatus,
  TranscriptData,
  Video,
  VideoDetail,
} from "./types";

const BASE = "/api";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
    cache: "no-store",
  });

  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      /* corpo não-JSON */
    }
    throw new ApiError(detail, res.status);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

const qs = (params: Record<string, string | number | boolean | undefined>) => {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== "" && v !== false) search.set(k, String(v));
  });
  const s = search.toString();
  return s ? `?${s}` : "";
};

export const api = {
  // ---------- sistema ----------
  status: () => request<SystemStatus>("/system/status"),
  stats: () => request<Stats>("/stats"),

  // ---------- bibliotecas ----------
  libraries: () => request<Library[]>("/libraries"),
  library: (id: number) => request<Library>(`/libraries/${id}`),
  createLibrary: (body: { name: string; description?: string; color?: string; privacy_mode?: string }) =>
    request<Library>("/libraries", { method: "POST", body: JSON.stringify(body) }),
  updateLibrary: (id: number, body: Record<string, unknown>) =>
    request<Library>(`/libraries/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteLibrary: (id: number) => request<void>(`/libraries/${id}`, { method: "DELETE" }),
  courses: (id: number) =>
    request<{ course: string; videos: number; duration: number }[]>(`/libraries/${id}/courses`),

  // ---------- fontes ----------
  sources: (libraryId?: number) => request<Source[]>(`/sources${qs({ library_id: libraryId })}`),
  previewFolder: (path: string) =>
    request<FolderPreview>("/sources/preview-folder", {
      method: "POST",
      body: JSON.stringify({ path }),
    }),
  createSource: (body: Record<string, unknown>) =>
    request<Source>("/sources", { method: "POST", body: JSON.stringify(body) }),
  scanSource: (id: number) => request<Source>(`/sources/${id}/scan`, { method: "POST" }),
  deleteSource: (id: number) => request<void>(`/sources/${id}`, { method: "DELETE" }),

  // ---------- vídeos ----------
  videos: (params: Record<string, string | number | boolean | undefined> = {}) =>
    request<Video[]>(`/videos${qs(params)}`),
  video: (id: number) => request<VideoDetail>(`/videos/${id}`),
  updateVideo: (id: number, body: Record<string, unknown>) =>
    request<Video>(`/videos/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteVideo: (id: number) => request<void>(`/videos/${id}`, { method: "DELETE" }),
  retryVideo: (id: number) => request<{ job_id: number }>(`/videos/${id}/retry`, { method: "POST" }),
  transcript: (id: number) => request<TranscriptData>(`/videos/${id}/transcript`),
  suggestedQuestions: (id: number) => request<string[]>(`/videos/${id}/suggested-questions`),
  streamUrl: (id: number) => `${BASE}/videos/${id}/stream`,
  thumbUrl: (id: number) => `${BASE}/videos/${id}/thumbnail`,

  // ---------- busca e chat ----------
  search: (body: { query: string; library_id?: number; course?: string; video_ids?: number[]; top_k?: number }) =>
    request<{ query: string; count: number; results: SearchHit[] }>("/search", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  ask: (body: {
    question: string;
    library_id?: number;
    course?: string;
    video_ids?: number[];
    conversation_id?: number;
    deep_reasoning?: boolean;
    rerank?: boolean;
  }) => request<AnswerResponse>("/ask", { method: "POST", body: JSON.stringify(body) }),
  conversations: () =>
    request<{ id: number; title: string; created_at: string; message_count: number }[]>("/conversations"),
  conversation: (id: number) => request<any[]>(`/conversations/${id}`),
  deleteConversation: (id: number) => request<void>(`/conversations/${id}`, { method: "DELETE" }),

  // ---------- providers ----------
  providers: () => request<Provider[]>("/providers"),
  updateProvider: (slug: string, body: Record<string, unknown>) =>
    request<Provider>(`/providers/${slug}`, { method: "PATCH", body: JSON.stringify(body) }),
  testProvider: (slug: string) =>
    request<{ ok: boolean; message: string; latency_ms: number; model_count: number }>(
      `/providers/${slug}/test`,
      { method: "POST" },
    ),
  testAllProviders: () => request<any[]>("/providers/test-all", { method: "POST" }),
  providerModels: (slug: string, refresh = false) =>
    request<{ models: { id: string; label: string; context_length: number }[] }>(
      `/providers/${slug}/models${qs({ refresh })}`,
    ),
  routes: () => request<RoutingRule[]>("/providers/routing/rules"),
  updateRoute: (task: string, body: Record<string, unknown>) =>
    request<RoutingRule>(`/providers/routing/rules/${task}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  // ---------- fila ----------
  jobs: (params: Record<string, string | number | undefined> = {}) =>
    request<Job[]>(`/jobs${qs(params)}`),
  jobStats: () => request<Record<string, number>>("/jobs/stats"),
  retryJob: (id: number) => request<void>(`/jobs/${id}/retry`, { method: "POST" }),
};
