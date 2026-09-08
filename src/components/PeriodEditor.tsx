import type { Video } from "../lib/types";
import { fmtClock } from "../lib/time";

interface Props {
  video: Video;
  currentTime: number;
  onChange: (patch: Partial<Video>) => void;
  onSeek: (t: number) => void;
}

const FIELDS: { k: keyof Video; label: string }[] = [
  { k: "kickoff_offset_seconds", label: "Kickoff" },
  { k: "halftime_offset_seconds", label: "Halftime" },
  { k: "second_half_offset_seconds", label: "2nd half kickoff" },
  { k: "fulltime_offset_seconds", label: "Full time" },
];

export default function PeriodEditor({ video, currentTime, onChange, onSeek }: Props) {
  return (
    <div>
      <p className="small muted">Scrub the video to each moment, then press <em>Set</em>. All times in the app become match time.</p>
      <div className="period-editor">
        {FIELDS.map((f) => {
          const v = video[f.k] as number | null;
          return (
            <div key={f.k} style={{ display: "contents" }}>
              <span className="k">{f.label}: <a href="#" className="mono" onClick={(e) => { e.preventDefault(); if (v != null) onSeek(v); }}>{v != null ? fmtClock(v) : "—"}</a></span>
              <button className="btn sm" onClick={() => onChange({ [f.k]: Math.round(currentTime) } as Partial<Video>)}>Set {fmtClock(currentTime)}</button>
              <button className="btn sm" disabled={v == null} onClick={() => onChange({ [f.k]: f.k === "kickoff_offset_seconds" ? 0 : null } as Partial<Video>)}>clear</button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
