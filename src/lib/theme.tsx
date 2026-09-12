import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

export type ThemeMode = "light" | "dark" | "auto";
export const THEME_KEY = "matchfilm.theme";
const ORDER: ThemeMode[] = ["light", "dark", "auto"];

/** Stamp the chosen theme on <html>. Auto = no attribute, so the CSS media query decides. */
export function applyTheme(mode: ThemeMode) {
  const r = document.documentElement;
  if (mode === "auto") r.removeAttribute("data-theme");
  else r.setAttribute("data-theme", mode);
}

export function readTheme(): ThemeMode {
  try {
    const v = localStorage.getItem(THEME_KEY);
    return v === "light" || v === "dark" ? v : "auto";
  } catch { return "auto"; }
}

interface ThemeState { mode: ThemeMode; resolved: "light" | "dark"; setMode: (m: ThemeMode) => void; cycle: () => void }
const Ctx = createContext<ThemeState>({ mode: "auto", resolved: "light", setMode: () => {}, cycle: () => {} });

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<ThemeMode>(readTheme);
  const [system, setSystem] = useState<"light" | "dark">(() => (typeof matchMedia !== "undefined" && matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"));

  useEffect(() => { applyTheme(mode); }, [mode]);
  useEffect(() => {
    if (typeof matchMedia === "undefined") return;
    const mq = matchMedia("(prefers-color-scheme: dark)");
    const on = () => setSystem(mq.matches ? "dark" : "light");
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);

  const setMode = useCallback((m: ThemeMode) => {
    try { if (m === "auto") localStorage.removeItem(THEME_KEY); else localStorage.setItem(THEME_KEY, m); } catch { /* private mode */ }
    setModeState(m);
  }, []);
  const cycle = useCallback(() => setMode(ORDER[(ORDER.indexOf(mode) + 1) % ORDER.length]), [mode, setMode]);

  const value = useMemo<ThemeState>(() => ({ mode, resolved: mode === "auto" ? system : mode, setMode, cycle }), [mode, system, setMode, cycle]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useTheme() { return useContext(Ctx); }

/** Header control: one tap steps Light → Dark → Auto. Shows the mode name so Auto is legible. */
export function ThemeToggle() {
  const { mode, resolved, cycle } = useTheme();
  const label = mode === "auto" ? "Auto" : mode === "dark" ? "Dark" : "Light";
  const next = ORDER[(ORDER.indexOf(mode) + 1) % ORDER.length];
  return (
    <button className="btn sm theme-btn" onClick={cycle} title={`Theme: ${label}${mode === "auto" ? ` (following system, currently ${resolved})` : ""}. Click for ${next}.`} aria-label={`Theme ${label}, switch to ${next}`}>
      {mode === "dark" ? (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" /></svg>
      ) : mode === "light" ? (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></svg>
      ) : (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M12 3a9 9 0 0 1 0 18z" fill="currentColor" stroke="none" /></svg>
      )}
      {label}
    </button>
  );
}
