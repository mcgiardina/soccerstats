// Circular tick gauge: 60 ticks around a ring, the first `value`% lit. Big numeral in the centre.
export default function Gauge({ value, label, chip, side = "us", unit = "%" }: {
  value: number | null; label: string; chip?: React.ReactNode; side?: "us" | "them"; unit?: string;
}) {
  const ticks = 60;
  const lit = value == null ? 0 : Math.round((Math.max(0, Math.min(100, value)) / 100) * ticks);
  const r = 46, cx = 60, cy = 60;
  return (
    <div className={`gauge ${side}`}>
      <svg viewBox="0 0 120 120" role="img" aria-label={`${label} ${value == null ? "unknown" : value + unit}`}>
        {Array.from({ length: ticks }, (_, i) => {
          const a = (-90 + (i / ticks) * 360) * (Math.PI / 180);
          const long = i % 5 === 0;
          const r1 = r - (long ? 7 : 4), r2 = r + 2;
          return <line key={i} className={`g-tick ${i < lit ? "on" : ""}`} x1={cx + r1 * Math.cos(a)} y1={cy + r1 * Math.sin(a)} x2={cx + r2 * Math.cos(a)} y2={cy + r2 * Math.sin(a)} />;
        })}
        <text x={cx} y={cy + 9} textAnchor="middle" className="g-num">{value == null ? "—" : Math.round(value)}<tspan className="g-unit">{value == null ? "" : unit}</tspan></text>
      </svg>
      <div className="g-label">{label}</div>
      {chip ? <div className="g-chip">{chip}</div> : null}
    </div>
  );
}
