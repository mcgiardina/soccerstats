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


# Defaults tuned on an 82-minute AI-panned sample game: ~24 candidates. Without a goal or
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


def classify(cands, dets, H, window_s=1.0, min_conf=0.4):
    """Upgrade kick candidates to shot candidates using pitch geometry when a plausible
    homography exists near the kick. A shot: the ball starts in the attacking third and its
    projected direction points at a goal mouth (x -> 0 or x -> 1, y within the goal-area
    width). Candidates without geometry stay kicks with reduced confidence.
    Returns (shots, kicks)."""
    import cv2
    by_t = {round(d.t, 1): d for d in dets}
    ts = sorted(by_t)
    shots, kicks = [], []
    for c in cands:
        t_kick = c["t"] + 1.0            # candidates store t-1s for the tag
        # best homography within the window
        best = None
        for t, (Hm, conf) in H.items():
            if abs(t - t_kick) <= window_s and conf >= min_conf and (best is None or conf > best[1]):
                best = (Hm, conf)
        if best is None:
            kicks.append({**c, "confidence": round(c["confidence"] * 0.6, 3)})
            continue
        Hm, hconf = best
        # ball positions: last sample before the kick and the next 3 after
        before = [t for t in ts if t <= t_kick and by_t[t].ball][-1:]
        after = [t for t in ts if t > t_kick and by_t[t].ball][:3]
        if not before or len(after) < 2:
            kicks.append({**c, "confidence": round(c["confidence"] * 0.6, 3)})
            continue
        pts = np.array([[by_t[t].ball[0], by_t[t].ball[1]] for t in before + after], np.float32)
        pp = cv2.perspectiveTransform(pts.reshape(-1, 1, 2), Hm).reshape(-1, 2)
        p0, p1 = pp[0], pp[-1]
        dx, dy = p1[0] - p0[0], p1[1] - p0[1]
        if abs(dx) < 1e-3:
            kicks.append(c); continue
        goal_x = 1.0 if dx > 0 else 0.0
        # where does the line cross the goal line?
        k = (goal_x - p0[0]) / dx
        y_at_goal = p0[1] + k * dy
        in_third = (p0[0] > 0.6) if goal_x == 1.0 else (p0[0] < 0.4)
        toward_goal = k > 0 and abs(y_at_goal - 0.5) < 0.16     # a bit wider than the goal box
        loc = {"x": float(np.clip(p0[0], 0, 1)), "y": float(np.clip(p0[1], 0, 1)), "confidence": round(hconf, 2)}
        if in_third and toward_goal:
            # attack-normalise: pitch_x=1 is the attacking goal for the shooter, whichever end
            x_att = loc["x"] if goal_x == 1.0 else 1.0 - loc["x"]
            y_att = loc["y"] if goal_x == 1.0 else 1.0 - loc["y"]
            shots.append({**c, "confidence": round(min(0.95, 0.5 + 0.5 * hconf), 3),
                          "location": {"x": x_att, "y": y_att, "confidence": loc["confidence"]},
                          "goal_end": "right" if goal_x == 1.0 else "left"})
        else:
            kicks.append({**c, "confidence": round(c["confidence"] * 0.6, 3), "location": loc})
    print(f"{len(shots)} shot candidates with geometry, {len(kicks)} kicks")
    return shots, kicks


def classify_by_keeper(kicks, dets, fps=5.0, window_s=2.0, approach_frac=0.35):
    """Fallback when no pitch geometry is available: a kick becomes a shot candidate if a
    goalkeeper is visible around the kick and the ball closes most of the distance toward
    that keeper in the following second or two. Keepers only stand in one place, so
    "toward the keeper" is a fair proxy for "toward the goal" on panned footage.
    Returns (shots, remaining_kicks)."""
    ts = [d.t for d in dets]
    shots, rest = [], []
    for c in kicks:
        t_kick = c["t"] + 1.0
        i0 = max(0, int(np.searchsorted(ts, t_kick - 0.3)))
        i1 = min(len(dets), int(np.searchsorted(ts, t_kick + window_s)))
        win = dets[i0:i1]
        keepers = [(d.t, k) for d in win for k in getattr(d, "keepers", []) or []]
        balls = [(d.t, d.ball) for d in win if d.ball]
        if not keepers or len(balls) < 3:
            rest.append(c); continue
        # keeper position: median of detections in the window (the camera pans, so tolerate drift)
        kx = float(np.median([(k[0] + k[2]) / 2 for _, k in keepers]))
        ky = float(np.median([k[3] for _, k in keepers]))
        d_start = np.hypot(balls[0][1][0] - kx, balls[0][1][1] - ky)
        d_min = min(np.hypot(b[0] - kx, b[1] - ky) for _, b in balls[1:])
        if d_start < 40:
            rest.append(c); continue                      # keeper already had it: a goal kick / punt
        closed = 1.0 - d_min / d_start
        if closed >= approach_frac:
            conf = round(min(0.95, 0.45 + 0.4 * closed), 3)
            shots.append({**c, "confidence": conf, "keeper_approach": round(closed, 2)})
        else:
            rest.append(c)
    print(f"{len(shots)} shot candidates via keeper approach, {len(rest)} kicks remain")
    return shots, rest
