import { useEffect, useRef, useState } from "react";

// One-panel date range picker: a pill that opens a two-month calendar. Click a start day,
// then an end day. Presets on the left. No dependencies. Values are ISO yyyy-mm-dd strings.
interface Props { from: string; to: string; onChange: (from: string, to: string) => void }

const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const parse = (s: string) => { const [y, m, d] = s.split("-").map(Number); return new Date(y, m - 1, d); };
const fmt = (s: string) => parse(s).toLocaleDateString(undefined, { month: "short", day: "numeric" });
const monthName = (d: Date) => d.toLocaleDateString(undefined, { month: "long", year: "numeric" });

function Month({ base, from, to, hover, onPick, onHover }: { base: Date; from: string; to: string; hover: string; onPick: (d: string) => void; onHover: (d: string) => void }) {
  const first = new Date(base.getFullYear(), base.getMonth(), 1);
  const lead = (first.getDay() + 6) % 7; // Monday first
  const days = new Date(base.getFullYear(), base.getMonth() + 1, 0).getDate();
  const cells: (string | null)[] = [...Array(lead).fill(null), ...Array.from({ length: days }, (_, i) => iso(new Date(base.getFullYear(), base.getMonth(), i + 1)))];
  const end = to || (from && hover && hover > from ? hover : "");
  return (
    <div className="drp-month">
      <div className="drp-title">{monthName(base)}</div>
      <div className="drp-grid">
        {["M", "T", "W", "T", "F", "S", "S"].map((d, i) => <div key={i} className="drp-dow">{d}</div>)}
        {cells.map((d, i) => {
          if (!d) return <div key={i} />;
          const inRange = from && end && d > from && d < end;
          const isEdge = d === from || d === to || (d === end && !to);
          return (
            <button key={d} type="button" className={`drp-day ${inRange ? "in" : ""} ${isEdge ? "edge" : ""}`} onClick={() => onPick(d)} onMouseEnter={() => onHover(d)}>{Number(d.slice(8))}</button>
          );
        })}
      </div>
    </div>
  );
}

export default function DateRangePicker({ from, to, onChange }: Props) {
  const [open, setOpen] = useState(false);
  const [hover, setHover] = useState("");
  const [view, setView] = useState(() => { const d = to ? parse(to) : new Date(); return new Date(d.getFullYear(), d.getMonth() - 1, 1); });
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", close); document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", esc); };
  }, [open]);

  function pick(d: string) {
    if (!from || (from && to)) { onChange(d, ""); return; }
    if (d < from) { onChange(d, from); } else { onChange(from, d); }
    setOpen(false);
  }
  const today = new Date();
  const preset = (days: number | "month" | "all") => {
    if (days === "all") { onChange("", ""); setOpen(false); return; }
    if (days === "month") { onChange(iso(new Date(today.getFullYear(), today.getMonth(), 1)), iso(today)); setOpen(false); return; }
    const s = new Date(today); s.setDate(s.getDate() - days); onChange(iso(s), iso(today)); setOpen(false);
  };
  const label = from && to ? `${fmt(from)} – ${fmt(to)}` : from ? `${fmt(from)} → pick end` : "Any dates";
  const next = new Date(view.getFullYear(), view.getMonth() + 1, 1);

  return (
    <div className="drp" ref={ref}>
      <button type="button" className={`btn ${from ? "primary" : ""}`} onClick={() => setOpen((o) => !o)} aria-haspopup="dialog" aria-expanded={open}>
        <svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="5" width="18" height="16" rx="3" /><path d="M3 10h18M8 3v4M16 3v4" /></svg>
        {label}
        {from ? <span className="drp-clear" role="button" aria-label="Clear dates" onClick={(e) => { e.stopPropagation(); onChange("", ""); }}>✕</span> : null}
      </button>
      {open ? (
        <div className="drp-pop" role="dialog" aria-label="Choose a date range">
          <div className="drp-presets">
            <button type="button" onClick={() => preset(30)}>Last 30 days</button>
            <button type="button" onClick={() => preset(90)}>Last 90 days</button>
            <button type="button" onClick={() => preset("month")}>This month</button>
            <button type="button" onClick={() => preset("all")}>All dates</button>
          </div>
          <div className="drp-cal">
            <div className="drp-nav">
              <button type="button" className="btn icon" onClick={() => setView(new Date(view.getFullYear(), view.getMonth() - 1, 1))} aria-label="Earlier">‹</button>
              <span className="tiny muted">{from && !to ? "Now pick the end date" : "Pick a start date"}</span>
              <button type="button" className="btn icon" onClick={() => setView(new Date(view.getFullYear(), view.getMonth() + 1, 1))} aria-label="Later">›</button>
            </div>
            <div className="drp-months">
              <Month base={view} from={from} to={to} hover={hover} onPick={pick} onHover={setHover} />
              <Month base={next} from={from} to={to} hover={hover} onPick={pick} onHover={setHover} />
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
