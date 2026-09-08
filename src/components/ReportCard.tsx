import type { GameBundle } from "../lib/types";
import { CONFIG } from "../config";
import { summarizeGame, trustedTags, isGoalTag } from "../lib/stats";
import { toMatchTime, fmtDate } from "../lib/time";
import PitchMap from "./PitchMap";
import StatsPanel from "./StatsPanel";
import Momentum from "./Momentum";

export default function ReportCard({ b }: { b: GameBundle }) {
  const video = b.videos[0] ?? null;
  const s = summarizeGame(b.game, video, b.tags, b.shots, b.teamStats);
  const goals = trustedTags(b.tags).filter(isGoalTag).sort((a, c) => a.t_seconds - c.t_seconds);
  const usFirst = b.game.home_away !== "away";
  const res = s.us.goals > s.them.goals ? "W" : s.us.goals < s.them.goals ? "L" : "D";
  const sp = { us: s.us.corners + s.us.freeKicks, them: s.them.corners + s.them.freeKicks };
  return (
    <div className="report">
      <div className="head">
        <div className="teams">{fmtDate(b.game.played_on)}{b.game.competition ? ` · ${b.game.competition}` : ""}</div>
        <div className="big">{usFirst ? `${s.us.goals} – ${s.them.goals}` : `${s.them.goals} – ${s.us.goals}`}</div>
        <div className="teams">{usFirst ? `${CONFIG.teamName} vs ${b.game.opponent}` : `${b.game.opponent} vs ${CONFIG.teamName}`} · {res}</div>
      </div>
      <div className="sec"><StatsPanel s={s} compact /></div>
      {b.shots.some((x) => x.pitch_x != null) ? (
        <div className="sec"><h3>Shot map</h3><PitchMap shots={b.shots} /><div className="tiny muted">Circle size = xG. Gold ring = goal. We attack →, they attack ←.</div></div>
      ) : null}
      {goals.length ? (
        <div className="sec"><h3>Goals</h3>
          {goals.map((g) => (
            <div key={g.id} className="goal-line"><span className={`dot ${g.team}`} /><span className="mono">{toMatchTime(video, g.t_seconds).label}</span><span>{g.team === "us" ? CONFIG.teamName : b.game.opponent}{g.label ? ` · ${g.label}` : ""}</span></div>
          ))}
        </div>
      ) : null}
      {b.buckets.length ? <div className="sec"><h3>Momentum</h3><Momentum buckets={b.buckets} /></div> : null}
      <div className="sec"><h3>Set pieces</h3>
        <div className="small">Us: {sp.us} ({s.us.corners} corners, {s.us.freeKicks} FKs), {s.us.setPieceGoals} goal{s.us.setPieceGoals === 1 ? "" : "s"}. Them: {sp.them} ({s.them.corners} corners, {s.them.freeKicks} FKs), {s.them.setPieceGoals} goal{s.them.setPieceGoals === 1 ? "" : "s"}.</div>
      </div>
      <div className="sec tiny muted">{CONFIG.appName} · human-tagged unless marked ≈</div>
    </div>
  );
}
