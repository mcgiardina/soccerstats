// Single place for club identity and pitch defaults. Nothing else hard-codes these.
export const CONFIG = {
  appName: "Match Film",
  teamName: "U13 Boys",
  colors: { primary: "#1A2D50", accent: "#7ECDB8" },
  font: "Inter",
  logoUrl: null as string | null,
  pitch: { lengthM: 105, widthM: 68 }, // default; per-game override allowed
};
