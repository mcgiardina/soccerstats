import type { Video } from "./types";
import { CONFIG } from "../config";

/** Where playback should start for a tag: a little before the moment itself. */
export function seekTime(tagSeconds: number): number {
  return Math.max(0, tagSeconds - CONFIG.leadInSeconds);
}

// Video seconds -> "m:ss" or "h:mm:ss" (YouTube chapter format).
export function fmtClock(total: number): string {
  const s = Math.max(0, Math.floor(total));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const mm = h > 0 ? String(m).padStart(2, "0") : String(m);
  return `${h > 0 ? h + ":" : ""}${mm}:${String(sec).padStart(2, "0")}`;
}

export type MatchPhase = "pre" | "h1" | "ht" | "h2" | "ft";

export interface MatchTime {
  phase: MatchPhase;
  /** Continuous match clock in seconds (halftime break removed). */
  seconds: number;
  label: string;
}

// Convert a raw video timestamp to match time using the video's period offsets.
// Halves are whatever length they actually were; the clock keeps running through H2.
export function toMatchTime(video: Video | null | undefined, t: number): MatchTime {
  if (!video) return { phase: "h1", seconds: t, label: fmtClock(t) };
  const ko = video.kickoff_offset_seconds ?? 0;
  const ht = video.halftime_offset_seconds;
  const sh = video.second_half_offset_seconds;
  const ft = video.fulltime_offset_seconds;
  const h1Len = ht != null ? Math.max(0, ht - ko) : null;

  if (t < ko) return { phase: "pre", seconds: 0, label: "Pre" };
  if (ht != null && t >= ht && (sh == null || t < sh)) {
    return { phase: "ht", seconds: h1Len ?? t - ko, label: "HT" };
  }
  if (sh != null && t >= sh) {
    const secs = (h1Len ?? 0) + (t - sh);
    if (ft != null && t >= ft) return { phase: "ft", seconds: (h1Len ?? 0) + (ft - sh), label: "FT" };
    return { phase: "h2", seconds: secs, label: `H2 ${fmtClock(secs)}` };
  }
  return { phase: "h1", seconds: t - ko, label: `H1 ${fmtClock(t - ko)}` };
}

export function periodOf(video: Video | null | undefined, t: number): "h1" | "h2" {
  const mt = toMatchTime(video, t);
  return mt.phase === "h2" || mt.phase === "ft" ? "h2" : "h1";
}

export function fmtDate(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

export function fmtDateShort(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}
