"""Machine pass estimates from ball motion and possession.

A pass = a kick (ball speed jumps) where the ball was with team X just before, and the next
holder after the ball settles is a teammate (completed) or an opponent / nobody (incomplete).
Recall is bounded by ball tracking (roughly half of frames on BallerCam footage), so every
count is a lower bound; `ball_coverage` is written alongside so the app can say so.
Origin / destination pitch coordinates and the origin third come from the homography when a
plausible one exists within a second; otherwise they are null."""
import numpy as np


def _holder_at(sequence, t):
    """Smoothed holder at time t (nearest sample at or before t)."""
    lo, hi = 0, len(sequence) - 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if sequence[mid][0] <= t:
            lo = mid
        else:
            hi = mid - 1
    return sequence[lo][1] if sequence and sequence[lo][0] <= t else None


def _raw_holder_after(dets, i1, i2):
    """First frame after the kick where the ball is within reach of a labelled player."""
    for d in dets[i1:i2]:
        if not d.ball or not d.players:
            continue
        bx, by = d.ball
        best, bd = None, 1e9
        for p in d.players:
            dist = np.hypot((p[0] + p[2]) / 2 - bx, p[3] - by)
            if dist < bd:
                best, bd = p, dist
        if best is None:
            continue
        med_h = float(np.median([p[3] - p[1] for p in d.players]))
        if bd <= max(60.0, 2.0 * med_h):
            lab = (d.labels or [None] * len(d.players))[best[4]]
            # a player received it but we can't tell which team: outcome unknown, not incomplete
            return (lab or "unknown"), d
    return None, None


def detect(dets, sequence, fps=5.0, min_speed=250.0, speed_jump=1.6, min_gap_s=1.2, settle_s=3.0, H=None, homog_conf=0.4):
    """Returns (events, summary). events: dicts with t, team, completed, from/to coords, third."""
    import cv2
    ts = [d.t for d in dets]
    pts = [(d.t, d.ball) for d in dets]
    events = []
    last_t = -1e9
    for i in range(2, len(pts)):
        (t0, b0), (t1, b1), (t2, b2) = pts[i - 2], pts[i - 1], pts[i]
        if not (b0 and b1 and b2) or (t2 - t0) > 2.5 / fps:
            continue
        v_before = np.hypot(b1[0] - b0[0], b1[1] - b0[1]) * fps
        v_after = np.hypot(b2[0] - b1[0], b2[1] - b1[1]) * fps
        if v_after < min_speed or v_after < speed_jump * max(v_before, 40.0):
            continue
        if t1 - last_t < min_gap_s:
            continue
        team = _holder_at(sequence, t1 - 0.2)
        if not team:
            continue
        # who has it next, once it settles
        i_settle_lo = int(np.searchsorted(ts, t1 + 0.4))
        i_settle_hi = int(np.searchsorted(ts, t1 + settle_s))
        nxt, d_next = _raw_holder_after(dets, i_settle_lo, i_settle_hi)
        if nxt is None:
            outcome, conf = "incomplete", 0.5      # ball went out / lost / never settled near anyone
        elif nxt == "unknown":
            outcome, conf = "unknown", 0.4         # received by someone we couldn't label: excluded from accuracy
        else:
            outcome, conf = ("completed" if nxt == team else "incomplete"), 0.7
        ev = {"t": round(t1, 1), "team": team, "outcome": outcome, "completed": outcome == "completed", "confidence": conf}
        # geometry if available
        if H:
            best = None
            for ht, (Hm, hc) in H.items():
                if abs(ht - t1) <= 1.0 and hc >= homog_conf and (best is None or hc > best[1]):
                    best = (Hm, hc)
            if best is not None:
                Hm = best[0]
                p0 = cv2.perspectiveTransform(np.array([[[b1[0], b1[1]]]], np.float32), Hm)[0][0]
                fx, fy = float(np.clip(p0[0], 0, 1)), float(np.clip(p0[1], 0, 1))
                ev["from_x"], ev["from_y"] = round(fx, 3), round(fy, 3)
                if d_next is not None and d_next.ball:
                    p1 = cv2.perspectiveTransform(np.array([[[d_next.ball[0], d_next.ball[1]]]], np.float32), Hm)[0][0]
                    ev["to_x"], ev["to_y"] = round(float(np.clip(p1[0], 0, 1)), 3), round(float(np.clip(p1[1], 0, 1)), 3)
                # thirds along the length; orientation (which goal is ours) is unknown without
                # more context, so this is the third from the left goal line. The app labels it.
                ev["third"] = "left" if fx < 1 / 3 else "mid" if fx < 2 / 3 else "right"
        events.append(ev)
        last_t = t1
    summary = {}
    for team in ("us", "them"):
        mine = [e for e in events if e["team"] == team and e["outcome"] != "unknown"]
        unk = sum(1 for e in events if e["team"] == team and e["outcome"] == "unknown")
        summary[team] = {"passes": len(mine), "passes_completed": sum(1 for e in mine if e["completed"]), "unknown": unk}
    coverage = sum(1 for d in dets if d.ball) / max(1, len(dets))
    print(f"passes: us {summary['us']['passes']} ({summary['us']['passes_completed']} completed, {summary['us']['unknown']} unknown), "
          f"them {summary['them']['passes']} ({summary['them']['passes_completed']} completed, {summary['them']['unknown']} unknown); "
          f"ball coverage {coverage:.0%}; located {sum(1 for e in events if 'from_x' in e)}")
    return events, summary, round(coverage, 3)
