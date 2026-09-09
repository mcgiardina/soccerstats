import { useState } from "react";
import Modal from "./Modal";
import PitchMap from "./PitchMap";
import type { Shot, Tag, Team } from "../lib/types";
import { computeXg, XG_MODEL_VERSION, CONTEXT_LABELS, ASSIST_LABELS, type ShotContext, type ShotAssist } from "../lib/xg";
import { useTeamNames } from "../lib/team";

interface Props {
  tag: Tag;
  existing: Shot | null;
  pitch: { lengthM: number; widthM: number };
  onSave: (shot: Partial<Shot>) => Promise<void>;
  onClose: () => void;
  opponent?: string | null;
}

export default function ShotPlacer({ tag, existing, pitch, onSave, onClose, opponent }: Props) {
  const team: Team = tag.team ?? "us";
  const names = useTeamNames(opponent);
  const [pos, setPos] = useState<[number, number] | null>(
    existing?.pitch_x != null && existing.pitch_y != null ? [existing.pitch_x, existing.pitch_y] : null,
  );
  const isGoal = tag.type === "goal" || tag.outcome === "goal";
  const [onTarget, setOnTarget] = useState<boolean | null>(existing?.on_target ?? (isGoal ? true : null));
  const [bodyPart, setBodyPart] = useState<"foot" | "head" | "">((existing?.body_part as "foot" | "head") ?? "");
  const defaultCtx: ShotContext = tag.type === "corner" ? "corner" : tag.type === "free_kick" ? "free_kick" : tag.type === "penalty" ? "penalty" : "regular";
  const [context, setContext] = useState<ShotContext>((existing?.context as ShotContext) ?? defaultCtx);
  const [assist, setAssist] = useState<ShotAssist>((existing?.assist as ShotAssist) ?? "none");
  const [saving, setSaving] = useState(false);

  const xgInputs = { context, assist, headed: bodyPart === "head" };
  const xg = pos ? computeXg(pos[0], pos[1], pitch.lengthM, pitch.widthM, xgInputs) : null;
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
      context,
      assist,
      xg,
      xg_model_version: pos ? XG_MODEL_VERSION : null,
    });
    setSaving(false);
    onClose();
  }

  return (
    <Modal onClose={onClose} title={`${isGoal ? "Goal" : "Shot"} location · ${names.of(team)}`}>
      <p className="small muted">Click where the shot was taken. Esc to skip; you can place it later from the tag list.</p>
      <PitchMap shots={preview} onPick={(x, y) => setPos([x, y])} pickTeam={team} attackLabel={`${names.of(team)} attack ${team === "us" ? "→" : "←"}`} />
      <div className="placer-opts">
        <div className="seg light">
          {(Object.keys(CONTEXT_LABELS) as ShotContext[]).map((k) => <button key={k} className={context === k ? "on" : ""} onClick={() => setContext(k)}>{CONTEXT_LABELS[k]}</button>)}
        </div>
        <div className="seg light">
          {(Object.keys(ASSIST_LABELS) as ShotAssist[]).map((k) => <button key={k} className={assist === k ? "on" : ""} onClick={() => setAssist(k)}>{ASSIST_LABELS[k]}</button>)}
        </div>
        <div className="row" style={{ justifyContent: "space-between" }}>
          <div className="seg light">
            <button className={bodyPart === "foot" ? "on" : ""} onClick={() => setBodyPart("foot")}>Foot</button>
            <button className={bodyPart === "head" ? "on" : ""} onClick={() => setBodyPart("head")}>Header</button>
            <button className={bodyPart === "" ? "on" : ""} onClick={() => setBodyPart("")}>?</button>
          </div>
          <div className="seg light">
            <button className={onTarget === true ? "on" : ""} onClick={() => setOnTarget(true)}>On target</button>
            <button className={onTarget === false ? "on" : ""} onClick={() => setOnTarget(false)}>Off</button>
            <button className={onTarget === null ? "on" : ""} onClick={() => setOnTarget(null)}>?</button>
          </div>
        </div>
      </div>
      <div className="row" style={{ marginTop: ".75rem", justifyContent: "space-between" }}>
        <span className="small">{xg != null ? <>xG <strong>{xg.toFixed(2)}</strong> <span className="muted tiny">({XG_MODEL_VERSION.startsWith("asa") ? "ASA xG 3.0" : "Soccermatics"}, pro-calibrated proxy)</span></> : <span className="muted">no location yet</span>}</span>
        <div className="row">
          <button className="btn" onClick={onClose}>Skip</button>
          <button className="btn primary" disabled={saving} onClick={save}>Save</button>
        </div>
      </div>
    </Modal>
  );
}
