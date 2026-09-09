import type { Game, Period, Shot, Tag, Team, TeamStats, Video } from "./types";
import { SET_PIECE_TYPES } from "./types";
import { periodOf } from "./time";

/** Tags a viewer should trust: human, or machine proposals a human confirmed. */
export function trustedTags(tags: Tag[]): Tag[] {
  return tags.filter((t) => t.source === "human" || t.confirmed === true);
}

export function isShotTag(t: Tag): boolean {
  if (t.type === "shot" || t.type === "goal") return true;
  if (t.type === "penalty") return true;
  if (SET_PIECE_TYPES.includes(t.type) && (t.outcome === "shot" || t.outcome === "goal")) return true;
  return false;
}

export function isGoalTag(t: Tag): boolean {
  return t.type === "goal" || (SET_PIECE_TYPES.includes(t.type) && t.outcome === "goal");
}

export interface SideSummary {
  goals: number;
  shots: number;
  shotsOnTarget: number | null;
  xg: number | null;
  xgShotsLocated: number;
  possession: number | null;
  possessionSource: "machine" | "human_adjusted" | null;
  turnovers: number | null;
  turnoversSource: "machine" | "human_adjusted" | null;
  corners: number;
  freeKicks: number;
  setPieceGoals: number;
  /** saves made by this side's keeper (human 'save' tags + confirmed machine saves) */
  saves: number;
  /** clear chances tagged that were not shots ('chance' tags) */
  chances: number;
  /** on-target share of shots, 0..1, when on-target data exists */
  accuracy: number | null;
  /** average xG per located shot */
  xgPerShot: number | null;
  penalties: number;
}

export interface GameSummary {
  us: SideSummary;
  them: SideSummary;
  period: Period;
}

function pickStats(rows: TeamStats[], team: Team, period: Period): TeamStats | null {
  const candidates = rows.filter((r) => r.team === team && r.period === period);
  return (
    candidates.find((r) => r.source === "human_adjusted") ??
    // newest machine row wins
    candidates.filter((r) => r.source === "machine").sort((a, b) => b.created_at.localeCompare(a.created_at))[0] ??
    null
  );
}

export function summarizeGame(
  game: Game,
  video: Video | null,
  tags: Tag[],
  shots: Shot[],
  teamStats: TeamStats[],
  period: Period = "full",
): GameSummary {
  const trusted = trustedTags(tags).filter((t) => period === "full" || periodOf(video, t.t_seconds) === period);
  const shotByTag = new Map(shots.map((s) => [s.tag_id, s]));

  function side(team: Team): SideSummary {
    const mine = trusted.filter((t) => t.team === team);
    const shotTags = mine.filter(isShotTag);
    let goals = mine.filter(isGoalTag).length;
    // Score entered on the game record is authoritative for full match if present.
    if (period === "full") {
      const s = team === "us" ? game.score_us : game.score_them;
      if (s != null) goals = s;
    }
    const located = shotTags
      .map((t) => shotByTag.get(t.id))
      .filter((s): s is Shot => Boolean(s && s.xg != null));
    const xg = located.length ? located.reduce((a, s) => a + (s.xg ?? 0), 0) : null;
    const onTargetKnown = shotTags.map((t) => shotByTag.get(t.id)).filter((s) => s && s.on_target != null);
    const shotsOnTarget = onTargetKnown.length
      ? onTargetKnown.filter((s) => s!.on_target).length + shotTags.filter((t) => isGoalTag(t) && shotByTag.get(t.id)?.on_target == null).length
      : null;
    const st = pickStats(teamStats, team, period);
    return {
      goals,
      shots: shotTags.length,
      shotsOnTarget,
      xg: xg == null ? null : Math.round(xg * 100) / 100,
      xgShotsLocated: located.length,
      possession: st?.possession_pct ?? null,
      possessionSource: st?.possession_pct != null ? st.source : null,
      turnovers: st?.turnovers ?? null,
      turnoversSource: st?.turnovers != null ? st.source : null,
      corners: mine.filter((t) => t.type === "corner").length,
      freeKicks: mine.filter((t) => t.type === "free_kick").length,
      setPieceGoals: mine.filter((t) => SET_PIECE_TYPES.includes(t.type) && t.outcome === "goal").length,
      saves: mine.filter((t) => t.type === "save").length,
      chances: mine.filter((t) => t.type === "chance").length,
      accuracy: shotsOnTarget != null && shotTags.length ? shotsOnTarget / shotTags.length : null,
      xgPerShot: xg != null && located.length ? Math.round((xg / located.length) * 100) / 100 : null,
      penalties: mine.filter((t) => t.type === "penalty").length,
    };
  }

  return { us: side("us"), them: side("them"), period };
}
