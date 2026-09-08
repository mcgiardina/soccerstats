import { useEffect } from "react";
import type { TagType } from "../lib/types";

export const HOTKEYS: { key: string; type: TagType }[] = [
  { key: "g", type: "goal" },
  { key: "x", type: "shot" },
  { key: "c", type: "chance" },
  { key: "s", type: "save" },
  { key: "t", type: "turnover" },
  { key: "k", type: "corner" },
  { key: "f", type: "free_kick" },
  { key: "i", type: "throw_in" },
  { key: "p", type: "penalty" },
  { key: "n", type: "note" },
];

interface Handlers {
  onTag: (type: TagType, opposing: boolean) => void;
  onTogglePlay: () => void;
  onNudge: (delta: number) => void;
  enabled: boolean;
}

// Shift + key = opposing team. Space toggles play. Arrows nudge ±5s, shift+arrows ±30s.
export function useHotkeys({ onTag, onTogglePlay, onNudge, enabled }: Handlers) {
  useEffect(() => {
    if (!enabled) return;
    function handler(e: KeyboardEvent) {
      const el = e.target as HTMLElement | null;
      if (el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.tagName === "SELECT" || el.isContentEditable)) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const k = e.key.toLowerCase();
      if (k === " ") { e.preventDefault(); onTogglePlay(); return; }
      if (e.key === "ArrowLeft") { e.preventDefault(); onNudge(e.shiftKey ? -30 : -5); return; }
      if (e.key === "ArrowRight") { e.preventDefault(); onNudge(e.shiftKey ? 30 : 5); return; }
      const hk = HOTKEYS.find((h) => h.key === k);
      if (hk) { e.preventDefault(); onTag(hk.type, e.shiftKey); }
    }
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onTag, onTogglePlay, onNudge, enabled]);
}
