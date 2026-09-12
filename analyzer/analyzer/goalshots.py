"""Shot / on-target / goal classification against the goal frame found in the image.

For each kick candidate we look at the ball's image path over the next few seconds and the
goal mouth found in the frame (goalworld: YOLO-World zero-shot; goalposts crossbar detector as
fallback). Everything is in pixels, scaled by keeper height (0.6 goal heights), so it works on
any camera that shows the goal.

  on_target : the ball's path enters the goal mouth (between the posts, below the bar)
  goal?     : it enters the mouth and is then not seen again for a while (in the net), and
              was not collected by the keeper
  save      : it enters the mouth (or the keeper's reach) and the keeper has it afterwards
  off_target: the path crosses the goal line beside/above the mouth within ~1.5 keeper-heights
  shot      : heads at the goal and gets close but the outcome could not be resolved
  kick      : none of the above
"""
import numpy as np

from analyzer import goalposts, goalworld
from analyzer.shots import PRE_ROLL


def _seg_intersects_rect(p, q, rect, pad=0.0):
    """Does segment p->q pass through the axis-aligned rect (l, t, r, b), padded by pad px?"""
    l, t, r, b = rect[0] - pad, rect[1] - pad, rect[2] + pad, rect[3] + pad
    # Liang-Barsky clip
    x0, y0 = p; x1, y1 = q
    dx, dy = x1 - x0, y1 - y0
    u0, u1 = 0.0, 1.0
    for pk, qk in ((-dx, x0 - l), (dx, r - x0), (-dy, y0 - t), (dy, b - y0)):
        if pk == 0:
            if qk < 0:
                return False
            continue
        u = qk / pk
        if pk < 0:
            u0 = max(u0, u)
        else:
            u1 = min(u1, u)
        if u0 > u1:
            return False
    return True


# A ball does not move faster than this in the image; a point that is farther than that from
# both its neighbours is another object (a keeper's sock, a cone) and is dropped.
MAX_BALL_SPEED_PX_S = 2500.0


def _drop_teleports(track, max_speed=MAX_BALL_SPEED_PX_S):
    """track: [(t, (x, y)), ...] sorted by t. Removes isolated points until the track is stable."""
    pts = list(track)
    changed = True
    while changed and len(pts) >= 2:
        changed = False
        keep = []
        for i, (t, p) in enumerate(pts):
            far = []
            for j in (i - 1, i + 1):
                if 0 <= j < len(pts):
                    tj, pj = pts[j]
                    far.append(np.hypot(p[0] - pj[0], p[1] - pj[1]) > max_speed * max(0.05, abs(t - tj)))
            if far and all(far):
                changed = True
                continue
            keep.append((t, p))
        pts = keep
    return pts


