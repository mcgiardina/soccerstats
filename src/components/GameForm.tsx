import { useEffect, useState } from "react";
import type { Game } from "../lib/types";
import { CONFIG } from "../config";

export type GameInput = Omit<Game, "id" | "created_at" | "published">;

interface Props {
  initial?: Partial<Game>;
  opponents: string[];
  onSubmit: (g: GameInput) => Promise<void>;
  submitLabel?: string;
  onOpponentChange?: (name: string) => void;
}

export default function GameForm({ initial, opponents, onSubmit, submitLabel = "Save", onOpponentChange }: Props) {
  const [f, setF] = useState<GameInput>({
    played_on: initial?.played_on ?? new Date().toISOString().slice(0, 10),
    opponent: initial?.opponent ?? "",
    home_away: initial?.home_away ?? "home",
    competition: initial?.competition ?? "league",
    venue: initial?.venue ?? "",
    score_us: initial?.score_us ?? null,
    score_them: initial?.score_them ?? null,
    pitch_length_m: initial?.pitch_length_m ?? null,
    pitch_width_m: initial?.pitch_width_m ?? null,
    notes: initial?.notes ?? "",
  });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { onOpponentChange?.(f.opponent); }, [f.opponent, onOpponentChange]);

  const set = <K extends keyof GameInput>(k: K, v: GameInput[K]) => setF((p) => ({ ...p, [k]: v }));
  const num = (v: string) => (v === "" ? null : Number(v));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!f.opponent.trim()) { setErr("Opponent is required."); return; }
    setBusy(true); setErr(null);
    try { await onSubmit({ ...f, opponent: f.opponent.trim(), venue: f.venue?.trim() || null, notes: f.notes?.trim() || null }); }
    catch (ex) { setErr((ex as Error).message); }
    finally { setBusy(false); }
  }

  return (
    <form onSubmit={submit}>
      <div className="form-grid">
        <label className="field"><span>Date</span><input type="date" required value={f.played_on} onChange={(e) => set("played_on", e.target.value)} /></label>
        <label className="field"><span>Opponent</span><input type="text" required list="opponents" value={f.opponent} onChange={(e) => set("opponent", e.target.value)} placeholder="Team name" />
          <datalist id="opponents">{opponents.map((o) => <option key={o} value={o} />)}</datalist></label>
        <label className="field"><span>Home / away</span>
          <select value={f.home_away ?? "home"} onChange={(e) => set("home_away", e.target.value as Game["home_away"])}><option value="home">Home</option><option value="away">Away</option><option value="neutral">Neutral</option></select></label>
        <label className="field"><span>Competition</span>
          <select value={f.competition ?? "league"} onChange={(e) => set("competition", e.target.value)}><option value="league">League</option><option value="tournament">Tournament</option><option value="friendly">Friendly</option></select></label>
        <label className="field"><span>Venue</span><input type="text" value={f.venue ?? ""} onChange={(e) => set("venue", e.target.value)} /></label>
        <div className="row" style={{ alignItems: "flex-end" }}>
          <label className="field" style={{ flex: 1 }}><span>Score us</span><input type="number" min={0} value={f.score_us ?? ""} onChange={(e) => set("score_us", num(e.target.value))} /></label>
          <label className="field" style={{ flex: 1 }}><span>Score them</span><input type="number" min={0} value={f.score_them ?? ""} onChange={(e) => set("score_them", num(e.target.value))} /></label>
        </div>
        <label className="field"><span>Pitch length (m) · default {CONFIG.pitch.lengthM}</span><input type="number" step="0.5" value={f.pitch_length_m ?? ""} onChange={(e) => set("pitch_length_m", num(e.target.value))} placeholder={String(CONFIG.pitch.lengthM)} /></label>
        <label className="field"><span>Pitch width (m) · default {CONFIG.pitch.widthM}</span><input type="number" step="0.5" value={f.pitch_width_m ?? ""} onChange={(e) => set("pitch_width_m", num(e.target.value))} placeholder={String(CONFIG.pitch.widthM)} /></label>
      </div>
      <label className="field"><span>Notes</span><textarea value={f.notes ?? ""} onChange={(e) => set("notes", e.target.value)} placeholder="Coach notes, conditions, anything searchable later" /></label>
      {err ? <p className="err small">{err}</p> : null}
      <button className="btn primary" type="submit" disabled={busy}>{busy ? "Saving…" : submitLabel}</button>
    </form>
  );
}
