"""Shot candidates: the ball accelerates sharply and a goal-ish region is in frame.
Recall over precision; a human confirms in the app. Team is guessed from who last had it."""
import numpy as np


def _holder_before(sequence, t, lookback_s=2.0):
    """Team that had the ball most recently before t, from the smoothed possession sequence."""
    holder = None
    for st, team in sequence:
        if st > t:
            break
        if team and st >= t - lookback_s:
            holder = team
    return holder


def candidates(dets, fps=5.0, accel_px=140, min_gap_s=6, sequence=None):
    out = []
    last_t = -1e9
    pts = [(d.t, d.ball) for d in dets]
    for i in range(2, len(pts)):
        (t0, b0), (t1, b1), (t2, b2) = pts[i - 2], pts[i - 1], pts[i]
        if not (b0 and b1 and b2):
            continue
        v1 = np.hypot(b1[0] - b0[0], b1[1] - b0[1]) * fps
        v2 = np.hypot(b2[0] - b1[0], b2[1] - b1[1]) * fps
        acc = v2 - v1
        if acc < accel_px * fps / 5:
            continue
        if t2 - last_t < min_gap_s:
            continue
        # crude goal-region cue: the ball is heading toward the upper third of the frame where goals sit
        h = dets[i].img.shape[0]
        toward_goal = b2[1] < h * 0.6
        conf = min(0.9, 0.35 + 0.15 * (acc / (accel_px * fps / 5)) + (0.15 if toward_goal else 0))
        team = _holder_before(sequence, t1) if sequence else None
        out.append({"t": max(0.0, t2 - 1.0), "confidence": conf, "team": team})
        last_t = t2
    print(f"{len(out)} shot candidates")
    return out
