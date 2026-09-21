"""The ball in open play from a FIXED wide camera, as FLIGHTS: passes, clearances, shots.

A ball at a player's feet cannot be told from the player, in any view. A ball that has been kicked
can: for a moment it is the only ball-sized thing on the pitch moving faster than anyone can run.
So this module does not try to follow the ball all the time. It finds flights, and reads the game
off their two ends: who struck it, who it reached. That is enough for possession (who had it last),
turnovers (a flight that ends with the other team) and pass completion, and it is the raw material
for shots (a flight that ends at a goal).

What makes it work across the whole pitch is the camera model (fieldmap): the ball is ~4 px wide at
the far touchline and ~20 px under the camera, so "ball-sized" is looked up per position instead of
being one number, and speed is measured in feet per second on the ground, not pixels.
"""
import cv2
import numpy as np

from . import fieldmap

BALL_FT = 0.72           # a size 4/5 ball
RUN_FT_S = 26.0          # nobody on a youth pitch covers ground faster than this
MIN_FLIGHT_FT_S = 30.0   # so anything ball-sized and faster, for long enough, is the ball
MIN_FLIGHT_FT = 12.0
MIN_FLIGHT_S = 0.2


class BallSize:
    """Expected ball width in pixels at any pixel of the pitch band, from the camera model."""

    def __init__(self, cam, size, band, step=24):
        self.step, self.band = step, band
        xs = np.arange(0, size[0] + step, step); ys = np.arange(band[0], band[1] + step, step)
        gx, gy = np.meshgrid(xs, ys)
        px = np.stack([gx.ravel(), gy.ravel()], 1).astype(float)
        ground = fieldmap.to_field(px, cam, size)
        ok = np.isfinite(ground).all(1)
        out = np.full(len(px), np.nan)
        g = ground[ok]
        lo = fieldmap.project(np.c_[g, np.zeros(len(g))], cam, size)
        hi = fieldmap.project(np.c_[g, np.full(len(g), BALL_FT)], cam, size)
        out[ok] = np.hypot(*(hi - lo).T)
        self.map = out.reshape(gy.shape)
        self.map[~np.isfinite(self.map)] = np.nanmin(self.map)   # above the horizon: as small as it gets

    def at(self, x, y):
        i = int(np.clip((y - self.band[0]) / self.step, 0, self.map.shape[0] - 1))
        j = int(np.clip(x / self.step, 0, self.map.shape[1] - 1))
        return float(np.clip(self.map[i, j], 2.5, 40.0))


