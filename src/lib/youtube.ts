// Parse a YouTube ID from any of the common URL shapes, or accept a bare ID.
export function parseYouTubeId(input: string): string | null {
  const s = input.trim();
  if (/^[\w-]{11}$/.test(s)) return s;
  try {
    const u = new URL(s);
    const host = u.hostname.replace(/^www\./, "").replace(/^m\./, "");
    if (host === "youtu.be") return u.pathname.slice(1).split("/")[0] || null;
    if (host.endsWith("youtube.com")) {
      const v = u.searchParams.get("v");
      if (v) return v;
      const m = u.pathname.match(/\/(embed|live|shorts|v)\/([\w-]{11})/);
      if (m) return m[2];
    }
  } catch {
    /* not a URL */
  }
  return null;
}

export interface OEmbed { title: string; thumbnail_url: string; author_name: string }

// No API key needed. oEmbed does not expose duration; the player fills that in on first load.
export async function fetchOEmbed(youtubeId: string): Promise<OEmbed | null> {
  try {
    const url = `https://www.youtube.com/oembed?url=${encodeURIComponent(
      `https://www.youtube.com/watch?v=${youtubeId}`,
    )}&format=json`;
    const res = await fetch(url);
    if (!res.ok) return null;
    return (await res.json()) as OEmbed;
  } catch {
    return null;
  }
}

export function thumbnailUrl(youtubeId: string, quality: "mq" | "hq" = "mq"): string {
  return `https://i.ytimg.com/vi/${youtubeId}/${quality}default.jpg`;
}

export function watchUrl(youtubeId: string, t?: number): string {
  const base = `https://www.youtube.com/watch?v=${youtubeId}`;
  return t && t > 0 ? `${base}&t=${Math.floor(t)}s` : base;
}
