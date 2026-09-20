import { forwardRef, useEffect, useImperativeHandle, useRef, useState, type ReactNode } from "react";
import YouTubePlayer, { toggleFullscreen, type PlayerHandle } from "./YouTubePlayer";
import type { Video } from "../lib/types";
import { fetchBallerCam } from "../lib/sources";

interface Props {
  video: Video;
  startAt?: number;
  onTime?: (t: number) => void;
  onDuration?: (d: number) => void;
  onPlaying?: (playing: boolean) => void;
  /** the app's controls, drawn over the bottom of the video; the host's own bar is then hidden */
  children?: ReactNode;
}

/** One player for every source: YouTube through its iframe API, anything else (BallerCam's HLS
 *  stream, a direct mp4) through a plain <video>, with hls.js where the browser has no native HLS. */
const VideoPlayer = forwardRef<PlayerHandle, Props>(function VideoPlayer({ video, ...rest }, ref) {
  if (video.youtube_id) return <YouTubePlayer ref={ref} youtubeId={video.youtube_id} {...rest} />;
  return <StreamPlayer ref={ref} video={video} {...rest} />;
});
export default VideoPlayer;

const StreamPlayer = forwardRef<PlayerHandle, Props>(function StreamPlayer({ video, startAt, onTime, onDuration, onPlaying, children }, ref) {
  const el = useRef<HTMLVideoElement>(null);
  const [src, setSrc] = useState(video.stream_url);
  const [err, setErr] = useState<string | null>(null);
  const retried = useRef(false);
  const onTimeRef = useRef(onTime); const onDurRef = useRef(onDuration);
  onTimeRef.current = onTime; onDurRef.current = onDuration;
  const onPlayingRef = useRef(onPlaying); onPlayingRef.current = onPlaying;

  useEffect(() => { setSrc(video.stream_url); retried.current = false; setErr(null); }, [video.id, video.stream_url]);

  useEffect(() => {
    const v = el.current; if (!v || !src) return;
    let hls: { destroy(): void } | null = null, cancelled = false;
    // A stored stream address can go stale; BallerCam will give the current one for the same game.
    const fail = async () => {
      if (!retried.current && video.provider === "ballercam" && video.provider_ref) {
        retried.current = true;
        try { const s = await fetchBallerCam(video.provider_ref); const fresh = s.h264VideoUrl || s.videoUrl; if (fresh && fresh !== src && !cancelled) { setSrc(fresh); return; } } catch { /* fall through */ }
      }
      if (!cancelled) setErr("This video couldn't be loaded from its host.");
    };
    const isHls = /\.m3u8($|\?)/i.test(src);
    const native = () => {
      v.src = src;
      if (startAt && startAt > 0) v.addEventListener("loadedmetadata", () => { v.currentTime = startAt; }, { once: true });
    };
    let usingHlsJs = false;
    if (isHls) {
      // hls.js wherever the browser has Media Source Extensions. Desktop Chrome now also answers
      // "maybe" for native HLS, but its native path never started this stream; the native path is
      // for iPhones, which have no MSE.
      usingHlsJs = true;
      import("hls.js").then(({ default: Hls }) => {
        if (cancelled) return;
        if (!Hls.isSupported()) {
          usingHlsJs = false;
          if (v.canPlayType("application/vnd.apple.mpegurl")) native(); else setErr("This browser can't play this stream.");
          return;
        }
        const h = new Hls({ startPosition: startAt && startAt > 0 ? startAt : -1 });
        h.on(Hls.Events.ERROR, (_e, data) => { if (data.fatal) fail(); });
        h.loadSource(src); h.attachMedia(v); hls = h;
      });
    } else native();
    const time = () => onTimeRef.current?.(v.currentTime);
    const dur = () => { if (Number.isFinite(v.duration) && v.duration > 0) onDurRef.current?.(v.duration); };
    const bad = () => { if (!usingHlsJs) fail(); };
    const play = () => onPlayingRef.current?.(true), pause = () => onPlayingRef.current?.(false);
    v.addEventListener("timeupdate", time); v.addEventListener("seeking", time); v.addEventListener("durationchange", dur); v.addEventListener("error", bad);
    v.addEventListener("play", play); v.addEventListener("pause", pause);
    return () => {
      cancelled = true; hls?.destroy();
      v.removeEventListener("timeupdate", time); v.removeEventListener("seeking", time); v.removeEventListener("durationchange", dur); v.removeEventListener("error", bad);
      v.removeEventListener("play", play); v.removeEventListener("pause", pause);
      v.removeAttribute("src"); v.load();
    };
    // startAt is read once, like the YouTube player.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [src, video.provider, video.provider_ref]);

  useImperativeHandle(ref, () => ({
    seek(t, play = true) { const v = el.current; if (!v) return; v.currentTime = Math.max(0, t); if (play) void v.play().catch(() => {}); onTimeRef.current?.(Math.max(0, t)); },
    currentTime() { return el.current?.currentTime ?? 0; },
    togglePlay() { const v = el.current; if (!v) return; if (v.paused) void v.play().catch(() => {}); else v.pause(); },
    nudge(delta) { const v = el.current; if (v) v.currentTime = Math.max(0, v.currentTime + delta); },
    toggleMute() { const v = el.current; if (!v) return false; v.muted = !v.muted; return v.muted; },
    fullscreen() { toggleFullscreen(el.current?.parentElement ?? null, el.current); },
  }));

  return (
    <div className="player-wrap">
      <video ref={el} controls={!children} playsInline preload="metadata" onClick={children ? () => { const v = el.current; if (v) { if (v.paused) void v.play().catch(() => {}); else v.pause(); } } : undefined} />
      {children}
      {err ? <div className="player-err">{err}{video.source_url ? <> <a href={video.source_url} target="_blank" rel="noreferrer">Open it there ↗</a></> : null}</div> : null}
    </div>
  );
});
