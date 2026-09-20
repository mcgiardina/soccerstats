import { fetchOEmbed, parseYouTubeId, thumbnailUrl, watchUrl } from "./youtube";
import type { Video } from "./types";

export type Provider = NonNullable<Video["provider"]>;

export const PROVIDERS: Record<Provider, { label: string }> = {
  youtube: { label: "YouTube" },
  ballercam: { label: "BallerCam" },
  veo: { label: "Veo" },
  trace: { label: "Trace" },
  xbot: { label: "XbotGo" },
  file: { label: "Video file" },
};

/** What a pasted link turned out to be. Only the video fields go in the database; `game` is a
 *  one-time offer to prefill the game from what the camera's scoreboard knew. */
export interface ResolvedSource {
  video: Pick<Video, "provider" | "youtube_id" | "provider_ref" | "source_url" | "stream_url" | "raw_url" | "title"> & { kickoff_offset_seconds?: number };
  thumbnail: string | null;
  game?: {
    playedOn: string | null;
    teams: { name: string; color: string | null; score: number | null }[];
    goals: { t: number; teamName: string }[];   // video seconds, as tapped on the scoreboard (late by ~20-40 s)
  };
  note?: string;
}

const CSS_COLORS: Record<string, string> = {
  white: "#ffffff", black: "#111111", red: "#d62828", blue: "#1d4ed8", navy: "#1a2d50", green: "#15803d", yellow: "#facc15",
  orange: "#f97316", purple: "#7e22ce", pink: "#ec4899", gray: "#6b7280", grey: "#6b7280", maroon: "#7f1d1d", gold: "#d4a017",
  teal: "#0f766e", lightblue: "#60a5fa", skyblue: "#38bdf8",
};
const DIRECT = /\.(mp4|m4v|webm|mov|m3u8)$/i;

function host(u: URL) { return u.hostname.replace(/^www\./, ""); }

export function detectProvider(input: string): Provider | null {
  if (parseYouTubeId(input)) return "youtube";
  let u: URL;
  try { u = new URL(input.trim()); } catch { return null; }
  const h = host(u);
  if (h === "blrcam.co" || h.endsWith("ballercam.com")) return "ballercam";
  if (h.endsWith("veo.co")) return "veo";
  if (h.endsWith("traceup.com")) return "trace";
  if (h.endsWith("xbotgo.com")) return "xbot";
  if (DIRECT.test(u.pathname)) return "file";
  return null;
}

async function ballercamSlug(u: URL): Promise<string> {
  if (host(u) === "blrcam.co") {
    const r = await fetch(`/api/resolve-link?u=${encodeURIComponent(`${u.origin}${u.pathname}`)}`);
    if (!r.ok) throw new Error("Couldn't follow that short link. Open it, then paste the long app.ballercam.com address instead.");
    u = new URL(((await r.json()) as { url: string }).url);
  }
  const m = u.pathname.match(/\/streams\/([\w-]+)/);
  if (!m) throw new Error("That BallerCam link isn't a game. Use the game's Share link.");
  return m[1];
}

interface BcStream {
  title?: string; slug: string; startedAt?: string; shareUrl?: string;
  videoUrl?: string; h264VideoUrl?: string; rawVideoUrl?: string;
  teams?: { name: string; score?: number | null; color?: { css_name?: string } | null }[];
  periods?: { corrected_milliseconds_from_start?: number | null; milliseconds_from_start?: number | null }[];
  scoringPlays?: { corrected_milliseconds_from_start?: number | null; milliseconds_from_start?: number | null; team_name?: string }[];
}

/** BallerCam's share page reads this public JSON; it needs no login for a game shared by link. */
export async function fetchBallerCam(slug: string): Promise<BcStream> {
  const r = await fetch(`https://www.ballertv.com/api/ballercam_web/streams/${encodeURIComponent(slug)}`);
  if (!r.ok) throw new Error(r.status === 404 ? "BallerCam doesn't know that game (is sharing turned on?)." : `BallerCam answered ${r.status}.`);
  return (await r.json()) as BcStream;
}

export async function resolveSource(input: string): Promise<ResolvedSource> {
  const provider = detectProvider(input);
  if (!provider) throw new Error("Not a link I recognise. Paste a YouTube or BallerCam share link, or a direct .mp4 / .m3u8 address.");
  const blank = { youtube_id: null, provider_ref: null, stream_url: null, raw_url: null, title: null };
  if (provider === "youtube") {
    const id = parseYouTubeId(input)!; const o = await fetchOEmbed(id);
    return { video: { ...blank, provider, youtube_id: id, source_url: watchUrl(id), title: o?.title ?? null }, thumbnail: thumbnailUrl(id, "hq"), note: o ? undefined : "YouTube didn't return details (private video?). You can still save it." };
  }
  const u = new URL(input.trim());
  if (provider === "ballercam") {
    const s = await fetchBallerCam(await ballercamSlug(u));
    const stream = s.h264VideoUrl || s.videoUrl;
    if (!stream) throw new Error("BallerCam hasn't finished processing that game yet.");
    const ms = (p: { corrected_milliseconds_from_start?: number | null; milliseconds_from_start?: number | null }) => (p.corrected_milliseconds_from_start ?? p.milliseconds_from_start ?? 0) / 1000;
    const starts = (s.periods ?? []).map(ms).filter((t) => t > 0).sort((a, b) => a - b);
    return {
      video: { ...blank, provider, provider_ref: s.slug, source_url: s.shareUrl || `https://app.ballercam.com/streams/${s.slug}`, stream_url: stream, raw_url: s.rawVideoUrl ?? null, title: s.title ?? null, kickoff_offset_seconds: starts.length ? Math.round(starts[0]) : undefined },
      thumbnail: null,
      game: {
        playedOn: s.startedAt ? new Date(s.startedAt).toLocaleDateString("en-CA") : null,
        teams: (s.teams ?? []).map((t) => ({ name: t.name, score: t.score ?? null, color: CSS_COLORS[(t.color?.css_name ?? "").toLowerCase().replace(/[\s_-]/g, "")] ?? null })),
        goals: (s.scoringPlays ?? []).map((p) => ({ t: ms(p), teamName: p.team_name ?? "" })).filter((g) => g.t > 0),
      },
    };
  }
  if (provider === "file") return { video: { ...blank, provider, source_url: u.href, stream_url: u.href, title: decodeURIComponent(u.pathname.split("/").pop() ?? "") || null }, thumbnail: null };
  throw new Error(`${PROVIDERS[provider].label} links aren't supported yet (no one has tested a real one). For now upload the download to YouTube, or paste a direct .mp4 / .m3u8 address if you have one.`);
}

export function openUrl(v: Video, t?: number): string | null {
  if (v.youtube_id) return watchUrl(v.youtube_id, t);
  return v.source_url ?? null;
}
export function providerLabel(v: Pick<Video, "provider">): string { return PROVIDERS[(v.provider ?? "youtube") as Provider]?.label ?? "Video"; }
