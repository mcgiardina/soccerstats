import type { GameSummary } from "../lib/stats";
import Gauge from "./Gauge";
import { useShow, useTeamNames } from "../lib/team";

function V({ v, machine, suffix = "" }: { v: number | string | null | undefined; machine?: boolean; suffix?: string }) {
  if (v == null) return <td className="v muted">—</td>;
  return <td className={`v ${machine ? "machine" : ""}`}>{v}{suffix}</td>;
}

/** territory: share of playing time each side was "on top" in the match flow (wide camera), shown
 *  only when there is no possession figure. */
export default function StatsPanel({ s, compact, opponent, territory }: { s: GameSummary; compact?: boolean; opponent?: string | null; territory?: { us: number; them: number } | null }) {
  const show = useShow();
  const names = useTeamNames(opponent);
  const posM = (src: string | null) => src === "machine";
  const chip = (src: string | null) => src == null ? null : src === "machine" ? <span className="badge machine">≈ Machine</span> : <span className="badge plain">Confirmed</span>;
  return (
    <div>
      {show("possession") && (s.us.possession != null || s.them.possession != null) ? <>
        <h3 className="gauge-title">Possession</h3>
        <div className="gauges">
          <Gauge value={s.us.possession} label={names.us} side="us" chip={chip(s.us.possessionSource)} />
          <Gauge value={s.them.possession} label={names.them} side="them" chip={chip(s.them.possessionSource)} />
        </div>
      </> : show("possession") && territory ? <>
        <h3 className="gauge-title">Time on top <span className="muted">· share of play spent pushing the other team back</span></h3>
        <div className="gauges">
          <Gauge value={territory.us} label={names.us} side="us" chip={<span className="badge machine">≈ Machine</span>} />
          <Gauge value={territory.them} label={names.them} side="them" chip={<span className="badge machine">≈ Machine</span>} />
        </div>
      </> : null}
      <table className="stat-table">
        <thead><tr><th>{names.us}</th><th></th><th>{names.them}</th></tr></thead>
        <tbody>
          <tr><V v={s.us.goals} /><td className="lbl">Goals</td><V v={s.them.goals} /></tr>
          <tr><V v={s.us.shots} /><td className="lbl">Shots</td><V v={s.them.shots} /></tr>
          <tr><V v={s.us.shotsOnTarget} /><td className="lbl">On target</td><V v={s.them.shotsOnTarget} /></tr>
          {show("xg") ? <tr><V v={s.us.xg != null ? s.us.xg.toFixed(2) : null} /><td className="lbl">xG*</td><V v={s.them.xg != null ? s.them.xg.toFixed(2) : null} /></tr> : null}
          {show("saves") ? <tr><V v={s.us.saves} /><td className="lbl">Saves</td><V v={s.them.saves} /></tr> : null}
          {!compact ? (
            <>
              <tr><V v={s.us.chances} /><td className="lbl">Chances</td><V v={s.them.chances} /></tr>
              {show("accuracy") ? <tr><V v={s.us.accuracy != null ? Math.round(s.us.accuracy * 100) : null} suffix="%" /><td className="lbl">Shot accuracy</td><V v={s.them.accuracy != null ? Math.round(s.them.accuracy * 100) : null} suffix="%" /></tr> : null}
              {show("xg") ? <tr><V v={s.us.xgPerShot != null ? s.us.xgPerShot.toFixed(2) : null} /><td className="lbl">xG per shot*</td><V v={s.them.xgPerShot != null ? s.them.xgPerShot.toFixed(2) : null} /></tr> : null}
              {show("passes") && (s.us.passes != null || s.them.passes != null) ? <>
                <tr><V v={s.us.passes} machine /><td className="lbl">Passes</td><V v={s.them.passes} machine /></tr>
                <tr><V v={s.us.passesCompleted} machine /><td className="lbl">Completed</td><V v={s.them.passesCompleted} machine /></tr>
                <tr><V v={s.us.passAccuracy != null ? Math.round(s.us.passAccuracy * 100) : null} machine suffix="%" /><td className="lbl">Pass accuracy</td><V v={s.them.passAccuracy != null ? Math.round(s.them.passAccuracy * 100) : null} machine suffix="%" /></tr>
              </> : null}
              {show("turnovers") && (s.us.turnovers != null || s.them.turnovers != null) ? <tr><V v={s.us.turnovers} machine={posM(s.us.turnoversSource)} /><td className="lbl">Turnovers</td><V v={s.them.turnovers} machine={posM(s.them.turnoversSource)} /></tr> : null}
              {show("setpieces") ? <>
                <tr><V v={s.us.corners} /><td className="lbl">Corners</td><V v={s.them.corners} /></tr>
                <tr><V v={s.us.freeKicks} /><td className="lbl">Free kicks</td><V v={s.them.freeKicks} /></tr>
                {(s.us.penalties || s.them.penalties) ? <tr><V v={s.us.penalties} /><td className="lbl">Penalties</td><V v={s.them.penalties} /></tr> : null}
              </> : null}
              {(s.us.fouls || s.them.fouls) ? <tr><V v={s.us.fouls} /><td className="lbl">Fouls</td><V v={s.them.fouls} /></tr> : null}
              {(s.us.yellowCards || s.them.yellowCards) ? <tr><V v={s.us.yellowCards} /><td className="lbl">Yellow cards</td><V v={s.them.yellowCards} /></tr> : null}
              {(s.us.redCards || s.them.redCards) ? <tr><V v={s.us.redCards} /><td className="lbl">Red cards</td><V v={s.them.redCards} /></tr> : null}
            </>
          ) : null}
        </tbody>
      </table>
      <div className="legend" style={{ marginTop: ".4rem" }}>
        *xG is a pro-calibrated proxy from shot location; compare relatively, don't read as gospel.
        {(s.us.xg != null || s.them.xg != null) ? ` Located ${s.us.xgShotsLocated}/${s.us.shots} of our shots, ${s.them.xgShotsLocated}/${s.them.shots} of theirs.` : ""}
        {(posM(s.us.possessionSource) || posM(s.us.turnoversSource)) ? <span className="m"> ≈ machine estimate, not confirmed.</span> : null}
        {s.us.passes != null && s.us.ballCoverage != null ? <span> Passes are counted only while the ball was tracked ({Math.round(s.us.ballCoverage * 100)}% of the game), so they're lower bounds.</span> : null}
      </div>
    </div>
  );
}
