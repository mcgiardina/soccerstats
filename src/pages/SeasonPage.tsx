import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { loadSeason, type SeasonData } from "../lib/api";
import { useAuth } from "../lib/auth";
import { fmtDate } from "../lib/time";
import { thumbnailUrl } from "../lib/youtube";
import { summarizeGame } from "../lib/stats";
import TrendCharts, { buildTrend } from "../components/TrendCharts";
import { CONFIG } from "../config";

export default function SeasonPage() {
  const { isAdmin } = useAuth();
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
      <div className="row" style={{ justifyContent: "space-between", marginBottom: ".75rem" }}>
        <div><h1 style={{ marginBottom: 0 }}>{CONFIG.teamName} · Season</h1><span className="muted small">{games.length} game{games.length === 1 ? "" : "s"} · {record.w}W {record.d}D {record.l}L</span></div>
        {isAdmin ? <Link className="btn primary" to="/games/new">+ Add game</Link> : null}
      </div>

      <TrendCharts data={trend} />

      <div className="filters">
        <input type="text" placeholder="Search notes & tag labels" value={q} onChange={(e) => setQ(e.target.value)} />
        <select value={opp} onChange={(e) => setOpp(e.target.value)}><option value="">All opponents</option>{opponents.map((o) => <option key={o}>{o}</option>)}</select>
        <select value={comp} onChange={(e) => setComp(e.target.value)}><option value="">All competitions</option><option value="league">League</option><option value="tournament">Tournament</option><option value="friendly">Friendly</option></select>
        <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} title="From" />
        <input type="date" value={to} onChange={(e) => setTo(e.target.value)} title="To" />
      </div>

      {games.length === 0 ? <div className="card muted">No games{isAdmin ? " yet. Add one to get started." : " published yet."}</div> : null}
      <div className="game-list">
        {games.map((g) => {
          const v = g.videos[0];
          const s = summarizeGame(g, v ?? null, data.tags.filter((t) => t.game_id === g.id), [], []);
          const cls = s.us.goals > s.them.goals ? "win" : s.us.goals < s.them.goals ? "loss" : "draw";
          const hasScore = g.score_us != null || data.tags.some((t) => t.game_id === g.id && t.type === "goal");
          return (
            <Link key={g.id} to={isAdmin ? `/games/${g.id}` : `/g/${g.id}`} className="game-card">
              {v ? <img className="thumb" src={thumbnailUrl(v.youtube_id)} alt="" loading="lazy" /> : <div className="thumb empty">⚽</div>}
              <div className="body">
                <div className="opp">{g.home_away === "away" ? "@ " : "vs "}{g.opponent}</div>
                <div className="small muted">{fmtDate(g.played_on)}{g.competition ? ` · ${g.competition}` : ""}</div>
                <div className="row" style={{ gap: ".4rem", marginTop: ".25rem" }}>
                  {hasScore ? <span className={`score ${cls}`}>{s.us.goals}–{s.them.goals}</span> : <span className="muted small">no score</span>}
                  {!g.published ? <span className="badge draft">draft</span> : null}
                  {!v ? <span className="badge">no video</span> : null}
                </div>
              </div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
