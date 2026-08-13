"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { Badge, EmptyState, Panel, ProgressBar, SectionTitle, Stat } from "@/components/ui";
import { useEvents } from "@/hooks/useEvents";
import { api } from "@/lib/api";
import { cx, formatRelative } from "@/lib/format";
import type { Job } from "@/lib/types";

const FILTERS = [
  { value: "", label: "Todos" },
  { value: "running", label: "Rodando" },
  { value: "pending", label: "Na fila" },
  { value: "failed", label: "Falhas" },
  { value: "done", label: "Concluídos" },
];

const TONE: Record<string, string> = {
  running: "border-signal-cyan/25 bg-signal-cyan/10 text-signal-cyan",
  pending: "border-white/10 bg-white/[.04] text-slate-400",
  done: "border-signal-lime/25 bg-signal-lime/10 text-signal-lime",
  failed: "border-signal-rose/25 bg-signal-rose/10 text-signal-rose",
  canceled: "border-white/10 bg-white/[.03] text-slate-500",
};

export default function QueuePage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [stats, setStats] = useState<Record<string, number>>({});
  const [filter, setFilter] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    const [j, s] = await Promise.all([
      api.jobs({ status: filter || undefined, limit: 100 }),
      api.jobStats(),
    ]);
    setJobs(j);
    setStats(s);
    setLoading(false);
  }, [filter]);

  useEffect(() => {
    load();
  }, [load]);

  useEvents((event) => {
    if (event.kind === "job.progress") {
      setJobs((prev) =>
        prev.map((j) =>
          j.id === event.data.job_id
            ? { ...j, progress: event.data.progress, stage: event.data.stage }
            : j,
        ),
      );
    }
    if (["job.created", "job.finished"].includes(event.kind)) load();
  });

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="label">Processamento</div>
          <h1 className="text-3xl font-semibold">Fila de trabalho</h1>
          <p className="mt-1.5 max-w-2xl text-sm text-slate-400">
            Cada etapa é retomável. Se a máquina reiniciar no meio da transcrição, o job volta para
            a fila e continua do último estágio concluído.
          </p>
        </div>
        <button
          onClick={async () => {
            await fetch("/api/jobs/requeue-stale", { method: "POST" });
            load();
          }}
          className="btn-ghost"
        >
          ⟳ Recuperar travados
        </button>
      </header>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Rodando" value={stats.running ?? 0} tone="cyan" />
        <Stat label="Na fila" value={stats.pending ?? 0} />
        <Stat label="Concluídos" value={stats.done ?? 0} tone="accent" />
        <Stat label="Falhas" value={stats.failed ?? 0} tone={stats.failed ? "rose" : "default"} />
      </div>

      <div className="flex gap-1 rounded-lg border border-white/[.07] bg-ink-850 p-1 w-fit">
        {FILTERS.map((f) => (
          <button
            key={f.value}
            onClick={() => setFilter(f.value)}
            className={cx(
              "rounded-md px-3 py-1.5 text-xs transition",
              filter === f.value ? "bg-accent/20 text-accent-soft" : "text-slate-400 hover:text-white",
            )}
          >
            {f.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="skeleton h-64" />
      ) : jobs.length === 0 ? (
        <EmptyState
          icon="⟳"
          title="Fila vazia"
          description="Nenhum job com esse filtro. Importe uma pasta para colocar vídeos na fila."
          action={
            <Link href="/biblioteca" className="btn-primary">
              Ir para a biblioteca
            </Link>
          }
        />
      ) : (
        <Panel className="divide-y divide-white/[.05]">
          {jobs.map((job) => (
            <div key={job.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
              <span className="mono-num w-12 shrink-0 text-slate-600">#{job.id}</span>

              <div className="min-w-[180px] flex-1">
                {job.video_id ? (
                  <Link
                    href={`/video/${job.video_id}`}
                    className="text-sm text-slate-200 hover:text-white"
                  >
                    {job.video_title || `Vídeo ${job.video_id}`}
                  </Link>
                ) : (
                  <span className="text-sm text-slate-300">{job.kind}</span>
                )}
                <div className="mt-0.5 text-[11px] text-slate-500">
                  {job.kind}
                  {job.stage && ` · ${job.stage}`}
                  {job.attempts > 1 && ` · tentativa ${job.attempts}/${job.max_attempts}`}
                </div>
                {job.error && (
                  <p className="mt-1 line-clamp-2 text-[11px] text-signal-rose/80">{job.error}</p>
                )}
              </div>

              {job.status === "running" && (
                <div className="w-32 shrink-0">
                  <ProgressBar value={job.progress} />
                </div>
              )}

              <Badge className={TONE[job.status]}>{job.status}</Badge>

              <span className="w-20 shrink-0 text-right text-[11px] text-slate-600">
                {formatRelative(job.finished_at || job.started_at || job.created_at)}
              </span>

              {job.status === "failed" && (
                <button
                  onClick={async () => {
                    await api.retryJob(job.id);
                    load();
                  }}
                  className="btn-ghost text-xs"
                >
                  Repetir
                </button>
              )}
            </div>
          ))}
        </Panel>
      )}
    </div>
  );
}
