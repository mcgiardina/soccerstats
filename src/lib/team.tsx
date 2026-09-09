import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { supabase } from "./supabase";
import { CONFIG } from "../config";

// Team identity and parent-visible sections, editable by the admin (Settings) and, for the
// hidden list, by anyone holding the coach link. Falls back to src/config.ts.

export interface TeamPublic {
  team_name: string | null; short_name: string | null; logo_data_url: string | null;
  primary_color: string | null; accent_color: string | null;
  pitch_length_m: number | null; pitch_width_m: number | null;
  hidden: string[];
}

/** Everything a coach or admin can hide from the public view. */
export const GATEABLE: { key: string; label: string; group: string }[] = [
  { key: "possession", label: "Possession gauges", group: "Stats" },
  { key: "xg", label: "xG and xG per shot", group: "Stats" },
  { key: "turnovers", label: "Turnovers", group: "Stats" },
  { key: "saves", label: "Saves", group: "Stats" },
  { key: "accuracy", label: "Shot accuracy", group: "Stats" },
  { key: "setpieces", label: "Corners, free kicks, penalties", group: "Stats" },
  { key: "shotmap", label: "Shot map", group: "Sections" },
  { key: "momentum", label: "Momentum bars", group: "Sections" },
  { key: "stats", label: "Whole stats panel", group: "Sections" },
  { key: "tags", label: "Tag list and timeline markers", group: "Sections" },
  { key: "report", label: "Report card", group: "Sections" },
  { key: "trends", label: "Season trend charts", group: "Season" },
  { key: "opponent", label: "Opponent history pages", group: "Season" },
];

interface TeamState {
  team: TeamPublic;
  name: string; shortName: string; logo: string | null;
  pitch: { lengthM: number; widthM: number };
  hidden: Set<string>;
  /** true for admins and coach-link holders: gates don't apply */
  canSeeAll: boolean;
  isCoach: boolean;
  coachToken: string | null;
  reload: () => Promise<void>;
  setCoachToken: (t: string | null) => void;
}

const EMPTY: TeamPublic = { team_name: null, short_name: null, logo_data_url: null, primary_color: null, accent_color: null, pitch_length_m: null, pitch_width_m: null, hidden: [] };
const Ctx = createContext<TeamState>(null as unknown as TeamState);
const TOKEN_KEY = "matchfilm.coachToken";

export function TeamProvider({ children, isAdmin }: { children: ReactNode; isAdmin: boolean }) {
  const [team, setTeam] = useState<TeamPublic>(EMPTY);
  const [coachToken, setTok] = useState<string | null>(() => { try { return localStorage.getItem(TOKEN_KEY); } catch { return null; } });
  const [isCoach, setIsCoach] = useState(false);

  const reload = useCallback(async () => {
    const { data } = await supabase.from("team_public").select("*").eq("id", 1).maybeSingle();
    if (data) setTeam({ ...EMPTY, ...data, hidden: Array.isArray(data.hidden) ? data.hidden : [] });
  }, []);
  useEffect(() => { reload(); }, [reload]);

  useEffect(() => {
    if (!coachToken) { setIsCoach(false); return; }
    supabase.rpc("coach_check", { p_token: coachToken }).then(({ data }) => setIsCoach(Boolean(data)));
  }, [coachToken]);

  const setCoachToken = useCallback((t: string | null) => {
    try { if (t) localStorage.setItem(TOKEN_KEY, t); else localStorage.removeItem(TOKEN_KEY); } catch { /* ignore */ }
    setTok(t);
  }, []);

  // brand colours apply live
  useEffect(() => {
    const r = document.documentElement.style;
    r.setProperty("--primary", team.primary_color || CONFIG.colors.primary);
    r.setProperty("--us", team.primary_color || CONFIG.colors.primary);
    r.setProperty("--accent", team.accent_color || CONFIG.colors.accent);
    document.title = team.team_name ? `${CONFIG.appName} · ${team.team_name}` : CONFIG.appName;
  }, [team]);

  const value = useMemo<TeamState>(() => ({
    team,
    name: team.team_name || CONFIG.teamName,
    shortName: team.short_name || team.team_name || CONFIG.teamName,
    logo: team.logo_data_url || CONFIG.logoUrl,
    pitch: { lengthM: team.pitch_length_m ?? CONFIG.pitch.lengthM, widthM: team.pitch_width_m ?? CONFIG.pitch.widthM },
    hidden: new Set(team.hidden),
    canSeeAll: isAdmin || isCoach,
    isCoach, coachToken, reload, setCoachToken,
  }), [team, isAdmin, isCoach, coachToken, reload, setCoachToken]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useTeam() { return useContext(Ctx); }

/** true when a gated key should be shown to the current viewer */
export function useShow() {
  const t = useTeam();
  return (key: string) => t.canSeeAll || !t.hidden.has(key);
}


/** Compact display name for an opponent: drop a "TEST " prefix and any parenthetical, cap the length. */
export function shortOpponent(name: string, max = 16): string {
  let n = name.replace(/^TEST\s+/i, "").replace(/\s*\(.*?\)\s*/g, " ").trim();
  if (n.length > max) n = n.slice(0, max - 1).trimEnd() + "…";
  return n || name;
}

/** Names to print instead of "us" / "them" for a given game. */
export function useTeamNames(opponent: string | null | undefined) {
  const t = useTeam();
  const them = opponent ? shortOpponent(opponent) : "Them";
  return { us: t.shortName, them, full: { us: t.name, them: opponent ?? "Them" }, of: (side: "us" | "them" | null | undefined) => (side === "us" ? t.shortName : side === "them" ? them : "—") };
}
