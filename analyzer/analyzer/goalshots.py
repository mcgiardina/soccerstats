"""Shot / on-target / goal classification against the goal frame found in the image.

For each kick candidate we look at the ball's image path over the next few seconds and the
goal mouth located near the visible keeper (goalposts.find_goal). Everything is in pixels,
scaled by keeper height, so it works on any camera that shows the goal.

  on_target : the ball's path enters the goal mouth (between the posts, below the bar)
  goal?     : it enters the mouth and is then not seen again for a while (in the net), and
              was not collected by the keeper
  save      : it enters the mouth (or the keeper's reach) and the keeper has it afterwards
  off_target: the path crosses the goal line beside/above the mouth within ~1.5 keeper-heights
  shot      : heads at the goal and gets close but the outcome could not be resolved
  kick      : none of the above
"""
import numpy as np

from analyzer import goalposts


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


def classify(kicks, dets, frame_at, fps=5.0, horizon_s=3.0, step_s=0.2):
    """kicks: candidate dicts with 't' (= kick time - 1s). frame_at(t) -> BGR image or None.
    Returns list of dicts with outcome and goal geometry."""
    ts = [d.t for d in dets]
    by_i = lambda t: int(np.clip(np.searchsorted(ts, t), 0, len(dets) - 1))
    out = []
    for c in kicks:
        t_kick = c["t"] + 1.0
        i0, i1 = by_i(t_kick - 0.4), by_i(t_kick + horizon_s)
        win = dets[i0:i1 + 1]
        # goal mouth: median of the detections across the window (needs a few agreeing frames)
        hits = []
        for d in win[::2]:
            if not d.keepers:
                continue
            img = frame_at(d.t)
            if img is None:
                continue
            for k in d.keepers:
                g = goalposts.find_goal(img, k)
                if g:
                    hits.append(g); break
        res = {**c, "outcome": "kick"}
        if len(hits) < 2:
            out.append(res); continue
        # keep the hits that agree with the median (camera may pan a little)
        med = {k: float(np.median([h[k] for h in hits])) for k in ("left", "right", "top", "bottom", "kh")}
        agree = [h for h in hits if abs(h["left"] - med["left"]) < 1.5 * med["kh"] and abs(h["top"] - med["top"]) < 1.0 * med["kh"]]
        if len(agree) < 2:
            out.append(res); continue
        goal = {k: float(np.median([h[k] for h in agree])) for k in ("left", "right", "top", "bottom", "kh")}
        kh = goal["kh"]
        rect = (goal["left"], goal["top"], goal["right"], goal["bottom"])
        res["goal_hits"] = len(agree)
        balls = [(d.t, d.ball) for d in win if d.ball]
        if len(balls) < 2:
            out.append(res); continue
        # distance from kick origin to goal centre, in keeper heights
        gx, gy = (goal["left"] + goal["right"]) / 2, goal["bottom"]
        b0 = balls[0][1]
        dist0 = float(np.hypot(b0[0] - gx, b0[1] - gy) / kh)
        res.update({"goal_px": rect, "kh": kh, "range_h": round(dist0, 1)})
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
                for d in win:
                    if abs(d.t - t) < 1e-3 and d.keepers:
                        for k in d.keepers:
                            if np.hypot((k[0] + k[2]) / 2 - b[0], k[3] - b[1]) <= 0.8 * kh:
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
