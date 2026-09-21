import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import VideoPlayer from "../components/VideoPlayer";
import type { PlayerHandle } from "../components/YouTubePlayer";
import Timeline from "../components/Timeline";
import TagList from "../components/TagList";
import TagEditor from "../components/TagEditor";
import ShotPlacer from "../components/ShotPlacer";
import PitchMap from "../components/PitchMap";
import PeriodEditor from "../components/PeriodEditor";
import ChaptersExport from "../components/ChaptersExport";
import StatsPanel from "../components/StatsPanel";
import Momentum from "../components/Momentum";
import FlowField, { type FlowEvent } from "../components/FlowField";
import type { FlowData } from "../lib/types";
import ShapePlot from "../components/ShapePlot";
import GameForm from "../components/GameForm";
import Modal from "../components/Modal";
import { HOTKEYS, useHotkeys } from "../components/useHotkeys";
import * as api from "../lib/api";
import { useAuth } from "../lib/auth";
import { useShow, useTeam, useTeamNames } from "../lib/team";
import { kitVars } from "../lib/kit";
import { useTheme } from "../lib/theme";
import type { GameBundle, Period, Shot, Tag, TagType, Video } from "../lib/types";
import { SET_PIECE_TYPES, TAG_LABELS, VIDEO_KINDS, mainVideo } from "../lib/types";
import { isGoalTag, leadKind, summarizeGame, trustedTags } from "../lib/stats";
import { cap, fmtClock, fmtDate, seekTime, toMatchTime } from "../lib/time";
import { copyText, shareUrl } from "../lib/links";
import { openUrl, providerLabel, resolveSource } from "../lib/sources";
import { computeXg, XG_MODEL_VERSION } from "../lib/xg";

/** An estimate of how far a run is: the worker's own figure, else read off its stage text (older
 *  worker code), else elapsed time against a typical 100-minute run. */
function RunProgress({ run }: { run: import("../lib/types").StatRun }) {
  const [, tick] = useState(0);
  useEffect(() => { const t = window.setInterval(() => tick((n) => n + 1), 15000); return () => clearInterval(t); }, []);
  if (run.status !== "running" || !run.started_at) return null;
  const elapsedMin = (Date.now() - new Date(run.started_at).getTime()) / 60000;
  const stage = typeof run.params?.stage === "string" ? run.params.stage : "";
  let p = typeof run.params?.progress === "number" ? run.params.progress : null;
  const p1 = stage.match(/pass 1 of 2: (\d+) of (\d+) min/), p2 = stage.match(/pass 2 of 2: window (\d+) of (\d+)/);
  if (p == null && p1) p = 0.04 + 0.52 * (Number(p1[1]) / Math.max(1, Number(p1[2])));
  if (p == null && p2) p = 0.56 + 0.42 * (Number(p2[1]) / Math.max(1, Number(p2[2])));
  const guessed = p == null;
  if (p == null) p = Math.min(0.95, elapsedMin / 100);
  p = Math.min(0.99, Math.max(0.01, p));
  const left = !guessed && p > 0.08 ? Math.max(1, Math.round(elapsedMin / p - elapsedMin)) : null;
  return (
    <div className="run-bar" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(p * 100)} aria-label="Analysis progress (estimate)">
      <div className="bar"><i style={{ width: `${p * 100}%` }} /></div>
      <span>{guessed ? "~" : ""}{Math.round(p * 100)}%{left != null ? ` · about ${left} min left` : ` · ${Math.round(elapsedMin)} min so far`}</span>
    </div>
  );
}

/** Possession has no answer key, so the run hands over a sample of its own calls to be marked right
 *  or wrong against the film. The tally is the honest accuracy figure for its ball reading. */
