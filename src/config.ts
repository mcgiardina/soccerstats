// Single place for club identity and pitch defaults. Nothing else hard-codes these.
export const CONFIG = {
  appName: "Match Film",
  teamName: "U13 Boys",
  colors: { primary: "#1A2D50", accent: "#7ECDB8" },
  font: "Plus Jakarta Sans",
  displayFont: "Bricolage Grotesque",
  logoUrl: null as string | null,
  pitch: { lengthM: 105, widthM: 68 }, // default; per-game override allowed
  // Seconds of run-up shown before a tagged moment when you jump to it or share it.
  leadInSeconds: 3,
  // "asa" (ASA xG 3.0, uses shot context) or "soccermatics" (location only). See src/lib/xg.ts.
  xgModel: "asa" as "asa" | "soccermatics",
  // Supabase project. These values are public by design (they ship to every browser);
  // Row Level Security is the actual boundary. VITE_* env vars override them when set.
  supabase: {
    url: "https://lrovuuhgnevxrdxoeuxl.supabase.co",
    publishableKey: "sb_publishable_0AQkCLZFW3x4tYpaDolfbQ_XIV5LuIO",
    adminEmail: "mcgiardina@gmail.com",
  },
};
