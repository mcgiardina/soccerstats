import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import GameForm, { type GameInput } from "../components/GameForm";
import { addVideo, createGame, listGames, listOpponents, type GameRow } from "../lib/api";
import { fetchOEmbed, parseYouTubeId, thumbnailUrl } from "../lib/youtube";
import { fmtDate } from "../lib/time";

export default function NewGamePage() {
  const nav = useNavigate();
  const [opponents, setOpponents] = useState<string[]>([]);
  const [allGames, setAllGames] = useState<GameRow[]>([]);
  const [history, setHistory] = useState<GameRow[]>([]);
  const [url, setUrl] = useState("");
  const [ytId, setYtId] = useState<string | null>(null);
  const [ytTitle, setYtTitle] = useState<string | null>(null);
  const [ytErr, setYtErr] = useState<string | null>(null);

  useEffect(() => { listOpponents().then(setOpponents); listGames().then(setAllGames); }, []);

  const onOpponentChange = useCallback((name: string) => {
    const n = name.trim().toLowerCase();
    setHistory(n ? allGames.filter((g) => g.opponent.trim().toLowerCase() === n) : []);
  }, [allGames]);

  useEffect(() => {
    const id = parseYouTubeId(url);
    setYtId(id); setYtTitle(null); setYtErr(null);
    if (!id) { if (url.trim()) setYtErr("Couldn't find a YouTube ID in that."); return; }
    let live = true;
    fetchOEmbed(id).then((o) => { if (!live) return; if (o) setYtTitle(o.title); else setYtErr("YouTube didn't return details (private video?). You can still save it."); });
    return () => { live = false; };
  }, [url]);

  async function submit(g: GameInput) {
    const game = await createGame(g);
    if (ytId) await addVideo({ game_id: game.id, youtube_id: ytId, kind: "stream_archive", title: ytTitle });
    nav(`/games/${game.id}`);
  }

  return (
    <div className="page" style={{ maxWidth: 760 }}>
      <h1>Add game</h1>
      <div className="card">
        <label className="field"><span>YouTube URL (unlisted stream archive or upload)</span>
          <input type="url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://youtu.be/…" />
        </label>
        {ytId ? (
          <div className="row" style={{ marginBottom: ".75rem" }}>
            <img src={thumbnailUrl(ytId)} alt="" style={{ width: 120, borderRadius: 6 }} />
            <div className="small"><div><strong>{ytTitle ?? ytId}</strong></div><div className="muted">ID {ytId}. Duration is read from the player once you open the game.</div></div>
          </div>
        ) : null}
        {ytErr ? <p className="err small">{ytErr}</p> : null}
        <GameForm opponents={opponents} onSubmit={submit} submitLabel="Create game" onOpponentChange={onOpponentChange} />
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
