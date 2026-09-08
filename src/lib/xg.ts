// xG from shot location. Uses the published logistic model from David Sumpter's
// Soccermatics teaching materials (Lesson 2, "Fitting the xG model"), fitted on
// Wyscout professional data:
//   https://soccermatics.readthedocs.io/en/latest/gallery/lesson2/plot_xGModelFit.html
// Formula: Goal ~ Angle + Distance + X + C + X2 + C2 + AX, xG = 1/(1+exp(-bsum)).
// Coefficients are taken verbatim from that page; nothing here is invented.
// This is a PRO-CALIBRATED PROXY. At U13 the absolute numbers are off; use it for
// relative comparison only (this shot vs that shot, this game vs last game).

export const XG_MODEL_VERSION = "soccermatics-l2-full-wyscout-v1";
export const GOAL_WIDTH_M = 7.32;

const B = {
  intercept: 0.5103,
  angle: 0.6338,
  distance: -0.2798,
  x: 0.1243,
  c: -0.03,
  x2: 0.0014,
  c2: 0.0041,
  ax: -0.1251,
};

export interface ShotGeometry {
  /** metres from the attacking goal line, along the pitch length */
  x: number;
  /** metres from the centre line of the goal, across the pitch width */
  c: number;
  distance: number;
  /** angle subtended by the goal mouth, radians */
  angle: number;
}

// pitch_x: 0 = own goal line, 1 = attacking goal line. pitch_y: 0..1 left→right facing attack.
export function shotGeometry(pitchX: number, pitchY: number, lengthM: number, widthM: number): ShotGeometry {
  const x = Math.max(0.01, (1 - pitchX) * lengthM);
  const c = Math.abs(pitchY - 0.5) * widthM;
  const distance = Math.sqrt(x * x + c * c);
  let angle = Math.atan((GOAL_WIDTH_M * x) / (x * x + c * c - (GOAL_WIDTH_M / 2) ** 2));
  if (angle < 0) angle += Math.PI;
  return { x, c, distance, angle };
}

export function computeXg(pitchX: number, pitchY: number, lengthM: number, widthM: number): number {
  const g = shotGeometry(pitchX, pitchY, lengthM, widthM);
  const bsum =
    B.intercept +
    B.angle * g.angle +
    B.distance * g.distance +
    B.x * g.x +
    B.c * g.c +
    B.x2 * g.x * g.x +
    B.c2 * g.c * g.c +
    B.ax * g.angle * g.x;
  const xg = 1 / (1 + Math.exp(-bsum));
  return Math.round(xg * 1000) / 1000;
}
