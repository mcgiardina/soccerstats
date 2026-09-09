// Expected goals from shot location plus (optionally) shot context.
//
// Two published, transparent models. Nothing here is invented; coefficients are copied
// verbatim from their sources and the model version is stored on every shot.
//
// 1. American Soccer Analysis "Expected Goals 3.0" shooter/team model (MLS data, 2015):
//    https://www.americansocceranalysis.com/explanation
//    logit = 4.172 − 2.353·ln(distance_yd) + 0.069·g − 0.026·g² + context terms
//    where g is "goal mouth available" in yards (8 straight on, shrinking with angle).
//    INTERPRETATION NOTE: taken literally, a quadratic in g peaks at 1.3 yd and makes a
//    central penalty 49% and a central 12-yd shot 6%, contradicting ASA's own description
//    ("diminishing returns for better angles"). Centring the quadratic on the full mouth,
//    i.e. using (8 − g)², gives 83% and 25%, which matches their description and the
//    calibration plots. That centring is our reading of their variable, and is flagged here.
// 2. Soccermatics lesson 2 model (Wyscout data), location only:
//    https://soccermatics.readthedocs.io/en/latest/gallery/lesson2/plot_xGModelFit.html
//
// Both are PRO-CALIBRATED PROXIES. At U13 the absolute numbers are off; use them for
// relative comparison (this shot vs that shot, this game vs last game).

import { CONFIG } from "../config";

export const GOAL_WIDTH_M = 7.32;
const M_PER_YD = 0.9144;

export type ShotContext = "regular" | "corner" | "free_kick" | "indirect_free_kick" | "fastbreak" | "penalty";
export type ShotAssist = "none" | "cross" | "through_ball";
export interface XgInputs {
  context?: ShotContext | null;
  assist?: ShotAssist | null;
  headed?: boolean | null;
}

export const CONTEXT_LABELS: Record<ShotContext, string> = {
  regular: "Open play", fastbreak: "Counter", corner: "Corner", free_kick: "Direct FK", indirect_free_kick: "Indirect FK", penalty: "Penalty",
};
export const ASSIST_LABELS: Record<ShotAssist, string> = { none: "No assist", cross: "From a cross", through_ball: "Through ball" };

// ---- geometry ---------------------------------------------------------------------------
export interface ShotGeometry {
  /** metres from the attacking goal line, along the pitch length */
  x: number;
  /** metres from the centre line of the goal, across the pitch width */
  c: number;
  distance: number;
  /** angle subtended by the goal mouth, radians (Soccermatics) */
  angle: number;
  /** goal mouth available to the shooter, yards (ASA): 8 straight on, less from the side */
  goalMouthYd: number;
}

// pitch_x: 0 = own goal line, 1 = attacking goal line. pitch_y: 0..1 left→right facing attack.
export function shotGeometry(pitchX: number, pitchY: number, lengthM: number, widthM: number): ShotGeometry {
  const x = Math.max(0.01, (1 - pitchX) * lengthM);
  const c = Math.abs(pitchY - 0.5) * widthM;
  const distance = Math.sqrt(x * x + c * c);
  let angle = Math.atan((GOAL_WIDTH_M * x) / (x * x + c * c - (GOAL_WIDTH_M / 2) ** 2));
  if (angle < 0) angle += Math.PI;
  // width of the goal mouth as seen from the shot: the mouth projected perpendicular to the line of sight
  const offCentre = Math.atan2(c, x);
  const goalMouthYd = Math.max(0.3, (GOAL_WIDTH_M / M_PER_YD) * Math.cos(offCentre));
  return { x, c, distance, angle, goalMouthYd };
}

// ---- ASA xG 3.0 -------------------------------------------------------------------------
export const ASA_VERSION = "asa-xg3-2015-v1";
const ASA = {
  intercept: 4.172, logDistance: -2.353, goalMouth: 0.069, goalMouthSq: -0.026,
  headed: -0.648, cross: -0.38, throughBall: 0.909,
  corner: -0.622, freeKick: 0.539, indirectFreeKick: -0.192, fastbreak: 0.68, penalty: 2.735,
};
const FULL_MOUTH_YD = GOAL_WIDTH_M / M_PER_YD; // 8.005

export function xgAsa(pitchX: number, pitchY: number, lengthM: number, widthM: number, inp: XgInputs = {}): number {
  const g = shotGeometry(pitchX, pitchY, lengthM, widthM);
  const ctx = inp.context ?? "regular";
  const distYd = ctx === "penalty" ? 12 : Math.max(0.5, g.distance / M_PER_YD);
  const mouth = ctx === "penalty" ? FULL_MOUTH_YD : g.goalMouthYd;
  let logit = ASA.intercept + ASA.logDistance * Math.log(distYd) + ASA.goalMouth * mouth + ASA.goalMouthSq * (FULL_MOUTH_YD - mouth) ** 2;
  if (inp.headed) logit += ASA.headed;
  if (inp.assist === "cross") logit += ASA.cross;
  if (inp.assist === "through_ball") logit += ASA.throughBall;
  if (ctx === "corner") logit += ASA.corner;
  if (ctx === "free_kick") logit += ASA.freeKick;
  if (ctx === "indirect_free_kick") logit += ASA.indirectFreeKick;
  if (ctx === "fastbreak") logit += ASA.fastbreak;
  if (ctx === "penalty") logit += ASA.penalty;
  return Math.round((1 / (1 + Math.exp(-logit))) * 1000) / 1000;
}

// ---- Soccermatics (location only) -------------------------------------------------------
export const SOCCERMATICS_VERSION = "soccermatics-l2-full-wyscout-v1";
const SM = { intercept: 0.5103, angle: 0.6338, distance: -0.2798, x: 0.1243, c: -0.03, x2: 0.0014, c2: 0.0041, ax: -0.1251 };

export function xgSoccermatics(pitchX: number, pitchY: number, lengthM: number, widthM: number): number {
  const g = shotGeometry(pitchX, pitchY, lengthM, widthM);
  const bsum = SM.intercept + SM.angle * g.angle + SM.distance * g.distance + SM.x * g.x + SM.c * g.c + SM.x2 * g.x * g.x + SM.c2 * g.c * g.c + SM.ax * g.angle * g.x;
  return Math.round((1 / (1 + Math.exp(-bsum))) * 1000) / 1000;
}

// ---- active model -----------------------------------------------------------------------
export const XG_MODEL_VERSION = CONFIG.xgModel === "soccermatics" ? SOCCERMATICS_VERSION : ASA_VERSION;

export function computeXg(pitchX: number, pitchY: number, lengthM: number, widthM: number, inp: XgInputs = {}): number {
  return CONFIG.xgModel === "soccermatics" ? xgSoccermatics(pitchX, pitchY, lengthM, widthM) : xgAsa(pitchX, pitchY, lengthM, widthM, inp);
}
