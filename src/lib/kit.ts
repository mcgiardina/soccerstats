import type { CSSProperties } from "react";

/** Relative luminance of a hex colour (0 = black, 1 = white). */
export function luminance(hex: string): number {
  const h = hex.replace("#", "");
  const full = h.length === 3 ? h.split("").map((c) => c + c).join("") : h;
  if (full.length !== 6) return 0.5;
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(full.slice(i, i + 2), 16) / 255).map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

const ok = (hex: string | null | undefined): hex is string => !!hex && /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.test(hex.trim());

/**
 * CSS variables that recolour a game page to that game's kits: event pills, timeline markers, shot
 * dots, gauge ticks. The text version of each colour is pushed toward black on a light page or
 * toward white on a dark one when the kit itself would not be readable (white shirts, navy in dark).
 */
export function kitVars(us: string | null | undefined, them: string | null | undefined, theme: "light" | "dark"): CSSProperties {
  const vars: Record<string, string> = {};
  const set = (side: "us" | "them", hex: string) => {
    const c = hex.trim();
    const lum = luminance(c);
    const ink = theme === "light"
      ? (lum > 0.45 ? `color-mix(in oklab, ${c} 55%, #000)` : c)
      : (lum < 0.3 ? `color-mix(in oklab, ${c} 55%, #fff)` : c);
    vars[`--${side}`] = c;
    vars[`--${side}-ink`] = ink;
    vars[`--tint-${side}`] = `color-mix(in oklab, ${c} ${theme === "light" ? 16 : 28}%, var(--surface))`;
    vars[`--${side}-soft`] = `color-mix(in oklab, ${c} 45%, var(--surface))`;
  };
  if (ok(us)) set("us", us);
  if (ok(them)) set("them", them);
  return vars as CSSProperties;
}
