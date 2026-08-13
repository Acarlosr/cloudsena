"use client";

import Link from "next/link";
import { Fragment } from "react";

import { api } from "@/lib/api";
import { cx, formatCost } from "@/lib/format";
import type { AnswerResponse, Citation } from "@/lib/types";
import { Badge } from "./ui";

/**
 * Renderiza a resposta destacando os marcadores [1], [2] como links clicáveis
 * que abrem o vídeo no minuto exato — o coração do produto.
 */
export default function AnswerBlock({
  answer,
  onSeek,
}: {
  answer: AnswerResponse;
  onSeek?: (videoId: number, seconds: number) => void;
}) {
  const byMarker = new Map(answer.citations.map((c) => [c.marker, c]));

  return (
    <div className="space-y-4">
      {!answer.grounded && (
        <div className="rounded-xl border border-signal-amber/25 bg-signal-amber/[.06] px-4 py-3 text-sm text-signal-amber">
          Sem evidência suficiente nos vídeos indexados para responder com segurança.
        </div>
      )}

      <div className="prose-answer whitespace-pre-wrap">
        {renderWithCitations(answer.text, byMarker, onSeek)}
      </div>

      {answer.citations.length > 0 && (
        <div>
          <div className="label mb-2">Onde assistir</div>
          <div className="grid gap-2 sm:grid-cols-2">
            {answer.citations.map((citation) => (
              <CitationCard key={citation.marker} citation={citation} onSeek={onSeek} />
            ))}
          </div>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2 border-t border-white/[.05] pt-3 text-[11px] text-slate-500">
        <Badge dot={answer.grounded ? "bg-signal-lime" : "bg-signal-amber"}>
          {answer.grounded ? "Ancorado nos vídeos" : "Sem evidência"}
        </Badge>
        {answer.model && (
          <span className="font-mono">
            {answer.provider}/{answer.model}
          </span>
        )}
        {answer.latency_ms > 0 && <span>{(answer.latency_ms / 1000).toFixed(1)}s</span>}
        {answer.cost_usd > 0 && <span>{formatCost(answer.cost_usd)}</span>}
      </div>
    </div>
  );
}

function renderWithCitations(
  text: string,
  byMarker: Map<number, Citation>,
  onSeek?: (videoId: number, seconds: number) => void,
) {
  const parts = text.split(/(\[\d{1,2}\])/g);
  return parts.map((part, index) => {
    const match = part.match(/^\[(\d{1,2})\]$/);
    if (!match) return <Fragment key={index}>{part}</Fragment>;

    const marker = Number(match[1]);
    const citation = byMarker.get(marker);
    if (!citation) return <Fragment key={index}>{part}</Fragment>;

    const label = `${citation.video_title} · ${citation.start_label}`;
    const className =
      "mx-0.5 inline-flex h-[18px] min-w-[18px] items-center justify-center rounded-md border border-accent/40 bg-accent/15 px-1 align-[1px] font-mono text-[10px] font-semibold text-accent-soft transition hover:bg-accent/30";

    if (onSeek) {
      return (
        <button
          key={index}
          title={label}
          onClick={() => onSeek(citation.video_id, citation.start)}
          className={className}
        >
          {marker}
        </button>
      );
    }
    return (
      <Link key={index} href={citation.deep_link} title={label} className={className}>
        {marker}
      </Link>
    );
  });
}

function CitationCard({
  citation,
  onSeek,
}: {
  citation: Citation;
  onSeek?: (videoId: number, seconds: number) => void;
}) {
  const body = (
    <div className="panel panel-hover flex gap-3 p-2.5 text-left">
      <div className="relative h-14 w-24 shrink-0 overflow-hidden rounded-lg bg-ink-800">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={api.thumbUrl(citation.video_id)}
          alt=""
          className="h-full w-full object-cover"
          loading="lazy"
        />
        <span className="mono-num absolute bottom-1 right-1 rounded bg-black/80 px-1 text-[9px] text-white">
          {citation.start_label}
        </span>
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          <span className="flex h-4 w-4 items-center justify-center rounded bg-accent/20 font-mono text-[9px] text-accent-soft">
            {citation.marker}
          </span>
          {citation.course && (
            <span className="truncate text-[10px] uppercase tracking-wide text-slate-500">
              {citation.course}
            </span>
          )}
        </div>
        <div className="mt-0.5 line-clamp-1 text-[13px] font-medium text-slate-200">
          {citation.video_title}
        </div>
        <p className="mt-0.5 line-clamp-2 text-[11px] leading-snug text-slate-500">
          {citation.excerpt}
        </p>
      </div>
    </div>
  );

  if (onSeek) {
    return (
      <button onClick={() => onSeek(citation.video_id, citation.start)} className="block w-full">
        {body}
      </button>
    );
  }
  return (
    <Link href={citation.deep_link} className="block">
      {body}
    </Link>
  );
}
