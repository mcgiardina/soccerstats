import { useMemo, useState } from "react";
import type { Tag, Video } from "../lib/types";
import { buildChapters } from "../lib/chapters";
import { copyText } from "../lib/links";

export default function ChaptersExport({ video, tags }: { video: Video; tags: Tag[] }) {
  const text = useMemo(() => buildChapters(video, tags), [video, tags]);
  const [copied, setCopied] = useState(false);
  const lines = text.split("\n").length;
  return (
    <div>
      <p className="small muted">Paste this into the YouTube video description. Chapters appear on any device, no app needed. YouTube needs ≥3 chapters, each ≥10s; this list already respects that.</p>
      <pre className="chapters">{text}</pre>
      <div className="row">
        <button className="btn primary" onClick={async () => { setCopied(await copyText(text)); setTimeout(() => setCopied(false), 1500); }}>{copied ? "Copied ✓" : "Copy to clipboard"}</button>
        <span className="small muted">{lines} chapter{lines === 1 ? "" : "s"}{lines < 3 ? " — add more tags for YouTube to show chapters" : ""}</span>
      </div>
    </div>
  );
}
