"""Shot candidates from a FIXED wide camera (BallerCam's raw panoramic file), by motion alone.

Why: from a low camera the ball near the far goal is a few pixels across, in front of a running
track and a fence, and the recognition models do not see it (0 of 14 frames on the first ASC LB
game, even at 1080p/1920). In a fixed view none of that matters: the background is still, so
anything small and bright that was not there a moment ago is a mover, painted field markings can
never qualify, and the goals sit at the same pixels all game.

Pipeline, per goal: crop a region around the goal; mark pixels brighter than they were 0.1-0.5 s
ago (rolling background, tolerant to 1 px jitter); keep ball-sized, roundish blobs; drop frames
where the whole crop lights up (a knock to the tripod); link blobs into tracks; report fast tracks
that close on the goal. Output times are in the raw file's clock, which matches Smart View.
"""
import json

import cv2
import numpy as np


def _blobs(cur, past_max, thr=22.0, min_area=3, max_area=60, max_side=10):
    m = ((cur - past_max) > thr).astype(np.uint8)
    n, _lab, st, cen = cv2.connectedComponentsWithStats(m, connectivity=8)
    out = []
    for j in range(1, n):
        a, w, h = st[j, cv2.CC_STAT_AREA], st[j, cv2.CC_STAT_WIDTH], st[j, cv2.CC_STAT_HEIGHT]
        if min_area <= a <= max_area and max(w, h) <= max_side and max(w, h) / max(1, min(w, h)) <= 2.2:
            out.append((float(cen[j][0]), float(cen[j][1])))
    return out


class GoalWatcher:
    def __init__(self, name, goal, frame_size, reach=3.2, lag=(3, 15)):
        self.name, self.goal = name, goal                     # goal: (left, top, right, bottom) in source pixels
        W, H = frame_size
        gw, gh = goal[2] - goal[0], goal[3] - goal[1]
        self.gw = gw
        self.x0, self.x1 = int(max(0, goal[0] - reach * gw)), int(min(W, goal[2] + reach * gw))
        self.y0, self.y1 = int(max(0, goal[1] - 1.2 * gh)), int(min(H, goal[3] + 2.2 * gh))
        self.lag, self.hist = lag, []
        self.tracks, self.done = [], []                       # track: {"pts": [(t, x, y)], "miss": n}
        self.K = np.ones((3, 3), np.uint8)
        self.jolts = 0

    def feed(self, t, frame, link_px=34.0, max_miss=3):
        g = cv2.GaussianBlur(cv2.cvtColor(frame[self.y0:self.y1, self.x0:self.x1], cv2.COLOR_BGR2GRAY), (3, 3), 0).astype(np.float32)
        self.hist.append(g)
        if len(self.hist) > self.lag[1] + 1:
            self.hist.pop(0)
        if len(self.hist) <= self.lag[1]:
            return
        past = cv2.dilate(np.max(self.hist[:-self.lag[0]], axis=0), self.K)
        blobs = _blobs(g, past)
        if len(blobs) > 45:                                   # the whole crop moved: tripod knock, not play
            self.jolts += 1
            blobs = []
        blobs = [(x + self.x0, y + self.y0) for x, y in blobs]
        used = set()
        for tr in self.tracks:
            lt, lx, ly = tr["pts"][-1]
            # predict with the last step, so a fast ball is followed and a player's sock is not
            if len(tr["pts"]) >= 2:
                pt, px, py = tr["pts"][-2]
                k = (t - lt) / max(lt - pt, 1e-3)
                ex, ey = lx + (lx - px) * k, ly + (ly - py) * k
            else:
                ex, ey = lx, ly
            best, bd = None, link_px
            for i, (x, y) in enumerate(blobs):
                if i in used:
                    continue
                d = float(np.hypot(x - ex, y - ey))
                if d < bd:
                    best, bd = i, d
            if best is None:
                tr["miss"] += 1
            else:
                used.add(best); tr["pts"].append((t, *blobs[best])); tr["miss"] = 0
        keep = []
        for tr in self.tracks:
            if tr["miss"] > max_miss:
                if len(tr["pts"]) >= 5:
                    self.done.append(tr["pts"])
            else:
                keep.append(tr)
        self.tracks = keep + [{"pts": [(t, x, y)], "miss": 0} for i, (x, y) in enumerate(blobs) if i not in used]

    def finish(self):
        self.done += [tr["pts"] for tr in self.tracks if len(tr["pts"]) >= 5]
        self.tracks = []

    def candidates(self, min_score=10.0, min_straight=0.8, min_close_gw=0.3):
        """Fast, straight segments of a track that close on the goal. Units are goal-widths so the
        near and the far goal share thresholds. score = speed (gw/s) x distance closed (gw); on the
        first ASC LB game the 99th percentile of all closing segments was ~10, and the top segments
        in the two minutes before each of the four real goals scored 10-14. PROVISIONAL: precision
        and recall are not measured yet (needs the true shot list for a game)."""
        L, T, R, B = self.goal
        gx, gy, gw = (L + R) / 2, (T + B) / 2, self.gw
        out = []
        for pts in self.done:
            a = np.array(pts)
            best = None
            for i in range(0, len(a) - 3):
                for j in range(i + 3, min(len(a), i + 45)):
                    dt = a[j, 0] - a[i, 0]
                    if dt <= 0.08 or dt > 2.5:
                        continue
                    path = float(np.hypot(*(a[j, 1:] - a[i, 1:])))
                    steps = float(np.hypot(*np.diff(a[i:j + 1, 1:], axis=0).T).sum())
                    d0 = float(np.hypot(a[i, 1] - gx, a[i, 2] - gy)); d1 = float(np.hypot(a[j, 1] - gx, a[j, 2] - gy))
                    speed, closed, straight = path / dt / gw, (d0 - d1) / gw, path / max(steps, 1e-6)
                    if straight < min_straight or closed < min_close_gw:
                        continue
                    score = speed * closed
                    if score >= min_score and (best is None or score > best["score"]):
                        inside = bool(L - 0.1 * gw <= a[j, 1] <= R + 0.1 * gw and T - 0.1 * gw <= a[j, 2] <= B + 0.15 * gw)
                        best = {"goal": self.name, "t": float(a[i, 0]), "t_end": float(a[j, 0]), "speed_gw_s": round(speed, 2),
                                "closed_gw": round(closed, 2), "end_dist_gw": round(d1 / gw, 2), "ends_in_mouth": inside,
                                "score": round(score, 2), "from": [round(float(a[i, 1])), round(float(a[i, 2]))], "to": [round(float(a[j, 1])), round(float(a[j, 2]))]}
            if best:
                out.append(best)
        return out