function SpotCheck({ run, names, onSeek, onSaved }: { run: import("../lib/types").StatRun; names: { us: string; them: string }; onSeek: (t: number) => void; onSaved: () => void }) {
  const f = run.params?.fixed as undefined | { spot_check?: { t: number; from: "us" | "them"; to: "us" | "them" }[] };
  const items = f?.spot_check ?? [];
  const answers = (run.params?.spot_answers ?? {}) as Record<string, boolean>;
  if (!items.length) return null;
  const marked = Object.values(answers), right = marked.filter(Boolean).length;
  const mark = async (i: number, ok: boolean) => { await api.mergeRunParams(run.id, { spot_answers: { ...answers, [i]: ok } }); onSaved(); };
  return (
    <details className="spot" style={{ gridColumn: "1 / -1" }}>
      <summary>Check the ball reading · {marked.length ? `${right} of ${marked.length} right so far` : `${items.length} moments to mark`}</summary>
      <p className="tiny muted" style={{ margin: ".3rem 0" }}>Possession, turnovers and passes come from ball flights the wide camera saw. Watch each moment and mark whether the machine has the two teams right.</p>
      {items.map((it, i) => (
        <div key={i} className="spot-row">
          <button className="btn sm" onClick={() => onSeek(Math.max(0, it.t - 2))} title="Watch">▶ {fmtClock(it.t)}</button>
          <span className="small">{names[it.from]} played it, {it.from === it.to ? "and kept it" : <>and <strong>{names[it.to]}</strong> got it</>}</span>
          <span className="spot-marks">
            <button className={`btn sm ${answers[i] === true ? "ok on" : ""}`} onClick={() => mark(i, true)} aria-label="Right">✓</button>
            <button className={`btn sm ${answers[i] === false ? "danger on" : ""}`} onClick={() => mark(i, false)} aria-label="Wrong">✗</button>
          </span>
        </div>
      ))}
    </details>
  );
}

/** What a wide-camera run found, and how it did against the goals already on the game. */
function FixedRunSummary({ run }: { run: import("../lib/types").StatRun }) {
  const f = run.params?.fixed as undefined | {
    ball?: { flights?: number; full?: { possession_us?: number | null; read_share?: number } };
    minutes?: number; clock_offset_s?: number; goals?: { t: number; team: string | null }[];
    compare?: { known_goals?: { known_t: number; found: boolean; dt_s: number | null; team_right: boolean }[]; machine_goals_with_no_known_goal?: number[] };
  };
  if (!f) return null;
  const known = f.compare?.known_goals ?? [], extra = f.compare?.machine_goals_with_no_known_goal ?? [];
  const found = known.filter((k) => k.found);
  return (
    <div className="tiny muted" style={{ gridColumn: "1 / -1", marginTop: ".1rem" }}>
      Wide camera · {f.goals?.length ?? 0} goals found in {f.minutes ?? "?"} min{known.length ? <> · against the {known.length} goals already on this game: <strong>{found.length} found</strong>, {found.filter((k) => k.team_right).length} with the right team{found.length ? `, off by ${found.map((k) => `${k.dt_s! > 0 ? "+" : ""}${k.dt_s}s`).join(", ")}` : ""}{known.length - found.length ? ` · missed ${known.filter((k) => !k.found).map((k) => fmtClock(k.known_t)).join(", ")}` : ""}</> : null}{extra.length ? ` · ${extra.length} with no known goal nearby (${extra.map((t) => fmtClock(t)).join(", ")})` : " · no extra goals"}{f.ball?.flights ? ` · ${f.ball.flights} ball flights read${f.ball.full?.possession_us != null ? `, possession ≈ ${Math.round(f.ball.full.possession_us)}% from ${Math.round((f.ball.full.read_share ?? 0) * 100)}% of playing time` : ""}` : ""}
    </div>
  );
}

function PassThirds({ passes, names }: { passes: import("../lib/types").PassEvent[]; names: { us: string; them: string } }) {
  const located = passes.filter((p) => p.third);
  if (!located.length) return null;
  const count = (team: "us" | "them", third: string) => located.filter((p) => p.team === team && p.third === third).length;
  return (
    <table className="stat-table" style={{ marginTop: ".5rem" }}>
      <thead><tr><th>{names.us}</th><th></th><th>{names.them}</th></tr></thead>
      <tbody>
        {(["left", "mid", "right"] as const).map((t) => (
          <tr key={t}><td className="v machine">{count("us", t)}</td><td className="lbl">{t === "mid" ? "Middle third" : `${t[0].toUpperCase()}${t.slice(1)} third`}</td><td className="v machine">{count("them", t)}</td></tr>
        ))}
      </tbody>
    </table>
  );
}

