import { supabase } from "./supabase";
import type {
  Game, GameBundle, Shot, StatBucket, StatRun, Tag, TeamStats, Video, ShapeSnapshot, PassEvent, FlowData,
} from "./types";

function unwrap<T>(res: { data: T | null; error: { message: string } | null }): T {
  if (res.error) throw new Error(res.error.message);
  return res.data as T;
}

// ---- Games -----------------------------------------------------------------

export interface GameRow extends Game { videos: Video[] }

export async function listGames(): Promise<GameRow[]> {
  const res = await supabase
    .from("games")
    .select("*, videos(*)")
    .order("played_on", { ascending: false })
    .order("created_at", { ascending: false });
  return unwrap(res) as GameRow[];
}

/** Flow for the momentum graphic. Loaded on its own (it is ~100 KB) and absent for most games. */
export async function getFlow(gameId: string): Promise<FlowData | null> {
  const res = await supabase.from("game_flow").select("data").eq("game_id", gameId).order("created_at", { ascending: false }).limit(1).maybeSingle();
  return res.error || !res.data ? null : (res.data.data as FlowData);
}

export async function listRuns(gameId: string): Promise<StatRun[]> {
  return unwrap(await supabase.from("stat_runs").select("*").eq("game_id", gameId).order("created_at", { ascending: false })) as StatRun[];
}

/** Take a run out of the queue before the worker has started it. */
export async function cancelQueuedRun(runId: string): Promise<void> {
  unwrap(await supabase.from("stat_runs").delete().eq("id", runId).eq("status", "queued"));
}

/** Stop a run the worker has started: it checks this status every 20 s and ends the job. */
export async function stopRun(runId: string): Promise<void> {
  unwrap(await supabase.from("stat_runs").update({ status: "cancelled", finished_at: new Date().toISOString(), error: "stopped from the app" }).eq("id", runId).eq("status", "running"));
}

/** Replace a game's flow with one built by analyzer/flow.py (admin only; the worker writes it directly). */
export async function saveFlow(gameId: string, data: FlowData): Promise<void> {
  if (!data || data.v !== 1 || !data.h || !data.seam || !Array.isArray(data.m)) throw new Error("That isn't a match flow file.");
  unwrap(await supabase.from("game_flow").delete().eq("game_id", gameId));
  unwrap(await supabase.from("game_flow").insert({ game_id: gameId, data }));
}

export async function getGameBundle(id: string): Promise<GameBundle> {
  const [g, v, t, s, ts, b, sh, r, pe] = await Promise.all([
    supabase.from("games").select("*").eq("id", id).single(),
    supabase.from("videos").select("*").eq("game_id", id).order("created_at"),
    supabase.from("tags").select("*").eq("game_id", id).order("t_seconds"),
    supabase.from("shots").select("*").eq("game_id", id),
    supabase.from("team_stats").select("*").eq("game_id", id).order("created_at"),
    supabase.from("stat_buckets").select("*").eq("game_id", id).order("bucket_start_s"),
    supabase.from("shape_snapshots").select("*").eq("game_id", id),
    supabase.from("stat_runs").select("*").eq("game_id", id).order("created_at", { ascending: false }),
    supabase.from("pass_events").select("*").eq("game_id", id).order("t_seconds"),
  ]);
  return {
    game: unwrap(g) as Game,
    videos: unwrap(v) as Video[],
    tags: unwrap(t) as Tag[],
    shots: unwrap(s) as Shot[],
    teamStats: unwrap(ts) as TeamStats[],
    buckets: unwrap(b) as StatBucket[],
    shapes: unwrap(sh) as ShapeSnapshot[],
    runs: unwrap(r) as StatRun[],
    passes: unwrap(pe) as PassEvent[],
  };
}

export async function createGame(input: Partial<Game>): Promise<Game> {
  return unwrap(await supabase.from("games").insert(input).select().single()) as Game;
}

export async function updateGame(id: string, patch: Partial<Game>): Promise<Game> {
  return unwrap(await supabase.from("games").update(patch).eq("id", id).select().single()) as Game;
}

export async function deleteGame(id: string): Promise<void> {
  unwrap(await supabase.from("games").delete().eq("id", id));
}

// ---- Videos ----------------------------------------------------------------

export async function addVideo(input: Partial<Video>): Promise<Video> {
  return unwrap(await supabase.from("videos").insert(input).select().single()) as Video;
}

export async function updateVideo(id: string, patch: Partial<Video>): Promise<Video> {
  return unwrap(await supabase.from("videos").update(patch).eq("id", id).select().single()) as Video;
}

export async function deleteVideo(id: string): Promise<void> {
  unwrap(await supabase.from("videos").delete().eq("id", id));
}

// ---- Tags ------------------------------------------------------------------

export async function addTag(input: Partial<Tag>): Promise<Tag> {
  return unwrap(await supabase.from("tags").insert(input).select().single()) as Tag;
}

export async function updateTag(id: string, patch: Partial<Tag>): Promise<Tag> {
  return unwrap(await supabase.from("tags").update(patch).eq("id", id).select().single()) as Tag;
}

export async function deleteTag(id: string): Promise<void> {
  unwrap(await supabase.from("tags").delete().eq("id", id));
}

// ---- Shots -----------------------------------------------------------------

export async function upsertShot(input: Partial<Shot> & { tag_id: string; game_id: string }): Promise<Shot> {
  return unwrap(
    await supabase.from("shots").upsert(input, { onConflict: "tag_id" }).select().single(),
  ) as Shot;
}

export async function deleteShotByTag(tagId: string): Promise<void> {
  unwrap(await supabase.from("shots").delete().eq("tag_id", tagId));
}

// ---- Stats -----------------------------------------------------------------

export async function upsertHumanTeamStats(input: Partial<TeamStats> & { game_id: string; team: string; period: string }): Promise<TeamStats> {
  // One human_adjusted row per (game, team, period). Delete then insert keeps it simple.
  await supabase.from("team_stats").delete()
    .eq("game_id", input.game_id).eq("team", input.team).eq("period", input.period).eq("source", "human_adjusted");
  return unwrap(
    await supabase.from("team_stats").insert({ ...input, source: "human_adjusted" }).select().single(),
  ) as TeamStats;
}

export async function queueStatRun(gameId: string, videoId: string): Promise<StatRun> {
  return unwrap(
    await supabase.from("stat_runs").insert({ game_id: gameId, video_id: videoId, status: "queued" }).select().single(),
  ) as StatRun;
}

// ---- Season-wide -----------------------------------------------------------

export interface SeasonData {
  games: GameRow[];
  tags: Tag[];
  shots: Shot[];
  teamStats: TeamStats[];
}

export async function loadSeason(): Promise<SeasonData> {
  const [g, t, s, ts] = await Promise.all([
    listGames(),
    supabase.from("tags").select("*"),
    supabase.from("shots").select("*"),
    supabase.from("team_stats").select("*"),
  ]);
  return { games: g, tags: unwrap(t) as Tag[], shots: unwrap(s) as Shot[], teamStats: unwrap(ts) as TeamStats[] };
}

export async function listOpponents(): Promise<string[]> {
  const rows = unwrap(await supabase.from("games").select("opponent")) as { opponent: string }[];
  return Array.from(new Set(rows.map((r) => r.opponent))).sort((a, b) => a.localeCompare(b));
}

export type { StatBucket };
