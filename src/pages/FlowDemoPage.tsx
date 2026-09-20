import { useEffect, useState } from "react";
import FlowField from "../components/FlowField";
import type { FlowData } from "../lib/types";

// The first real wide-camera game, before it has a YouTube upload and a game page of its own.
// Goal times are the true ones (video clock); everything else is the machine's.
const GOALS = [{ t: 1740, team: "them" as const }, { t: 3654, team: "them" as const }, { t: 4596, team: "us" as const }, { t: 5398, team: "them" as const }];

export default function FlowDemoPage() {
  const [flow, setFlow] = useState<FlowData | null>(null);
  useEffect(() => { fetch("/demo/flow.json").then((r) => r.json()).then(setFlow).catch(() => setFlow(null)); }, []);
  return (
    <div className="page">
      <h1>Match flow</h1>
      <p className="small muted">ASC Long Beach BU13 1–3 Possible FC BU13 · 12 Sep 2026 · from the fixed wide camera. Machine estimate.</p>
      {flow ? <FlowField flow={flow} names={{ us: "ASC LB", them: "Possible FC" }} colors={{ us: "#ffffff", them: "#111111" }} goals={GOALS} /> : <div className="card small muted">Loading…</div>}
    </div>
  );
}
