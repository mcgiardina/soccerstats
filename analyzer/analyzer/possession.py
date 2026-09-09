"""Ball-carrier attribution. Never uses the ball's pixel position as a field position."""
import numpy as np

from analyzer.video import match_period, match_seconds

BUCKET_S = 300


def compute(dets, label_of, offsets, fps=5.0, smooth_s=1.5, min_hold_s=2.0, max_dist_px=90):
    raw = []  # (t, 'us'|'them'|None)
    for d in dets:
        if d.ball is None or not d.players:
            raw.append((d.t, None)); continue
        bx, by = d.ball
        best, bd = None, 1e9
        for p in d.players:
            # feet point: bottom-centre of the box
            fx, fy = (p[0] + p[2]) / 2, p[3]
            dist = np.hypot(fx - bx, fy - by)
            if dist < bd:
                best, bd = p, dist
        if best is None or bd > max_dist_px:
            raw.append((d.t, None)); continue
        cached = getattr(d, "labels", None)
        raw.append((d.t, cached[best[4]] if cached is not None else label_of(d.img, best)))

    # majority vote over a sliding window
    win = max(1, int(round(smooth_s * fps)))
    teams = [x[1] for x in raw]
    voted = []
    for i in range(len(teams)):
        lo, hi = max(0, i - win // 2), min(len(teams), i + win // 2 + 1)
        w = [t for t in teams[lo:hi] if t]
        if not w:
            voted.append(None); continue
        n_us, n_them = w.count("us"), w.count("them")
        if n_us != n_them:
            voted.append("us" if n_us > n_them else "them")
        else:
            # Tie: keep continuity with the previous vote, else this frame's own attribution.
            # (Never break ties by set order: that varies per process and moved possession ±5 pts.)
            prev = voted[-1] if voted else None
            voted.append(prev or teams[i] or "us")

    # Hysteresis: the holder only changes once the other team has been attributed for a
    # sustained stretch. Brief flickers while the ball is between players are not turnovers.
    hold = max(2, int(round(min_hold_s * fps)))
    smoothed = []
    holder, streak = None, 0
    for t in voted:
        if t is None:
            smoothed.append(holder); continue
        if t == holder:
            streak = 0
        else:
            streak += 1
            if holder is None or streak >= hold:
                holder, streak = t, 0
        smoothed.append(holder)

    # per period + full, only frames inside a half
    tallies = {"full": {"us": 0, "them": 0, "to_us": 0, "to_them": 0}, "h1": {"us": 0, "them": 0, "to_us": 0, "to_them": 0}, "h2": {"us": 0, "them": 0, "to_us": 0, "to_them": 0}}
    buckets = {}
    prev = None
    for (t, _), seen, team in zip(raw, voted, smoothed):
        per = match_period(offsets, t)
        # Only frames where the ball was actually seen count toward the share; the carried
        # holder is used for labelling but never inflates the denominator.
        if per is None or team is None or seen is None:
            continue
        ms = match_seconds(offsets, t)
        bk = int(ms // BUCKET_S) * BUCKET_S
        b = buckets.setdefault(bk, {"us": 0, "them": 0, "to_us": 0, "to_them": 0})
        for T in (tallies["full"], tallies[per], b):
            T[team] += 1
        if prev is not None and prev != team:
            # a change means the new holder won it: count the loser's turnover
            loser = "to_us" if prev == "us" else "to_them"
            for T in (tallies["full"], tallies[per], b):
                T[loser] += 1
        prev = team

    def pct(T):
        n = T["us"] + T["them"]
        return None if n < fps * 60 else round(100 * T["us"] / n, 1)  # need ≥ 1 min of attributed ball

    team_stats = []
    for period, T in tallies.items():
        p = pct(T)
        if p is None:
            continue
        team_stats.append({"team": "us", "period": period, "possession_pct": p, "turnovers": T["to_us"]})
        team_stats.append({"team": "them", "period": period, "possession_pct": round(100 - p, 1), "turnovers": T["to_them"]})

    bucket_rows = []
    for start, T in sorted(buckets.items()):
        n = T["us"] + T["them"]
        bucket_rows.append({"bucket_start_s": start, "bucket_end_s": start + BUCKET_S,
                            "possession_us_pct": round(100 * T["us"] / n, 1) if n else None,
                            "ball_frames": n, "turnovers_us": T["to_us"], "turnovers_them": T["to_them"]})
    full = tallies["full"]
    print(f"attributed frames: {full['us'] + full['them']} / {len(raw)}")
    sequence = [(t, team) for (t, _), team in zip(raw, smoothed)]
    return {"team_stats": team_stats, "buckets": bucket_rows, "sequence": sequence}
