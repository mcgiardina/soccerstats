import { useEffect, useState } from "react";
import { supabase } from "../lib/supabase";
import { GATEABLE, useTeam } from "../lib/team";
import { CONFIG } from "../config";
import { copyText } from "../lib/links";

interface Row { team_name: string | null; short_name: string | null; logo_data_url: string | null; primary_color: string | null; accent_color: string | null; pitch_length_m: number | null; pitch_width_m: number | null; coach_token: string; hidden: string[] }

export default function SettingsPage() {
  const team = useTeam();
  const [row, setRow] = useState<Row | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => { supabase.from("team_settings").select("*").eq("id", 1).single().then(({ data, error }) => { if (error) setMsg(error.message); else setRow(data as Row); }); }, []);

  const set = <K extends keyof Row>(k: K, v: Row[K]) => setRow((r) => (r ? { ...r, [k]: v } : r));

  async function save() {
    if (!row) return;
    setBusy(true);
    const { coach_token: _t, ...patch } = row;
    const { error } = await supabase.from("team_settings").update({ ...patch, updated_at: new Date().toISOString() }).eq("id", 1);
    setBusy(false);
    setMsg(error ? error.message : "Saved");
    if (!error) team.reload();
    setTimeout(() => setMsg(null), 2000);
  }

  async function rotateToken() {
    if (!confirm("Create a new coach link? The old link stops working immediately.")) return;
    const bytes = new Uint8Array(16); crypto.getRandomValues(bytes);
    const token = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
    const { error } = await supabase.from("team_settings").update({ coach_token: token }).eq("id", 1);
    if (!error) set("coach_token", token);
  }

  function onLogo(file: File | undefined) {
    if (!file) return;
    if (file.size > 400_000) { setMsg("Logo must be under 400 KB. A 512-pixel PNG is plenty."); return; }
    const reader = new FileReader();
    reader.onload = () => set("logo_data_url", String(reader.result));
    reader.readAsDataURL(file);
  }

  if (!row) return <div className="page muted">{msg ?? "Loading…"}</div>;
  const coachUrl = `${window.location.origin}/coach?token=${row.coach_token}`;
  const toggle = (k: string) => set("hidden", row.hidden.includes(k) ? row.hidden.filter((x) => x !== k) : [...row.hidden, k]);

  return (
    <div className="page" style={{ maxWidth: 820 }}>
      <div className="eyebrow">Admin</div>
      <h1>Team settings</h1>

      <div className="card">
        <h2>Identity</h2>
        <div className="form-grid">
          <label className="field"><span>Team name</span><input type="text" value={row.team_name ?? ""} onChange={(e) => set("team_name", e.target.value)} placeholder={CONFIG.teamName} /></label>
          <label className="field"><span>Short name (nav, score lines)</span><input type="text" value={row.short_name ?? ""} onChange={(e) => set("short_name", e.target.value)} placeholder="e.g. U13B" /></label>
          <label className="field"><span>Primary colour</span><div className="row"><input type="color" value={row.primary_color || CONFIG.colors.primary} onChange={(e) => set("primary_color", e.target.value)} style={{ width: 48, height: 36, padding: 2, borderRadius: 10 }} /><input type="text" value={row.primary_color ?? ""} onChange={(e) => set("primary_color", e.target.value)} placeholder={CONFIG.colors.primary} style={{ flex: 1 }} /></div></label>
          <label className="field"><span>Accent colour</span><div className="row"><input type="color" value={row.accent_color || CONFIG.colors.accent} onChange={(e) => set("accent_color", e.target.value)} style={{ width: 48, height: 36, padding: 2, borderRadius: 10 }} /><input type="text" value={row.accent_color ?? ""} onChange={(e) => set("accent_color", e.target.value)} placeholder={CONFIG.colors.accent} style={{ flex: 1 }} /></div></label>
          <label className="field"><span>Default pitch length (m)</span><input type="number" step="0.5" value={row.pitch_length_m ?? ""} onChange={(e) => set("pitch_length_m", e.target.value === "" ? null : Number(e.target.value))} placeholder={String(CONFIG.pitch.lengthM)} /></label>
          <label className="field"><span>Default pitch width (m)</span><input type="number" step="0.5" value={row.pitch_width_m ?? ""} onChange={(e) => set("pitch_width_m", e.target.value === "" ? null : Number(e.target.value))} placeholder={String(CONFIG.pitch.widthM)} /></label>
        </div>
        <label className="field"><span>Logo (PNG or SVG, under 400 KB)</span>
          <div className="row">
            {row.logo_data_url ? <img src={row.logo_data_url} alt="" style={{ height: 48, borderRadius: 10 }} /> : <span className="muted small">none</span>}
            <input type="file" accept="image/png,image/svg+xml,image/jpeg,image/webp" onChange={(e) => onLogo(e.target.files?.[0])} style={{ width: "auto" }} />
            {row.logo_data_url ? <button className="btn sm" onClick={() => set("logo_data_url", null)}>Remove</button> : null}
          </div>
        </label>
      </div>

      <div className="card">
        <h2>What parents can see</h2>
        <p className="small muted">Unticked items are hidden from anyone without the admin login or the coach link. Coaches can change this list too.</p>
        {["Stats", "Sections", "Season"].map((g) => (
          <div key={g} style={{ marginBottom: ".6rem" }}>
            <div className="eyebrow" style={{ marginBottom: ".3rem" }}>{g}</div>
            <div className="row" style={{ gap: ".4rem" }}>
              {GATEABLE.filter((x) => x.group === g).map((x) => (
                <button key={x.key} className={`btn sm ${row.hidden.includes(x.key) ? "" : "primary"}`} onClick={() => toggle(x.key)} aria-pressed={!row.hidden.includes(x.key)}>{row.hidden.includes(x.key) ? "○" : "●"} {x.label}</button>
              ))}
            </div>
          </div>
        ))}
      </div>

      <div className="card">
        <h2>Coach link</h2>
        <p className="small muted">Anyone opening this link sees everything, including hidden stats and unpublished games' proposals are still admin-only. They can also change what parents see. Share it privately; rotate it if it leaks.</p>
        <div className="row">
          <code style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{coachUrl}</code>
          <button className="btn sm" onClick={async () => setMsg((await copyText(coachUrl)) ? "Coach link copied" : "Copy failed")}>Copy</button>
          <button className="btn sm danger" onClick={rotateToken}>New link</button>
        </div>
      </div>

      <div className="row" style={{ justifyContent: "flex-end" }}>
        {msg ? <span className="small muted">{msg}</span> : null}
        <button className="btn primary" disabled={busy} onClick={save}>{busy ? "Saving…" : "Save settings"}</button>
      </div>
    </div>
  );
}
