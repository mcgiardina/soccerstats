import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { FlowData } from "../lib/types";
import { luminance } from "../lib/kit";
import { fmtClock } from "../lib/time";

export interface FlowGoal { t: number; team: "us" | "them" }

interface Props {
  flow: FlowData;
  names: { us: string; them: string };
  colors: { us: string; them: string };
  goals?: FlowGoal[];
  onSeek?: (t: number) => void;
  /** remembers this viewer's colour choices for this game */
  storageKey?: string;
}

// Surface mesh. The data grid (20 x 10) is sampled smoothly onto this finer one.
const MX = 72, MY = 36;
const PITCH_W = 0.66;          // width / length of the drawn pitch
const RELIEF = 0.17;           // height of the tallest crowd of players, in pitch lengths
const SPIKE = 0.22;            // height of the strongest attack
const YAW = -0.42, ELEV = 0.6, DIST = 3.6;
const GAME_SECONDS_PER_SECOND = 75;   // the whole match in about 70 s
const GOAL_SLOWDOWN = 0.12;           // near a goal, time almost stops so it cannot be missed
const GOAL_SHOW_S = 75;               // game seconds the goal banner stays up
const SHADES = 14;

function decode(b64: string): Uint8Array {
  const s = atob(b64); const out = new Uint8Array(s.length);
  for (let i = 0; i < s.length; i++) out[i] = s.charCodeAt(i);
  return out;
}

function rgb(hex: string): [number, number, number] {
  const h = hex.replace("#", ""); const f = h.length === 3 ? h.split("").map((c) => c + c).join("") : h;
  return [0, 2, 4].map((i) => parseInt(f.slice(i, i + 2), 16)) as [number, number, number];
}

/** A kit colour as it should glow on the dark stage: black shirts become graphite, not a hole. */
function stageColor(hex: string, fallback: string): [number, number, number] {
  const ok = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.test(hex || "");
  const c = rgb(ok ? hex : fallback); const lum = luminance(ok ? hex : fallback);
  const lift = lum < 0.08 ? 0.36 : lum < 0.2 ? 0.18 : 0;
  return c.map((v) => Math.round(v + (255 - v) * lift)) as [number, number, number];
}

// Light kits (white, yellow) are drawn as a bright sheet and dark kits as a dark one with lit mesh
// lines, so white v black still reads as two teams.
function ramp(c: [number, number, number], light: boolean): { fill: string[]; line: string[] } {
  const fill: string[] = [], line: string[] = [];
  for (let i = 0; i < SHADES; i++) {
    const k = i / (SHADES - 1);
    const f = light ? 0.3 + 0.5 * k : 0.1 + 0.34 * k, l = light ? 0.7 + 0.3 * k : 0.42 + 0.58 * k;
    fill.push(`rgb(${c.map((v) => Math.round(v * f + 8 * (1 - f))).join(",")})`);
    line.push(`rgba(${c.map((v) => Math.round(v * l)).join(",")},${0.55 + 0.45 * k})`);
  }
  return { fill, line };
}