class FieldTracker:
    """Ball-sized, brighter-than-a-moment-ago blobs over the whole pitch band, linked into tracks."""

    def __init__(self, cam, size, band, field=None, lag=(3, 15), thr=22.0):
        self.cam, self.size, self.band, self.lag, self.thr, self.field = cam, size, band, lag, thr, field
        self.ball = BallSize(cam, size, band)
        self.hist, self.tracks, self.done = [], [], []
        self.K = np.ones((3, 3), np.uint8)

    def _blobs(self, cur, past, past_lo):
        # 8-bit saturating arithmetic throughout: this runs on every frame of a 4K recording
        thr = int(self.thr)
        bright = cv2.compare(cv2.subtract(cur, past), thr, cv2.CMP_GT)
        # everything that moved, brighter or darker: a player is a big patch of it, a ball in flight
        # is a speck of it on still grass. A hand, a head or a white sock is ball-sized too, but it
        # is never alone, and that is how the two are told apart.
        moving = cv2.bitwise_or(bright, cv2.compare(cv2.subtract(past_lo, cur), thr, cv2.CMP_GT))
        moving = (moving > 0).astype(np.uint8)
        ii = cv2.integral(moving)
        n, _lab, st, cen = cv2.connectedComponentsWithStats(bright, connectivity=8)
        H, W = cur.shape
        out = []
        for j in range(1, n):
            a, w, h = st[j, cv2.CC_STAT_AREA], st[j, cv2.CC_STAT_WIDTH], st[j, cv2.CC_STAT_HEIGHT]
            if a < 3:
                continue
            cx, cy = float(cen[j][0]), float(cen[j][1])
            x, y = cx, cy + self.band[0]
            b = self.ball.at(x, y)
            side = max(w, h)
            # a moving ball smears along its path, so allow it to be longer than it is wide
            if not (0.45 * b <= side <= 2.6 * b + 2 and min(w, h) <= 1.6 * b + 2 and a >= 0.25 * b * b):
                continue
            x0, x1 = int(max(0, cx - 4 * b)), int(min(W, cx + 4 * b)); y0, y1 = int(max(0, cy - 7 * b)), int(min(H, cy + 7 * b))
            around = float(ii[y1, x1] - ii[y0, x1] - ii[y1, x0] + ii[y0, x0]) - float(a)
            out.append((x, y, b, around < 1.5 * b * b))
        return out

    def feed(self, t, frame, max_miss=3):
        g = cv2.GaussianBlur(cv2.cvtColor(frame[self.band[0]:self.band[1]], cv2.COLOR_BGR2GRAY), (3, 3), 0)
        self.hist.append(g)
        if len(self.hist) > self.lag[1] + 1:
            self.hist.pop(0)
        if len(self.hist) <= self.lag[1]:
            return
        older = self.hist[:-self.lag[0]]
        past = cv2.dilate(np.max(older, axis=0), self.K)
        past_lo = cv2.erode(np.min(older, axis=0), self.K)
        blobs = self._blobs(g, past, past_lo)
        if len(blobs) > 400:          # the whole picture moved (a knock to the tripod)
            blobs = []
        used = set()
        for tr in self.tracks:
            lt, lx, ly, lb, _alone = tr["pts"][-1]
            if len(tr["pts"]) >= 2:
                pt, px, py = tr["pts"][-2][:3]
                k = (t - lt) / max(lt - pt, 1e-3)
                ex, ey, reach = lx + (lx - px) * k, ly + (ly - py) * k, max(8.0, 1.6 * lb)
            else:
                ex, ey, reach = lx, ly, float(np.clip(3.7 * lb, 12.0, 80.0))   # first step: up to ~80 ft/s
            best, bd = None, reach
            for i, (x, y, _b, _al) in enumerate(blobs):
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
        self.tracks = keep + [{"pts": [(t, *b)], "miss": 0} for i, b in enumerate(blobs) if i not in used]

    def finish(self):
        self.done += [tr["pts"] for tr in self.tracks if len(tr["pts"]) >= 5]
        self.tracks = []

    def pop_flights(self):
        """Flights among the tracks finished since the last call."""
        out = [f for f in (flight_of(p, self.cam, self.size, self.field) for p in self.done) if f]
        self.done = []
        return out


def flight_of(pts, cam, size, field=None):
    """The fastest straight stretch of a track, if it is faster than a runner for long enough.
    Speed is measured on the ground; a lofted ball maps a little long, which only helps."""
    a = np.array([(p[0], p[1], p[2]) for p in pts], float)
    ball_px = float(np.median([p[3] for p in pts]))
    alone = np.array([bool(p[4]) for p in pts])
    g = fieldmap.to_field(a[:, 1:], cam, size)
    if not np.isfinite(g).all():
        return None
    if field is not None:   # spectators and the far track are not the game
        x0, x1, y0, y1 = field
        inside = (g[:, 0] > x0 - 10) & (g[:, 0] < x1 + 10) & (g[:, 1] > y0 - 6) & (g[:, 1] < y1 + 6)
        if not inside.all():
            return None
    best = None
    n = len(a)
    for i in range(0, n - 3):
        for j in range(i + 3, n):
            dt = a[j, 0] - a[i, 0]
            if dt < MIN_FLIGHT_S:
                continue
            if dt > 4.0:
                break
            dist = float(np.hypot(*(g[j] - g[i])))
            if dist < MIN_FLIGHT_FT or dist / dt < MIN_FLIGHT_FT_S:
                continue
            # far from the camera a pixel of jitter is feet of "movement": also ask for real travel in the picture
            if float(np.hypot(*(a[j, 1:] - a[i, 1:]))) < max(30.0, 8.0 * ball_px):
                continue
            steps = float(np.hypot(*np.diff(a[i:j + 1, 1:], axis=0).T).sum())
            straight = float(np.hypot(*(a[j, 1:] - a[i, 1:]))) / max(steps, 1e-6)
            if straight < 0.9:
                continue
            # the ball in flight is on its own for most of the way; a hand or a head never is
            if alone[i:j + 1].sum() < 3 or alone[i:j + 1].mean() < 0.4:
                continue
            if best is None or dist > best["ft"]:
                best = {"t0": float(a[i, 0]), "t1": float(a[j, 0]), "ft": round(dist, 1), "ft_s": round(dist / dt, 1), "straight": round(straight, 2),
                        "px0": [round(float(a[i, 1])), round(float(a[i, 2]))], "px1": [round(float(a[j, 1])), round(float(a[j, 2]))],
                        "xy0": [round(float(g[i, 0]), 1), round(float(g[i, 1]), 1)], "xy1": [round(float(g[j, 0]), 1), round(float(g[j, 1]), 1)],
                        # where the speck was first and last seen: closer to the two players than the fast stretch is
                        "first": [float(a[0, 0]), round(float(a[0, 1])), round(float(a[0, 2]))], "last": [float(a[-1, 0]), round(float(a[-1, 1])), round(float(a[-1, 2]))],
                        "v_px": [round(float((a[j, 1] - a[i, 1]) / dt), 1), round(float((a[j, 2] - a[i, 2]) / dt), 1)]}
    return best


