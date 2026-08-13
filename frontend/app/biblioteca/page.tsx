"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";

import ImportDialog from "@/components/ImportDialog";
import VideoCard from "@/components/VideoCard";
import { EmptyState, Panel, Skeleton } from "@/components/ui";
import { useEvents } from "@/hooks/useEvents";
import { api } from "@/lib/api";
import { cx, formatHours } from "@/lib/format";
import type { Library, Video } from "@/lib/types";

const STATUS_FILTERS = [
  { value: "", label: "Todos" },
  { value: "ready", label: "Prontos" },
  { value: "queued", label: "Na fila" },
  { value: "failed", label: "Com erro" },
];

const SORTS = [
  { value: "recent", label: "Mais recentes" },
  { value: "title", label: "Título" },
  { value: "course", label: "Curso" },
  { value: "duration", label: "Duração" },
  { value: "progress", label: "Progresso" },
];

function LibraryContent() {
  const params = useSearchParams();
  const libParam = params.get("lib");

  const [libraries, setLibraries] = useState<Library[]>([]);
  const [libraryId, setLibraryId] = useState<number | undefined>(
    libParam ? Number(libParam) : undefined,
  );
  const [courses, setCourses] = useState<{ course: string; videos: number; duration: number }[]>([]);
  const [course, setCourse] = useState("");
  const [status, setStatus] = useState("");
  const [sort, setSort] = useState("recent");
  const [favorites, setFavorites] = useState(false);
  const [q, setQ] = useState("");
  const [videos, setVideos] = useState<Video[]>([]);
  const [loading, setLoading] = useState(true);
  const [importOpen, setImportOpen] = useState(false);

  useEffect(() => {
    api.libraries().then((libs) => {
      setLibraries(libs);
      setLibraryId((cur) => cur ?? libs[0]?.id);
    });
  }, []);

  // Clicar em outra biblioteca na sidebar navega para a mesma rota só trocando
  // ?lib=, sem desmontar a página — sem isso, o estado ficava preso na primeira
  // biblioteca aberta na sessão.
  useEffect(() => {
    if (libParam) {
      setLibraryId(Number(libParam));
      setCourse("");
    }
  }, [libParam]);

  useEffect(() => {
    if (libraryId) api.courses(libraryId).then(setCourses).catch(() => setCourses([]));
  }, [libraryId]);

  const load = useCallback(async () => {
    if (!libraryId) return;
    setLoading(true);
    try {
      setVideos(
        await api.videos({
          library_id: libraryId,
          course: course || undefined,
          status: status || undefined,
          favorites: favorites || undefined,
          q: q || undefined,
          sort,
          limit: 200,
        }),
      );
    } finally {
      setLoading(false);
    }
  }, [libraryId, course, status, sort, favorites, q]);

  useEffect(() => {
    const timer = setTimeout(load, q ? 350 : 0);
    return () => clearTimeout(timer);
  }, [load, q]);

  useEvents((event) => {
    if (event.kind === "video.status") {
      setVideos((prev) =>
        prev.map((v) =>
          v.id === event.data.video_id
            ? { ...v, status: event.data.status, stage_progress: event.data.progress ?? v.stage_progress }
            : v,
        ),
      );
    }
    if (event.kind === "source.scanned") load();
  });

  const library = useMemo(
    () => libraries.find((l) => l.id === libraryId),
    [libraries, libraryId],
  );

  const toggleFavorite = async (video: Video) => {
    setVideos((prev) =>
      prev.map((v) => (v.id === video.id ? { ...v, is_favorite: !v.is_favorite } : v)),
    );
    await api.updateVideo(video.id, { is_favorite: !video.is_favorite }).catch(load);
  };

  const retry = async (video: Video) => {
    await api.retryVideo(video.id);
    load();
  };

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="label">Biblioteca</div>
          <h1 className="text-3xl font-semibold">{library?.name || "Meus vídeos"}</h1>
          {library && (
            <p className="mt-1.5 text-sm text-slate-400">
              {library.video_count} vídeos · {library.ready_count} indexados ·{" "}
              {formatHours(library.total_duration)} de conteúdo
            </p>
          )}
        </div>
        <div className="flex gap-2">
          {libraries.length > 1 && (
            <select
              value={libraryId ?? ""}
              onChange={(e) => {
                setLibraryId(Number(e.target.value));
                setCourse("");
              }}
            >
              {libraries.map((lib) => (
                <option key={lib.id} value={lib.id}>
                  {lib.name}
                </option>
              ))}
            </select>
          )}
          <button onClick={() => setImportOpen(true)} className="btn-primary">
            + Importar
          </button>
        </div>
      </header>

      <Panel className="p-3">
        <div className="flex flex-wrap items-center gap-2">
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Filtrar por título ou curso…"
            className="min-w-[200px] flex-1"
          />
          <div className="flex gap-1 rounded-lg border border-white/[.07] bg-ink-850 p-1">
            {STATUS_FILTERS.map((f) => (
              <button
                key={f.value}
                onClick={() => setStatus(f.value)}
                className={cx(
                  "rounded-md px-2.5 py-1 text-xs transition",
                  status === f.value
                    ? "bg-accent/20 text-accent-soft"
                    : "text-slate-400 hover:text-white",
                )}
              >
                {f.label}
              </button>
            ))}
          </div>
          <button
            onClick={() => setFavorites((v) => !v)}
            className={cx(
              "btn",
              favorites
                ? "border border-signal-amber/30 bg-signal-amber/10 text-signal-amber"
                : "btn-ghost",
            )}
          >
            ★ Favoritos
          </button>
          <select value={sort} onChange={(e) => setSort(e.target.value)}>
            {SORTS.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
        </div>

        {courses.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5 border-t border-white/[.05] pt-3">
            <button
              onClick={() => setCourse("")}
              className={cx(
                "chip transition",
                !course && "border-accent/40 bg-accent/15 text-accent-soft",
              )}
            >
              Todos os cursos
            </button>
            {courses.map((c) => (
              <button
                key={c.course}
                onClick={() => setCourse(c.course === course ? "" : c.course)}
                className={cx(
                  "chip transition hover:border-white/20",
                  course === c.course && "border-accent/40 bg-accent/15 text-accent-soft",
                )}
              >
                {c.course}
                <span className="text-slate-500">{c.videos}</span>
              </button>
            ))}
          </div>
        )}
      </Panel>

      {loading ? (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="h-56" />
          ))}
        </div>
      ) : videos.length === 0 ? (
        <EmptyState
          icon="▤"
          title="Nada por aqui"
          description={
            q || course || status
              ? "Nenhum vídeo corresponde aos filtros aplicados."
              : "Importe uma pasta de cursos para começar a construir sua biblioteca."
          }
          action={
            !q && !course && !status ? (
              <button onClick={() => setImportOpen(true)} className="btn-primary">
                Importar uma pasta
              </button>
            ) : (
              <button
                onClick={() => {
                  setQ("");
                  setCourse("");
                  setStatus("");
                }}
                className="btn-ghost"
              >
                Limpar filtros
              </button>
            )
          }
        />
      ) : (
        <>
          <div className="text-xs text-slate-500">{videos.length} vídeo(s)</div>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-4">
            {videos.map((video) => (
              <VideoCard
                key={video.id}
                video={video}
                onToggleFavorite={toggleFavorite}
                onRetry={retry}
              />
            ))}
          </div>
        </>
      )}

      <ImportDialog
        open={importOpen}
        onClose={() => setImportOpen(false)}
        onDone={load}
        defaultLibraryId={libraryId}
      />
    </div>
  );
}

export default function LibraryPage() {
  return (
    <Suspense fallback={<Skeleton className="h-64" />}>
      <LibraryContent />
    </Suspense>
  );
}
