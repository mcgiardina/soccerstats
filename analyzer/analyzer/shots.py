"""Shot candidates from ball motion. A kick shows up as: the ball is tracked steadily for a
couple of frames, then jumps to a much higher speed and keeps going the same way. Noise in
ball detection (a false positive flickering in) fails the direction-consistency test.
Recall over precision; a human confirms in the app. Team = whoever had the ball just before."""
import numpy as np

# Machine tags are stamped this many seconds before the kick so a viewer lands just ahead of it.
# The app adds its own lead-in on top (CONFIG.leadInSeconds).
PRE_ROLL = 0.5


def _holder_before(sequence, t, lookback_s=2.0):
    holder = None
    for st, team in sequence:
        if st > t:
            break
        if team and st >= t - lookback_s:
            holder = team
    return holder


# min_speed 400 px/s suits the higher BallerCam view (36 kicks in 65 min); 600 suited a lower XbotGo view. Without a goal or
# goalkeeper detector these are *kicks* (long balls, clearances, goal kicks, some shots).
def candidates(dets, fps=5.0, min_speed=400.0, speed_jump=2.0, min_gap_s=8, sequence=None):
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
        out.append({"t": max(0.0, t1 - PRE_ROLL), "confidence": round(min(0.95, conf), 3), "team": team,
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
        t_kick = c["t"] + PRE_ROLL            # candidates store t-1s for the tag
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


def approach_candidates(dets, fps=5.0, sequence=None, near_h=3.0, far_h=7.0, lookback_s=2.0, min_gap_s=6, existing=()):
    """Second trigger for shots: the ball arriving fast at a goalkeeper. A strike from 15 m reaches
    the keeper in about a second, and at 5 fps the ball is often seen in only one or two of those
    frames, so the speed-jump detector (candidates) misses it; the ball being far from the keeper
    and then within a few keeper-heights of them within two seconds does not need the frames in
    between. Emits candidates in the same shape as candidates(); skipped near an existing one."""
    out, taken = [], sorted(c["t"] + PRE_ROLL for c in existing)
    last_t = -1e9
    idx = [i for i, d in enumerate(dets) if d.ball and d.keepers]
    for i in idx:
        d = dets[i]
        for k in d.keepers:
            kh = max(12.0, k[3] - k[1]); cx, cy = (k[0] + k[2]) / 2, k[3] - 0.5 * kh
            if np.hypot(d.ball[0] - cx, d.ball[1] - cy) / kh > near_h:
                continue
            # was the ball far from this keeper a moment ago?
            t_far = None
            j = i - 1
            while j >= 0 and d.t - dets[j].t <= lookback_s:
                dj = dets[j]
                if dj.ball and np.hypot(dj.ball[0] - cx, dj.ball[1] - cy) / kh >= far_h:
                    t_far = dj.t; break
                j -= 1
            if t_far is None:
                continue
            t_kick = t_far
            if t_kick - last_t < min_gap_s or any(abs(t_kick - t) < min_gap_s for t in taken):
                break
            team = _holder_before(sequence, t_kick) if sequence else None
            out.append({"t": max(0.0, t_kick - PRE_ROLL), "confidence": 0.5, "team": team, "trigger": "approach",
                        "speed_px_s": None, "jump": None, "t_arrive": round(float(d.t), 1)})
            last_t = t_kick
            break
    print(f"{len(out)} keeper-approach candidates")
    return out


def classify_by_keeper(kicks, dets, fps=5.0, window_s=2.0, max_range_h=22.0, end_within_h=6.0, min_cos=0.75):
    """Fallback when no pitch geometry is available. The keeper's bounding-box height is used
    as a ruler (~1.4 m for a youth keeper), so the test is camera-independent:
      - the kick starts within `max_range_h` keeper-heights of a visible keeper (shooting range),
      - the ball moves toward that keeper (cosine >= min_cos),
      - and ends within `end_within_h` keeper-heights of the keeper, or passes beyond them.
    With two keepers in frame the one the ball travels toward is used.
    Returns (shots, remaining_kicks)."""
    ts = [d.t for d in dets]
    shots, rest = [], []
    for c in kicks:
        t_kick = c["t"] + PRE_ROLL
        i0 = max(0, int(np.searchsorted(ts, t_kick - 0.3)))
        i1 = min(len(dets), int(np.searchsorted(ts, t_kick + window_s)))
        win = dets[i0:i1]
        balls = [(d.t, d.ball) for d in win if d.ball]
        if len(balls) < 3:
            rest.append(c); continue
        b0 = np.array(balls[0][1], float)
        b1 = np.array(balls[-1][1], float)
        move = b1 - b0
        if np.linalg.norm(move) < 1e-3:
            rest.append(c); continue
        # candidate keepers: cluster keeper detections in the window by position
        kps = [k for d in win for k in (getattr(d, "keepers", []) or [])]
        if not kps:
            rest.append(c); continue
        best = None
        for k in kps:
            kx, ky, kh = (k[0] + k[2]) / 2, k[3], max(8.0, k[3] - k[1])
            to_k = np.array([kx, ky]) - b0
            dist0 = np.linalg.norm(to_k)
            if dist0 < 1e-3:
                continue
            cos = float(np.dot(move, to_k) / (np.linalg.norm(move) * dist0))
            score = cos
            if best is None or score > best[0]:
                best = (score, kx, ky, kh, dist0)
        if best is None:
            rest.append(c); continue
        cos, kx, ky, kh, dist0 = best
        if dist0 < 2.5 * kh:                         # keeper already on the ball: goal kick / punt
            rest.append(c); continue
        if dist0 > max_range_h * kh or cos < min_cos:
            rest.append(c); continue
        d_end = min(np.hypot(b[0] - kx, b[1] - ky) for _, b in balls[1:])
        # "passes beyond": projection of the end point along the kick direction exceeds the keeper's
        along_end = float(np.dot(b1 - b0, move) / np.linalg.norm(move))
        along_k = float(np.dot(np.array([kx, ky]) - b0, move) / np.linalg.norm(move))
        if d_end > end_within_h * kh and along_end < along_k:
            rest.append(c); continue
        closeness = 1.0 - min(1.0, d_end / (end_within_h * kh))
        conf = round(min(0.95, 0.45 + 0.25 * closeness + 0.25 * max(0.0, cos - min_cos) / (1 - min_cos)), 3)
        # Outcome, all as proposals:
        #  - the ball ends on the keeper (< ~1 keeper-height): probably a save / collection
        #  - the ball carries on well past the keeper's line: possibly a goal (or wide)
        #  - otherwise a shot of unknown outcome
        beyond = along_end > along_k + 1.5 * kh
        if d_end <= 1.0 * kh:
            outcome = "save"
        elif beyond:
            outcome = "goal?"
        else:
            outcome = "shot"
        shots.append({**c, "confidence": conf, "outcome": outcome, "keeper_range_h": round(dist0 / kh, 1),
                      "keeper_cos": round(cos, 2), "keeper_end_h": round(d_end / kh, 1)})
    print(f"{len(shots)} shot candidates via keeper approach, {len(rest)} kicks remain")
    return shots, rest
