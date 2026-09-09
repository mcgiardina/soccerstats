import { mainVideo } from "../lib/types";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { loadSeason, type SeasonData } from "../lib/api";
import { useAuth } from "../lib/auth";
import { fmtDate } from "../lib/time";
import { thumbnailUrl } from "../lib/youtube";
import { summarizeGame } from "../lib/stats";
import TrendCharts, { buildTrend } from "../components/TrendCharts";
import DateRangePicker from "../components/DateRangePicker";
import { useShow, useTeam } from "../lib/team";

export default function SeasonPage() {
  const { isAdmin } = useAuth();
  const team = useTeam();
  const show = useShow();
  const [data, setData] = useState<SeasonData | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [opp, setOpp] = useState("");
  const [comp, setComp] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");

  useEffect(() => { loadSeason().then(setData).catch((e) => setErr(e.message)); }, [isAdmin]);

  const opponents = useMemo(() => Array.from(new Set(data?.games.map((g) => g.opponent) ?? [])).sort(), [data]);

  const games = useMemo(() => {
    if (!data) return [];
    const ql = q.trim().toLowerCase();
    return data.games.filter((g) => {
      if (opp && g.opponent !== opp) return false;
      if (comp && g.competition !== comp) return false;
      if (from && g.played_on < from) return false;
      if (to && g.played_on > to) return false;
      if (ql) {
        const hay = [g.opponent, g.venue, g.notes, ...data.tags.filter((t) => t.game_id === g.id).map((t) => t.label ?? "")].join(" ").toLowerCase();
        if (!hay.includes(ql)) return false;
      }
      return true;
    });
  }, [data, q, opp, comp, from, to]);

  const trend = useMemo(() => (data ? buildTrend({ ...data, games }) : []), [data, games]);

  if (err) return <div className="page"><div className="card err">Could not load: {err}</div></div>;
  if (!data) return <div className="page muted">Loading…</div>;

  const record = trend.reduce((r, p) => { if (p.goalsFor > p.goalsAgainst) r.w++; else if (p.goalsFor < p.goalsAgainst) r.l++; else r.d++; return r; }, { w: 0, l: 0, d: 0 });

  return (
    <div className="page">
      <div className="hero">
        <div className="reveal">
          <div className="eyebrow">{team.name} · season</div>
          <div className="kpi">
            <span className="num">{record.w}<small>W</small></span>
            <span className="num">{record.d}<small>D</small></span>
            <span className="num">{record.l}<small>L</small></span>
          </div>
        </div>
        <div className="kpi-row reveal">
          <div className="item"><div className="v">{games.length}</div><div className="l">games</div></div>
          <div className="item"><div className="v">{trend.reduce((a, p) => a + p.goalsFor, 0)}</div><div className="l">goals for</div></div>
          <div className="item"><div className="v">{trend.reduce((a, p) => a + p.goalsAgainst, 0)}</div><div className="l">goals against</div></div>
          {isAdmin ? <Link className="btn primary" to="/games/new" style={{ alignSelf: "center" }}>+ Add game</Link> : null}
        </div>
      </div>

      {show("trends") ? <TrendCharts data={trend} /> : null}

      <div className="filters">
        <div className="search"><input className="pill" type="text" placeholder="Search notes & tag labels" value={q} onChange={(e) => setQ(e.target.value)} /></div>
        <select className="pill" value={opp} onChange={(e) => setOpp(e.target.value)}><option value="">All opponents</option>{opponents.map((o) => <option key={o}>{o}</option>)}</select>
        <div className="seg">
          {[["", "All"], ["league", "League"], ["tournament", "Tournament"], ["friendly", "Friendly"]].map(([v, l]) => (
            <button key={v} className={comp === v ? "on" : ""} onClick={() => setComp(v)}>{l}</button>
          ))}
        </div>
        <DateRangePicker from={from} to={to} onChange={(f, t) => { setFrom(f); setTo(t); }} />
      </div>

      {games.length === 0 ? <div className="card muted">No games{isAdmin ? " yet. Add one to get started." : " published yet."}</div> : null}
      <div className="game-list">
        {games.map((g) => {
          const v = mainVideo(g.videos);
          const s = summarizeGame(g, v ?? null, data.tags.filter((t) => t.game_id === g.id), [], []);
          const cls = s.us.goals > s.them.goals ? "win" : s.us.goals < s.them.goals ? "loss" : "draw";
          const hasScore = g.score_us != null || data.tags.some((t) => t.game_id === g.id && t.type === "goal");
          return (
            <Link key={g.id} to={isAdmin ? `/games/${g.id}` : `/g/${g.id}`} className="game-card reveal">
              {v ? <img className="thumb" src={thumbnailUrl(v.youtube_id, "hq")} alt="" loading="lazy" /> : <div className="thumb empty">⚽</div>}
              <div className="body">
                <div className="opp">{g.home_away === "away" ? "@ " : "vs "}{g.opponent}</div>
                <div className="meta">
                  <span className="small muted">{fmtDate(g.played_on)}{g.competition ? ` · ${g.competition}` : ""}</span>
                  {hasScore ? <span className={`score pill ${cls}`}>{s.us.goals}–{s.them.goals}</span> : <span className="badge plain">no score</span>}
                </div>
                {(!g.published || !v) ? <div className="row" style={{ gap: ".4rem", marginTop: ".4rem" }}>
                  {!g.published ? <span className="badge draft">draft</span> : null}
                  {!v ? <span className="badge">no video</span> : null}
                </div> : null}
              </div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
