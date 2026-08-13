"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import AnswerBlock from "@/components/AnswerBlock";
import { Badge, ErrorNote, Panel, ProgressBar, Spinner } from "@/components/ui";
import { useEvents } from "@/hooks/useEvents";
import { api } from "@/lib/api";
import {
  STATUS_LABEL,
  STATUS_TONE,
  WATCH_LABEL,
  cx,
  formatBytes,
  formatDuration,
  isProcessing,
} from "@/lib/format";
import type { AnswerResponse, Segment, VideoDetail } from "@/lib/types";

type Tab = "resumo" | "transcricao" | "perguntar";

export default function VideoWorkspace({ videoId }: { videoId: number }) {
  const [video, setVideo] = useState<VideoDetail | null>(null);
  const [segments, setSegments] = useState<Segment[]>([]);
  const [tab, setTab] = useState<Tab>("resumo");
  const [current, setCurrent] = useState(0);
  const [error, setError] = useState("");
  const videoRef = useRef<HTMLVideoElement>(null);
  const activeLineRef = useRef<HTMLButtonElement>(null);
  const [followTranscript, setFollowTranscript] = useState(true);

  const load = useCallback(async () => {
    try {
      const detail = await api.video(videoId);
      setVideo(detail);
      if (detail.has_transcript) {
        const t = await api.transcript(videoId).catch(() => null);
        if (t) setSegments(t.segments);
      }
    } catch (e: any) {
      setError(e.message);
    }
  }, [videoId]);

  useEffect(() => {
    load();
  }, [load]);

  // Deep link: /video/12?t=860 abre já no minuto certo.
  useEffect(() => {
    const t = Number(new URLSearchParams(window.location.search).get("t"));
    if (t && videoRef.current) {
      const el = videoRef.current;
      const seek = () => {
        el.currentTime = t;
        el.removeEventListener("loadedmetadata", seek);
      };
      el.readyState >= 1 ? (el.currentTime = t) : el.addEventListener("loadedmetadata", seek);
    }
  }, [video?.id]);

  useEvents((event) => {
    if (event.kind === "video.status" && event.data.video_id === videoId) load();
  });

  // Salva progresso de leitura a cada 15s.
  useEffect(() => {
    const timer = setInterval(() => {
      const el = videoRef.current;
      if (el && el.currentTime > 5 && !el.paused) {
        api.updateVideo(videoId, { watched_seconds: el.currentTime }).catch(() => {});
      }
    }, 15000);
    return () => clearInterval(timer);
  }, [videoId]);

  useEffect(() => {
    if (followTranscript && tab === "transcricao") {
      activeLineRef.current?.scrollIntoView({ block: "center", behavior: "smooth" });
    }
  }, [current, followTranscript, tab]);

  const seek = (seconds: number) => {
    const el = videoRef.current;
    if (!el) return;
    el.currentTime = seconds;
    el.play().catch(() => {});
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  if (error) return <ErrorNote message={error} />;
  if (!video) return <div className="skeleton h-[60vh]" />;

  const processing = isProcessing(video.status);
  const activeIndex = segments.findIndex((s) => current >= s.start && current < s.end);
  const chapters = video.summary?.chapters || [];
  const activeChapter = [...chapters].reverse().find((c) => current >= c.start);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <Link href="/biblioteca" className="text-slate-500 hover:text-slate-300">
          ← Biblioteca
        </Link>
        {video.course && (
          <>
            <span className="text-slate-700">/</span>
            <Link
              href={`/biblioteca?course=${encodeURIComponent(video.course)}`}
              className="text-slate-400 hover:text-white"
            >
              {video.course}
            </Link>
          </>
        )}
      </div>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.65fr)_minmax(360px,1fr)]">
        {/* ------------------------- coluna do player ------------------------- */}
        <div className="space-y-4">
          <div className="overflow-hidden rounded-2xl border border-white/[.07] bg-black shadow-panel">
            <video
              ref={videoRef}
              controls
              preload="metadata"
              poster={video.thumbnail_path ? api.thumbUrl(video.id) : undefined}
              src={api.streamUrl(video.id)}
              onTimeUpdate={(e) => setCurrent(e.currentTarget.currentTime)}
              className="aspect-video w-full bg-black"
            />
          </div>

          <div>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <h1 className="text-xl font-semibold leading-snug">{video.title}</h1>
                <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                  <Badge className={STATUS_TONE[video.status]}>
                    {processing && <Spinner className="h-3 w-3" />}
                    {STATUS_LABEL[video.status]}
                  </Badge>
                  <span>{formatDuration(video.duration_seconds)}</span>
                  {video.width > 0 && (
                    <span>
                      {video.width}×{video.height}
                    </span>
                  )}
                  {video.file_size > 0 && <span>{formatBytes(video.file_size)}</span>}
                  {video.language && <span className="uppercase">{video.language}</span>}
                  {video.chunk_count > 0 && <span>{video.chunk_count} trechos indexados</span>}
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                {video.status === "ready" && (
                  <select
                    value={video.watch_status}
                    onChange={async (e) => {
                      await api.updateVideo(video.id, { watch_status: e.target.value });
                      load();
                    }}
                    className="text-xs"
                    title="Status de leitura"
                  >
                    {Object.entries(WATCH_LABEL).map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                )}
                <button
                  onClick={async () => {
                    await api.updateVideo(video.id, { is_favorite: !video.is_favorite });
                    load();
                  }}
                  className={cx(
                    "btn",
                    video.is_favorite
                      ? "border border-signal-amber/30 bg-signal-amber/10 text-signal-amber"
                      : "btn-ghost",
                  )}
                >
                  {video.is_favorite ? "★" : "☆"}
                </button>
                {(video.status === "failed" || video.status === "ready") && (
                  <button
                    onClick={async () => {
                      await api.retryVideo(video.id);
                      load();
                    }}
                    className="btn-ghost"
                  >
                    ⟳ Reprocessar
                  </button>
                )}
              </div>
            </div>

            {processing && (
              <div className="mt-4">
                <div className="mb-1.5 flex justify-between text-[11px] text-slate-500">
                  <span>{STATUS_LABEL[video.status]}</span>
                  <span className="mono-num">{Math.round(video.stage_progress * 100)}%</span>
                </div>
                <ProgressBar value={video.stage_progress} />
              </div>
            )}

            {video.status === "failed" && video.error_message && (
              <div className="mt-4">
                <ErrorNote message={video.error_message} />
              </div>
            )}
          </div>

          {chapters.length > 0 && (
            <Panel className="p-4">
              <div className="label mb-2.5">Capítulos</div>
              <div className="space-y-1">
                {chapters.map((chapter, index) => (
                  <button
                    key={index}
                    onClick={() => seek(chapter.start)}
                    className={cx(
                      "flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-[13px] transition",
                      activeChapter === chapter
                        ? "bg-accent/12 text-white"
                        : "text-slate-300 hover:bg-white/[.04]",
                    )}
                  >
                    <span className="mono-num w-12 shrink-0 text-slate-500">
                      {formatDuration(chapter.start)}
                    </span>
                    <span className="truncate">{chapter.title}</span>
                  </button>
                ))}
              </div>
            </Panel>
          )}
        </div>

        {/* --------------------------- painel lateral -------------------------- */}
        <Panel className="flex h-fit max-h-[calc(100vh-7rem)] flex-col overflow-hidden xl:sticky xl:top-6">
          <div className="flex border-b border-white/[.06]">
            {(["resumo", "transcricao", "perguntar"] as Tab[]).map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={cx(
                  "flex-1 px-4 py-3 text-[13px] font-medium capitalize transition",
                  tab === t
                    ? "border-b-2 border-accent text-white"
                    : "text-slate-500 hover:text-slate-300",
                )}
              >
                {t === "transcricao" ? "Transcrição" : t}
              </button>
            ))}
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto scroll-thin p-4">
            {tab === "resumo" && <SummaryTab video={video} onSeek={seek} />}
            {tab === "transcricao" && (
              <TranscriptTab
                segments={segments}
                activeIndex={activeIndex}
                activeRef={activeLineRef}
                follow={followTranscript}
                setFollow={setFollowTranscript}
                onSeek={seek}
                ready={video.has_transcript}
              />
            )}
            {tab === "perguntar" && <VideoChatTab video={video} onSeek={seek} />}
          </div>
        </Panel>
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
function SummaryTab({ video, onSeek }: { video: VideoDetail; onSeek: (s: number) => void }) {
  const summary = video.summary;
  if (!summary?.short_summary) {
    return (
      <p className="py-8 text-center text-sm text-slate-500">
        {isProcessing(video.status)
          ? "O resumo aparece assim que o processamento terminar."
          : "Sem resumo para este vídeo ainda."}
      </p>
    );
  }

  return (
    <div className="space-y-5 text-sm">
      <div>
        <div className="label">Em resumo</div>
        <p className="leading-relaxed text-slate-200">{summary.short_summary}</p>
      </div>

      {summary.topics.length > 0 && (
        <div>
          <div className="label">Tópicos abordados</div>
          <ul className="space-y-1.5">
            {summary.topics.map((topic, i) => (
              <li key={i} className="flex gap-2 text-slate-300">
                <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-accent" />
                {topic}
              </li>
            ))}
          </ul>
        </div>
      )}

      {summary.long_summary && (
        <div>
          <div className="label">Detalhado</div>
          <p className="whitespace-pre-wrap leading-relaxed text-slate-300">
            {summary.long_summary}
          </p>
        </div>
      )}

      {summary.entities.length > 0 && (
        <div>
          <div className="label">Ferramentas e conceitos citados</div>
          <div className="flex flex-wrap gap-1.5">
            {summary.entities.map((entity) => (
              <span key={entity} className="chip">
                {entity}
              </span>
            ))}
          </div>
        </div>
      )}

      {summary.keywords.length > 0 && (
        <div>
          <div className="label">Palavras-chave</div>
          <div className="flex flex-wrap gap-1.5">
            {summary.keywords.map((k) => (
              <span key={k} className="chip">
                {k}
              </span>
            ))}
          </div>
        </div>
      )}

      {summary.model && (
        <p className="border-t border-white/[.05] pt-3 font-mono text-[10px] text-slate-600">
          gerado por {summary.model}
        </p>
      )}
    </div>
  );
}

