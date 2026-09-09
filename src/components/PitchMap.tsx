import { useState } from "react";
import type { PassEvent, Shot, Team } from "../lib/types";

// Draws a full pitch horizontally. "us" attacks the right goal; "them" the left.
// Shot coordinates are stored attack-normalized (x=1 is the attacking goal line),
// so "them" shots are mirrored for display.
interface Props {
  shots: (Shot & { label?: string })[];
  onPick?: (pitchX: number, pitchY: number) => void;
  pickTeam?: Team;
  onShotClick?: (shot: Shot) => void;
  highlightId?: string | null;
  height?: number;
  attackLabel?: string;
  names?: { us: string; them: string };
  /** when given, draw located passes instead of shots */
  passes?: PassEvent[];
}

const L = 105, W = 68; // drawing units (shape only; real dims come from config/game)

export function toDisplay(team: Team | null, x: number, y: number): [number, number] {
  return team === "them" ? [(1 - x) * L, (1 - y) * W] : [x * L, y * W];
}

export default function PitchMap({ shots, onPick, pickTeam = "us", onShotClick, highlightId, attackLabel, names, passes }: Props) {
  const [hover, setHover] = useState<[number, number] | null>(null);

  function coords(e: React.MouseEvent<SVGSVGElement>): [number, number] {
    const svg = e.currentTarget;
    const r = svg.getBoundingClientRect();
    const dx = ((e.clientX - r.left) / r.width) * L;
    const dy = ((e.clientY - r.top) / r.height) * W;
    return [dx, dy];
  }

  function handleClick(e: React.MouseEvent<SVGSVGElement>) {
    if (!onPick) return;
    const [dx, dy] = coords(e);
    let x = dx / L, y = dy / W;
    if (pickTeam === "them") { x = 1 - x; y = 1 - y; }
    onPick(Math.min(1, Math.max(0, x)), Math.min(1, Math.max(0, y)));
  }

  return (
    <svg
      className="pitch"
      viewBox={`-2 -2 ${L + 4} ${W + 4}`}
      onClick={handleClick}
      onMouseMove={onPick ? (e) => setHover(coords(e)) : undefined}
      onMouseLeave={() => setHover(null)}
      style={{ cursor: onPick ? "crosshair" : "default" }}
      role="img"
      aria-label="Shot map"
    >
      <rect className="grass" x={-2} y={-2} width={L + 4} height={W + 4} rx={2} />
      <g className="line">
        <rect x={0} y={0} width={L} height={W} />
        <line x1={L / 2} y1={0} x2={L / 2} y2={W} />
        <circle cx={L / 2} cy={W / 2} r={9.15} />
        {/* penalty areas */}
        <rect x={0} y={W / 2 - 20.16} width={16.5} height={40.32} />
        <rect x={L - 16.5} y={W / 2 - 20.16} width={16.5} height={40.32} />
        <rect x={0} y={W / 2 - 9.16} width={5.5} height={18.32} />
        <rect x={L - 5.5} y={W / 2 - 9.16} width={5.5} height={18.32} />
        <rect x={-2} y={W / 2 - 3.66} width={2} height={7.32} />
        <rect x={L} y={W / 2 - 3.66} width={2} height={7.32} />
        <circle cx={11} cy={W / 2} r={0.5} fill="#fff" />
        <circle cx={L - 11} cy={W / 2} r={0.5} fill="#fff" />
      </g>
      {onPick ? (
        <>
          <text x={pickTeam === "us" ? L - 1 : 1} y={W - 1.5} fontSize={3.2} fill="#fff" textAnchor={pickTeam === "us" ? "end" : "start"} opacity={0.9}>
            {attackLabel ?? (pickTeam === "us" ? "we attack →" : "← they attack")}
          </text>
          {hover ? <circle cx={hover[0]} cy={hover[1]} r={1.6} fill="none" stroke="#fff" strokeWidth={0.4} /> : null}
        </>
      ) : null}
      {passes ? (
        <>
          <defs>
            <marker id="arr-us" viewBox="0 0 6 6" refX="5" refY="3" markerWidth="4" markerHeight="4" orient="auto"><path d="M0 0L6 3L0 6z" fill="var(--us)" /></marker>
            <marker id="arr-them" viewBox="0 0 6 6" refX="5" refY="3" markerWidth="4" markerHeight="4" orient="auto"><path d="M0 0L6 3L0 6z" fill="var(--them)" /></marker>
          </defs>
          {passes.filter((p) => p.from_x != null && p.from_y != null).map((p) => {
            const x1 = p.from_x! * L, y1 = p.from_y! * W;
            const has = p.to_x != null && p.to_y != null;
            const col = p.team === "them" ? "var(--them)" : "var(--us)";
            const op = p.outcome === "completed" ? 0.85 : 0.45;
            return (
              <g key={p.id}>
                {has ? <line x1={x1} y1={y1} x2={p.to_x! * L} y2={p.to_y! * W} stroke={col} strokeWidth={0.7} opacity={op} markerEnd={`url(#arr-${p.team === "them" ? "them" : "us"})`} strokeDasharray={p.outcome === "completed" ? undefined : "1.2 1"} /> : null}
                <circle cx={x1} cy={y1} r={1.1} fill={col} opacity={op}><title>{`${p.team === "us" ? (names?.us ?? "Us") : (names?.them ?? "Them")} · ${p.outcome ?? "?"}`}</title></circle>
              </g>
            );
          })}
        </>
      ) : null}
      {passes ? null : shots.filter((s) => s.pitch_x != null && s.pitch_y != null).map((s) => {
        const [cx, cy] = toDisplay(s.team, s.pitch_x!, s.pitch_y!);
        const r = 1.4 + (s.xg ?? 0.05) * 3.5;
        return (
          <g key={s.id}>
            <circle
              className={`shot ${s.team ?? "us"} ${s.is_goal ? "goal" : ""} ${s.location_source === "machine" ? "machine" : ""}`}
              cx={cx} cy={cy} r={r}
              opacity={highlightId && highlightId !== s.id ? 0.45 : 0.9}
              onClick={(e) => { if (onShotClick) { e.stopPropagation(); onShotClick(s); } }}
            >
              <title>{`${s.team === "us" ? (names?.us ?? "Us") : (names?.them ?? "Them")} · ${s.is_goal ? "GOAL · " : ""}xG ${s.xg ?? "?"}${s.location_source === "machine" ? " (machine)" : ""}`}</title>
            </circle>
          </g>
        );
      })}
    </svg>
  );
}
