import { useState } from "react";
import Modal from "./Modal";
import type { SetPieceOutcome, Tag, TagType, Team } from "../lib/types";
import { SET_PIECE_TYPES, TAG_LABELS } from "../lib/types";
import { fmtClock } from "../lib/time";

interface Props {
  tag: Partial<Tag> & { t_seconds: number; type: TagType };
  onSave: (patch: Partial<Tag>) => Promise<void>;
  onClose: () => void;
  /** Quick mode: opened right after a hotkey; only asks what is needed. */
  quick?: boolean;
}

export default function TagEditor({ tag, onSave, onClose, quick }: Props) {
  const [type, setType] = useState<TagType>(tag.type);
  const [team, setTeam] = useState<Team>(tag.team ?? "us");
  const [outcome, setOutcome] = useState<SetPieceOutcome | "">(tag.outcome ?? "");
  const [label, setLabel] = useState(tag.label ?? "");
  const [t, setT] = useState(tag.t_seconds);
  const isSetPiece = SET_PIECE_TYPES.includes(type);

  async function save() {
    await onSave({ type, team, outcome: isSetPiece && outcome ? outcome : null, label: label.trim() || null, t_seconds: t });
    onClose();
  }

  return (
    <Modal onClose={onClose} title={quick ? `${TAG_LABELS[type]} · ${team}` : "Edit tag"}>
      {!quick ? (
        <div className="form-grid">
          <label className="field"><span>Type</span>
            <select value={type} onChange={(e) => setType(e.target.value as TagType)}>
              {(Object.keys(TAG_LABELS) as TagType[]).map((k) => <option key={k} value={k}>{TAG_LABELS[k]}</option>)}
            </select>
          </label>
          <label className="field"><span>Team</span>
            <select value={team} onChange={(e) => setTeam(e.target.value as Team)}><option value="us">us</option><option value="them">them</option></select>
          </label>
          <label className="field"><span>Video time (seconds) · {fmtClock(t)}</span>
            <input type="number" step="0.5" value={t} onChange={(e) => setT(Number(e.target.value))} />
          </label>
        </div>
      ) : null}
      {isSetPiece ? (
        <label className="field"><span>Outcome</span>
          <div className="row">
            {(["goal", "shot", "cleared", "lost"] as SetPieceOutcome[]).map((o) => (
              <button key={o} className={`btn ${outcome === o ? "primary" : ""}`} onClick={() => setOutcome(o)} autoFocus={o === "goal" && quick}>{o}</button>
            ))}
          </div>
        </label>
      ) : null}
      <label className="field"><span>Label (optional)</span>
        <input type="text" value={label} autoFocus={!isSetPiece} onChange={(e) => setLabel(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") save(); }} placeholder={type === "note" ? "What happened?" : "e.g. counter, header, long ball"} />
      </label>
      <div className="row" style={{ justifyContent: "flex-end" }}>
        <button className="btn" onClick={onClose}>Cancel</button>
        <button className="btn primary" onClick={save}>Save</button>
      </div>
    </Modal>
  );
}
