import { useEffect, useRef, useState } from "react";
import FlowField from "../components/FlowField";
import VideoPlayer from "../components/VideoPlayer";
import type { PlayerHandle } from "../components/YouTubePlayer";
import { resolveSource } from "../lib/sources";
import type { FlowData, Video } from "../lib/types";

// The first real wide-camera game, before it has a game page of its own. The film plays straight
// from its BallerCam share link. Goal times are the true ones (video clock); the rest is the machine's.
const GOALS = [{ t: 1740, team: "them" as const }, { t: 3654, team: "them" as const }, { t: 4596, team: "us" as const }, { t: 5398, team: "them" as const }];
const LINK = "https://app.ballercam.com/streams/athletic-soccer-club-long-beach-bu13-vs-possible-fc-bu13-20260912031107-ogosfqtj";

export default function FlowDemoPage() {
  const [flow, setFlow] = useState<FlowData | null>(null);
  const [video, setVideo] = useState<Video | null>(null);
  const player = useRef<PlayerHandle>(null);
  useEffect(() => { fetch("/demo/flow.json").then((r) => r.json()).then(setFlow).catch(() => setFlow(null)); }, []);
  useEffect(() => {
    resolveSource(LINK).then((r) => setVideo({ id: "demo", game_id: "demo", kind: "upload", duration_seconds: null, kickoff_offset_seconds: 0, halftime_offset_seconds: null, second_half_offset_seconds: null, fulltime_offset_seconds: null, created_at: "", ...r.video })).catch(() => setVideo(null));
  }, []);
  return (
    <div className="page">
      <h1>Match flow</h1>
      <p className="small muted">ASC Long Beach BU13 1–3 Possible FC BU13 · 20 Sep 2026 · from the fixed wide camera. Machine estimate.</p>
      {flow ? <FlowField flow={flow} names={{ us: "ASC LB", them: "Possible FC" }} colors={{ us: "#ffffff", them: "#111111" }} goals={GOALS} storageKey="demo" onSeek={video ? (t) => { player.current?.seek(t); document.getElementById("demo-film")?.scrollIntoView({ behavior: "smooth", block: "center" }); } : undefined} /> : <div className="card small muted">Loading…</div>}
      {video ? <div id="demo-film" style={{ marginTop: "1rem" }}><VideoPlayer ref={player} video={video} /></div> : null}
    </div>
  );
}
