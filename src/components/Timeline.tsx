import { useRef } from "react";
import type { Tag, Video } from "../lib/types";
import { fmtClock, seekTime } from "../lib/time";

interface Props {
  video: Video;
  duration: number;
  current: number;
  tags: Tag[];
  onSeek: (t: number) => void;
  activeTagId?: string | null;
}

export default function Timeline({ video, duration, current, tags, onSeek, activeTagId }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const D = Math.max(duration, 1);
  const pct = (t: number) => `${Math.min(100, Math.max(0, (t / D) * 100))}%`;

  function handle(e: React.PointerEvent) {
    const el = ref.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const x = Math.min(Math.max(0, e.clientX - r.left), r.width);
    onSeek((x / r.width) * D);
  }

  const periods: { t: number; l: string }[] = [];
  if (video.kickoff_offset_seconds > 0) periods.push({ t: video.kickoff_offset_seconds, l: "KO" });
  if (video.halftime_offset_seconds != null) periods.push({ t: video.halftime_offset_seconds, l: "HT" });
  if (video.second_half_offset_seconds != null) periods.push({ t: video.second_half_offset_seconds, l: "H2" });
  if (video.fulltime_offset_seconds != null) periods.push({ t: video.fulltime_offset_seconds, l: "FT" });

  return (
    <div className="timeline" ref={ref} onPointerDown={handle} title={fmtClock(current)}>
      <div className="track" />
      <div className="played" style={{ width: pct(current) }} />
      {periods.map((p, i) => {
        // Halftime and second-half kickoff are usually a minute apart: stagger labels that would collide.
        const prev = periods[i - 1];
        const crowded = prev && (p.t - prev.t) / D < 0.04;
        return (
          <span key={p.l}>
            <div className="period" style={{ left: pct(p.t) }} />
            <div className="period-lbl" style={{ left: pct(p.t), top: crowded ? 54 : undefined }}>{p.l}</div>
          </span>
        );
      })}
      {tags.map((t) => (
        <div
          key={t.id}
          className={`marker ${t.team ?? "none"} ${t.type === "goal" ? "goal" : ""} ${t.source === "machine" && !t.confirmed ? "machine" : ""}`}
          style={{ left: pct(t.t_seconds), outline: activeTagId === t.id ? "2px solid #111" : undefined }}
          title={`${fmtClock(t.t_seconds)} ${t.type}${t.team ? " · " + t.team : ""}`}
          onPointerDown={(e) => { e.stopPropagation(); onSeek(seekTime(t.t_seconds)); }}
        />
      ))}
      <div className="playhead" style={{ left: pct(current) }} />
    </div>
  );
}
