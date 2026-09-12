import type { StatBucket } from "../lib/types";
import { fmtClock } from "../lib/time";

// Possession share per bucket, drawn as bars above/below the 50% line.
export default function Momentum({ buckets, names }: { buckets: StatBucket[]; names?: { us: string; them: string } }) {
  if (!buckets.length) return null;
  return (
    <div>
      <div className="momentum">
        {buckets.map((b) => {
          const p = b.possession_us_pct;
          if (p == null || !b.ball_frames) return <div key={b.id} className="b" style={{ height: 2, background: "var(--line-strong)" }} title="no data" />;
          const us = p >= 50;
          const h = Math.max(4, Math.abs(p - 50) / 50 * 48);
          return <div key={b.id} className={`b ${us ? "" : "them"}`} style={{ height: h }} title={`${fmtClock(b.bucket_start_s)}–${fmtClock(b.bucket_end_s)}: ${Math.round(p)}% ${names?.us ?? "us"} (${b.ball_frames} ball frames)`} />;
        })}
      </div>
      <div className="tiny muted">Momentum: taller = more one-sided possession in that 5-minute window. Teal = {names?.us ?? "us"}, pink = {names?.them ?? "them"}. Machine estimate.</div>
    </div>
  );
}
