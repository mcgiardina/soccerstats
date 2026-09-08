import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import ReportCard from "../components/ReportCard";
import { getGameBundle } from "../lib/api";
import type { GameBundle } from "../lib/types";
import { useAuth } from "../lib/auth";
import { shareUrl, copyText } from "../lib/links";

export default function ReportPage() {
  const { id = "" } = useParams();
  const { isAdmin } = useAuth();
  const [b, setB] = useState<GameBundle | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { getGameBundle(id).then(setB).catch((e) => setErr(e.message)); }, [id, isAdmin]);
  if (err) return <div className="page"><div className="card err">Not available. {err}</div></div>;
  if (!b) return <div className="page muted">Loading…</div>;
  return (
    <div className="page" style={{ maxWidth: 480 }}>
      <div className="row" style={{ justifyContent: "space-between", marginBottom: ".75rem" }}>
        <Link to={isAdmin ? `/games/${id}` : `/g/${id}`} className="small">← Game</Link>
        <button className="btn sm" onClick={() => copyText(`${shareUrl(id)}/report`)}>Copy link</button>
      </div>
      <ReportCard b={b} />
      <p className="tiny muted" style={{ textAlign: "center", marginTop: ".75rem" }}>Screenshot-friendly. Long-press to save on a phone.</p>
    </div>
  );
}
