import { fmtClock } from "./time";
import type { Tag, Video } from "./types";
import { TAG_LABELS } from "./types";
import { trustedTags } from "./stats";

// YouTube description chapters. Rules: first line must be 0:00, at least 3 chapters,
// each at least 10 seconds long. We build the list, then drop entries that violate the
// 10s rule (keeping the earlier one) so the export always pastes cleanly.
export function buildChapters(video: Video, tags: Tag[]): string {
  const entries: { t: number; label: string }[] = [];
  const ko = video.kickoff_offset_seconds ?? 0;
  if (ko > 0) entries.push({ t: 0, label: "Warmups" });
  entries.push({ t: ko, label: "Kickoff" });
  if (video.halftime_offset_seconds != null) entries.push({ t: video.halftime_offset_seconds, label: "Halftime" });
  if (video.second_half_offset_seconds != null) entries.push({ t: video.second_half_offset_seconds, label: "Second half" });
  if (video.fulltime_offset_seconds != null) entries.push({ t: video.fulltime_offset_seconds, label: "Full time" });

  for (const tag of trustedTags(tags).filter((t) => !t.video_id || t.video_id === video.id)) {
    if (tag.type === "turnover" || tag.type === "throw_in") continue; // too noisy for chapters
    const who = tag.team === "us" ? "us" : tag.team === "them" ? "them" : "";
    const base = TAG_LABELS[tag.type] ?? tag.type;
    const outcome = tag.outcome ? ` (${tag.outcome})` : "";
    const label = tag.type === "note" ? tag.label || "Note" : `${base}${who ? ` — ${who}` : ""}${outcome}${tag.label ? ` · ${tag.label}` : ""}`;
    entries.push({ t: Math.max(0, tag.t_seconds), label });
  }

  entries.sort((a, b) => a.t - b.t);
  const out: { t: number; label: string }[] = [];
  for (const e of entries) {
    const last = out[out.length - 1];
    if (last && e.t - last.t < 10) continue;
    out.push(e);
  }
  if (out.length === 0 || out[0].t !== 0) out.unshift({ t: 0, label: "Start" });
  return out.map((e) => `${fmtClock(e.t)} ${e.label}`).join("\n");
}
