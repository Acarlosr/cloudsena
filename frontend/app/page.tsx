"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import VideoCard from "@/components/VideoCard";
import ImportDialog from "@/components/ImportDialog";
import { EmptyState, Panel, ProgressBar, SectionTitle, Skeleton, Stat } from "@/components/ui";
import { useEvents } from "@/hooks/useEvents";
import { api } from "@/lib/api";
import { cx, formatCost, formatDuration, formatRelative } from "@/lib/format";
import type { Job, Stats, SystemStatus, Video } from "@/lib/types";

export default function DashboardPage() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [recent, setRecent] = useState<Video[]>([]);
  const [active, setActive] = useState<Job[]>([]);
  const [importOpen, setImportOpen] = useState(false);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    const [s, st, v, j] = await Promise.all([
      api.stats().catch(() => null),
      api.status().catch(() => null),
      api.videos({ limit: 8, sort: "recent" }).catch(() => []),
      api.jobs({ limit: 6 }).catch(() => []),
    ]);
    setStats(s);
    setStatus(st);
    setRecent(v);
    setActive(j.filter((x) => x.status === "running" || x.status === "pending"));
    setLoading(false);
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEvents((event) => {
    if (["job.finished", "video.status", "source.scanned"].includes(event.kind)) refresh();
    if (event.kind === "job.progress") {
      setActive((prev) =>
        prev.map((j) =>
          j.id === event.data.job_id
            ? { ...j, progress: event.data.progress, stage: event.data.stage }
            : j,
        ),
      );
    }
  });

  const setupIncomplete = status && (!status.ffmpeg || !status.whisper || status.providers_ok === 0);

  return (
    <div className="space-y-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="label">Painel</div>
          <h1 className="text-3xl font-semibold">Sua biblioteca, pesquisável</h1>
          <p className="mt-1.5 max-w-xl text-sm text-slate-400">
            Cada aula vira texto com timestamp. Pergunte em português e receba a resposta com o
            vídeo e o minuto exato.
          </p>
        </div>
        <div className="flex gap-2">
          <Link href="/perguntar" className="btn-ghost">
            ✧ Perguntar
          </Link>
          <button onClick={() => setImportOpen(true)} className="btn-primary">
            + Importar vídeos
          </button>
        </div>
      </header>

      {setupIncomplete && <SetupBanner status={status!} />}

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {loading || !stats ? (
          Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-[104px]" />)
        ) : (
          <>
            <Stat
              label="Vídeos indexados"
              value={stats.videos_ready}
              hint={`${stats.videos_total} no total${stats.videos_failed ? ` · ${stats.videos_failed} com erro` : ""}`}
              tone="accent"
            />
            <Stat
              label="Horas de conteúdo"
              value={stats.hours_indexed}
              hint={`${stats.courses} curso(s) · ${stats.libraries} biblioteca(s)`}
            />
            <Stat
              label="Trechos pesquisáveis"
              value={stats.chunks.toLocaleString("pt-BR")}
              hint="blocos com timestamp"
              tone="cyan"
            />
            <Stat
              label="Custo de IA (30 d)"
              value={formatCost(stats.cost_last_30d)}
              hint={
                stats.top_providers[0]
                  ? `principal: ${stats.top_providers[0].provider}`
                  : "sem chamadas ainda"
              }
            />
          </>
        )}
      </div>

      {active.length > 0 && (
        <section>
          <SectionTitle
            title="Processando agora"
            subtitle="A fila é retomável — se a máquina reiniciar, continua de onde parou."
            action={
              <Link href="/fila" className="text-sm text-accent-soft hover:underline">
                ver tudo →
              </Link>
            }
          />
          <Panel className="divide-y divide-white/[.05]">
            {active.map((job) => (
              <div key={job.id} className="flex items-center gap-4 px-4 py-3">
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm text-slate-200">
                    {job.video_title || `Job #${job.id}`}
                  </div>
                  <div className="mt-0.5 text-[11px] uppercase tracking-wide text-slate-500">
                    {job.stage || job.kind} · tentativa {job.attempts}/{job.max_attempts}
                  </div>
                </div>
                <div className="w-40 shrink-0">
                  <ProgressBar value={job.progress} />
                </div>
                <span className="mono-num w-10 shrink-0 text-right text-slate-400">
                  {Math.round(job.progress * 100)}%
                </span>
              </div>
            ))}
          </Panel>
        </section>
      )}

      <section>
        <SectionTitle
          title="Adicionados recentemente"
          action={
            <Link href="/biblioteca" className="text-sm text-accent-soft hover:underline">
              abrir biblioteca →
            </Link>
          }
        />
        {loading ? (
          <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-56" />
            ))}
          </div>
        ) : recent.length === 0 ? (
          <EmptyState
            icon="▤"
            title="Nenhum vídeo ainda"
            description="Aponte o CloudSena para uma pasta de cursos no seu computador. Ele varre as subpastas, gera thumbnails, transcreve e indexa tudo."
            action={
              <button onClick={() => setImportOpen(true)} className="btn-primary">
                Importar uma pasta
              </button>
            }
          />
        ) : (
          <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-4">
            {recent.map((video) => (
              <VideoCard key={video.id} video={video} />
            ))}
          </div>
        )}
      </section>

      {stats && stats.recent_activity.length > 0 && (
        <section className="grid gap-4 lg:grid-cols-2">
          <Panel className="p-5">
            <SectionTitle title="Últimos processados" />
            <ul className="space-y-2.5">
              {stats.recent_activity.map((item) => (
                <li key={item.video_id} className="flex items-center gap-3 text-sm">
                  <Link
                    href={`/video/${item.video_id}`}
                    className="min-w-0 flex-1 truncate text-slate-300 hover:text-white"
                  >
                    {item.title}
                  </Link>
                  <span className="shrink-0 text-[11px] text-slate-500">
                    {formatRelative(item.processed_at)}
                  </span>
                </li>
              ))}
            </ul>
          </Panel>

          <Panel className="p-5">
            <SectionTitle title="Uso de IA por provider" subtitle="Últimos 30 dias" />
            {stats.top_providers.length === 0 ? (
              <p className="text-sm text-slate-500">Nenhuma chamada registrada ainda.</p>
            ) : (
              <ul className="space-y-3">
                {stats.top_providers.map((p) => {
                  const max = Math.max(...stats.top_providers.map((x) => x.calls));
                  return (
                    <li key={p.provider}>
                      <div className="mb-1 flex justify-between text-xs">
                        <span className="text-slate-300">{p.provider}</span>
                        <span className="mono-num text-slate-500">
                          {p.calls} · {formatCost(p.cost)}
                        </span>
                      </div>
                      <ProgressBar value={p.calls / max} />
                    </li>
                  );
                })}
              </ul>
            )}
          </Panel>
        </section>
      )}

      <ImportDialog open={importOpen} onClose={() => setImportOpen(false)} onDone={refresh} />
    </div>
  );
}

