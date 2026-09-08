"""Same published Soccermatics lesson-2 model as src/lib/xg.ts. Keep the two in sync."""
import math

MODEL_VERSION = "soccermatics-l2-full-wyscout-v1"
GOAL_WIDTH_M = 7.32
B = dict(intercept=0.5103, angle=0.6338, distance=-0.2798, x=0.1243, c=-0.03, x2=0.0014, c2=0.0041, ax=-0.1251)


def compute_xg(pitch_x, pitch_y, length_m, width_m):
    x = max(0.01, (1 - pitch_x) * length_m)
    c = abs(pitch_y - 0.5) * width_m
    d = math.hypot(x, c)
    ang = math.atan((GOAL_WIDTH_M * x) / (x * x + c * c - (GOAL_WIDTH_M / 2) ** 2))
    if ang < 0:
        ang += math.pi
    bsum = (B["intercept"] + B["angle"] * ang + B["distance"] * d + B["x"] * x + B["c"] * c
            + B["x2"] * x * x + B["c2"] * c * c + B["ax"] * ang * x)
    return round(1 / (1 + math.exp(-bsum)), 3)