def classify(kicks, dets, frame_at, fps=5.0, horizon_s=3.0, step_s=0.2, finder=None):
    """kicks: candidate dicts with 't' (= kick time - PRE_ROLL). frame_at(t) -> BGR image or None.
    finder: goalworld.GoalFinder (default: shared instance; falls back to the crossbar detector).
    Returns list of dicts with outcome and goal geometry."""
    finder = finder or goalworld.default_finder()
    ts = [d.t for d in dets]
    by_i = lambda t: int(np.clip(np.searchsorted(ts, t), 0, len(dets) - 1))
    out = []
    for c in kicks:
        t_kick = c["t"] + PRE_ROLL
        i0, i1 = by_i(t_kick - 0.4), by_i(t_kick + horizon_s)
        win = dets[i0:i1 + 1]
        # goal mouth per frame (the camera pans, so the goal moves in the image); a few agreeing
        # frames are required, and the ball is judged in goal-relative coordinates.
        hits = []
        # approach-triggered windows are numerous; the goal moves slowly, so every 2nd frame is enough there
        stride = 2 if (finder is None or c.get("trigger") == "approach") else 1
        for d in win[::stride]:
            if finder is None and not d.keepers:
                continue
            img = frame_at(d.t)
            if img is None:
                continue
            if finder is not None:
                g = finder.find(img, d.keepers, d.players)
                if g:
                    hits.append((d.t, g))
                continue
            for k in d.keepers:
                g = goalposts.find_goal(img, k)
                if g:
                    hits.append((d.t, g)); break
        res = {**c, "outcome": "kick"}
        # the goal has to be in view for a fair share of the window, not just as the pan ends
        min_hits = max(3, int(0.3 * len(win))) if finder is not None else 2
        if len(hits) < min_hits:
            out.append(res); continue
        med_w = float(np.median([h["right"] - h["left"] for _, h in hits]))
        med_h = float(np.median([h["bottom"] - h["top"] for _, h in hits]))
        kh = float(np.median([h["kh"] for _, h in hits]))
        # drop outliers in size (the goal on the next pitch, a partial detection)
        agree = [(t, h) for t, h in hits if abs((h["right"] - h["left"]) - med_w) < 0.35 * med_w and abs((h["bottom"] - h["top"]) - med_h) < 0.5 * med_h]
        if len(agree) < min_hits:
            out.append(res); continue
        ht = np.array([t for t, _ in agree])
        hcx = np.array([(h["left"] + h["right"]) / 2 for _, h in agree])
        hby = np.array([h["bottom"] for _, h in agree])

        def anchor_at(t):
            return float(np.interp(t, ht, hcx)), float(np.interp(t, ht, hby))

        def anchored(t, tol=0.45):
            """The interpolated goal position is only trustworthy near an actual detection
            (the camera pans; extrapolating past the first/last hit puts the goal on empty grass)."""
            return bool(np.min(np.abs(ht - t)) <= tol)

        # goal-relative frame: origin at the centre of the goal line, y up is negative
        rect = (-med_w / 2, -med_h, med_w / 2, 0.0)
        res["goal_hits"] = len(agree)
        # ball track through the window: YOLO-World balls (on the pitch) merged with the cached
        # detection, chosen by continuity with the previous position
        balls = []
        prev = None
        for d in win:
            if not anchored(d.t):
                continue
            cands = [(d.ball[0], d.ball[1], 0.5)] if d.ball else []
            if finder is not None:
                img = frame_at(d.t)
                if img is not None:
                    cands += [(b[0], b[1], b[2]) for b in finder.balls(img)]
            if not cands:
                continue
            # the ball we want is the one that continues the track, or failing that the one
            # nearest the goal: a white shoe on the bench or a bright patch in the tree line
            # scores well on confidence but not on either
            ax_, ay_ = anchor_at(d.t)
            ref = prev if prev is not None else (ax_, ay_)
            pick = max(cands, key=lambda b: b[2] - 0.6 * min(2.0, np.hypot(b[0] - ref[0], b[1] - ref[1]) / (8.0 * kh)))
            prev = pick
            ax, ay = anchor_at(d.t)
            balls.append((d.t, (pick[0] - ax, pick[1] - ay)))
        balls = _drop_teleports(balls)
        if len(balls) < 2:
            out.append(res); continue
        res["ball_track"] = [(round(t, 1), round(p[0] + anchor_at(t)[0], 1), round(p[1] + anchor_at(t)[1], 1)) for t, p in balls]
        gx, gy = 0.0, 0.0
        b0 = balls[0][1]
        dist0 = float(np.hypot(b0[0] - gx, b0[1] - gy) / kh)
        g_last = agree[len(agree) // 2][1]
        res.update({"goal_px": (g_last["left"], g_last["top"], g_last["right"], g_last["bottom"]), "kh": kh, "range_h": round(dist0, 1),
                    "goal_track": [(round(t, 1), round(x, 1), round(y, 1)) for t, x, y in zip(ht.tolist(), hcx.tolist(), hby.tolist())]})
        if dist0 > 30:
            out.append(res); continue
        entered_t, off_t, near_keeper_after, crossed_front = None, None, False, False
        inside = lambda p: rect[0] - 0.15 * kh <= p[0] <= rect[2] + 0.15 * kh and rect[1] - 0.15 * kh <= p[1] <= rect[3] + 0.3 * kh
        entry_side = None
        for (ta, pa), (tb, pb) in zip(balls, balls[1:]):
            if entered_t is None and (_seg_intersects_rect(pa, pb, rect, pad=0.15 * kh) or inside(pb)):
                # a ball well below the goal line is on the pitch in front of the goal, not in the mouth
                if pb[1] > rect[3] + 0.6 * kh:
                    continue
                entered_t = tb
                entry_side = "left" if pa[0] < (rect[0] + rect[2]) / 2 else "right"
            elif entered_t is not None and not inside(pb):
                # left the mouth region again while still visible: passed across the front (a cross / clearance)
                exit_side = "left" if pb[0] < (rect[0] + rect[2]) / 2 else "right"
                if exit_side != entry_side and (tb - entered_t) < 1.0:
                    crossed_front = True
                break
            elif entered_t is None and _seg_intersects_rect(pa, pb, rect, pad=1.5 * kh):
                off_t = off_t or tb
        if entered_t is not None:
            # keeper collects? ball seen within 0.8 kh of the keeper after entering
            later = [(t, b) for t, b in balls if t > entered_t]
            for t, b in later:
                ax, ay = anchor_at(t)
                for d in win:
                    if abs(d.t - t) < 1e-3 and d.keepers:
                        for k in d.keepers:
                            if np.hypot((k[0] + k[2]) / 2 - (b[0] + ax), k[3] - (b[1] + ay)) <= 0.8 * kh:
                                near_keeper_after = True
            last_seen = balls[-1][0]
            gone = (t_kick + horizon_s) - last_seen >= 1.2 and abs(last_seen - entered_t) < 0.8
            if crossed_front:
                res["outcome"] = "cross"
            elif near_keeper_after:
                res["outcome"] = "save"
            elif gone:
                res["outcome"] = "goal?"
            else:
                res["outcome"] = "on_target"
            res["t_at_goal"] = round(float(entered_t), 1)
        elif off_t is not None:
            res["outcome"] = "off_target"; res["t_at_goal"] = round(float(off_t), 1)
        else:
            # heading toward the goal and ending within ~2.5 kh of the mouth: unresolved shot
            end = balls[-1][1]
            d_end = np.hypot(np.clip(end[0], rect[0], rect[2]) - end[0], np.clip(end[1], rect[1], rect[3]) - end[1]) / kh
            move = np.array(balls[-1][1]) - np.array(b0)
            to_goal = np.array([gx, gy]) - np.array(b0)
            cos = float(np.dot(move, to_goal) / (np.linalg.norm(move) * np.linalg.norm(to_goal) + 1e-6))
            if d_end <= 2.5 and cos > 0.8:
                res["outcome"] = "shot"
        out.append(res)
    return out
