import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import GameForm, { type GameInput } from "../components/GameForm";
import { addTag, addVideo, createGame, listGames, listOpponents, type GameRow } from "../lib/api";
import { PROVIDERS, detectProvider, resolveSource, type ResolvedSource } from "../lib/sources";
import { useTeam } from "../lib/team";
import { fmtClock, fmtDate } from "../lib/time";

// BallerCam goals are tapped on the scoreboard after the fact. On the first real game the four
// corrected scoreboard times were 36-39 s after the kick, so take that off; the tag stays a proposal.
const SCOREBOARD_LAG_S = 38;

const words = (s: string) => new Set(s.toLowerCase().split(/[^a-z0-9]+/).filter((w) => w.length > 1));

export default function NewGamePage() {
  const nav = useNavigate();
  const team = useTeam();
  const [opponents, setOpponents] = useState<string[]>([]);
  const [allGames, setAllGames] = useState<GameRow[]>([]);
  const [history, setHistory] = useState<GameRow[]>([]);
  const [url, setUrl] = useState("");
  const [src, setSrc] = useState<ResolvedSource | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [importGoals, setImportGoals] = useState(true);
  const provider = useMemo(() => detectProvider(url), [url]);

  useEffect(() => { listOpponents().then(setOpponents); listGames().then(setAllGames); }, []);

  const onOpponentChange = useCallback((name: string) => {
    const n = name.trim().toLowerCase();
    setHistory(n ? allGames.filter((g) => g.opponent.trim().toLowerCase() === n) : []);
  }, [allGames]);

  useEffect(() => {
    setSrc(null); setErr(null);
    if (!url.trim()) return;
    let live = true; setBusy(true);
    const timer = window.setTimeout(() => {
      resolveSource(url).then((r) => { if (live) setSrc(r); }).catch((e: Error) => { if (live) setErr(e.message); }).finally(() => { if (live) setBusy(false); });
    }, 350);
    return () => { live = false; clearTimeout(timer); };
  }, [url]);

  // Which of the camera's two teams is us: the one whose name shares the most words with ours.
  const sides = useMemo(() => {
    const t = src?.game?.teams; if (!t || t.length < 2) return null;
    const mine = words(`${team.name} ${team.shortName}`);
    const score = (n: string) => [...words(n)].filter((w) => mine.has(w)).length;
    const usIdx = score(t[1].name) > score(t[0].name) ? 1 : 0;
    return { us: t[usIdx], them: t[1 - usIdx] };
  }, [src, team.name, team.shortName]);

  const initial = useMemo(() => (src?.game && sides ? {
    played_on: src.game.playedOn ?? undefined, opponent: sides.them.name, score_us: sides.us.score, score_them: sides.them.score,
    kit_color: sides.us.color, opp_kit_color: sides.them.color,
  } : undefined), [src, sides]);

  async function submit(g: GameInput) {
    const game = await createGame(g);
    if (src) {
      const v = await addVideo({ game_id: game.id, kind: "upload", ...src.video });
      if (src.video.raw_url) await addVideo({ game_id: game.id, kind: "wide_fixed", provider: src.video.provider, provider_ref: src.video.provider_ref, source_url: src.video.source_url, stream_url: src.video.raw_url, raw_url: src.video.raw_url, title: `${src.video.title ?? "Game"} (full field)` });
      if (importGoals && sides) for (const goal of src.game?.goals ?? []) {
        await addTag({ game_id: game.id, video_id: v.id, t_seconds: Math.max(0, Math.round(goal.t - SCOREBOARD_LAG_S)), type: "goal", team: goal.teamName === sides.us.name ? "us" : "them", source: "machine", confidence: 0.9, label: "from the camera's scoreboard; check the time" });
      }
    }
    nav(`/games/${game.id}`);
  }

  return (
    <div className="page" style={{ maxWidth: 760 }}>
      <h1>Add game</h1>
      <div className="card">
        <label className="field"><span>Video link: YouTube (unlisted is fine) or a BallerCam share link</span>
          <input type="url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://youtu.be/…  or  https://blrcam.co/…" />
        </label>
        {busy ? <p className="small muted">Looking that up…</p> : null}
        {src ? (
          <div className="row" style={{ marginBottom: ".75rem", alignItems: "flex-start" }}>
            {src.thumbnail ? <img className="thumb-sm" src={src.thumbnail} alt="" style={{ maxWidth: 180 }} /> : null}
            <div className="small">
              <div><span className="badge">{PROVIDERS[src.video.provider ?? "youtube"].label}</span> <strong>{src.video.title ?? src.video.youtube_id ?? "Video"}</strong></div>
              {src.game && sides ? (
                <div className="muted" style={{ marginTop: ".3rem" }}>
                  Filled in below from the camera: {sides.us.name} {sides.us.score ?? "–"}–{sides.them.score ?? "–"} {sides.them.name}
                  {src.video.kickoff_offset_seconds ? `, kick-off at ${fmtClock(src.video.kickoff_offset_seconds)}` : ""}
                  {src.video.raw_url ? ". The full-field recording is attached for analysis." : "."}
                </div>
              ) : <div className="muted">Duration is read from the player once you open the game.</div>}
              {src.game?.goals.length ? (
                <label className="row" style={{ gap: ".4rem", marginTop: ".4rem" }}>
                  <input type="checkbox" checked={importGoals} onChange={(e) => setImportGoals(e.target.checked)} style={{ width: "auto" }} />
                  <span>Add the {src.game.goals.length} scoreboard goals as proposals to review ({src.game.goals.map((x) => fmtClock(Math.max(0, x.t - SCOREBOARD_LAG_S))).join(", ")})</span>
                </label>
              ) : null}
            </div>
          </div>
        ) : null}
        {err || src?.note ? <p className="err small">{err ?? src?.note}</p> : null}
        {!err && !src && !busy && url.trim() && !provider ? <p className="err small">Not a link I recognise.</p> : null}
        <GameForm key={src?.video.provider_ref ?? "blank"} initial={initial} opponents={opponents} onSubmit={submit} submitLabel="Create game" onOpponentChange={onOpponentChange} />
      </div>
      {history.length ? (
        <div className="card">
          <h2>We've played them before</h2>
          {history.map((g) => (
            <div key={g.id} className="tag-row">
              <span className="mono small">{fmtDate(g.played_on)}</span>
              <span className="lbl">{g.score_us != null ? <strong>{g.score_us}–{g.score_them}</strong> : <span className="muted">no score</span>}{g.notes ? <span className="muted"> · {g.notes.slice(0, 90)}</span> : null}</span>
              <Link to={`/games/${g.id}`} className="btn sm">Open</Link>
            </div>
          ))}
          <Link to={`/opponents/${encodeURIComponent(history[0].opponent)}`} className="small">Full history →</Link>
        </div>
      ) : null}
    </div>
  );
}