export default function FlowField({ flow, names, colors: kitColors, goals = [], onSeek, storageKey }: Props) {
  const wrap = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const spark = useRef<HTMLCanvasElement>(null);
  const tRef = useRef(flow.halves[0]?.[0] ?? flow.t0);
  const playing = useRef(false);
  const buf = useRef({ z: new Float32Array((MX + 1) * (MY + 1)), seam: new Float32Array(MY + 1), px: new Float32Array((MX + 1) * (MY + 1) * 2) });
  const [isPlaying, setPlaying] = useState(false);
  const [readout, setReadout] = useState<{ t: number; us: number; them: number; goal: FlowGoal | null }>({ t: tRef.current, us: 0, them: 0, goal: null });
  const [help, setHelp] = useState(false);
  // Kit colours are the default; anyone can pick their own (two dark kits, or a preference), kept on this device.
  const [picked, setPicked] = useState<{ us?: string; them?: string }>(() => {
    try { return storageKey ? JSON.parse(localStorage.getItem(`matchfilm.flow.${storageKey}`) ?? "{}") : {}; } catch { return {}; }
  });
  const pick = (side: "us" | "them", hex: string | undefined) => setPicked((p) => {
    const next = { ...p, [side]: hex }; if (!hex) delete next[side];
    try { if (storageKey) localStorage.setItem(`matchfilm.flow.${storageKey}`, JSON.stringify(next)); } catch { /* private mode */ }
    return next;
  });
  const colors = { us: picked.us ?? kitColors.us, them: picked.them ?? kitColors.them };

  const H = useMemo(() => decode(flow.h), [flow.h]);
  const S = useMemo(() => decode(flow.seam), [flow.seam]);
  const tEnd = flow.t0 + (flow.n - 1) * flow.step;
  const tStart = flow.halves[0]?.[0] ?? flow.t0;
  const tStop = flow.halves[flow.halves.length - 1]?.[1] ?? tEnd;
  const maxScore = useMemo(() => Math.max(12, ...flow.attacks.map((a) => a.score)), [flow.attacks]);
  const cUs = useMemo(() => stageColor(colors.us, "#7ecdb8"), [colors.us]);
  const cThem = useMemo(() => stageColor(colors.them, "#e07a5f"), [colors.them]);
  const pal = useMemo(() => ({ us: ramp(cUs, luminance(`#${cUs.map((v) => v.toString(16).padStart(2, "0")).join("")}`) > 0.55), them: ramp(cThem, luminance(`#${cThem.map((v) => v.toString(16).padStart(2, "0")).join("")}`) > 0.55) }), [cUs, cThem]);

  const matchMinute = useCallback((t: number) => {
    const [h1, h2] = flow.halves;
    if (!h1) return { label: fmtClock(t), half: "" };
    const h1Nominal = Math.max(5, Math.round((h1[1] - h1[0]) / 300) * 5);
    if (h2 && t >= h2[0]) return { label: `${h1Nominal + Math.floor((t - h2[0]) / 60) + 1}`, half: t > h2[1] ? "Full time" : "2nd half" };
    if (t > h1[1]) return { label: `${h1Nominal}`, half: "Half time" };
    return { label: `${Math.max(1, Math.floor((t - h1[0]) / 60) + 1)}`, half: "1st half" };
  }, [flow.halves]);

  // Height and seam at time t, sampled onto the mesh.
  const sample = useCallback((t: number, z: Float32Array, seam: Float32Array) => {
    const { nx, ny, n, step, t0 } = flow;
    const f = Math.min(n - 1.001, Math.max(0, (t - t0) / step)); const i0 = Math.floor(f), a = f - i0;
    const cell = (i: number, y: number, x: number) => H[(i * ny + y) * nx + x];
    const grid = (y: number, x: number) => (cell(i0, y, x) * (1 - a) + cell(i0 + 1, y, x) * a) / 255;
    const smooth = (k: number) => k * k * (3 - 2 * k);
    for (let my = 0; my <= MY; my++) {
      const gy = Math.min(ny - 1, Math.max(0, (my / MY) * ny - 0.5)); const y0 = Math.min(ny - 2, Math.floor(gy)), ky = smooth(gy - y0);
      const sv = (S[i0 * ny + y0] * (1 - a) + S[(i0 + 1) * ny + y0] * a) * (1 - ky) + (S[i0 * ny + y0 + 1] * (1 - a) + S[(i0 + 1) * ny + y0 + 1] * a) * ky;
      seam[my] = sv / 255;
      for (let mx = 0; mx <= MX; mx++) {
        const gx = Math.min(nx - 1, Math.max(0, (mx / MX) * nx - 0.5)); const x0 = Math.min(nx - 2, Math.floor(gx)), kx = smooth(gx - x0);
        const v = (grid(y0, x0) * (1 - kx) + grid(y0, x0 + 1) * kx) * (1 - ky) + (grid(y0 + 1, x0) * (1 - kx) + grid(y0 + 1, x0 + 1) * kx) * ky;
        // fade to the ground at the edges so the sheet has a clean rim
        const edge = Math.min(1, Math.min(mx, MX - mx) / 3) * Math.min(1, Math.min(my, MY - my) / 2.5);
        z[my * (MX + 1) + mx] = Math.pow(v, 0.8) * RELIEF * (0.35 + 0.65 * edge);
      }
    }
    // Attacks and goals: a spike at the goal mouth being attacked. We always attack to the right.
    const bump = (team: "us" | "them", amp: number, age: number, rise: number, fall: number) => {
      const env = age < 0 ? Math.exp(-0.5 * (age / rise) ** 2) : Math.exp(-age / fall);
      if (env < 0.02) return;
      const cu = team === "us" ? 0.955 : 0.045;
      for (let my = 0; my <= MY; my++) for (let mx = 0; mx <= MX; mx++) {
        const du = (mx / MX - cu) / 0.05, dv = (my / MY - 0.5) / 0.13;
        const g = Math.exp(-0.5 * (du * du + dv * dv));
        if (g > 0.01) z[my * (MX + 1) + mx] += g * amp * env;
      }
    };
    for (const at of flow.attacks) if (Math.abs(at.t - t) < 90) bump(at.team, SPIKE * Math.min(1, at.score / maxScore) * 0.8, t - at.t, 5, 14);
    for (const g of goals) if (Math.abs(g.t - t) < 140) bump(g.team, SPIKE * 0.95, t - g.t, 4, 30);
  }, [flow, H, S, goals, maxScore]);

  const draw = useCallback(() => {
    const cv = canvas.current; if (!cv) return;
    const ctx = cv.getContext("2d"); if (!ctx) return;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    const w = cv.clientWidth, h = cv.clientHeight;
    if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) { cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr); }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, w, h);
    const t = tRef.current;
    const { z, seam, px } = buf.current;
    sample(t, z, seam);

    const scale = Math.min(w * 0.78, h * 1.35), cx = w * 0.5, cy = h * 0.68;
    const cosY = Math.cos(YAW), sinY = Math.sin(YAW), cosE = Math.cos(ELEV), sinE = Math.sin(ELEV);
    const proj = (u: number, v: number, zz: number): [number, number] => {
      const x = u - 0.5, y = (v - 0.5) * PITCH_W;            // v = 0 is the near touchline
      const xr = x * cosY - y * sinY, yr = x * sinY + y * cosY;
      const s = DIST / (DIST + yr * cosE - zz * sinE);
      return [cx + xr * s * scale, cy - (yr * sinE + zz * cosE) * s * scale];
    };
    for (let my = 0; my <= MY; my++) for (let mx = 0; mx <= MX; mx++) {
      const i = my * (MX + 1) + mx; const p = proj(mx / MX, my / MY, z[i]); px[i * 2] = p[0]; px[i * 2 + 1] = p[1];
    }
    const zAt = (u: number, v: number) => {
      const fx = Math.min(MX - 0.001, Math.max(0, u * MX)), fy = Math.min(MY - 0.001, Math.max(0, v * MY));
      const x0 = Math.floor(fx), y0 = Math.floor(fy), kx = fx - x0, ky = fy - y0, r = MX + 1;
      return (z[y0 * r + x0] * (1 - kx) + z[y0 * r + x0 + 1] * kx) * (1 - ky) + (z[(y0 + 1) * r + x0] * (1 - kx) + z[(y0 + 1) * r + x0 + 1] * kx) * ky;
    };

    // soft shadow under the sheet
    const sh = [proj(0, 0, -0.035), proj(1, 0, -0.035), proj(1, 1, -0.035), proj(0, 1, -0.035)];
    ctx.save(); ctx.filter = "blur(18px)"; ctx.fillStyle = "rgba(0,0,0,.55)"; ctx.beginPath();
    sh.forEach((p, i) => (i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1]))); ctx.closePath(); ctx.fill(); ctx.restore();

    // quads, far to near (far touchline first; with this yaw the left end is further away)
    ctx.lineWidth = 0.5; ctx.lineJoin = "round";
    for (let my = MY - 1; my >= 0; my--) {
      const sv = (seam[my] + seam[my + 1]) / 2;
      for (let mx = 0; mx < MX; mx++) {
        const i = my * (MX + 1) + mx, j = i + MX + 1;
        const zc = (z[i] + z[i + 1] + z[j] + z[j + 1]) / 4;
        const slope = (z[i] + z[j] - z[i + 1] - z[j + 1]) * MX * 0.5;   // lit from the left
        const k = Math.max(0, Math.min(SHADES - 1, Math.round((0.25 + zc / (RELIEF * 1.3) * 0.55 + slope * 0.22) * (SHADES - 1))));
        const p = (mx + 0.5) / MX < sv ? pal.us : pal.them;
        ctx.beginPath(); ctx.moveTo(px[i * 2], px[i * 2 + 1]); ctx.lineTo(px[(i + 1) * 2], px[(i + 1) * 2 + 1]);
        ctx.lineTo(px[(j + 1) * 2], px[(j + 1) * 2 + 1]); ctx.lineTo(px[j * 2], px[j * 2 + 1]); ctx.closePath();
        ctx.fillStyle = p.fill[k]; ctx.fill(); ctx.strokeStyle = p.line[k]; ctx.stroke();
      }
    }

    // pitch markings and the seam, draped over the surface
    const drape = (pts: [number, number][], style: string, width: number) => {
      ctx.beginPath();
      pts.forEach(([u, v], i) => { const p = proj(u, v, zAt(u, v) + 0.002); if (i) ctx.lineTo(p[0], p[1]); else ctx.moveTo(p[0], p[1]); });
      ctx.strokeStyle = style; ctx.lineWidth = width; ctx.stroke();
    };
    const seg = (a: [number, number], b: [number, number], n = 24): [number, number][] => Array.from({ length: n + 1 }, (_, i) => [a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n]);
    const chalk = "rgba(255,255,255,.34)";
    const e = 0.012;
    drape([...seg([e, e], [1 - e, e]), ...seg([1 - e, e], [1 - e, 1 - e]), ...seg([1 - e, 1 - e], [e, 1 - e]), ...seg([e, 1 - e], [e, e])], chalk, 1);
    drape(seg([0.5, e], [0.5, 1 - e]), chalk, 1);
    drape(Array.from({ length: 41 }, (_, i) => [0.5 + Math.cos(i / 40 * Math.PI * 2) * 0.087, 0.5 + Math.sin(i / 40 * Math.PI * 2) * 0.087 / PITCH_W] as [number, number]), chalk, 1);
    for (const side of [0, 1]) {
      const gx = (d: number) => (side ? 1 - e - d : e + d);
      drape([...seg([gx(0), 0.2], [gx(0.157), 0.2], 8), ...seg([gx(0.157), 0.2], [gx(0.157), 0.8], 16), ...seg([gx(0.157), 0.8], [gx(0), 0.8], 8)], chalk, 1);
      drape([...seg([gx(0), 0.37], [gx(0.052), 0.37], 4), ...seg([gx(0.052), 0.37], [gx(0.052), 0.63], 8), ...seg([gx(0.052), 0.63], [gx(0), 0.63], 4)], chalk, 1);
    }
    const seamPts: [number, number][] = Array.from({ length: MY + 1 }, (_, my) => [seam[my], my / MY]);
    ctx.save(); ctx.shadowColor = "rgba(255,255,255,.8)"; ctx.shadowBlur = 8; drape(seamPts, "rgba(255,255,255,.92)", 1.6); ctx.restore();

    // goals: a wash of the scorer's colour over the stage, shock rings and a gold beacon at the goal mouth
    for (const g of goals) {
      const age = t - g.t; if (age < -2 || age > GOAL_SHOW_S) continue;
      const c = g.team === "us" ? cUs : cThem;
      const u = g.team === "us" ? 0.955 : 0.045; const p = proj(u, 0.5, zAt(u, 0.5) + 0.02);
      if (age >= 0 && age < 14) {
        const k = 1 - age / 14; const wash = ctx.createRadialGradient(p[0], p[1], 0, p[0], p[1], Math.max(w, h) * 0.9);
        wash.addColorStop(0, `rgba(${c.join(",")},${0.42 * k})`); wash.addColorStop(0.5, `rgba(${c.join(",")},${0.12 * k})`); wash.addColorStop(1, "rgba(0,0,0,0)");
        ctx.save(); ctx.globalCompositeOperation = "lighter"; ctx.fillStyle = wash; ctx.fillRect(0, 0, w, h); ctx.restore();
      }
      if (age >= 0) for (const lag of [0, 9, 18]) {
        const a = age - lag; if (a < 0 || a > 40) continue;
        ctx.beginPath(); ctx.arc(p[0], p[1], 8 + a * 3.2, 0, Math.PI * 2); ctx.strokeStyle = `rgba(255,214,102,${0.9 * (1 - a / 40)})`; ctx.lineWidth = 2.5; ctx.stroke();
      }
      const fade = Math.max(0, Math.min(1, (GOAL_SHOW_S - age) / 20));
      const beam = ctx.createLinearGradient(p[0], p[1], p[0], p[1] - h * 0.5);
      beam.addColorStop(0, `rgba(255,214,102,${0.75 * fade})`); beam.addColorStop(1, "rgba(255,214,102,0)");
      ctx.fillStyle = beam; ctx.fillRect(p[0] - 2, p[1] - h * 0.5, 4, h * 0.5);
      ctx.save(); ctx.shadowColor = "#ffd666"; ctx.shadowBlur = 18; ctx.beginPath(); ctx.arc(p[0], p[1], 6, 0, Math.PI * 2); ctx.fillStyle = `rgba(255,214,102,${fade})`; ctx.fill(); ctx.restore();
    }

    // end labels
    if (w < 520) return;
    ctx.font = `600 10px ${getComputedStyle(cv).fontFamily}`; ctx.fillStyle = "rgba(255,255,255,.5)";
    const la = proj(0, 1, 0), lb = proj(1, 1, 0);
    ctx.textAlign = "left"; ctx.fillText(`${names.us.toUpperCase()} GOAL`, la[0], la[1] - 10);
    ctx.textAlign = "right"; ctx.fillText(`${names.them.toUpperCase()} GOAL`, lb[0], lb[1] - 10);
  }, [sample, pal, goals, names, cUs, cThem]);

  const drawSpark = useCallback(() => {
    const cv = spark.current; if (!cv) return;
    const ctx = cv.getContext("2d"); if (!ctx) return;
    const dpr = Math.min(2, window.devicePixelRatio || 1); const w = cv.clientWidth, h = cv.clientHeight;
    if (cv.width !== Math.round(w * dpr)) { cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr); }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, w, h);
    const X = (t: number) => ((t - tStart) / (tStop - tStart)) * w, mid = h / 2, amp = h / 2 - 3;
    const live = (t: number) => flow.halves.some((hf) => t >= hf[0] && t <= hf[1]);
    for (const [sign, c] of [[1, cUs], [-1, cThem]] as const) {
      ctx.beginPath(); ctx.moveTo(0, mid);
      for (let i = 0; i < flow.n; i++) { const t = flow.t0 + i * flow.step; const v = live(t) ? Math.max(0, flow.m[i] * sign) : 0; ctx.lineTo(X(t), mid - sign * v * amp); }
      ctx.lineTo(w, mid); ctx.closePath(); ctx.fillStyle = `rgba(${c.join(",")},.85)`; ctx.fill();
    }
    ctx.fillStyle = "rgba(255,255,255,.22)"; ctx.fillRect(0, mid - 0.5, w, 1);
    if (flow.halves.length > 1) { ctx.fillStyle = "rgba(255,255,255,.06)"; ctx.fillRect(X(flow.halves[0][1]), 0, X(flow.halves[1][0]) - X(flow.halves[0][1]), h); }
    for (const g of goals) { ctx.beginPath(); ctx.arc(X(g.t), g.team === "us" ? 4 : h - 4, 3.2, 0, Math.PI * 2); ctx.fillStyle = "#ffd666"; ctx.fill(); }
    const x = X(tRef.current); ctx.fillStyle = "#fff"; ctx.fillRect(x - 0.75, 0, 1.5, h); ctx.beginPath(); ctx.arc(x, mid, 3.5, 0, Math.PI * 2); ctx.fill();
  }, [flow, goals, cUs, cThem, tStart, tStop]);

  const sync = useCallback(() => {
    const t = tRef.current;
    setReadout({ t, us: goals.filter((g) => g.team === "us" && g.t <= t).length, them: goals.filter((g) => g.team === "them" && g.t <= t).length, goal: goals.find((g) => t >= g.t && t - g.t < GOAL_SHOW_S) ?? null });
  }, [goals]);

  // animation loop
  useEffect(() => {
    let raf = 0, last = performance.now(), lastSync = 0;
    const tick = (now: number) => {
      const dt = Math.min(0.1, (now - last) / 1000); last = now;
      if (playing.current) {
        const nearGoal = goals.some((g) => tRef.current > g.t - 4 && tRef.current < g.t + 14);
        let t = tRef.current + dt * GAME_SECONDS_PER_SECOND * (nearGoal ? GOAL_SLOWDOWN : 1);
        if (flow.halves.length > 1 && t > flow.halves[0][1] + 20 && t < flow.halves[1][0]) t = flow.halves[1][0];   // skip the break
        if (t >= tStop) { t = tStop; playing.current = false; setPlaying(false); }
        tRef.current = t;
        if (now - lastSync > 120) { lastSync = now; sync(); }
      }
      draw(); drawSpark();
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [draw, drawSpark, sync, flow.halves, tStop, goals]);

  // start when scrolled into view, unless the visitor prefers reduced motion
  useEffect(() => {
    const el = wrap.current; if (!el || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    let started = false;
    const io = new IntersectionObserver((en) => { if (en[0].isIntersecting && !started) { started = true; playing.current = true; setPlaying(true); } }, { threshold: 0.5 });
    io.observe(el); return () => io.disconnect();
  }, []);

  const toggle = () => {
    if (!playing.current && tRef.current >= tStop - 1) tRef.current = tStart;
    playing.current = !playing.current; setPlaying(playing.current);
  };
  const scrub = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (e.type === "pointermove" && !(e.buttons & 1)) return;
    const r = e.currentTarget.getBoundingClientRect();
    tRef.current = tStart + Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)) * (tStop - tStart); sync();
  };

  const mm = matchMinute(readout.t);
  const i = Math.min(flow.n - 1, Math.max(0, Math.round((readout.t - flow.t0) / flow.step)));
  const m = flow.m[i] ?? 0;
  const onTop = mm.half === "Half time" || mm.half === "Full time" ? mm.half : Math.abs(m) < 0.12 ? "Even" : `${m > 0 ? names.us : names.them} on top`;
  const css = { "--flow-us": `rgb(${cUs.join(",")})`, "--flow-them": `rgb(${cThem.join(",")})` } as React.CSSProperties;

  return (
    <div className="flow" ref={wrap} style={css}>
      <div className="flow-score">
        {(["us", "them"] as const).map((side) => (
          <div className="side" key={side}>
            <span className="nm">{names[side]}</span>
            <label className="swatch" style={{ background: `var(--flow-${side})` }} title={`Change ${names[side]}'s colour`}>
              <input type="color" aria-label={`Colour for ${names[side]}`} value={`#${(side === "us" ? cUs : cThem).map((v) => v.toString(16).padStart(2, "0")).join("")}`} onChange={(e) => pick(side, e.target.value)} />
            </label>
            <b key={readout[side]} className={readout[side] > 0 ? "pop" : ""}>{readout[side]}</b>
          </div>
        ))}
        {picked.us || picked.them ? <button className="flow-reset" onClick={() => { pick("us", undefined); pick("them", undefined); }}>Kit colours</button> : null}
      </div>
      <div className="flow-clock"><b>{mm.label}<sup>'</sup></b><span>{mm.half}</span><span className="ontop">{onTop}</span></div>
      <button className="flow-help" onClick={() => setHelp((v) => !v)}>{help ? "Close" : "How to read it"}</button>
      {readout.goal ? (
        <div className="flow-goal" key={readout.goal.t} style={{ "--c": `var(--flow-${readout.goal.team})` } as React.CSSProperties}>
          <span>Goal</span><b>{names[readout.goal.team]}</b><em>{matchMinute(readout.goal.t).label}'</em>
        </div>
      ) : null}
      <canvas ref={canvas} className="flow-stage" aria-label={`Animated pitch showing which team was on top through the match. ${names.us} attack to the right.`} />
      {help ? (
        <div className="flow-notes">
          <p><b>The two colours are the two teams.</b> {names.us} always attack to the right here, in both halves.</p>
          <p><b>The bright seam is who's on top.</b> It sits midway between the two teams' blocks of players. The further it is pushed toward a goal, the more that team is pinned back.</p>
          <p><b>The surface rises where the players are.</b> Sharp spikes at a goal are attacks the camera saw reach it; the taller, the faster and more direct. Gold marks a goal.</p>
          <p className="dim">A machine estimate of territory from the wide camera, not of possession.</p>
        </div>
      ) : null}
      <div className="flow-bar">
        <button className="flow-play" onClick={toggle} aria-label={isPlaying ? "Pause" : "Play"}>
          {isPlaying ? <svg viewBox="0 0 24 24" width="18" height="18"><rect x="6" y="5" width="4" height="14" rx="1" /><rect x="14" y="5" width="4" height="14" rx="1" /></svg> : <svg viewBox="0 0 24 24" width="18" height="18"><path d="M8 5.5v13a1 1 0 0 0 1.5.86l10.5-6.5a1 1 0 0 0 0-1.72L9.5 4.64A1 1 0 0 0 8 5.5z" /></svg>}
        </button>
        <div className="flow-spark">
          <div className="lbl"><span>Momentum</span><span className="dim">{fmtClock(readout.t)} on the video</span></div>
          <canvas ref={spark} onPointerDown={(e) => { e.currentTarget.setPointerCapture(e.pointerId); scrub(e); }} onPointerMove={scrub} />
        </div>
        {onSeek ? <button className="flow-watch" onClick={() => onSeek(Math.max(0, tRef.current - 8))}>Watch this moment</button> : null}
      </div>
    </div>
  );
}
