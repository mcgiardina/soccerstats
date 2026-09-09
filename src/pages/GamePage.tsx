import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import YouTubePlayer, { type PlayerHandle } from "../components/YouTubePlayer";
import Timeline from "../components/Timeline";
import TagList from "../components/TagList";
import TagEditor from "../components/TagEditor";
import ShotPlacer from "../components/ShotPlacer";
import PitchMap from "../components/PitchMap";
import PeriodEditor from "../components/PeriodEditor";
import ChaptersExport from "../components/ChaptersExport";
import StatsPanel from "../components/StatsPanel";
import Momentum from "../components/Momentum";
import ShapePlot from "../components/ShapePlot";
import GameForm from "../components/GameForm";
import Modal from "../components/Modal";
import { HOTKEYS, useHotkeys } from "../components/useHotkeys";
import * as api from "../lib/api";
import { useAuth } from "../lib/auth";
import { CONFIG } from "../config";
import type { GameBundle, Period, Shot, Tag, TagType, Video } from "../lib/types";
import { SET_PIECE_TYPES, TAG_LABELS, VIDEO_KINDS, mainVideo } from "../lib/types";
import { summarizeGame, trustedTags } from "../lib/stats";
import { fmtDate, seekTime, toMatchTime } from "../lib/time";
import { copyText, shareUrl } from "../lib/links";
import { fetchOEmbed, parseYouTubeId, watchUrl } from "../lib/youtube";
import { computeXg, XG_MODEL_VERSION } from "../lib/xg";

function SkipIcon({ dir, n }: { dir: "back" | "fwd"; n: number }) {
  const flip = dir === "back" ? "scale(-1,1) translate(-24,0)" : undefined;
  return (
    <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
      <g transform={flip} fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 4a8 8 0 1 1-7.5 5.2" />
        <path d="M12 1.5L15 4l-3 2.5" fill="currentColor" stroke="none" />
      </g>
      <text x="12" y="15.2" textAnchor="middle" fontSize={n >= 10 ? 7.5 : 8.5} fontWeight="800" fill="currentColor" fontFamily="var(--font)">{n}</text>
    </svg>
  );
}

