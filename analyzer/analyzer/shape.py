"""Team shape snapshots: positions only, no identity, no tracker ids."""
from analyzer.homography import project
from analyzer.video import match_period


def snapshots(dets, label_of, H, offsets, min_players=7, min_conf=0.6):
    out = []
    by_t = {round(d.t, 1): d for d in dets}
    for t, (Hm, conf) in H.items():
        if conf < min_conf:
            continue
        d = by_t.get(round(t, 1))
        per = match_period(offsets, t)
        if d is None or per is None:
            continue
        teams = {"us": [], "them": []}
        cached = getattr(d, "labels", None)
        for p in d.players:
            lab = cached[p[4]] if cached is not None else label_of(d.img, p)
            if lab is None:
                continue
            x, y = project(Hm, (p[0] + p[2]) / 2, p[3])
            if 0 <= x <= 1 and 0 <= y <= 1:
                teams[lab].append({"x": round(x, 3), "y": round(y, 3)})
        for team, pts in teams.items():
            if len(pts) >= min_players:
                # orient so both halves attack the same way: flip in h2 (assumption: teams switch ends)
                if per == "h2":
                    pts = [{"x": round(1 - q["x"], 3), "y": round(1 - q["y"], 3)} for q in pts]
                out.append({"t_seconds": round(t, 1), "period": per, "team": team, "players_visible": len(pts),
                            "homography_confidence": round(conf, 2), "positions": pts})
    print(f"{len(out)} shape snapshots")
    return out
