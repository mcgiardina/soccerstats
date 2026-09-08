import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../lib/auth";

export default function LoginPage() {
  const { login, isAdmin } = useAuth();
  const nav = useNavigate();
  const [pw, setPw] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    const msg = await login(pw);
    setBusy(false);
    if (msg) setErr(msg); else nav("/");
  }

  return (
    <div className="page" style={{ maxWidth: 420 }}>
      <div className="card">
        <h1>Admin</h1>
        {isAdmin ? <p className="ok">You are signed in.</p> : null}
        <form onSubmit={submit}>
          <label className="field"><span>Password</span><input type="password" autoFocus value={pw} onChange={(e) => setPw(e.target.value)} /></label>
          {err ? <p className="err small">{err}</p> : null}
          <button className="btn primary" disabled={busy || !pw}>Sign in</button>
        </form>
        <p className="tiny muted" style={{ marginTop: "1rem" }}>Parents and coaches don't need this. Published games are open to anyone with the link.</p>
      </div>
    </div>
  );
}
