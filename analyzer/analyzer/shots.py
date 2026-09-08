"""Shot candidates from ball motion. A kick shows up as: the ball is tracked steadily for a
couple of frames, then jumps to a much higher speed and keeps going the same way. Noise in
ball detection (a false positive flickering in) fails the direction-consistency test.
Recall over precision; a human confirms in the app. Team = whoever had the ball just before."""
import numpy as np


def _holder_before(sequence, t, lookback_s=2.0):
    holder = None
    for st, team in sequence:
        if st > t:
            break
        if team and st >= t - lookback_s:
            holder = team
    return holder


# Defaults tuned on an 82-minute XbotGo Chameleon game: ~24 candidates. Without a goal or
# goalkeeper detector these are *kicks* (long balls, clearances, goal kicks, some shots).
def candidates(dets, fps=5.0, min_speed=600.0, speed_jump=2.0, min_gap_s=8, sequence=None):
    """min_speed: px/s the ball must reach; speed_jump: ratio to its speed before the kick."""
    out = []
    last_t = -1e9
    pts = [(d.t, d.ball) for d in dets]
    n = len(pts)
    for i in range(3, n):
        (t0, b0), (t1, b1), (t2, b2), (t3, b3) = pts[i - 3], pts[i - 2], pts[i - 1], pts[i]
        if not (b0 and b1 and b2 and b3):
            continue
        # consecutive samples only (gaps mean the ball was lost in between)
        if (t3 - t0) > 3.5 / fps:
            continue
        v_before = np.hypot(b1[0] - b0[0], b1[1] - b0[1]) * fps
        d12 = np.array([b2[0] - b1[0], b2[1] - b1[1]])
        d23 = np.array([b3[0] - b2[0], b3[1] - b2[1]])
        v1 = np.linalg.norm(d12) * fps
        v2 = np.linalg.norm(d23) * fps
        if v1 < min_speed or v2 < 0.5 * min_speed:
            continue
        if v1 < speed_jump * max(v_before, 60.0):
            continue
        cos = float(np.dot(d12, d23) / (np.linalg.norm(d12) * np.linalg.norm(d23) + 1e-6))
        if cos < 0.6:
            continue
        if t2 - last_t < min_gap_s:
            continue
        jump = v1 / max(v_before, 60.0)
        conf = 0.35 + 0.25 * min(1.0, (jump - speed_jump) / 6.0) + 0.25 * max(0.0, cos - 0.6) / 0.4 + 0.1 * min(1.0, v1 / (2 * min_speed))
        team = _holder_before(sequence, t1) if sequence else None
        out.append({"t": max(0.0, t1 - 1.0), "confidence": round(min(0.95, conf), 3), "team": team,
                    "speed_px_s": round(v1), "jump": round(jump, 1)})
        last_t = t2
    print(f"{len(out)} shot candidates")
    return out