function SkipIcon({ dir, n }: { dir: "back" | "fwd"; n: number }) {
  // Forward = a clockwise arrow: head at the top pointing right, tail trailing round behind it
  // (the gap is AHEAD of the head). Back is its mirror image.
  const flip = dir === "back" ? "scale(-1,1) translate(-24,0)" : undefined;
  return (
    <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
      <g transform={flip} fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 4a8 8 0 1 0 7.5 5.2" />
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
  const team = useTeam();
  const theme = useTheme();
  const show = useShow();

  const [b, setB] = useState<GameBundle | null>(null);
  const names = useTeamNames(b?.game.opponent);
  const [err, setErr] = useState<string | null>(null);
  const [current, setCurrent] = useState(0);
  const [duration, setDuration] = useState(0);
  const [toast, setToast] = useState<string | null>(null);
  const [editing, setEditing] = useState<{ tag: Partial<Tag> & { t_seconds: number; type: TagType }; quick: boolean; isNew: boolean } | null>(null);
  const [placing, setPlacing] = useState<Tag | null>(null);
  const [editGame, setEditGame] = useState(false);
  const [period, setPeriod] = useState<Period>("full");
  const [panel, setPanel] = useState<"tags" | "periods" | "chapters" | "analysis" | "shape">("tags");
  const [mapMode, setMapMode] = useState<"shots" | "passes">("shots");
  const [videoUrl, setVideoUrl] = useState("");
  const [videoKind, setVideoKind] = useState<NonNullable<Video["kind"]>>("upload");
  const player = useRef<PlayerHandle>(null);
  const startAt = useMemo(() => { const t = Number(params.get("t")); return Number.isFinite(t) && t > 0 ? t : undefined; }, [params]);

  const reload = useCallback(() => api.getGameBundle(id).then(setB).catch((e) => setErr(e.message)), [id]);
  useEffect(() => { if (ready) reload(); }, [reload, ready, isAdmin]);
  const [flow, setFlow] = useState<FlowData | null>(null);
  const [playId, setPlayId] = useState<string | null>(null);
  const resumeAt = useRef<number | null>(null);
  const [flowUrl, setFlowUrl] = useState("");
  const [isPlaying, setIsPlaying] = useState(false);
  const [muted, setMuted] = useState(false);
  useEffect(() => { let on = true; if (ready && id) api.getFlow(id).then((f) => { if (on) setFlow(f); }); return () => { on = false; }; }, [ready, id, isAdmin]);

  // While the worker has something to do, keep the run list (and its progress line) fresh; when a
  // run finishes, load everything it wrote.
  const busy = !!b?.runs.some((r) => r.status === "queued" || r.status === "running");
  useEffect(() => {
    if (!busy || !admin) return;
    const timer = window.setInterval(async () => {
      try {
        const runs = await api.listRuns(id);
        const stillBusy = runs.some((r) => r.status === "queued" || r.status === "running");
        setB((prev) => (prev ? { ...prev, runs } : prev));
        if (!stillBusy) { reload(); api.getFlow(id).then(setFlow); }
      } catch { /* offline for a moment: try again next tick */ }
    }, 20000);
    return () => clearInterval(timer);
  }, [busy, admin, id, reload]);

  const showToast = useCallback((m: string) => { setToast(m); setTimeout(() => setToast(null), 1600); }, []);
  const video = b ? mainVideo(b.videos) : null;
  const watchable = b ? b.videos.filter((v) => v.kind !== "wide_fixed") : [];
  const playing = watchable.find((v) => v.id === playId) ?? video;
  const pitch = { lengthM: b?.game.pitch_length_m ?? team.pitch.lengthM, widthM: b?.game.pitch_width_m ?? team.pitch.widthM };
  const visibleTags = useMemo(() => (b ? (admin ? b.tags : trustedTags(b.tags)) : []), [b, admin]);
  // What people tagged (or confirmed), for the match flow's running stats. Parents see only trusted tags.
  const flowEvents = useMemo<FlowEvent[]>(() => {
    if (!b) return [];
    const onTarget = new Map(b.shots.map((s) => [s.tag_id, s.on_target]));
    const out: FlowEvent[] = [];
    for (const t of trustedTags(b.tags)) {
      if (t.team !== "us" && t.team !== "them") continue;
      const kind: FlowEvent["kind"] | null = t.type === "shot" || t.type === "penalty" ? (onTarget.get(t.id) ? "shot_on_target" : "shot")
        : t.type === "goal" ? "shot_on_target" : t.type === "save" ? "save" : t.type === "corner" ? "corner" : t.type === "free_kick" ? "free_kick"
        : t.type === "foul" ? "foul" : t.type === "yellow_card" || t.type === "red_card" || (t.type === "note" && /\bcard\b/i.test(t.label ?? "")) ? "card" : null;
      if (kind) out.push({ t: t.t_seconds, team: t.team, kind });
      // a corner or free kick that ended in a shot or a goal is also a shot
      if (kind && kind !== "shot" && kind !== "shot_on_target" && (t.outcome === "goal" || t.outcome === "shot")) out.push({ t: t.t_seconds, team: t.team, kind: t.outcome === "goal" || onTarget.get(t.id) ? "shot_on_target" : "shot" });
    }
    return out;
  }, [b]);
  // Who was on top, from the match flow, for the chosen period (we always attack right in the flow).
  const territory = useMemo(() => {
    if (!flow) return null;
    const halves = period === "h1" ? flow.halves.slice(0, 1) : period === "h2" ? flow.halves.slice(1, 2) : flow.halves;
    let us = 0, them = 0;
    flow.m.forEach((m, i) => {
      const t = flow.t0 + i * flow.step;
      if (!halves.some((h) => t >= h[0] && t <= h[1])) return;
      if (m > 0.05) us++; else if (m < -0.05) them++;
    });
    return us + them ? { us: Math.round((us / (us + them)) * 100), them: 100 - Math.round((us / (us + them)) * 100) } : null;
  }, [flow, period]);
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
    showToast(`${TAG_LABELS[type]} · ${names.of(team)} @ ${toMatchTime(video, t).label}`);
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

  async function importFlow(load: () => Promise<unknown>) {
    try {
      const data = (await load()) as FlowData; await api.saveFlow(id, data); setFlow(data); setFlowUrl("");
      // The flow knows the halves (kick-offs from the line-ups, half time from the 3+ minute empty
      // pitch). Use them for the periods unless someone has already set half time by hand.
      const [h1, h2] = data.halves ?? [];
      if (video && h1 && video.halftime_offset_seconds == null) {
        await api.updateVideo(video.id, { ...(data.us_attack_h1 ? { us_attack_h1: data.us_attack_h1 } : {}), kickoff_offset_seconds: Math.round(h1[0]), halftime_offset_seconds: Math.round(h1[1]), second_half_offset_seconds: h2 ? Math.round(h2[0]) : null, fulltime_offset_seconds: h2 ? Math.round(h2[1]) : null });
        await reload(); showToast("Match flow attached · periods set from it");
      } else showToast("Match flow attached");
    }
    catch (e) { showToast(e instanceof Error ? e.message : "Couldn't import that"); }
  }

  // ---- video ---------------------------------------------------------------
  async function attachVideo() {
    if (!b) return;
    try {
      const r = await resolveSource(videoUrl);
      await api.addVideo({ game_id: b.game.id, kind: videoKind, ...r.video });
      // a camera link also knows where its full-field file is: keep it as the analysis source
      if (r.video.raw_url && videoKind !== "wide_fixed" && !b.videos.some((v) => v.raw_url === r.video.raw_url && v.kind === "wide_fixed")) {
        await api.addVideo({ game_id: b.game.id, kind: "wide_fixed", provider: r.video.provider, provider_ref: r.video.provider_ref, source_url: r.video.source_url, stream_url: r.video.raw_url, raw_url: r.video.raw_url, title: `${r.video.title ?? "Game"} (full field)` });
      }
      setVideoUrl(""); reload();
    } catch (e) { showToast(e instanceof Error ? e.message : "Couldn't attach that link"); }
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
    <div className="page game-page" style={kitVars(g.kit_color, g.opp_kit_color, theme.resolved)}>
      {toast ? <div className="toast">{toast}</div> : null}
      <div className="row" style={{ justifyContent: "space-between", marginBottom: ".2rem" }}>
        <Link to="/" className="crumb">← Season</Link>
        {!g.published ? <span className="badge draft">Draft · only admins can see this</span> : null}
      </div>
      <div className="title-row">
        <div>
          <h1>{usFirst ? `${team.shortName} ${scoreText} ` : ""}<Link to={`/opponents/${encodeURIComponent(g.opponent)}`}>{g.opponent}</Link>{!usFirst ? ` ${scoreText} ${team.shortName}` : ""}</h1>
          <div className="sub">{fmtDate(g.played_on)} · {cap(g.home_away)}{g.competition ? ` · ${cap(g.competition)}` : ""}{g.venue ? ` · ${g.venue}` : ""}</div>
        </div>
        <div className="actions-pills">
          {video ? <button className="btn" onClick={async () => showToast((await copyText(shareUrl(g.id, current > 5 ? current : undefined))) ? "Share link copied" : "Copy failed")}>↗ Share</button> : null}
          {show("report") ? <Link className="btn" to={`/${admin ? "games" : "g"}/${g.id}/report`}>▤ Report card</Link> : null}
          {admin ? <button className={`btn ${g.published ? "" : "accent"}`} onClick={togglePublish}>{g.published ? "Unpublish" : "Publish"}</button> : null}
          {admin ? <button className="btn" onClick={() => setEditGame(true)}>Edit</button> : null}
        </div>
      </div>

      <div className="game-layout">
        <div className="game-main">
          {video ? (
            <VideoPlayer key={playing!.id} ref={player} video={playing!} startAt={resumeAt.current ?? startAt} onTime={setCurrent} onDuration={setDuration} onPlaying={setIsPlaying}>
              <div className={`player-ui ${isPlaying ? "playing" : ""}`}>
                <Timeline video={video} duration={duration || video.duration_seconds || 1} current={current} tags={show("tags") ? visibleTags : []} onSeek={seek} />
                <div className="transport">
                  <span className="mono clock">{toMatchTime(video, current).label}</span>
                  <div className="transport-btns" role="group" aria-label="Playback">
                    <button className="btn icon" title="Back 30 seconds (shift+←)" onClick={() => player.current?.nudge(-30)}><SkipIcon dir="back" n={30} /></button>
                    <button className="btn icon" title="Back 5 seconds (←)" onClick={() => player.current?.nudge(-5)}><SkipIcon dir="back" n={5} /></button>
                    <button className="btn icon play" title="Play / pause (space)" aria-label={isPlaying ? "Pause" : "Play"} onClick={() => player.current?.togglePlay()}>
                      <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">{isPlaying ? <path d="M7 5h4v14H7zM13 5h4v14h-4z" fill="currentColor" /> : <path d="M8 5v14l11-7z" fill="currentColor" />}</svg>
                    </button>
                    <button className="btn icon" title="Forward 5 seconds (→)" onClick={() => player.current?.nudge(5)}><SkipIcon dir="fwd" n={5} /></button>
                    <button className="btn icon" title="Forward 30 seconds (shift+→)" onClick={() => player.current?.nudge(30)}><SkipIcon dir="fwd" n={30} /></button>
                  </div>
                  <div className="transport-end">
                    {watchable.length > 1 ? (
                      <div className="seg" role="group" aria-label="Video source" title="Same recording, two hosts. Tag times follow the first source.">
                        {watchable.map((v) => <button key={v.id} className={v.id === playing!.id ? "on" : ""} onClick={() => { resumeAt.current = player.current?.currentTime() ?? current; setPlayId(v.id); }}>{providerLabel(v)}</button>)}
                      </div>
                    ) : null}
                    {openUrl(playing!, current) ? <a className="btn icon" href={openUrl(playing!, current)!} target="_blank" rel="noreferrer" title={`Open on ${providerLabel(playing!)}`} aria-label={`Open on ${providerLabel(playing!)}`}><svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" /></svg></a> : null}
                    <button className="btn icon" title={muted ? "Unmute" : "Mute"} aria-label={muted ? "Unmute" : "Mute"} onClick={() => setMuted(player.current?.toggleMute() ?? false)}>
                      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M4 9v6h4l5 4V5L8 9z" fill="currentColor" stroke="none" />{muted ? <path d="M17 9l5 6M22 9l-5 6" /> : <path d="M16.5 8.5a5 5 0 0 1 0 7M19 6a8.5 8.5 0 0 1 0 12" />}</svg>
                    </button>
                    <button className="btn icon" title="Full screen" aria-label="Full screen" onClick={() => player.current?.fullscreen()}>
                      <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5" /></svg>
                    </button>
                  </div>
                </div>
              </div>
            </VideoPlayer>
          ) : (
            <div className="card">
              <h2>No video yet</h2>
              {admin ? (
                <div className="row"><input type="url" placeholder="Paste a YouTube or BallerCam link" value={videoUrl} onChange={(e) => setVideoUrl(e.target.value)} style={{ flex: 1 }} />
                  <select value={videoKind} onChange={(e) => setVideoKind(e.target.value as NonNullable<Video["kind"]>)} style={{ width: "auto" }}>{VIDEO_KINDS.map((k) => <option key={k.value} value={k.value}>{k.label}</option>)}</select>
                  <button className="btn primary" onClick={attachVideo}>Attach</button></div>
              ) : <p className="muted">Film hasn't been attached to this game.</p>}
            </div>
          )}
        </div>

        <aside className="game-side" hidden={!show("tags") && !admin}>
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
                  <TagList tags={show("tags") ? visibleTags : []} shots={b.shots} video={video} gameId={g.id} opponent={g.opponent} isAdmin={admin} currentTime={current} onSeek={seek}
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
                  <p className="small muted">Nothing runs on its own. Queue a run here and the Mac mini worker picks it up within a minute (an hour or two per game). When the camera's full-field recording is attached, goals, half times and the match flow come from that wide view. It tells the teams apart by the kit colour set on this game{g.kit_color ? "" : " (none set: the team colour is used)"}.</p>
                  <div className="row" style={{ alignItems: "center", gap: 8, marginBottom: 8 }}>
                    <span className="small muted">Kits:</span>
                    <span className="badge us">{names.us}</span><span className="small mono">{g.kit_color || "team colour"}</span>
                    <span className="badge them">{names.them}</span><span className="small mono">{g.opp_kit_color || "not set"}</span>
                    {admin ? <button className="btn sm" onClick={() => setEditGame(true)}>Change</button> : null}
                  </div>
                  <button className="btn primary sm" disabled={!video} onClick={queueRun}>Queue analysis run</button>
                  {b.runs.length ? (
                    <div style={{ marginTop: ".75rem" }}>
                      {b.runs.map((r) => (
                        <div key={r.id} className="tag-row small">
                          <span className="mono">{r.id.slice(0, 8)}</span>
                          <span className={`badge ${r.status === "failed" ? "them" : r.status === "done" ? "us" : ""}`}>{cap(r.status === "cancelled" ? "stopped" : r.status)}</span>
                          <span className="lbl muted">{r.model_version ?? ""}{r.finished_at ? ` · ${new Date(r.finished_at).toLocaleString()}` : r.started_at ? ` · started ${new Date(r.started_at).toLocaleTimeString()}` : ` · ${new Date(r.created_at).toLocaleString()}`}{r.status === "running" && typeof r.params?.stage === "string" ? ` · ${r.params.stage}` : ""}{r.error ? ` · ${r.error}` : ""}</span>
                          {r.status === "queued" ? <button className="btn sm" onClick={async () => { await api.cancelQueuedRun(r.id); reload(); }}>Cancel</button>
                            : r.status === "running" ? <button className="btn sm danger" onClick={async () => { if (confirm("Stop this run? What it has worked out so far is thrown away.")) { await api.stopRun(r.id); showToast("Stopping: the worker ends it within half a minute"); reload(); } }}>Stop</button> : <span />}
                          <RunProgress run={r} />
                          <FixedRunSummary run={r} />
                          <SpotCheck run={r} names={names} onSeek={seek} onSaved={reload} />
                        </div>
                      ))}
                    </div>
                  ) : null}
                  {admin ? (
                    <div style={{ marginTop: ".9rem" }}>
                      <div className="small"><strong>Match flow</strong> <span className="muted">{flow ? "· attached" : "· none yet"}</span></div>
                      <p className="tiny muted" style={{ margin: ".2rem 0 .4rem" }}>The momentum graphic's data, built from the full-field recording by <code>analyzer/flow.py</code>. Pick the flow.json it wrote, or give its address.</p>
                      <div className="row" style={{ gap: ".4rem" }}>
                        <input type="text" placeholder="/demo/flow.json" value={flowUrl} onChange={(e) => setFlowUrl(e.target.value)} style={{ flex: 1, minWidth: 140 }} />
                        <button className="btn sm" disabled={!flowUrl.trim()} onClick={() => importFlow(() => fetch(flowUrl.trim()).then((r) => { if (!r.ok) throw new Error(`Couldn't fetch that (${r.status})`); return r.json(); }))}>Import</button>
                        <label className="btn sm" style={{ cursor: "pointer" }}>File…<input type="file" accept="application/json,.json" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) importFlow(() => f.text().then((t) => JSON.parse(t))); e.target.value = ""; }} /></label>
                      </div>
                    </div>
                  ) : null}
                  {b.teamStats.some((s) => s.source === "machine") ? <div className="notice info" style={{ marginTop: ".75rem" }}>Machine possession and turnover numbers show with ≈. If you disagree after watching, the numbers stay a proposal; there's no per-player data to correct.</div> : null}
                </div>
              ) : null}
            </div>
          </div>
        </aside>
      </div>

      {admin && video ? (
        <details className="keys-details">
          <summary>Tagging keys</summary>
          <div className="keys" style={{ marginTop: ".4rem" }}>
            {HOTKEYS.map((h) => <span key={h.key}><kbd>{h.key}</kbd> <span className="tiny">{TAG_LABELS[h.type]}</span></span>)}
            <span><kbd>⇧</kbd> <span className="tiny">+key = {names.them} (fouls and cards: the team that committed it)</span></span>
            <span><kbd>space</kbd> <span className="tiny">play/pause</span></span>
            <span><kbd>←</kbd><kbd>→</kbd> <span className="tiny">±5s (⇧ ±30s)</span></span>
          </div>
        </details>
      ) : null}

      {flow && show("momentum") ? (
        <div style={{ marginTop: "1rem" }}>
          <FlowField flow={flow} names={names} colors={{ us: g.kit_color || "", them: g.opp_kit_color || "" }} storageKey={g.id} events={flowEvents} onSeek={(t) => { seek(t); window.scrollTo({ top: 0, behavior: "smooth" }); }}
            goals={b.tags.filter((t) => isGoalTag(t) && (t.team === "us" || t.team === "them") && (t.source === "human" || t.confirmed || (admin && t.confirmed == null))).map((t) => ({ t: t.t_seconds, team: t.team as "us" | "them" }))} />
        </div>
      ) : null}

      <div className="below">
        <div className="card" hidden={!show("stats")}>
          <div className="row" style={{ justifyContent: "space-between" }}>
            <h2 style={{ margin: 0 }}>Stats</h2>
            <div className="seg">
              {(["full", "h1", "h2"] as Period[]).map((p) => <button key={p} className={period === p ? "on" : ""} onClick={() => setPeriod(p)}>{p === "full" ? "Match" : p.toUpperCase()}</button>)}
            </div>
          </div>
          <StatsPanel s={summary} opponent={g.opponent} territory={territory} />
          {b.buckets.length && show("momentum") ? <div style={{ marginTop: ".75rem" }}><Momentum buckets={b.buckets} names={names} /></div> : null}
        </div>

        <div className="card" hidden={!show("shotmap") && !(show("passes") && b.passes.length)}>
          <div className="row" style={{ justifyContent: "space-between" }}>
            <h2 style={{ margin: 0 }}>{mapMode === "shots" ? "Shot map" : "Pass map"}</h2>
            <div className="row" style={{ gap: ".4rem" }}>
              {b.passes.length && show("passes") && show("shotmap") ? (
                <div className="seg">
                  <button className={mapMode === "shots" ? "on" : ""} onClick={() => setMapMode("shots")}>Shots</button>
                  <button className={mapMode === "passes" ? "on" : ""} onClick={() => setMapMode("passes")}>Passes</button>
                </div>
              ) : null}
              {admin && b.shots.length && mapMode === "shots" ? <button className="btn sm" onClick={recomputeXg} title="Recompute after changing pitch size">↻ xG</button> : null}
            </div>
          </div>
          {mapMode === "shots" || !show("passes") ? (
            <>
              <PitchMap names={names} shots={b.shots.filter((s) => { const t = b.tags.find((x) => x.id === s.tag_id); return t && (admin || t.source === "human" || t.confirmed); })} onShotClick={(s) => { const t = b.tags.find((x) => x.id === s.tag_id); if (t) { seek(seekTime(t.t_seconds, leadKind(t))); if (admin) setPlacing(t); } }} />
              <div className="tiny muted">Circle size = xG (pro-calibrated proxy). Gold ring = goal. Dashed = machine-located. Click a shot to watch it{admin ? " and move it or change its details" : ""}. Both halves are drawn the same way round: {names.us} always attack →, {names.them} always attack ←.</div>
            </>
          ) : (
            <>
              <PitchMap names={names} shots={[]} passes={b.passes.filter((p) => p.from_x != null)} />
              <PassThirds passes={b.passes} names={names} />
              <div className="tiny muted">Machine estimate. Arrows = passes the analyzer could place on the pitch ({b.passes.filter((p) => p.from_x != null).length} of {b.passes.length}); solid = completed, dashed = not. Thirds are left / middle / right of the video's pitch, not defensive / attacking.</div>
            </>
          )}
        </div>

        <div className="below-span">
          {g.notes ? <div className="card"><h3>Notes</h3><p className="small" style={{ whiteSpace: "pre-wrap" }}>{g.notes}</p></div> : null}
          {video ? <div className="card tiny muted">Video: {video.title ?? video.youtube_id ?? "untitled"}{video.duration_seconds ? ` · ${Math.round(video.duration_seconds / 60)} min` : ""} · {watchable.map(providerLabel).join(" + ")}{b.videos.some((v) => v.kind === "wide_fixed") ? " · wide-angle source attached for analysis" : ""}</div> : null}
        </div>
      </div>

      {editing ? <TagEditor tag={editing.tag} quick={editing.quick} opponent={g.opponent} onSave={saveTag} onClose={() => setEditing(null)} /> : null}
      {placing ? <ShotPlacer tag={placing} existing={shotFor(placing)} pitch={pitch} opponent={g.opponent} video={video} onSetDirection={video ? async (d) => { await api.updateVideo(video.id, { us_attack_h1: d }); reload(); } : undefined} onSave={(s) => saveShot(placing, s)} onClose={() => setPlacing(null)} /> : null}
      {editGame ? (
        <Modal onClose={() => setEditGame(false)} title="Edit game">
          <GameForm initial={g} opponents={[]} onSubmit={async (input) => { await api.updateGame(g.id, input); setEditGame(false); reload(); }} />
          <hr style={{ border: 0, borderTop: "1px solid var(--line)", margin: "1rem 0" }} />
          <h3>Video sources</h3>
          {b.videos.map((v) => (
            <div key={v.id} className="tag-row small">
              <span className="badge">{VIDEO_KINDS.find((k) => k.value === v.kind)?.label ?? cap(v.kind) ?? "Video"}</span>
              <span className="lbl">{providerLabel(v)} · {v.title ?? v.youtube_id}{v.duration_seconds ? ` · ${Math.round(v.duration_seconds / 60)} min` : ""}</span>
              <button className="btn sm danger" onClick={async () => { if (confirm("Detach this video? Tags stay but lose their video link.")) { await api.deleteVideo(v.id); reload(); } }}>Detach</button>
            </div>
          ))}
          <div className="row" style={{ marginTop: ".5rem" }}>
            <input type="url" placeholder="YouTube or BallerCam link of another source" value={videoUrl} onChange={(e) => setVideoUrl(e.target.value)} style={{ flex: 1, minWidth: 180 }} />
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
