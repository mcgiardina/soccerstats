"""xG models mirrored from src/lib/xg.ts. Keep the two in sync.

ASA xG 3.0 (americansocceranalysis.com/explanation, MLS 2015) with the goal-mouth quadratic
centred on the full 8-yd mouth (see the note in xg.ts), plus the Soccermatics lesson-2 model.
Machine-located shots have no context, so they use 'regular' play."""
import math

GOAL_WIDTH_M = 7.32
M_PER_YD = 0.9144
FULL_MOUTH_YD = GOAL_WIDTH_M / M_PER_YD

ASA_VERSION = "asa-xg3-2015-v1"
SOCCERMATICS_VERSION = "soccermatics-l2-full-wyscout-v1"
MODEL_VERSION = ASA_VERSION
ASA = dict(intercept=4.172, log_distance=-2.353, goal_mouth=0.069, goal_mouth_sq=-0.026, headed=-0.648, cross=-0.38,
           through_ball=0.909, corner=-0.622, free_kick=0.539, indirect_free_kick=-0.192, fastbreak=0.68, penalty=2.735)
SM = dict(intercept=0.5103, angle=0.6338, distance=-0.2798, x=0.1243, c=-0.03, x2=0.0014, c2=0.0041, ax=-0.1251)


def geometry(pitch_x, pitch_y, length_m, width_m):
    x = max(0.01, (1 - pitch_x) * length_m)
    c = abs(pitch_y - 0.5) * width_m
    d = math.hypot(x, c)
    ang = math.atan((GOAL_WIDTH_M * x) / (x * x + c * c - (GOAL_WIDTH_M / 2) ** 2))
    if ang < 0:
        ang += math.pi
    mouth = max(0.3, FULL_MOUTH_YD * math.cos(math.atan2(c, x)))
    return x, c, d, ang, mouth


def xg_asa(pitch_x, pitch_y, length_m, width_m, context="regular", assist="none", headed=False):
    x, c, d, ang, mouth = geometry(pitch_x, pitch_y, length_m, width_m)
    dist_yd = 12.0 if context == "penalty" else max(0.5, d / M_PER_YD)
    if context == "penalty":
        mouth = FULL_MOUTH_YD
    logit = ASA["intercept"] + ASA["log_distance"] * math.log(dist_yd) + ASA["goal_mouth"] * mouth + ASA["goal_mouth_sq"] * (FULL_MOUTH_YD - mouth) ** 2
    if headed:
        logit += ASA["headed"]
    if assist in ("cross", "through_ball"):
        logit += ASA[assist]
    if context in ("corner", "free_kick", "indirect_free_kick", "fastbreak", "penalty"):
        logit += ASA[context]
    return round(1 / (1 + math.exp(-logit)), 3)


def xg_soccermatics(pitch_x, pitch_y, length_m, width_m):
    x, c, d, ang, _ = geometry(pitch_x, pitch_y, length_m, width_m)
    bsum = (SM["intercept"] + SM["angle"] * ang + SM["distance"] * d + SM["x"] * x + SM["c"] * c
            + SM["x2"] * x * x + SM["c2"] * c * c + SM["ax"] * ang * x)
    return round(1 / (1 + math.exp(-bsum)), 3)


def compute_xg(pitch_x, pitch_y, length_m, width_m, **ctx):
    return xg_asa(pitch_x, pitch_y, length_m, width_m, **ctx)