export default function GamePage({ shareView = false }: { shareView?: boolean }) {
  const { id = "" } = useParams();
  const [params] = useSearchParams();
  const nav = useNavigate();
  const { isAdmin, ready } = useAuth();
  const admin = isAdmin && !shareView;

  const [b, setB] = useState<GameBundle | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [current, setCurrent] = useState(0);
  const [duration, setDuration] = useState(0);
  const [toast, setToast] = useState<string | null>(null);
  const [editing, setEditing] = useState<{ tag: Partial<Tag> & { t_seconds: number; type: TagType }; quick: boolean; isNew: boolean } | null>(null);
  const [placing, setPlacing] = useState<Tag | null>(null);
  const [editGame, setEditGame] = useState(false);
  const [period, setPeriod] = useState<Period>("full");
  const [panel, setPanel] = useState<"tags" | "periods" | "chapters" | "analysis" | "shape">("tags");
  const [videoUrl, setVideoUrl] = useState("");
  const [videoKind, setVideoKind] = useState<NonNullable<Video["kind"]>>("upload");
  const player = useRef<PlayerHandle>(null);
  const startAt = useMemo(() => { const t = Number(params.get("t")); return Number.isFinite(t) && t > 0 ? t : undefined; }, [params]);

  const reload = useCallback(() => api.getGameBundle(id).then(setB).catch((e) => setErr(e.message)), [id]);
  useEffect(() => { if (ready) reload(); }, [reload, ready, isAdmin]);

  const showToast = useCallback((m: string) => { setToast(m); setTimeout(() => setToast(null), 1600); }, []);
  const video = b ? mainVideo(b.videos) : null;
  const pitch = { lengthM: b?.game.pitch_length_m ?? CONFIG.pitch.lengthM, widthM: b?.game.pitch_width_m ?? CONFIG.pitch.widthM };
  const visibleTags = useMemo(() => (b ? (admin ? b.tags : trustedTags(b.tags)) : []), [b, admin]);
  const summary = useMemo(() => (b ? summarizeGame(b.game, video, b.tags, b.shots, b.teamStats, period) : null), [b, video, period]);

  // Persist duration the first time the player reports it.
  useEffect(() => {
    if (admin && video && duration > 0 && !video.duration_seconds) {
      api.updateVideo(video.id, { duration_seconds: Math.round(duration) }).then(reload);
    }
  }, [admin, video, duration, reload]);

  const seek = useCallback((t: number) => player.current?.seek(t), []);

  // ---- tagging -------------------------------------------------------------
  const onTag = useCallback(async (type: TagType, opposing: boolean) => {
    if (!b || !video) return;
    const t = player.current?.currentTime() ?? current;
    const team = opposing ? "them" : "us";
    const tag = await api.addTag({ game_id: b.game.id, video_id: video.id, t_seconds: Math.round(t * 10) / 10, type, team, source: "human" });
    const isShotLike = type === "shot" || type === "goal" || type === "penalty";
    showToast(`${TAG_LABELS[type]} · ${team} @ ${toMatchTime(video, t).label}`);
    await reload();
    if (isShotLike) setPlacing(tag);
    else if (SET_PIECE_TYPES.includes(type) || type === "note") setEditing({ tag, quick: true, isNew: true });
  }, [b, video, current, reload, showToast]);

  useHotkeys({
    enabled: !editing && !placing && !editGame,
    tagging: admin,
    onTag,
    onTogglePlay: () => player.current?.togglePlay(),
    onNudge: (d) => player.current?.nudge(d),
  });

  async function saveTag(patch: Partial<Tag>) {
    if (!editing) return;
    const existing = editing.tag.id;
    if (existing) await api.updateTag(existing, patch);
    else if (b && video) await api.addTag({ game_id: b.game.id, video_id: video.id, source: "human", ...editing.tag, ...patch });
    await reload();
    // A set piece that ended in a shot or goal deserves a location too.
    if (existing && (patch.outcome === "shot" || patch.outcome === "goal")) {
      const t = b?.tags.find((x) => x.id === existing);
      if (t) setPlacing({ ...t, ...patch } as Tag);
    }
  }

  async function removeTag(tag: Tag) {
    if (!confirm(`Delete ${TAG_LABELS[tag.type]} at ${toMatchTime(video, tag.t_seconds).label}?`)) return;
    await api.deleteTag(tag.id);
    reload();
  }

  async function review(tag: Tag, confirmed: boolean) {
    await api.updateTag(tag.id, { confirmed, confirmed_at: new Date().toISOString() });
    reload();
  }

  async function saveShot(tag: Tag, shot: Partial<Shot>) {
    await api.upsertShot({ ...shot, tag_id: tag.id, game_id: tag.game_id });
    reload();
  }

  // ---- video ---------------------------------------------------------------
  async function attachVideo() {
    const yid = parseYouTubeId(videoUrl);
    if (!yid || !b) { showToast("Not a YouTube URL"); return; }
    const o = await fetchOEmbed(yid);
    await api.addVideo({ game_id: b.game.id, youtube_id: yid, kind: videoKind, title: o?.title ?? null });
    setVideoUrl(""); reload();
  }

  async function updatePeriods(patch: Partial<typeof video>) {
    if (!video) return;
    await api.updateVideo(video.id, patch as Partial<NonNullable<typeof video>>);
    reload();
  }

  async function togglePublish() {
    if (!b) return;
    await api.updateGame(b.game.id, { published: !b.game.published });
    reload();
  }

  async function recomputeXg() {
    if (!b) return;
    let n = 0;
    for (const s of b.shots) {
      if (s.pitch_x != null && s.pitch_y != null) {
        await api.upsertShot({ tag_id: s.tag_id, game_id: s.game_id, xg: computeXg(s.pitch_x, s.pitch_y, pitch.lengthM, pitch.widthM, { context: s.context, assist: s.assist, headed: s.body_part === "head" }), xg_model_version: XG_MODEL_VERSION });
        n++;
      }
    }
    showToast(`Recomputed xG for ${n} shots`); reload();
  }

  async function queueRun() {
    if (!b || !video) return;
    const r = await api.queueStatRun(b.game.id, video.id);
    showToast(`Run ${r.id.slice(0, 8)} queued`); reload();
  }

  if (err) return <div className="page"><div className="card"><h1>Not available</h1><p className="muted">{err.includes("0 rows") || err.includes("multiple") ? "This game isn't published, or the link is wrong." : err}</p><Link to="/">← Season</Link></div></div>;
  if (!b || !summary) return <div className="page muted">Loading…</div>;

  const g = b.game;
  const shotFor = (tag: Tag) => b.shots.find((s) => s.tag_id === tag.id) ?? null;
  const usFirst = g.home_away !== "away";
  const scoreText = usFirst ? `${summary.us.goals}–${summary.them.goals}` : `${summary.them.goals}–${summary.us.goals}`;

  return (
    <div className="page game-page">
      {toast ? <div className="toast">{toast}</div> : null}
      <div className="row" style={{ justifyContent: "space-between", marginBottom: ".6rem" }}>
        <Link to="/" className="crumb">← Season</Link>
        {!g.published ? <span className="badge draft">draft · only admins can see this</span> : null}
      </div>

      <div className="game-layout">
        <div className="game-main">
          {video ? (
            <>
              <YouTubePlayer ref={player} youtubeId={video.youtube_id} startAt={startAt} onTime={setCurrent} onDuration={setDuration} />
              <Timeline video={video} duration={duration || video.duration_seconds || 1} current={current} tags={visibleTags} onSeek={seek} />
              <div className="transport">
                <span className="mono clock">{toMatchTime(video, current).label}</span>
                <div className="transport-btns" role="group" aria-label="Playback">
                  <button className="btn icon" title="Back 30 seconds (shift+←)" onClick={() => player.current?.nudge(-30)}><SkipIcon dir="back" n={30} /></button>
                  <button className="btn icon" title="Back 5 seconds (←)" onClick={() => player.current?.nudge(-5)}><SkipIcon dir="back" n={5} /></button>
                  <button className="btn icon play" title="Play / pause (space)" onClick={() => player.current?.togglePlay()}>
                    <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M8 5v14l11-7z" fill="currentColor" /></svg>
                  </button>
                  <button className="btn icon" title="Forward 5 seconds (→)" onClick={() => player.current?.nudge(5)}><SkipIcon dir="fwd" n={5} /></button>
                  <button className="btn icon" title="Forward 30 seconds (shift+→)" onClick={() => player.current?.nudge(30)}><SkipIcon dir="fwd" n={30} /></button>
                </div>
                <a className="small muted" href={watchUrl(video.youtube_id, current)} target="_blank" rel="noreferrer">Open on YouTube ↗</a>
              </div>
              <div className="title-row">
                <div>
                  <h1>{usFirst ? `${CONFIG.teamName} ${scoreText} ` : ""}<Link to={`/opponents/${encodeURIComponent(g.opponent)}`}>{g.opponent}</Link>{!usFirst ? ` ${scoreText} ${CONFIG.teamName}` : ""}</h1>
                  <div className="sub">{fmtDate(g.played_on)} · {g.home_away}{g.competition ? ` · ${g.competition}` : ""}{g.venue ? ` · ${g.venue}` : ""}</div>
                </div>
                <div className="actions-pills">
                  <button className="btn" onClick={async () => showToast((await copyText(shareUrl(g.id, current > 5 ? current : undefined))) ? "Share link copied" : "Copy failed")}>↗ Share</button>
                  <Link className="btn" to={`/${admin ? "games" : "g"}/${g.id}/report`}>▤ Report card</Link>
                  {admin ? <button className={`btn ${g.published ? "" : "accent"}`} onClick={togglePublish}>{g.published ? "Unpublish" : "Publish"}</button> : null}
                  {admin ? <button className="btn" onClick={() => setEditGame(true)}>Edit</button> : null}
                </div>
              </div>
              {admin ? (
                <details className="keys-details">
                  <summary>Tagging keys</summary>
                  <div className="keys" style={{ marginTop: ".4rem" }}>
                    {HOTKEYS.map((h) => <span key={h.key}><kbd>{h.key}</kbd> <span className="tiny">{TAG_LABELS[h.type]}</span></span>)}
                    <span><kbd>⇧</kbd> <span className="tiny">+key = them</span></span>
                    <span><kbd>space</kbd> <span className="tiny">play/pause</span></span>
                    <span><kbd>←</kbd><kbd>→</kbd> <span className="tiny">±5s (⇧ ±30s)</span></span>
                  </div>
                </details>
              ) : null}
            </>
          ) : (
            <div className="card">
              <h1 style={{ marginBottom: ".25rem" }}>{usFirst ? `${CONFIG.teamName} ${scoreText} ` : ""}{g.opponent}{!usFirst ? ` ${scoreText} ${CONFIG.teamName}` : ""}</h1>
              <div className="actions-pills" style={{ marginBottom: "1rem" }}>
                <Link className="btn" to={`/${admin ? "games" : "g"}/${g.id}/report`}>▤ Report card</Link>
                {admin ? <button className={`btn ${g.published ? "" : "accent"}`} onClick={togglePublish}>{g.published ? "Unpublish" : "Publish"}</button> : null}
                {admin ? <button className="btn" onClick={() => setEditGame(true)}>Edit</button> : null}
              </div>
              <h2>No video yet</h2>
              {admin ? (
                <div className="row"><input type="url" placeholder="Paste YouTube URL" value={videoUrl} onChange={(e) => setVideoUrl(e.target.value)} style={{ flex: 1 }} />
                  <select value={videoKind} onChange={(e) => setVideoKind(e.target.value as NonNullable<Video["kind"]>)} style={{ width: "auto" }}>{VIDEO_KINDS.map((k) => <option key={k.value} value={k.value}>{k.label}</option>)}</select>
                  <button className="btn primary" onClick={attachVideo}>Attach</button></div>
              ) : <p className="muted">Film hasn't been attached to this game.</p>}
            </div>
          )}
        </div>

        <aside className="game-side">
          <div className="card side-card">
            {!admin && !b.shapes.length ? <h3 style={{ marginBottom: ".6rem" }}>Tags <span className="muted">· {visibleTags.length}</span></h3> : null}
            <div className="seg" style={{ marginBottom: ".6rem", flexWrap: "wrap", display: !admin && !b.shapes.length ? "none" : undefined }}>
              <button className={panel === "tags" ? "on" : ""} onClick={() => setPanel("tags")}>Tags · {visibleTags.length}</button>
              {admin && video ? <button className={panel === "periods" ? "on" : ""} onClick={() => setPanel("periods")}>Periods</button> : null}
              {admin && video ? <button className={panel === "chapters" ? "on" : ""} onClick={() => setPanel("chapters")}>Chapters</button> : null}
              {admin ? <button className={panel === "analysis" ? "on" : ""} onClick={() => setPanel("analysis")}>Analysis</button> : null}
              {b.shapes.length ? <button className={panel === "shape" ? "on" : ""} onClick={() => setPanel("shape")}>Shape</button> : null}
            </div>
            <div className="side-scroll">
              {panel === "tags" ? (
                <>
                  {admin && b.tags.some((t) => t.source === "machine" && t.confirmed == null) ? <div className="notice">Machine proposals need review. ✓ accepts, ✗ rejects. Only confirmed ones show to parents.</div> : null}
                  <TagList tags={visibleTags} shots={b.shots} video={video} gameId={g.id} isAdmin={admin} currentTime={current} onSeek={seek}
                    onEdit={(t) => setEditing({ tag: t, quick: false, isNew: false })} onDelete={removeTag} onPlace={setPlacing} onReview={review} onToast={showToast} />
                  {admin && video ? <button className="btn sm" style={{ marginTop: ".5rem" }} onClick={() => setEditing({ tag: { t_seconds: Math.round(current), type: "note", team: "us" }, quick: false, isNew: true })}>+ Add tag at {toMatchTime(video, current).label}</button> : null}
                </>
              ) : null}
              {panel === "periods" && video ? <PeriodEditor video={video} currentTime={current} onChange={updatePeriods} onSeek={seek} /> : null}
              {panel === "chapters" && video ? <ChaptersExport video={video} tags={b.tags} /> : null}
              {panel === "shape" ? (
                <div>
                  <ShapePlot snapshots={b.shapes} team="us" period={period} />
                  <ShapePlot snapshots={b.shapes} team="them" period={period} />
                </div>
              ) : null}
              {panel === "analysis" ? (
                <div>
                  <p className="small muted">Analysis runs on your Mac, never automatically. Queue a run here, then execute it:</p>
                  <pre className="chapters">cd analyzer && python analyze.py --game-id {g.id}</pre>
                  <button className="btn primary sm" disabled={!video} onClick={queueRun}>Queue analysis run</button>
                  {b.runs.length ? (
                    <div style={{ marginTop: ".75rem" }}>
                      {b.runs.map((r) => (
                        <div key={r.id} className="tag-row small">
                          <span className="mono">{r.id.slice(0, 8)}</span>
                          <span className={`badge ${r.status === "failed" ? "them" : r.status === "done" ? "us" : ""}`}>{r.status}</span>
                          <span className="lbl muted">{r.model_version ?? ""}{r.finished_at ? ` · ${new Date(r.finished_at).toLocaleString()}` : r.started_at ? ` · started ${new Date(r.started_at).toLocaleTimeString()}` : ` · ${new Date(r.created_at).toLocaleString()}`}{r.error ? ` · ${r.error}` : ""}</span>
                        </div>
                      ))}
                    </div>
                  ) : null}
                  {b.teamStats.some((s) => s.source === "machine") ? <div className="notice info" style={{ marginTop: ".75rem" }}>Machine possession and turnover numbers show with ≈. If you disagree after watching, the numbers stay a proposal; there's no per-player data to correct.</div> : null}
                </div>
              ) : null}
            </div>
          </div>
        </aside>
      </div>

      <div className="below">
        <div className="card">
          <div className="row" style={{ justifyContent: "space-between" }}>
            <h2 style={{ margin: 0 }}>Stats</h2>
            <div className="seg">
              {(["full", "h1", "h2"] as Period[]).map((p) => <button key={p} className={period === p ? "on" : ""} onClick={() => setPeriod(p)}>{p === "full" ? "Match" : p.toUpperCase()}</button>)}
            </div>
          </div>
          <StatsPanel s={summary} />
          {b.buckets.length ? <div style={{ marginTop: ".75rem" }}><Momentum buckets={b.buckets} /></div> : null}
        </div>

        <div className="card">
          <div className="row" style={{ justifyContent: "space-between" }}>
            <h2 style={{ margin: 0 }}>Shot map</h2>
            {admin && b.shots.length ? <button className="btn sm" onClick={recomputeXg} title="Recompute after changing pitch size">↻ xG</button> : null}
          </div>
          <PitchMap shots={b.shots.filter((s) => { const t = b.tags.find((x) => x.id === s.tag_id); return t && (admin || t.source === "human" || t.confirmed); })} onShotClick={(s) => { const t = b.tags.find((x) => x.id === s.tag_id); if (t) seek(seekTime(t.t_seconds)); }} />
          <div className="tiny muted">Circle size = xG (pro-calibrated proxy). Gold ring = goal. Dashed = machine-located. Click a shot to watch it. We attack →.</div>
        </div>

        <div className="below-span">
          {g.notes ? <div className="card"><h3>Notes</h3><p className="small" style={{ whiteSpace: "pre-wrap" }}>{g.notes}</p></div> : null}
          {video ? <div className="card tiny muted">Video: {video.title ?? video.youtube_id}{video.duration_seconds ? ` · ${Math.round(video.duration_seconds / 60)} min` : ""} · YouTube{b.videos.some((v) => v.kind === "wide_fixed") ? " · wide-angle source attached for analysis" : ""}</div> : null}
        </div>
      </div>

      {editing ? <TagEditor tag={editing.tag} quick={editing.quick} onSave={saveTag} onClose={() => setEditing(null)} /> : null}
      {placing ? <ShotPlacer tag={placing} existing={shotFor(placing)} pitch={pitch} onSave={(s) => saveShot(placing, s)} onClose={() => setPlacing(null)} /> : null}
      {editGame ? (
        <Modal onClose={() => setEditGame(false)} title="Edit game">
          <GameForm initial={g} opponents={[]} onSubmit={async (input) => { await api.updateGame(g.id, input); setEditGame(false); reload(); }} />
          <hr style={{ border: 0, borderTop: "1px solid var(--line)", margin: "1rem 0" }} />
          <h3>Video sources</h3>
          {b.videos.map((v) => (
            <div key={v.id} className="tag-row small">
              <span className="badge">{VIDEO_KINDS.find((k) => k.value === v.kind)?.label ?? v.kind ?? "video"}</span>
              <span className="lbl">{v.title ?? v.youtube_id}{v.duration_seconds ? ` · ${Math.round(v.duration_seconds / 60)} min` : ""}</span>
              <button className="btn sm danger" onClick={async () => { if (confirm("Detach this video? Tags stay but lose their video link.")) { await api.deleteVideo(v.id); reload(); } }}>Detach</button>
            </div>
          ))}
          <div className="row" style={{ marginTop: ".5rem" }}>
            <input type="url" placeholder="YouTube URL of another source" value={videoUrl} onChange={(e) => setVideoUrl(e.target.value)} style={{ flex: 1, minWidth: 180 }} />
            <select value={videoKind} onChange={(e) => setVideoKind(e.target.value as NonNullable<Video["kind"]>)} style={{ width: "auto" }}>{VIDEO_KINDS.map((k) => <option key={k.value} value={k.value}>{k.label}</option>)}</select>
            <button className="btn sm" onClick={attachVideo}>Attach</button>
          </div>
          <p className="tiny muted" style={{ marginTop: ".3rem" }}>{VIDEO_KINDS.find((k) => k.value === videoKind)?.hint}</p>
          <div className="row" style={{ justifyContent: "flex-end", marginTop: "1rem" }}>
            <button className="btn sm danger" onClick={async () => { if (confirm("Delete this game and all its tags? This cannot be undone.")) { await api.deleteGame(g.id); nav("/"); } }}>Delete game</button>
          </div>
        </Modal>
      ) : null}
    </div>
  );
}
