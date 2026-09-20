import { forwardRef, useEffect, useImperativeHandle, useRef, type ReactNode } from "react";

// Minimal typing for the YouTube IFrame Player API.
interface YTPlayer {
  seekTo(seconds: number, allowSeekAhead: boolean): void;
  getCurrentTime(): number;
  getDuration(): number;
  playVideo(): void;
  pauseVideo(): void;
  getPlayerState(): number;
  mute(): void;
  unMute(): void;
  isMuted(): boolean;
  destroy(): void;
}
interface YTNamespace {
  Player: new (el: HTMLElement, opts: Record<string, unknown>) => YTPlayer;
  PlayerState: { PLAYING: number };
}
declare global {
  interface Window { YT?: YTNamespace; onYouTubeIframeAPIReady?: () => void }
}

let apiPromise: Promise<YTNamespace> | null = null;
function loadApi(): Promise<YTNamespace> {
  if (window.YT?.Player) return Promise.resolve(window.YT);
  if (!apiPromise) {
    apiPromise = new Promise((resolve) => {
      const prev = window.onYouTubeIframeAPIReady;
      window.onYouTubeIframeAPIReady = () => { prev?.(); resolve(window.YT!); };
      const s = document.createElement("script");
      s.src = "https://www.youtube.com/iframe_api";
      document.head.appendChild(s);
    });
  }
  return apiPromise;
}

export interface PlayerHandle {
  seek(t: number, play?: boolean): void;
  currentTime(): number;
  togglePlay(): void;
  nudge(delta: number): void;
  /** returns the new muted state */
  toggleMute(): boolean;
  fullscreen(): void;
}

/** Full screen for the whole player box, so the app's own controls come along. */
export function toggleFullscreen(box: HTMLElement | null, video?: HTMLVideoElement | null) {
  if (!box) return;
  if (document.fullscreenElement) { void document.exitFullscreen(); return; }
  if (box.requestFullscreen) void box.requestFullscreen().catch(() => {});
  else (video as unknown as { webkitEnterFullscreen?: () => void } | null)?.webkitEnterFullscreen?.();   // iPhone
}

interface Props {
  youtubeId: string;
  startAt?: number;
  onTime?: (t: number) => void;
  onDuration?: (d: number) => void;
  onPlaying?: (playing: boolean) => void;
  /** the app's controls, drawn over the bottom of the video; YouTube's own bar is then hidden */
  children?: ReactNode;
}

const YouTubePlayer = forwardRef<PlayerHandle, Props>(function YouTubePlayer(
  { youtubeId, startAt, onTime, onDuration, onPlaying, children }, ref,
) {
  const hostRef = useRef<HTMLDivElement>(null);
  const playerRef = useRef<YTPlayer | null>(null);
  const readyRef = useRef(false);
  const pendingSeek = useRef<number | null>(startAt ?? null);
  const onTimeRef = useRef(onTime);
  const onDurRef = useRef(onDuration);
  onTimeRef.current = onTime;
  onDurRef.current = onDuration;
  const onPlayingRef = useRef(onPlaying);
  onPlayingRef.current = onPlaying;
  const chromeless = !!children;

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;
    const host = hostRef.current!;
    const mount = document.createElement("div");
    host.appendChild(mount);

    loadApi().then((YT) => {
      if (cancelled) return;
      playerRef.current = new YT.Player(mount, {
        videoId: youtubeId,
        playerVars: { rel: 0, modestbranding: 1, playsinline: 1, controls: chromeless ? 0 : 1, fs: chromeless ? 0 : 1, start: startAt ? Math.floor(startAt) : undefined },
        events: {
          onStateChange: (e: { data: number }) => onPlayingRef.current?.(e.data === 1 || e.data === 3),
          onReady: () => {
            readyRef.current = true;
            const d = playerRef.current?.getDuration() ?? 0;
            if (d > 0) onDurRef.current?.(d);
            if (pendingSeek.current != null) {
              playerRef.current?.seekTo(pendingSeek.current, true);
              pendingSeek.current = null;
            }
            timer = window.setInterval(() => {
              const p = playerRef.current;
              if (!p) return;
              try {
                onTimeRef.current?.(p.getCurrentTime());
                const dd = p.getDuration();
                if (dd > 0) onDurRef.current?.(dd);
              } catch { /* player torn down */ }
            }, 250);
          },
        },
      });
    });

    return () => {
      cancelled = true;
      if (timer) clearInterval(timer);
      readyRef.current = false;
      try { playerRef.current?.destroy(); } catch { /* ignore */ }
      playerRef.current = null;
      if (mount.parentNode === host) host.removeChild(mount);
    };
    // startAt is intentionally read once; deep-link seeks happen via pendingSeek.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [youtubeId]);

  useImperativeHandle(ref, () => ({
    seek(t, play = true) {
      const p = playerRef.current;
      if (!p || !readyRef.current) { pendingSeek.current = t; return; }
      p.seekTo(Math.max(0, t), true);
      if (play) p.playVideo();
      onTimeRef.current?.(Math.max(0, t));
    },
    currentTime() {
      try { return playerRef.current?.getCurrentTime() ?? 0; } catch { return 0; }
    },
    togglePlay() {
      const p = playerRef.current;
      if (!p) return;
      if (p.getPlayerState() === window.YT?.PlayerState.PLAYING) p.pauseVideo(); else p.playVideo();
    },
    nudge(delta) {
      const p = playerRef.current;
      if (!p) return;
      p.seekTo(Math.max(0, p.getCurrentTime() + delta), true);
    },
    toggleMute() {
      const p = playerRef.current;
      if (!p) return false;
      if (p.isMuted()) { p.unMute(); return false; }
      p.mute(); return true;
    },
    fullscreen() { toggleFullscreen(hostRef.current?.parentElement ?? null); },
  }));

  return <div className="player-wrap"><div ref={hostRef} />{children}</div>;
});

export default YouTubePlayer;
