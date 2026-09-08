import type { ShapeSnapshot, Team } from "../lib/types";

// Average-position plot per team from shape snapshots. No identities: positions in a
// snapshot are sorted by x then y so "slot k" is roughly consistent across frames.
export default function ShapePlot({ snapshots, team, period }: { snapshots: ShapeSnapshot[]; team: Team; period: "h1" | "h2" | "full" }) {
  const rows = snapshots.filter((s) => s.team === team && (period === "full" || s.period === period) && s.positions && s.positions.length >= 7);
  if (rows.length < 5) return <p className="small muted">Not enough usable frames for {team} ({rows.length}). Needs ≥5 frames with ≥7 players and a confident pitch fit.</p>;
  const slots = 7;
  const acc = Array.from({ length: slots }, () => ({ x: 0, y: 0, n: 0 }));
  for (const r of rows) {
    const pts = [...r.positions!].sort((a, b) => a.x - b.x || a.y - b.y).slice(0, slots);
    pts.forEach((p, i) => { acc[i].x += p.x; acc[i].y += p.y; acc[i].n += 1; });
  }
  const L = 105, W = 68;
  return (
    <div>
      <svg className="pitch" viewBox={`-2 -2 ${L + 4} ${W + 4}`} role="img" aria-label="Average positions">
        <rect className="grass" x={-2} y={-2} width={L + 4} height={W + 4} rx={2} />
        <g className="line"><rect x={0} y={0} width={L} height={W} /><line x1={L / 2} y1={0} x2={L / 2} y2={W} /><circle cx={L / 2} cy={W / 2} r={9.15} /></g>
        {acc.filter((a) => a.n).map((a, i) => (
          <circle key={i} cx={(a.x / a.n) * L} cy={(a.y / a.n) * W} r={2.4} fill={team === "us" ? "var(--us)" : "var(--them)"} stroke="#fff" strokeWidth={0.5} />
        ))}
      </svg>
      <div className="tiny muted">{rows.length} sampled frames, attacking →. Biased toward zoomed-out moments (goal kicks, build-up, set pieces); true shape needs a fixed wide camera.</div>
    </div>
  );
}
