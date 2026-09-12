export type Team = "us" | "them";
export type Period = "full" | "h1" | "h2";
export type TagType =
  | "goal" | "shot" | "chance" | "save" | "turnover"
  | "corner" | "free_kick" | "throw_in" | "penalty" | "note";
export type SetPieceOutcome = "goal" | "shot" | "cleared" | "lost";

export const SET_PIECE_TYPES: TagType[] = ["corner", "free_kick", "throw_in", "penalty"];
export const SHOT_LIKE_TYPES: TagType[] = ["shot", "goal", "penalty"];

export const TAG_LABELS: Record<TagType, string> = {
  goal: "Goal", shot: "Shot", chance: "Chance", save: "Save", turnover: "Turnover",
  corner: "Corner", free_kick: "Free kick", throw_in: "Throw-in", penalty: "Penalty", note: "Note",
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
  youtube_id: string;
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
  status: "queued" | "running" | "done" | "failed" | null;
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
  { value: "upload", label: "Processed upload", hint: "BallerCam 1080p file from the camera roll, uploaded to YouTube" },
  { value: "stream_archive", label: "Stream archive", hint: "A live-stream recording saved on YouTube" },
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
