import { useState } from "react";
import type { Shot, Tag, Video } from "../lib/types";
import { TAG_LABELS, SET_PIECE_TYPES } from "../lib/types";
import { toMatchTime } from "../lib/time";
import { shareUrl, copyText } from "../lib/links";

interface Props {
  tags: Tag[];
  shots: Shot[];
  video: Video | null;
  gameId: string;
  isAdmin: boolean;
  currentTime: number;
  onSeek: (t: number) => void;
  onEdit?: (tag: Tag) => void;
  onDelete?: (tag: Tag) => void;
  onPlace?: (tag: Tag) => void;
  onReview?: (tag: Tag, confirmed: boolean) => void;
  onToast?: (msg: string) => void;
}

const FILTERS: { key: string; label: string; types: string[] | null }[] = [
  { key: "all", label: "All", types: null },
  { key: "goals", label: "Goals", types: ["goal"] },
  { key: "shots", label: "Shots", types: ["shot", "goal", "chance", "save", "penalty"] },
  { key: "setpieces", label: "Set pieces", types: SET_PIECE_TYPES },
  { key: "notes", label: "Notes", types: ["note"] },
];

export default function TagList(p: Props) {
  const [filter, setFilter] = useState("all");
  const [side, setSide] = useState<"all" | "us" | "them">("all");
  const f = FILTERS.find((x) => x.key === filter)!;
  const shotByTag = new Map(p.shots.map((s) => [s.tag_id, s]));
  const list = p.tags
    .filter((t) => !f.types || f.types.includes(t.type))
    .filter((t) => side === "all" || t.team === side)
    .sort((a, b) => a.t_seconds - b.t_seconds);

  const activeId = [...list].reverse().find((t) => t.t_seconds <= p.currentTime + 0.5)?.id ?? null;

  async function copyLink(t: Tag) {
    const ok = await copyText(shareUrl(p.gameId, Math.max(0, t.t_seconds - 3)));
    p.onToast?.(ok ? "Link copied" : "Copy failed");
  }

  return (
    <div>
      <div className="row" style={{ marginBottom: ".5rem", justifyContent: "space-between" }}>
        <div className="row" style={{ gap: ".25rem" }}>
          {FILTERS.map((x) => (
            <button key={x.key} className={`btn sm ${filter === x.key ? "primary" : ""}`} onClick={() => setFilter(x.key)}>{x.label}</button>
          ))}
        </div>
        <select value={side} onChange={(e) => setSide(e.target.value as "all" | "us" | "them")} style={{ width: "auto" }} className="small">
          <option value="all">both</option><option value="us">us</option><option value="them">them</option>
        </select>
      </div>
      {list.length === 0 ? <p className="muted small">No tags yet.</p> : null}
      {list.map((t) => {
        const mt = toMatchTime(p.video, t.t_seconds);
        const shot = shotByTag.get(t.id);
        const machine = t.source === "machine";
        const unreviewed = machine && t.confirmed == null;
        return (
          <div key={t.id} className={`tag-row ${unreviewed ? "machine" : ""} ${activeId === t.id ? "active" : ""}`}>
            <span className="t" onClick={() => p.onSeek(Math.max(0, t.t_seconds - 3))} title="Jump">{mt.label}</span>
            <span className={`badge ${t.team ?? ""}`}>{t.team ?? "—"}</span>
            <span className="lbl">
              <strong>{TAG_LABELS[t.type] ?? t.type}</strong>
              {t.outcome ? <span className="muted"> · {t.outcome}</span> : null}
              {t.label && !t.label.startsWith("machine ") ? <span> · {t.label}</span> : t.label ? <span className="muted"> · {t.label.replace("machine ", "")}</span> : null}
              {shot?.xg != null ? <span className="muted small"> · xG {shot.xg.toFixed(2)}</span> : null}
              {machine ? <span className="badge machine" style={{ marginLeft: 6 }} title="Machine proposal">≈{t.confidence != null ? ` ${Math.round(t.confidence * 100)}%` : ""}{t.confirmed === true ? " ✓" : t.confirmed === false ? " ✗" : ""}</span> : null}
            </span>
            <span className="actions">
              <button className="btn sm" onClick={() => copyLink(t)} title="Copy share link">🔗</button>
              {p.isAdmin && unreviewed ? (
                <>
                  <button className="btn sm ok" onClick={() => p.onReview?.(t, true)} title="Accept">✓</button>
                  <button className="btn sm danger" onClick={() => p.onReview?.(t, false)} title="Reject">✗</button>
                </>
              ) : null}
              {p.isAdmin && (t.type === "shot" || t.type === "goal" || t.type === "penalty" || t.outcome === "shot" || t.outcome === "goal") ? (
                <button className="btn sm" onClick={() => p.onPlace?.(t)} title="Place on pitch">{shot?.pitch_x != null ? "📍" : "＋📍"}</button>
              ) : null}
              {p.isAdmin ? <button className="btn sm" onClick={() => p.onEdit?.(t)} title="Edit">✎</button> : null}
              {p.isAdmin ? <button className="btn sm danger" onClick={() => p.onDelete?.(t)} title="Delete">🗑</button> : null}
            </span>
          </div>
        );
      })}
    </div>
  );
}
