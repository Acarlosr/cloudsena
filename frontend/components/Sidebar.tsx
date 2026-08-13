"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { useEvents } from "@/hooks/useEvents";
import { api } from "@/lib/api";
import { cx } from "@/lib/format";
import type { Library, SystemStatus } from "@/lib/types";

const NAV = [
  { href: "/", label: "Painel", icon: "◆" },
  { href: "/biblioteca", label: "Biblioteca", icon: "▤" },
  { href: "/perguntar", label: "Perguntar", icon: "✧" },
  { href: "/fila", label: "Processamento", icon: "⟳" },
  { href: "/conexoes", label: "Conexões de IA", icon: "⌁" },
];

export default function Sidebar() {
  const pathname = usePathname();
  const [libraries, setLibraries] = useState<Library[]>([]);
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const { connected, last } = useEvents();

  useEffect(() => {
    api.libraries().then(setLibraries).catch(() => {});
    api.status().then(setStatus).catch(() => {});
  }, []);

  useEffect(() => {
    if (last?.kind === "job.finished" || last?.kind === "source.scanned") {
      api.libraries().then(setLibraries).catch(() => {});
      api.status().then(setStatus).catch(() => {});
    }
  }, [last]);

  const queue = status?.queue || {};
  const busy = (queue.pending || 0) + (queue.running || 0);

  return (
    <aside className="fixed inset-y-0 left-0 z-40 hidden w-[248px] flex-col border-r border-white/[.06] bg-ink-900/60 backdrop-blur-xl lg:flex">
      <div className="px-5 pb-6 pt-6">
        <Link href="/" className="group flex items-center gap-3">
          <div className="relative flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-accent to-signal-cyan text-sm font-bold text-white shadow-glow">
            CS
          </div>
          <div>
            <div className="text-[15px] font-semibold leading-none text-white">CloudSena</div>
            <div className="mt-1 text-[10px] uppercase tracking-[.18em] text-slate-500">
              Biblioteca inteligente
            </div>
          </div>
        </Link>
      </div>

      <nav className="flex-1 space-y-1 overflow-y-auto px-3 scroll-thin">
        {NAV.map((item) => {
          const active =
            item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cx(
                "flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition",
                active
                  ? "bg-accent/12 text-white shadow-[inset_0_0_0_1px_rgba(124,92,255,.28)]"
                  : "text-slate-400 hover:bg-white/[.04] hover:text-slate-100",
              )}
            >
              <span className={cx("text-xs", active ? "text-accent-soft" : "text-slate-600")}>
                {item.icon}
              </span>
              {item.label}
              {item.href === "/fila" && busy > 0 && (
                <span className="ml-auto rounded-full bg-accent/20 px-2 py-0.5 text-[10px] font-semibold text-accent-soft">
                  {busy}
                </span>
              )}
            </Link>
          );
        })}

        {libraries.length > 0 && (
          <div className="pt-6">
            <div className="label px-3">Bibliotecas</div>
            {libraries.map((lib) => (
              <Link
                key={lib.id}
                href={`/biblioteca?lib=${lib.id}`}
                className="group flex items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] text-slate-400 transition hover:bg-white/[.04] hover:text-slate-100"
              >
                <span
                  className="h-2 w-2 shrink-0 rounded-full"
                  style={{ background: lib.color }}
                />
                <span className="truncate">{lib.name}</span>
                <span className="mono-num ml-auto text-slate-600">{lib.video_count}</span>
              </Link>
            ))}
          </div>
        )}
      </nav>

      <div className="border-t border-white/[.06] px-4 py-4">
        <div className="flex items-center gap-2 text-[11px] text-slate-500">
          <span
            className={cx(
              "h-1.5 w-1.5 rounded-full",
              connected ? "bg-signal-lime animate-pulse-ring" : "bg-slate-600",
            )}
          />
          {connected ? "Tempo real ativo" : "Reconectando…"}
        </div>
        {status && (
          <div className="mt-2.5 space-y-1 text-[11px] text-slate-500">
            <Line ok={status.ffmpeg} label="FFmpeg" />
            <Line ok={status.whisper} label="Whisper local" />
            <Line
              ok={status.gpu.available}
              label={status.gpu.available ? status.gpu.name.replace("NVIDIA ", "") : "GPU"}
            />
            <Line
              ok={status.providers_ok > 0}
              label={`${status.providers_enabled} provider(s) ativos`}
            />
          </div>
        )}
      </div>
    </aside>
  );
}

function Line({ ok, label }: { ok: boolean; label: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className={cx("text-[9px]", ok ? "text-signal-lime" : "text-slate-600")}>
        {ok ? "●" : "○"}
      </span>
      <span className="truncate">{label}</span>
    </div>
  );
}
