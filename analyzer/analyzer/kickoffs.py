"""Goals from restarts, for a FIXED wide camera.

A goal is the one event in football that is always followed by a kickoff, and in a fixed view a
kickoff has a signature nothing else has: for several seconds every outfield player of one team is
on one side of the halfway line and every player of the other team on the other side. That needs
only player boxes and shirt brightness, which are reliable even when the ball is a 5 px speck.

First real game (ASC LB 1-3 Possible FC, 2026-09-12): the rule fired 5 times in 80 minutes, all
true restarts (both half starts and 3 of the 4 goals), no false alarms. The miss was a first-half
restart taken in ~10 s before the teams had separated. Paired with the motion tracker
(fixedcam.py) each goal got the right end and the right scoring team.

people rows: [{"t": seconds, "p": [[x, y_feet, height, V, S, cls], ...]}, ...] sampled ~0.5-1 fps.
"""
import numpy as np


def classify(p, white_v=145, white_s=95, dark_v=120):
    """'light' / 'dark' / None from the torso's median HSV value and saturation. Two kits that
    are not light-vs-dark need a per-game colour split instead (not needed yet)."""
    if p[3] >= white_v and p[4] < white_s:
        return "light"
    if p[3] < dark_v:
        return "dark"
    return None


def split_purity(people, x_mid, y_range, tol=300, step=50, min_each=3, min_total=8):
    """Best left/right split near halfway: share of players on their own team's side, tolerating
    a stray referee or keeper. Returns (purity, +1 if light is on the left else -1) or (nan, 0)."""
    P = [p for p in people if y_range[0] <= p[1] <= y_range[1]]
    lt = [p[0] for p in P if classify(p) == "light"]; dk = [p[0] for p in P if classify(p) == "dark"]
    n = len(lt) + len(dk)
    if len(lt) < min_each or len(dk) < min_each or n < min_total:
        return float("nan"), 0
    best, side = 0.0, 0
    for x in np.arange(x_mid - tol, x_mid + tol + 1, step):
        ll = sum(1 for v in lt if v < x); dl = sum(1 for v in dk if v < x)
        a, c = (ll + len(dk) - dl) / n, (len(lt) - ll + dl) / n
        if a > best:
            best, side = a, 1
        if c > best:
            best, side = c, -1
    return best, side


def restarts(rows, x_mid, y_range, window_s=10.0, min_purity=0.9, min_samples=3, min_gap_s=75.0):
    ts = np.array([r["t"] for r in rows])
    F = [split_purity(r["p"], x_mid, y_range) for r in rows]
    pu = np.array([f[0] for f in F]); sd = np.array([f[1] for f in F])
    out, last = [], -1e9
    for i in range(len(ts)):
        m = (ts > ts[i] - window_s) & (ts <= ts[i]) & np.isfinite(pu)
        if m.sum() >= min_samples and pu[m].mean() >= min_purity and abs(sd[m].sum()) == m.sum() and ts[i] - last > min_gap_s:
            out.append({"t": float(ts[m][0]), "light_side": "left" if sd[i] > 0 else "right", "purity": round(float(pu[m].mean()), 2)})
            last = ts[i]
    return out


def goals(restart_list, goal_activity, us_is_light=True, lookback_s=90.0, settle_s=8.0, burst_gap_s=5.0, min_burst=6):
    """goal_activity: {"left": sorted times of ball-track points near that goal, "right": ...}.
    A restart that flips sides is the start of a half; any other restart follows a goal at the end
    where the ball was last busy. The goal is stamped at the START of that last burst."""
    out = []
    for k, r in enumerate(restart_list):
        if k == 0 or r["light_side"] != restart_list[k - 1]["light_side"]:
            out.append({"kind": "half_start", "t": r["t"], "light_defends": r["light_side"]})
            continue
        best = None
        for side, a in goal_activity.items():
            a = np.asarray(a); a = a[(a >= r["t"] - lookback_s) & (a <= r["t"] - settle_s)]
            if len(a) < min_burst:
                continue
            cuts = np.where(np.diff(a) > burst_gap_s)[0]
            starts = np.r_[0, cuts + 1]; ends = np.r_[cuts, len(a) - 1]
            bursts = [(a[s], a[e], e - s + 1) for s, e in zip(starts, ends) if e - s + 1 >= min_burst]
            if not bursts:
                continue
            # goals came 20-38 s before their restart: take the latest attack that started at least
            # 12 s before it (later activity is the ball being fetched from the net)
            ok = [x for x in bursts if r["t"] - 60.0 <= x[0] <= r["t"] - 12.0]
            if not ok:
                continue
            b = max(ok, key=lambda x: x[0])
            if best is None or b[0] > best[1][0]:
                best = (side, b)
        if best is None:
            out.append({"kind": "goal", "t": r["t"] - 35.0, "restart_t": r["t"], "goal_end": None, "team": None, "confidence": 0.5})
            continue
        side, b = best
        light_scored = side != r["light_side"]
        out.append({"kind": "goal", "t": float(b[0]), "restart_t": r["t"], "goal_end": side,
                    "team": ("us" if light_scored == us_is_light else "them"), "confidence": 0.85})
    return out
