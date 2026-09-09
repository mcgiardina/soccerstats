import { useState } from "react";
import Modal from "./Modal";
import PitchMap from "./PitchMap";
import type { Shot, Tag, Team } from "../lib/types";
import { computeXg, XG_MODEL_VERSION } from "../lib/xg";

interface Props {
  tag: Tag;
  existing: Shot | null;
  pitch: { lengthM: number; widthM: number };
  onSave: (shot: Partial<Shot>) => Promise<void>;
  onClose: () => void;
}

export default function ShotPlacer({ tag, existing, pitch, onSave, onClose }: Props) {
  const team: Team = tag.team ?? "us";
  const [pos, setPos] = useState<[number, number] | null>(
    existing?.pitch_x != null && existing.pitch_y != null ? [existing.pitch_x, existing.pitch_y] : null,
  );
  const isGoal = tag.type === "goal" || tag.outcome === "goal";
  const [onTarget, setOnTarget] = useState<boolean | null>(existing?.on_target ?? (isGoal ? true : null));
  const [bodyPart, setBodyPart] = useState<"foot" | "head" | "">((existing?.body_part as "foot" | "head") ?? "");
  const [saving, setSaving] = useState(false);

  const xg = pos ? computeXg(pos[0], pos[1], pitch.lengthM, pitch.widthM) : null;
  const preview: Shot[] = pos
    ? [{ ...(existing ?? ({} as Shot)), id: "preview", tag_id: tag.id, game_id: tag.game_id, team, pitch_x: pos[0], pitch_y: pos[1], is_goal: isGoal, xg, location_source: "manual" } as Shot]
    : [];

  async function save() {
    setSaving(true);
    await onSave({
      team,
      pitch_x: pos?.[0] ?? null,
      pitch_y: pos?.[1] ?? null,
      location_source: pos ? "manual" : null,
      location_confidence: null,
      on_target: onTarget,
      is_goal: isGoal,
      body_part: bodyPart || null,
      xg,
      xg_model_version: pos ? XG_MODEL_VERSION : null,
    });
    setSaving(false);
    onClose();
  }

  return (
    <Modal onClose={onClose} title={`${isGoal ? "Goal" : "Shot"} location · ${team === "us" ? "us" : "them"}`}>
      <p className="small muted">Click where the shot was taken. Esc to skip; you can place it later from the tag list.</p>
      <PitchMap shots={preview} onPick={(x, y) => setPos([x, y])} pickTeam={team} />
      <div className="row" style={{ marginTop: ".6rem", justifyContent: "space-between" }}>
        <div className="row">
          <label className="small"><input type="radio" checked={onTarget === true} onChange={() => setOnTarget(true)} /> on target</label>
          <label className="small"><input type="radio" checked={onTarget === false} onChange={() => setOnTarget(false)} /> off target</label>
          <label className="small"><input type="radio" checked={onTarget === null} onChange={() => setOnTarget(null)} /> unknown</label>
        </div>
        <select value={bodyPart} onChange={(e) => setBodyPart(e.target.value as "foot" | "head" | "")} className="pill">
          <option value="">body part?</option>
          <option value="foot">foot</option>
          <option value="head">head</option>
        </select>
      </div>
      <div className="row" style={{ marginTop: ".75rem", justifyContent: "space-between" }}>
        <span className="small">{xg != null ? <>xG <strong>{xg.toFixed(2)}</strong> <span className="muted tiny">(pro-calibrated proxy)</span></> : <span className="muted">no location yet</span>}</span>
        <div className="row">
          <button className="btn" onClick={onClose}>Skip</button>
          <button className="btn primary" disabled={saving} onClick={save}>Save</button>
        </div>
      </div>
    </Modal>
  );
}
