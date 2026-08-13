export function formatDuration(seconds: number): string {
  if (!seconds || seconds < 0) return "—";
  const total = Math.floor(seconds);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  return h > 0
    ? `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`
    : `${m}:${String(s).padStart(2, "0")}`;
}

export function formatHours(seconds: number): string {
  const hours = seconds / 3600;
  if (hours < 1) return `${Math.round(seconds / 60)} min`;
  return `${hours.toFixed(1)} h`;
}

export function formatBytes(bytes: number): string {
  if (!bytes) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let i = 0;
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024;
    i++;
  }
  return `${value.toFixed(value >= 100 || i === 0 ? 0 : 1)} ${units[i]}`;
}

export function formatDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

export function formatRelative(iso: string | null): string {
  if (!iso) return "—";
  const diff = Date.now() - new Date(iso).getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return "agora";
  if (minutes < 60) return `há ${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `há ${hours} h`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `há ${days} d`;
  return formatDate(iso);
}

export function formatCost(usd: number): string {
  if (!usd) return "$0";
  if (usd < 0.01) return `$${usd.toFixed(4)}`;
  return `$${usd.toFixed(2)}`;
}

export const STATUS_LABEL: Record<string, string> = {
  discovered: "Descoberto",
  queued: "Na fila",
  extracting: "Extraindo áudio",
  transcribing: "Transcrevendo",
  summarizing: "Resumindo",
  indexing: "Indexando",
  ready: "Pronto",
  failed: "Falhou",
  skipped: "Ignorado",
};

export const STATUS_TONE: Record<string, string> = {
  ready: "text-signal-lime border-signal-lime/25 bg-signal-lime/10",
  failed: "text-signal-rose border-signal-rose/25 bg-signal-rose/10",
  queued: "text-slate-400 border-white/10 bg-white/[.04]",
  discovered: "text-slate-400 border-white/10 bg-white/[.04]",
  skipped: "text-slate-500 border-white/10 bg-white/[.03]",
  extracting: "text-signal-cyan border-signal-cyan/25 bg-signal-cyan/10",
  transcribing: "text-signal-cyan border-signal-cyan/25 bg-signal-cyan/10",
  summarizing: "text-accent-soft border-accent/30 bg-accent/10",
  indexing: "text-accent-soft border-accent/30 bg-accent/10",
};

export const WATCH_LABEL: Record<string, string> = {
  unwatched: "Não visto",
  in_progress: "Em andamento",
  completed: "Concluído",
  revisit: "Revisitar",
};

export function isProcessing(status: string): boolean {
  return ["queued", "extracting", "transcribing", "summarizing", "indexing"].includes(status);
}

export function cx(...classes: (string | false | null | undefined)[]): string {
  return classes.filter(Boolean).join(" ");
}
