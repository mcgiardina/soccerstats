import { mainVideo } from "../lib/types";
import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { loadSeason, type SeasonData } from "../lib/api";
import { useAuth } from "../lib/auth";
import { summarizeGame } from "../lib/stats";
import { fmtDate } from "../lib/time";
import { thumbnailUrl } from "../lib/youtube";
import PitchMap from "../components/PitchMap";
import { useShow } from "../lib/team";

export default function OpponentPage() {
  const { name = "" } = useParams();
  const { isAdmin } = useAuth();
  const show = useShow();
  const [data, setData] = useState<SeasonData | null>(null);
  useEffect(() => { loadSeason().then(setData); }, [isAdmin]);
  if (!show("opponent")) return <div className="page centered"><div className="card"><h1>Opponent history</h1><p className="muted">This section is turned off for parents.</p><Link to="/">← Season</Link></div></div>;

  const games = useMemo(() => (data?.games ?? []).filter((g) => g.opponent.toLowerCase() === name.toLowerCase()), [data, name]);
  if (!data) return <div className="page muted">Loading…</div>;

  const shots = data.shots.filter((s) => games.some((g) => g.id === s.game_id));
  const record = games.reduce((r, g) => {
    const s = summarizeGame(g, mainVideo(g.videos), data.tags.filter((t) => t.game_id === g.id), [], []);
    if (s.us.goals > s.them.goals) r.w++; else if (s.us.goals < s.them.goals) r.l++; else r.d++;
    r.gf += s.us.goals; r.ga += s.them.goals; return r;
  }, { w: 0, d: 0, l: 0, gf: 0, ga: 0 });

  return (
    <div className="page">
      <Link to="/" className="small">← Season</Link>
      <h1>vs {name}</h1>
      <p className="muted small">{games.length} game{games.length === 1 ? "" : "s"} · {record.w}W {record.d}D {record.l}L · GF {record.gf} GA {record.ga}</p>
      {shots.some((s) => s.pitch_x != null) ? (
        <div className="card"><h3>All shots across these games</h3><div className="pitch-wrap"><PitchMap shots={shots} /></div><div className="tiny muted">We attack →, they attack ←. Gold ring = goal. Look for patterns: where do they hurt us, where do we get chances.</div></div>
      ) : null}
      {games.map((g) => {
        const v = mainVideo(g.videos);
        const s = summarizeGame(g, v ?? null, data.tags.filter((t) => t.game_id === g.id), data.shots.filter((x) => x.game_id === g.id), data.teamStats.filter((x) => x.game_id === g.id));
        return (
          <div key={g.id} className="card row opp-card" style={{ alignItems: "flex-start" }}>
            {v ? <img className="thumb-sm" src={thumbnailUrl(v.youtube_id, "hq")} alt="" /> : null}
            <div style={{ flex: 1, minWidth: 200 }}>
              <div className="row" style={{ justifyContent: "space-between" }}>
                <strong>{fmtDate(g.played_on)} · {g.home_away}{g.competition ? ` · ${g.competition}` : ""}</strong>
                <span className="score">{s.us.goals}–{s.them.goals}</span>
              </div>
              <div className="small muted">Shots {s.us.shots}–{s.them.shots}{s.us.xg != null || s.them.xg != null ? ` · xG ${s.us.xg ?? "?"}–${s.them.xg ?? "?"}` : ""}{s.us.possession != null ? ` · poss ${Math.round(s.us.possession)}% ≈` : ""}</div>
              {g.notes ? <p className="small" style={{ marginTop: ".4rem" }}>{g.notes}</p> : null}
              <div className="row" style={{ marginTop: ".4rem" }}>
                <Link className="btn sm" to={isAdmin ? `/games/${g.id}` : `/g/${g.id}`}>Watch</Link>
                <Link className="btn sm" to={`/${isAdmin ? "games" : "g"}/${g.id}/report`}>Report card</Link>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
