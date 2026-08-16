"use client";

/**
 * Player pra vídeos importados de playlist do YouTube (video.youtube_id
 * setado). Vídeos assim não têm arquivo local — não há o que servir por
 * Range request — então em vez do <video> nativo usado pros cursos baixados,
 * embutimos o player oficial do YouTube via IFrame API.
 *
 * A API expõe seekTo/getCurrentTime por postMessage entre janelas; carregamos
 * o script uma única vez (é comum a mesma página ter só um player, mas o
 * carregamento é idempotente mesmo assim) e expomos seek()/getCurrentTime()
 * pro componente pai via ref — o mesmo contrato que o <video> nativo oferece
 * através de `videoRef.current.currentTime`, pra VideoWorkspace não precisar
 * saber qual dos dois players está montado.
 */

import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";

declare global {
  interface Window {
    YT: any;
    onYouTubeIframeAPIReady?: () => void;
  }
}

let apiLoadPromise: Promise<void> | null = null;

function loadYouTubeApi(): Promise<void> {
  if (window.YT?.Player) return Promise.resolve();
  if (apiLoadPromise) return apiLoadPromise;

  apiLoadPromise = new Promise((resolve) => {
    const previous = window.onYouTubeIframeAPIReady;
    window.onYouTubeIframeAPIReady = () => {
      previous?.();
      resolve();
    };
    const script = document.createElement("script");
    script.src = "https://www.youtube.com/iframe_api";
    document.head.appendChild(script);
  });
  return apiLoadPromise;
}

export interface YouTubePlayerHandle {
  seek: (seconds: number) => void;
  getCurrentTime: () => number;
}

const YouTubePlayer = forwardRef<
  YouTubePlayerHandle,
  {
    youtubeId: string;
    startSeconds?: number;
    onTimeUpdate?: (seconds: number) => void;
  }
>(({ youtubeId, startSeconds, onTimeUpdate }, ref) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const playerRef = useRef<any>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useImperativeHandle(ref, () => ({
    seek: (seconds: number) => {
      playerRef.current?.seekTo?.(seconds, true);
      playerRef.current?.playVideo?.();
    },
    getCurrentTime: () => playerRef.current?.getCurrentTime?.() ?? 0,
  }));

  useEffect(() => {
    let cancelled = false;

    loadYouTubeApi().then(() => {
      if (cancelled || !containerRef.current) return;
      playerRef.current = new window.YT.Player(containerRef.current, {
        videoId: youtubeId,
        playerVars: {
          start: startSeconds ? Math.floor(startSeconds) : undefined,
          rel: 0,
          modestbranding: 1,
        },
        events: {
          onStateChange: (e: any) => {
            // 1 = tocando. Só faz sentido perguntar o tempo atual enquanto
            // toca — parado/pausado não muda, e poupamos chamadas de postMessage.
            if (pollRef.current) {
              clearInterval(pollRef.current);
              pollRef.current = null;
            }
            if (e.data === 1) {
              pollRef.current = setInterval(() => {
                const t = playerRef.current?.getCurrentTime?.();
                if (typeof t === "number") onTimeUpdate?.(t);
              }, 1000);
            }
          },
        },
      });
    });

    return () => {
      cancelled = true;
      if (pollRef.current) clearInterval(pollRef.current);
      playerRef.current?.destroy?.();
      playerRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [youtubeId]);

  return (
    <div className="aspect-video w-full overflow-hidden bg-black">
      <div ref={containerRef} className="h-full w-full" />
    </div>
  );
});

YouTubePlayer.displayName = "YouTubePlayer";

export default YouTubePlayer;
