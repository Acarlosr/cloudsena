"use client";

import Link from "next/link";

import { api } from "@/lib/api";
import {
  STATUS_LABEL,
  STATUS_TONE,
  cx,
  formatDuration,
  isProcessing,
} from "@/lib/format";
import type { Video } from "@/lib/types";
import { Badge, ProgressBar, Spinner } from "./ui";

export default function VideoCard({
  video,
  onToggleFavorite,
  onRetry,
}: {
  video: Video;
  onToggleFavorite?: (v: Video) => void;
  onRetry?: (v: Video) => void;
}) {
  const processing = isProcessing(video.status);
  const watchedRatio = video.duration_seconds
    ? Math.min(1, video.watched_seconds / video.duration_seconds)
    : 0;

  return (
    <div className="panel panel-hover group relative overflow-hidden animate-fade-up">
      <Link href={`/video/${video.id}`} className="block">
        <div className="relative aspect-video overflow-hidden bg-ink-800">
          {video.thumbnail_path ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={api.thumbUrl(video.id)}
              alt={video.title}
              loading="lazy"
              className="h-full w-full object-cover transition duration-500 group-hover:scale-[1.04]"
            />
          ) : (
            <div className="flex h-full items-center justify-center text-2xl text-ink-500">▶</div>
          )}

          <div className="absolute inset-0 bg-gradient-to-t from-ink-950/90 via-transparent to-transparent" />

          {video.duration_seconds > 0 && (
            <span className="mono-num absolute bottom-2 right-2 rounded-md bg-black/75 px-1.5 py-0.5 text-[10px] text-slate-200 backdrop-blur">
              {formatDuration(video.duration_seconds)}
            </span>
          )}

          {video.status !== "ready" && (
            <div className="absolute left-2 top-2">
              <Badge className={cx("backdrop-blur", STATUS_TONE[video.status])}>
                {processing && <Spinner className="h-3 w-3" />}
                {STATUS_LABEL[video.status] || video.status}
              </Badge>
            </div>
          )}

          {onToggleFavorite && (
            <button
              onClick={(e) => {
                e.preventDefault();
                onToggleFavorite(video);
              }}
              className={cx(
                "absolute right-2 top-2 rounded-lg p-1.5 text-sm backdrop-blur transition",
                video.is_favorite
                  ? "bg-signal-amber/20 text-signal-amber"
                  : "bg-black/40 text-slate-400 opacity-0 group-hover:opacity-100 hover:text-white",
              )}
              aria-label="Favoritar"
            >
              {video.is_favorite ? "★" : "☆"}
            </button>
          )}

          {watchedRatio > 0.01 && (
            <div className="absolute inset-x-0 bottom-0 h-[3px] bg-black/50">
              <div
                className="h-full bg-accent"
                style={{ width: `${watchedRatio * 100}%` }}
              />
            </div>
          )}
        </div>

        <div className="p-3.5">
          {video.course && (
            <div className="mb-1 truncate text-[11px] font-medium uppercase tracking-wide text-accent-soft/80">
              {video.course}
            </div>
          )}
          <h3 className="line-clamp-2 text-[13.5px] font-medium leading-snug text-slate-100">
            {video.title}
          </h3>

          {processing && video.stage_progress > 0 && (
            <div className="mt-3">
              <ProgressBar value={video.stage_progress} />
            </div>
          )}

          {video.tags?.length > 0 && video.status === "ready" && (
            <div className="mt-2.5 flex flex-wrap gap-1">
              {video.tags.slice(0, 3).map((tag) => (
                <span
                  key={tag}
                  className="rounded-md bg-white/[.04] px-1.5 py-0.5 text-[10px] text-slate-400"
                >
                  {tag}
                </span>
              ))}
            </div>
          )}
        </div>
      </Link>

      {video.status === "failed" && (
        <div className="border-t border-white/[.06] px-3.5 py-2.5">
          <p className="line-clamp-2 text-[11px] text-signal-rose/90">
            {video.error_message || "Falha no processamento"}
          </p>
          {onRetry && (
            <button
              onClick={() => onRetry(video)}
              className="mt-2 text-[11px] font-medium text-accent-soft hover:underline"
            >
              Tentar novamente
            </button>
          )}
        </div>
      )}
    </div>
  );
}
