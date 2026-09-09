import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { supabase } from "../lib/supabase";
import { GATEABLE, useTeam } from "../lib/team";

// Landing page for the coach link. Stores the token on this device and lets the coach
// choose what parents can see. No account: the link is the credential.
export default function CoachPage() {
  const [params] = useSearchParams();
  const team = useTeam();
  const [hidden, setHidden] = useState<string[]>([]);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    const t = params.get("token");
    if (t && t !== team.coachToken) team.setCoachToken(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params]);
  useEffect(() => { setHidden(Array.from(team.hidden)); }, [team.hidden]);

  async function save(next: string[]) {
    setHidden(next);
    const { data, error } = await supabase.rpc("coach_set_hidden", { p_token: team.coachToken, p_hidden: next });
    if (error || !data) { setMsg("Couldn't save. Is the link still valid?"); return; }
    setMsg("Saved"); setTimeout(() => setMsg(null), 1500);
    team.reload();
  }

  if (!team.coachToken) return <div className="page centered"><div className="card"><h1>Coach link</h1><p className="muted">This page needs the link the admin shared with you.</p></div></div>;
  if (!team.isCoach) return <div className="page centered"><div className="card"><h1>Link not valid</h1><p className="muted">This coach link has expired or was replaced. Ask the admin for the current one.</p><button className="btn sm" onClick={() => team.setCoachToken(null)}>Forget it</button></div></div>;

  const toggle = (k: string) => save(hidden.includes(k) ? hidden.filter((x) => x !== k) : [...hidden, k]);
  return (
    <div className="page" style={{ maxWidth: 720 }}>
      <div className="eyebrow">Coach</div>
      <h1>{team.name}</h1>
      <p className="muted">You're signed in with the coach link on this device. You see every stat, including ones hidden from parents, and you can change what they see below. <Link to="/">Go to the season →</Link></p>
      <div className="card">
        <h2>What parents can see</h2>
        {["Stats", "Sections", "Season"].map((g) => (
          <div key={g} style={{ marginBottom: ".6rem" }}>
            <div className="eyebrow" style={{ marginBottom: ".3rem" }}>{g}</div>
            <div className="row" style={{ gap: ".4rem" }}>
              {GATEABLE.filter((x) => x.group === g).map((x) => (
                <button key={x.key} className={`btn sm ${hidden.includes(x.key) ? "" : "primary"}`} onClick={() => toggle(x.key)} aria-pressed={!hidden.includes(x.key)}>{hidden.includes(x.key) ? "○" : "●"} {x.label}</button>
              ))}
            </div>
          </div>
        ))}
        {msg ? <div className="small muted" style={{ marginTop: ".5rem" }}>{msg}</div> : null}
      </div>
      <button className="btn sm" onClick={() => team.setCoachToken(null)}>Sign out of the coach link on this device</button>
    </div>
  );
}