function SetupBanner({ status }: { status: SystemStatus }) {
  const items = [
    {
      ok: status.ffmpeg,
      label: "FFmpeg",
      fix: "sudo apt install ffmpeg",
      why: "necessário para thumbnails e extração de áudio",
    },
    {
      ok: status.whisper,
      label: "faster-whisper",
      fix: "pip install faster-whisper",
      why: "transcrição local na GPU",
    },
    {
      ok: status.providers_ok > 0,
      label: "Provider de IA",
      fix: "Conexões de IA → testar conexão",
      why: "resumos e respostas",
    },
  ].filter((i) => !i.ok);

  if (!items.length) return null;

  return (
    <Panel className="border-signal-amber/25 bg-signal-amber/[.05] p-5">
      <div className="flex items-start gap-3">
        <span className="mt-0.5 text-signal-amber">⚠</span>
        <div className="flex-1">
          <h3 className="text-sm font-semibold text-signal-amber">Configuração incompleta</h3>
          <ul className="mt-2.5 space-y-1.5 text-sm text-slate-300">
            {items.map((item) => (
              <li key={item.label} className="flex flex-wrap items-center gap-2">
                <span className="font-medium">{item.label}</span>
                <span className="text-slate-500">— {item.why}</span>
                <code className="rounded bg-black/40 px-1.5 py-0.5 font-mono text-[11px] text-slate-400">
                  {item.fix}
                </code>
              </li>
            ))}
          </ul>
        </div>
        <Link href="/conexoes" className="btn-ghost shrink-0">
          Configurar
        </Link>
      </div>
    </Panel>
  );
}
