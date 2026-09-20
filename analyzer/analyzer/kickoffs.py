"""Goals from restarts, for a FIXED wide camera.

A goal is the one event in football that is always followed by a kickoff, and in a fixed view a
kickoff has a signature nothing else has: for several seconds every outfield player of one team is
on one side of the halfway line and every player of the other team on the other side. That needs
only player boxes and shirt brightness, which are reliable even when the ball is a 5 px speck.

First real game (ASC LB 1-3 Possible FC, 2026-09-12): the rule fired 5 times in 80 minutes, all
true restarts (both half starts and 3 of the 4 goals), no false alarms. The miss was a first-half
restart taken in ~10 s before the teams had separated; a second stage (nominate -> dense re-sample
-> own_half_restarts, in field coordinates) catches it, giving 4 of 4. Paired with the motion tracker
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


def nominate(rows, x_mid, y_range, window_s=8.0, min_purity=0.8, min_samples=2, min_gap_s=40.0):
    """Loose first stage for restarts taken quickly: times worth re-sampling densely (2 fps, with a
    zoomed pass on the far side) and judging with own_half_restarts. Covers every true restart of
    the first real game, plus ~4x as many false windows, which is why it is not a detector."""
    ts = np.array([r["t"] for r in rows])
    F = [split_purity(r["p"], x_mid, y_range, min_each=2, min_total=6) for r in rows]
    pu = np.array([f[0] for f in F])
    out, last = [], -1e9
    for i in range(len(ts)):
        m = (ts > ts[i] - window_s) & (ts <= ts[i]) & np.isfinite(pu)
        if m.sum() >= min_samples and pu[m].mean() >= min_purity and ts[i] - last > min_gap_s:
            out.append(float(ts[i])); last = ts[i]
    return out


def own_half_restarts(windows, to_field, field, tol_ft=6.0, min_people=9, max_wrong=1, span_s=8.0, min_hits=7):
    """Second stage, in FIELD coordinates (fieldmap.to_field), on densely sampled windows.
    A sample is a hit when, of >= 9 classified players on the pitch, at most one is in the wrong
    half (a referee in a dark shirt, a keeper walking back). A restart needs >= 7 hits within 8 s
    (at 2 fps), all with the teams on the same sides.

    First real game: the quickly-taken first-half restart the 0.5 fps rule missed scores 10 hits;
    the best false window scores 5 and the other 20 score <= 1, so 7 sits between. With both stages
    merged: 4 of 4 goals, right end and team, within 9 s, no false alarms; unchanged for min_hits
    6-10, tol 3-12 ft and restart times shifted +-6 s. Tuned and scored on the same single game.
    windows: [[row, ...], ...]; field: (x0, x1, y0, y1) ft with x = 0 at halfway."""
    out = []
    for rows in windows:
        hits = []
        for r in rows:
            P = [(p, classify(p)) for p in r["p"]]; P = [(p, c) for p, c in P if c]
            if len(P) < min_people:
                continue
            g = to_field([[p[0], p[1]] for p, _ in P])
            ok = np.isfinite(g).all(1) & (g[:, 0] > field[0] - 10) & (g[:, 0] < field[1] + 10) & (g[:, 1] > field[2] - 5) & (g[:, 1] < field[3] + 5)
            x = g[ok, 0]; lt = np.array([c == "light" for _, c in P])[ok]
            if len(x) < min_people or lt.sum() < 3 or (~lt).sum() < 3:
                continue
            wrong, side = min((int((sd * x[lt] > tol_ft).sum() + (sd * x[~lt] < -tol_ft).sum()), sd) for sd in (1, -1))
            if wrong <= max_wrong:
                hits.append((r["t"], side))
        best = None
        for i, (t, side) in enumerate(hits):
            span = [h for h in hits[i:] if h[0] <= t + span_s]
            if len(span) >= min_hits and all(h[1] == side for h in span) and (best is None or len(span) > best[2]):
                best = (t, side, len(span))
        if best:
            out.append({"t": float(best[0]), "light_side": "left" if best[1] > 0 else "right", "hits": best[2]})
    return out


def merge(*lists, min_gap_s=75.0):
    """Union of restart lists; two within 75 s are the same restart (the earlier time wins)."""
    out = []
    for r in sorted((r for l in lists for r in l), key=lambda r: r["t"]):
        if not out or r["t"] - out[-1]["t"] > min_gap_s:
            out.append(r)
    return out


def goals(restart_list, goal_activity, us_is_light=True, lookback_s=90.0, settle_s=8.0, burst_gap_s=5.0, min_burst=6, min_volume=100):
    """goal_activity: {"left": sorted times of ball-track points near that goal, "right": ...}.
    A restart that flips sides is the start of a half; any other restart follows a goal at the end
    where the ball was last busy. The goal is stamped at the START of that last burst."""
    out = []
    for k, r in enumerate(restart_list):
        if k == 0 or r["light_side"] != restart_list[k - 1]["light_side"]:
            out.append({"kind": "half_start", "t": r["t"], "light_defends": r["light_side"]})
            continue
        # WHICH END: where the ball was busier in the 90 s before the restart. On the first real game
        # the scoring end had 5x to 600x the other end's track points, so plain volume decides; the
        # bursts only place the time. (An earlier version let the bursts veto an end, and a 2 s
        # change in the restart time flipped a goal to the wrong team.)
        vol, last_burst = {}, {}
        for side, a in goal_activity.items():
            a = np.asarray(a); a = a[(a >= r["t"] - lookback_s) & (a <= r["t"] - settle_s)]
            vol[side] = len(a)
            if len(a) < min_burst:
                continue
            cuts = np.where(np.diff(a) > burst_gap_s)[0]
            starts = np.r_[0, cuts + 1]; ends = np.r_[cuts, len(a) - 1]
            bursts = [(a[s0], a[e0]) for s0, e0 in zip(starts, ends) if e0 - s0 + 1 >= min_burst and a[s0] <= r["t"] - 12.0 and a[e0] >= r["t"] - 60.0]
            if bursts:
                last_burst[side] = bursts[-1]
        best = None
        if vol:
            side = max(vol, key=vol.get); other = max([v for k, v in vol.items() if k != side], default=0)
            if vol[side] >= min_volume and vol[side] >= 2 * other:
                best = (side, last_burst.get(side, (r["t"] - 30.0, r["t"] - 30.0)), vol[side])
        if best is None:
            out.append({"kind": "goal", "t": r["t"] - 35.0, "restart_t": r["t"], "goal_end": None, "team": None, "confidence": 0.5})
            continue
        side, b, _volume = best
        light_scored = side != r["light_side"]
        # Stamp ~30 s before the restart (goals came 20-38 s before theirs), kept inside the attack
        # the ball tracker saw, so a long build-up does not drag the tag half a minute early.
        t_goal = float(np.clip(r["t"] - 30.0, b[0], max(b[0], b[1])))
        out.append({"kind": "goal", "t": t_goal, "restart_t": r["t"], "goal_end": side,
                    "team": ("us" if light_scored == us_is_light else "them"), "confidence": 0.85})
    return out
