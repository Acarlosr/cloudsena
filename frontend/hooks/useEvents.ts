"use client";

import { useEffect, useRef, useState } from "react";

export interface CloudSenaEvent {
  kind: string;
  ts: number;
  data: Record<string, any>;
}

/**
 * Assina o stream SSE do backend. Reconecta sozinho se a conexão cair
 * (por exemplo, quando o servidor reinicia durante o desenvolvimento).
 */
export function useEvents(onEvent?: (event: CloudSenaEvent) => void) {
  const [connected, setConnected] = useState(false);
  const [last, setLast] = useState<CloudSenaEvent | null>(null);
  const handler = useRef(onEvent);
  handler.current = onEvent;

  useEffect(() => {
    let source: EventSource | null = null;
    let retry: ReturnType<typeof setTimeout>;
    let closed = false;

    const connect = () => {
      source = new EventSource("/api/events");

      source.onopen = () => setConnected(true);

      const consume = (e: MessageEvent) => {
        try {
          const parsed = JSON.parse(e.data) as CloudSenaEvent;
          setLast(parsed);
          handler.current?.(parsed);
        } catch {
          /* keepalive */
        }
      };

      ["connected", "job.created", "job.progress", "job.finished", "video.status", "source.scanned"].forEach(
        (kind) => source?.addEventListener(kind, consume as EventListener),
      );
      source.onmessage = consume;

      source.onerror = () => {
        setConnected(false);
        source?.close();
        if (!closed) retry = setTimeout(connect, 3000);
      };
    };

    connect();
    return () => {
      closed = true;
      clearTimeout(retry);
      source?.close();
    };
  }, []);

  return { connected, last };
}

/** Polling simples com cancelamento — para telas que não dependem de SSE. */
export function usePoll<T>(fn: () => Promise<T>, intervalMs: number, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string>("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;

    const tick = async () => {
      try {
        const result = await fn();
        if (!alive) return;
        setData(result);
        setError("");
      } catch (e: any) {
        if (alive) setError(e?.message || "Erro ao carregar");
      } finally {
        if (alive) {
          setLoading(false);
          timer = setTimeout(tick, intervalMs);
        }
      }
    };

    tick();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { data, error, loading, setData };
}
