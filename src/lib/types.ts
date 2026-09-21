export type Team = "us" | "them";
export type Period = "full" | "h1" | "h2";
export type TagType =
  | "goal" | "shot" | "chance" | "save" | "turnover"
  | "corner" | "free_kick" | "throw_in" | "penalty" | "foul" | "yellow_card" | "red_card" | "note";
export type SetPieceOutcome = "goal" | "shot" | "cleared" | "lost";

export const SET_PIECE_TYPES: TagType[] = ["corner", "free_kick", "throw_in", "penalty"];
/** Fouls and cards belong to the team that committed them. */
export const DISCIPLINE_TYPES: TagType[] = ["foul", "yellow_card", "red_card"];
export const SHOT_LIKE_TYPES: TagType[] = ["shot", "goal", "penalty"];

export const TAG_LABELS: Record<TagType, string> = {
  goal: "Goal", shot: "Shot", chance: "Chance", save: "Save", turnover: "Turnover",
  corner: "Corner", free_kick: "Free kick", throw_in: "Throw-in", penalty: "Penalty",
  foul: "Foul", yellow_card: "Yellow card", red_card: "Red card", note: "Note",
};

export interface Game {
  id: string;
  played_on: string;
  opponent: string;
  home_away: "home" | "away" | "neutral" | null;
  competition: string | null;
  venue: string | null;
  score_us: number | null;
  score_them: number | null;
  pitch_length_m: number | null;
  pitch_width_m: number | null;
  notes: string | null;
  kit_color: string | null;       // our kit colour this game (hex); the analyzer maps clusters to us/them with it
  opp_kit_color: string | null;   // their kit colour this game (hex); recolours event pills and shot dots
  published: boolean;
  created_at: string;
}

export interface Video {
  id: string;
  game_id: string;
  youtube_id: string | null;
  provider: "youtube" | "ballercam" | "veo" | "trace" | "xbot" | "file" | null;
  provider_ref: string | null;
  source_url: string | null;
  stream_url: string | null;   // HLS or mp4 the in-app player uses when there is no youtube_id
  raw_url: string | null;      // the camera's full-field file, for the analyzer only
  /** which way we attack in the first half as seen on the film; the second half is the other way */
  us_attack_h1: "left" | "right" | null;
  kind: "stream_archive" | "upload" | "wide_fixed" | null;
  title: string | null;
  duration_seconds: number | null;
  kickoff_offset_seconds: number;
  halftime_offset_seconds: number | null;
  second_half_offset_seconds: number | null;
  fulltime_offset_seconds: number | null;
  created_at: string;
}

export interface Tag {
  id: string;
  game_id: string;
  video_id: string | null;
  t_seconds: number;
  type: TagType;
  team: Team | null;
  outcome: SetPieceOutcome | null;
  label: string | null;
  source: "human" | "machine";
  confidence: number | null;
  confirmed: boolean | null;
  confirmed_at: string | null;
  created_at: string;
}

export interface Shot {
  id: string;
  game_id: string;
  tag_id: string;
  team: Team | null;
  pitch_x: number | null;
  pitch_y: number | null;
  location_source: "machine" | "manual" | null;
  location_confidence: number | null;
  on_target: boolean | null;
  is_goal: boolean;
  body_part: "foot" | "head" | null;
  context: "regular" | "corner" | "free_kick" | "indirect_free_kick" | "fastbreak" | "penalty" | null;
  assist: "none" | "cross" | "through_ball" | null;
  xg: number | null;
  xg_model_version: string | null;
  created_at: string;
}

export interface StatRun {
  id: string;
  game_id: string;
  video_id: string | null;
  model_version: string | null;
  params: Record<string, unknown> | null;
  status: "queued" | "running" | "done" | "failed" | "cancelled" | null;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  created_at: string;
}

export interface TeamStats {
  id: string;
  game_id: string;
  run_id: string | null;
  team: Team;
  period: Period;
  possession_pct: number | null;
  shots: number | null;
  shots_on_target: number | null;
  turnovers: number | null;
  xg_total: number | null;
  passes: number | null;
  passes_completed: number | null;
  ball_coverage: number | null;
  source: "machine" | "human_adjusted";
  created_at: string;
}

export interface StatBucket {
  id: string;
  game_id: string;
  run_id: string | null;
  bucket_start_s: number;
  bucket_end_s: number;
  possession_us_pct: number | null;
  ball_frames: number | null;
  turnovers_us: number | null;
  turnovers_them: number | null;
}

/** Match flow from the fixed wide camera (analyzer/flow.py). Times are video seconds; we attack right. */
export interface FlowData {
  v: number;
  step: number;
  t0: number;
  n: number;
  nx: number;
  ny: number;
  halves: [number, number][];
  /** which way we attacked in the first half as the camera saw it */
  us_attack_h1?: "left" | "right";
  h: string;      // base64 uint8 [n][ny][nx]: where the players are
  seam: string;   // base64 uint8 [n][ny]: the front between the teams, 0..255 along the pitch
  m: number[];    // -1..1, + = us on top
  attacks: { t: number; team: Team; score: number }[];
}

export interface ShapeSnapshot {
  id: string;
  game_id: string;
  run_id: string | null;
  t_seconds: number | null;
  period: string | null;
  team: Team | null;
  players_visible: number | null;
  homography_confidence: number | null;
  positions: { x: number; y: number }[] | null;
}

/** The film people watch: the panned/processed upload, never the wide-angle analysis source. */
export function mainVideo(videos: Video[]): Video | null {
  return videos.find((v) => v.kind !== "wide_fixed") ?? videos[0] ?? null;
}

export const VIDEO_KINDS: { value: NonNullable<Video["kind"]>; label: string; hint: string }[] = [
  { value: "upload", label: "Processed upload", hint: "The film people watch: a YouTube upload or the camera's own share link (BallerCam)" },
  { value: "stream_archive", label: "Stream archive", hint: "A live-stream recording" },
  { value: "wide_fixed", label: "Wide-angle source", hint: "Raw fisheye / fixed full-pitch camera, for analysis only; not shown to viewers" },
];

export interface PassEvent {
  id: string;
  game_id: string;
  run_id: string | null;
  t_seconds: number;
  team: Team | null;
  completed: boolean;
  outcome: "completed" | "incomplete" | "unknown" | null;
  from_x: number | null; from_y: number | null;
  to_x: number | null; to_y: number | null;
  third: "left" | "mid" | "right" | null;
  confidence: number | null;
}

export interface GameBundle {
  game: Game;
  videos: Video[];
  tags: Tag[];
  shots: Shot[];
  teamStats: TeamStats[];
  buckets: StatBucket[];
  shapes: ShapeSnapshot[];
  runs: StatRun[];
  passes: PassEvent[];
}
