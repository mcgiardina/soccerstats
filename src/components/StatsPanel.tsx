import type { GameSummary } from "../lib/stats";

function V({ v, machine, suffix = "" }: { v: number | string | null | undefined; machine?: boolean; suffix?: string }) {
  if (v == null) return <td className="v muted">—</td>;
  return <td className={`v ${machine ? "machine" : ""}`}>{v}{suffix}</td>;
}

export default function StatsPanel({ s, compact }: { s: GameSummary; compact?: boolean }) {
  const posM = (src: string | null) => src === "machine";
  return (
    <div>
      <table className="stat-table">
        <thead><tr><th>Us</th><th></th><th>Them</th></tr></thead>
        <tbody>
          <tr><V v={s.us.goals} /><td className="lbl">Goals</td><V v={s.them.goals} /></tr>
          <tr><V v={s.us.possession != null ? Math.round(s.us.possession) : null} machine={posM(s.us.possessionSource)} suffix="%" /><td className="lbl">Possession</td><V v={s.them.possession != null ? Math.round(s.them.possession) : null} machine={posM(s.them.possessionSource)} suffix="%" /></tr>
          <tr><V v={s.us.shots} /><td className="lbl">Shots</td><V v={s.them.shots} /></tr>
          <tr><V v={s.us.shotsOnTarget} /><td className="lbl">On target</td><V v={s.them.shotsOnTarget} /></tr>
          <tr><V v={s.us.xg != null ? s.us.xg.toFixed(2) : null} /><td className="lbl">xG*</td><V v={s.them.xg != null ? s.them.xg.toFixed(2) : null} /></tr>
          {!compact ? (
            <>
              <tr><V v={s.us.turnovers} machine={posM(s.us.turnoversSource)} /><td className="lbl">Turnovers</td><V v={s.them.turnovers} machine={posM(s.them.turnoversSource)} /></tr>
              <tr><V v={s.us.corners} /><td className="lbl">Corners</td><V v={s.them.corners} /></tr>
              <tr><V v={s.us.freeKicks} /><td className="lbl">Free kicks</td><V v={s.them.freeKicks} /></tr>
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