def run(source, goals, t0=0.0, t1=None, every=1, progress=None):
    """source: path or URL of the fixed-camera video. goals: {"left": (l,t,r,b), "right": (...)}."""
    cap = cv2.VideoCapture(source)
    W, H = int(cap.get(3)), int(cap.get(4))
    if t0:
        cap.set(cv2.CAP_PROP_POS_MSEC, t0 * 1000)
    ws = [GoalWatcher(n, g, (W, H)) for n, g in goals.items()]
    i = 0
    while True:
        ok = cap.grab()
        if not ok:
            break
        i += 1
        if i % every:
            continue
        t = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
        if t1 is not None and t > t1:
            break
        ok, frame = cap.retrieve()
        if not ok:
            break
        for w in ws:
            w.feed(t, frame)
        if progress and i % 9000 == 0:
            progress(t)
    cands = []
    for w in ws:
        w.finish()
        cands += w.candidates()
    # one event per goal per few seconds: keep the strongest
    cands.sort(key=lambda c: c["t"])
    merged = []
    for c in cands:
        if merged and merged[-1]["goal"] == c["goal"] and c["t"] - merged[-1]["t"] < 4.0:
            if c["score"] > merged[-1]["score"]:
                merged[-1] = c
        else:
            merged.append(c)
    return merged, {w.name: {"tracks": len(w.done), "jolt_frames": w.jolts} for w in ws}


if __name__ == "__main__":
    import sys
    src, out = sys.argv[1], sys.argv[2]
    goals = json.loads(sys.argv[3])
    t0 = float(sys.argv[4]) if len(sys.argv) > 4 else 0.0
    t1 = float(sys.argv[5]) if len(sys.argv) > 5 else None
    cands, info = run(src, goals, t0=t0, t1=t1, progress=lambda t: print(f"  at {int(t // 60)}:{int(t % 60):02d}", flush=True))
    json.dump({"candidates": cands, "info": info}, open(out, "w"), indent=1)
    print(info, len(cands), "candidates")