function TranscriptTab({
  segments,
  activeIndex,
  activeRef,
  follow,
  setFollow,
  onSeek,
  ready,
}: {
  segments: Segment[];
  activeIndex: number;
  activeRef: React.RefObject<HTMLButtonElement>;
  follow: boolean;
  setFollow: (v: boolean) => void;
  onSeek: (s: number) => void;
  ready: boolean;
}) {
  const [filter, setFilter] = useState("");

  if (!ready || segments.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-slate-500">
        A transcrição aparece aqui quando o vídeo terminar de ser processado.
      </p>
    );
  }

  const visible = filter
    ? segments.filter((s) => s.text.toLowerCase().includes(filter.toLowerCase()))
    : segments;

  return (
    <div className="space-y-3">
      <div className="flex gap-2">
        <input
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Buscar na transcrição…"
          className="flex-1 text-[13px]"
        />
        <button
          onClick={() => setFollow(!follow)}
          className={cx("btn text-xs", follow ? "bg-accent/20 text-accent-soft" : "btn-ghost")}
          title="Acompanhar o player"
        >
          ⇅
        </button>
      </div>

      <div className="space-y-0.5">
        {visible.map((segment, index) => {
          const isActive = segments[activeIndex] === segment;
          return (
            <button
              key={`${segment.start}-${index}`}
              ref={isActive ? activeRef : undefined}
              onClick={() => onSeek(segment.start)}
              className={cx(
                "flex w-full gap-3 rounded-lg px-2 py-1.5 text-left text-[13px] leading-relaxed transition",
                isActive
                  ? "bg-accent/12 text-white"
                  : "text-slate-400 hover:bg-white/[.03] hover:text-slate-200",
              )}
            >
              <span className="mono-num shrink-0 pt-0.5 text-[10px] text-slate-600">
                {formatDuration(segment.start)}
              </span>
              <span>{segment.text}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function VideoChatTab({
  video,
  onSeek,
}: {
  video: VideoDetail;
  onSeek: (seconds: number) => void;
}) {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<AnswerResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [suggestions, setSuggestions] = useState<string[]>([]);

  useEffect(() => {
    api.suggestedQuestions(video.id).then(setSuggestions).catch(() => {});
  }, [video.id]);

  const ask = async (text?: string) => {
    const q = (text ?? question).trim();
    if (!q) return;
    setLoading(true);
    setError("");
    setQuestion(q);
    try {
      setAnswer(
        await api.ask({ question: q, video_ids: [video.id], library_id: video.library_id }),
      );
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <p className="text-xs text-slate-500">
        Perguntas restritas a <span className="text-slate-300">este vídeo</span>. As respostas
        citam o minuto exato.
      </p>

      <div className="flex gap-2">
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && ask()}
          placeholder="O que foi explicado sobre…"
          className="flex-1 text-[13px]"
        />
        <button onClick={() => ask()} disabled={loading || !question.trim()} className="btn-primary">
          {loading ? <Spinner /> : "→"}
        </button>
      </div>

      {suggestions.length > 0 && !answer && (
        <div className="space-y-1.5">
          <div className="label">Sugestões</div>
          {suggestions.map((s) => (
            <button
              key={s}
              onClick={() => ask(s)}
              className="block w-full rounded-lg border border-white/[.06] bg-white/[.02] px-3 py-2 text-left text-[12.5px] text-slate-400 transition hover:border-accent/30 hover:text-slate-200"
            >
              {s}
            </button>
          ))}
        </div>
      )}

      <ErrorNote message={error} />

      {loading && (
        <div className="flex items-center gap-2 py-6 text-sm text-slate-500">
          <Spinner /> Buscando nos trechos deste vídeo…
        </div>
      )}

      {answer && !loading && (
        <div className="animate-fade-up">
          <AnswerBlock answer={answer} onSeek={(_, seconds) => onSeek(seconds)} />
        </div>
      )}
    </div>
  );
}