def owner_at(people, probes, classify, reach=0.45):
    """Which team's player is the ball with, at one end of a flight? people: rows of
    [x, y_feet, height, V, S, cls] (kickoffs.py format). probes: points along the ball's line just
    beyond the end of the track, because the speck is only seen once it has left the kicker and is
    lost as it reaches the receiver. The ball counts as a player's when a probe is inside or just
    beside their box, feet to head, so a ball arriving at chest height still finds its receiver.
    Returns ("light" | "dark" | None, distance in player-heights)."""
    best, bd = None, reach
    for px in probes:
        for p in people:
            team = classify(p)
            if not team:
                continue
            x, yf, h = p[0], p[1], max(p[2], 1.0)
            dx = max(0.0, abs(px[0] - x) - 0.22 * h)
            dy = max(0.0, (yf - h) - px[1], px[1] - yf)
            d = float(np.hypot(dx, dy)) / h
            if d < bd:
                best, bd = team, d
    return best, (round(bd, 2) if best else None)


def end_probes(flight, which, steps=(0.0, 0.08, 0.16, 0.24, 0.32)):
    """(time to look at, probe points) for the kicker ("a") or the receiver ("b")."""
    vx, vy = flight["v_px"]
    if which == "a":
        t, x, y = flight["first"]; sign = -1.0
    else:
        t, x, y = flight["last"]; sign = 1.0
    return t + sign * 0.1, [(x + sign * vx * k, y + sign * vy * k) for k in steps]


def read_play(flights, halves, carry_s=8.0, restart_gap_s=25.0):
    """Possession, turnovers and passes from flights whose ends carry a team ("a"/"b" = kicker's and
    receiver's team, None when nobody was close enough).

    Possession follows the last team known to have the ball. It is only counted while we know:
    after an event the owner keeps the ball for up to carry_s seconds (a dribble), then the clock
    stops until the next event, so stoppages and stretches we could not read count for nobody.
    A turnover is the ball passing from one team to the other in open play, charged to the team that
    lost it; a change across a long silence is a restart, not a turnover."""
    ev = []
    for f in flights:
        if f.get("a"):
            ev.append((f["t0"], f["a"]))
        if f.get("b"):
            ev.append((f["t1"], f["b"]))
    ev.sort()
    out = []
    for h0, h1 in halves:
        e = [x for x in ev if h0 <= x[0] <= h1]
        held = {"light": 0.0, "dark": 0.0}; lost = {"light": [], "dark": []}
        for k, (t, team) in enumerate(e):
            nxt = e[k + 1][0] if k + 1 < len(e) else h1
            held[team] += min(nxt - t, carry_s)
            if k and e[k - 1][1] != team and t - e[k - 1][0] <= restart_gap_s:
                lost[e[k - 1][1]].append(round(t, 1))
        passes = {"light": [0, 0], "dark": [0, 0]}   # [completed, attempted]
        for f in flights:
            if h0 <= f["t0"] <= h1 and f.get("a") and f.get("b"):
                passes[f["a"]][1] += 1
                passes[f["a"]][0] += int(f["a"] == f["b"])
        out.append({"held_s": held, "turnovers": lost, "passes": passes, "events": len(e)})
    return out
