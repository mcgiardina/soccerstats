import type { GameSummary } from "../lib/stats";
import Gauge from "./Gauge";

function V({ v, machine, suffix = "" }: { v: number | string | null | undefined; machine?: boolean; suffix?: string }) {
  if (v == null) return <td className="v muted">—</td>;
  return <td className={`v ${machine ? "machine" : ""}`}>{v}{suffix}</td>;
}

export default function StatsPanel({ s, compact }: { s: GameSummary; compact?: boolean }) {
  const posM = (src: string | null) => src === "machine";
  const chip = (src: string | null) => src == null ? null : src === "machine" ? <span className="badge machine">≈ machine</span> : <span className="badge plain">confirmed</span>;
  return (
    <div>
      <div className="gauges">
        <Gauge value={s.us.possession} label="Possession · us" side="us" chip={chip(s.us.possessionSource)} />
        <Gauge value={s.them.possession} label="Possession · them" side="them" chip={chip(s.them.possessionSource)} />
      </div>
      <table className="stat-table">
        <thead><tr><th>Us</th><th></th><th>Them</th></tr></thead>
        <tbody>
          <tr><V v={s.us.goals} /><td className="lbl">Goals</td><V v={s.them.goals} /></tr>
          <tr><V v={s.us.shots} /><td className="lbl">Shots</td><V v={s.them.shots} /></tr>
          <tr><V v={s.us.shotsOnTarget} /><td className="lbl">On target</td><V v={s.them.shotsOnTarget} /></tr>
          <tr><V v={s.us.xg != null ? s.us.xg.toFixed(2) : null} /><td className="lbl">xG*</td><V v={s.them.xg != null ? s.them.xg.toFixed(2) : null} /></tr>
          <tr><V v={s.us.saves} /><td className="lbl">Saves</td><V v={s.them.saves} /></tr>
          {!compact ? (
            <>
              <tr><V v={s.us.chances} /><td className="lbl">Chances</td><V v={s.them.chances} /></tr>
              <tr><V v={s.us.accuracy != null ? Math.round(s.us.accuracy * 100) : null} suffix="%" /><td className="lbl">Shot accuracy</td><V v={s.them.accuracy != null ? Math.round(s.them.accuracy * 100) : null} suffix="%" /></tr>
              <tr><V v={s.us.xgPerShot != null ? s.us.xgPerShot.toFixed(2) : null} /><td className="lbl">xG per shot*</td><V v={s.them.xgPerShot != null ? s.them.xgPerShot.toFixed(2) : null} /></tr>
              <tr><V v={s.us.turnovers} machine={posM(s.us.turnoversSource)} /><td className="lbl">Turnovers</td><V v={s.them.turnovers} machine={posM(s.them.turnoversSource)} /></tr>
              <tr><V v={s.us.corners} /><td className="lbl">Corners</td><V v={s.them.corners} /></tr>
              <tr><V v={s.us.freeKicks} /><td className="lbl">Free kicks</td><V v={s.them.freeKicks} /></tr>
              {(s.us.penalties || s.them.penalties) ? <tr><V v={s.us.penalties} /><td className="lbl">Penalties</td><V v={s.them.penalties} /></tr> : null}
            </>
          ) : null}
        </tbody>
      </table>
      <div className="legend" style={{ marginTop: ".4rem" }}>
        *xG is a pro-calibrated proxy from shot location; compare relatively, don't read as gospel.
        {(s.us.xg != null || s.them.xg != null) ? ` Located ${s.us.xgShotsLocated}/${s.us.shots} of our shots, ${s.them.xgShotsLocated}/${s.them.shots} of theirs.` : ""}
        {(posM(s.us.possessionSource) || posM(s.us.turnoversSource)) ? <span className="m"> ≈ machine estimate, not confirmed.</span> : null}
      </div>
    </div>
  );
}
