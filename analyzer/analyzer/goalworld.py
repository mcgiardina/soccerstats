"""Goal-frame detection with an open-vocabulary detector (YOLO-World, ultralytics).

The classic crossbar/posts detector (goalposts.py) locks onto rows of parked cars and fence
rails behind the end line, and only sees ~25-30% of goals on BallerCam footage. YOLO-World
prompted with "goalpost with net" finds the real goal in the same frames without any training,
and its "soccer ball" prompt sees the ball in ~85% of shot-window frames (the stock detectors
~75%), so it also supplies the ball track inside those windows.

First use builds ~/Library/Caches/match-film/weights/goal-world.pt from yolov8l-worldv2.pt
(auto-downloaded by ultralytics, ~90 MB) plus the CLIP text encoder (downloaded once, ~340 MB);
the saved model already carries the prompt so later loads need neither CLIP nor the network.
"""
import os

import numpy as np

from analyzer.detect import WEIGHTS_DIR

PROMPTS = ["goalpost with net", "soccer ball"]
BASE = "yolov8l-worldv2.pt"
SAVED = "goal-ball-world.pt"
# a youth keeper is roughly 0.6 crossbar heights tall: keeps goalshots' keeper-height units
KH_PER_GOAL_H = 0.6


class GoalFinder:
    def __init__(self, device="mps", conf=0.2, ball_conf=0.2, imgsz=1280, ball_imgsz=1920):
        from ultralytics import YOLO
        os.makedirs(WEIGHTS_DIR, exist_ok=True)
        saved = os.path.join(WEIGHTS_DIR, SAVED)
        if not os.path.exists(saved):
            cwd = os.getcwd()
            os.chdir(WEIGHTS_DIR)
            try:
                m = YOLO(BASE)
                m.set_classes(PROMPTS)
                m.save(saved)
            finally:
                os.chdir(cwd)
        self.model = YOLO(saved)
        self.device, self.conf, self.ball_conf, self.imgsz, self.ball_imgsz = device, conf, ball_conf, imgsz, ball_imgsz

    def _predict(self, img, imgsz):
        r = self.model.predict(img, imgsz=imgsz, conf=min(self.conf, self.ball_conf), device=self.device, verbose=False)[0]
        goals, balls = [], []
        for c, s, b in zip(r.boxes.cls.tolist(), r.boxes.conf.tolist(), r.boxes.xyxy.tolist()):
            x1, y1, x2, y2 = [float(v) for v in b]
            w, h = x2 - x1, y2 - y1
            if int(c) == 0:
                # a goal mouth is wider than tall (even foreshortened) and not a lamp post
                if s >= self.conf and w >= 0.8 * h and w >= 40 and h >= 12:
                    goals.append({"left": x1, "top": y1, "right": x2, "bottom": y2, "score": float(s)})
            elif s >= self.ball_conf and max(w, h) <= 60:
                balls.append(((x1 + x2) / 2, (y1 + y2) / 2, float(s), max(w, h)))
        return goals, balls

    def detect(self, img):
        """(goal boxes, ball candidates) for this frame, cached per image object. Goals are
        best at 1280 input (confidence halves at 1920); the tiny ball is best at 1920, so a
        second pass at that size runs only when the first one saw no ball."""
        if getattr(self, "_last", None) is not None and self._last[0] is img:
            return self._last[1]
        goals, balls = self._predict(img, self.imgsz)
        if self.ball_imgsz and self.ball_imgsz != self.imgsz:
            # the ball in a crowded box at the far end is a few pixels: always add the high-res pass
            balls = balls + self._predict(img, self.ball_imgsz)[1]
        self._last = (img, (goals, balls))
        return goals, balls

    def boxes(self, img):
        return self.detect(img)[0]

    def balls(self, img):
        """Ball candidates (cx, cy, conf, size) that sit on the playing surface."""
        from analyzer.detect import ball_on_pitch
        return [b for b in self.detect(img)[1] if ball_on_pitch(img, b[0], b[1], b[3])]

    def find(self, img, keepers=(), players=()):
        """Best goal box for this frame. With keepers known, prefer the goal a keeper stands in;
        a goal that is small next to the people around it is on the neighbouring pitch and is
        dropped (a full-size goal is at least ~2 player heights wide even when foreshortened)."""
        cands = self.boxes(img)
        if not cands:
            return None
        people = list(keepers) + list(players)

        def on_this_pitch(g):
            if not people:
                return True
            w, h = g["right"] - g["left"], g["bottom"] - g["top"]
            near = [p[3] - p[1] for p in people
                    if g["left"] - 2.5 * w <= (p[0] + p[2]) / 2 <= g["right"] + 2.5 * w and g["top"] - h <= p[3] <= g["bottom"] + 2.5 * h]
            if not near:
                return False
            # full-size goal: 7.3 m wide, 2.4 m high; a youth player ~1.5 m. Frontal width ratio
            # is ~5, foreshortened still >= 2.2; the crossbar stands above head height either way.
            ph = float(np.median(near))
            return w >= 2.2 * ph and h >= 1.0 * ph

        cands = [g for g in cands if on_this_pitch(g)]
        if not cands:
            return None

        def anchored(g):
            for k in keepers:
                cx, feet = (k[0] + k[2]) / 2, k[3]
                w = g["right"] - g["left"]
                if g["left"] - 0.5 * w <= cx <= g["right"] + 0.5 * w and g["top"] <= feet <= g["bottom"] + 0.6 * (g["bottom"] - g["top"]):
                    return True
            return False

        anch = [g for g in cands if anchored(g)]
        pool = anch or [g for g in cands if (g["right"] - g["left"]) >= 80]
        if not pool:
            return None
        g = max(pool, key=lambda c: c["score"])
        g = dict(g)
        g["kh"] = float(max(8.0, KH_PER_GOAL_H * (g["bottom"] - g["top"])))
        g["source"] = "world"
        return g


_FINDER = None


def default_finder():
    """Shared finder; None when the world model cannot be loaded (offline first run)."""
    global _FINDER
    if _FINDER is None:
        try:
            _FINDER = GoalFinder()
        except Exception as e:  # noqa: BLE001
            print("YOLO-World goal finder unavailable, falling back to crossbar detector:", str(e)[:120])
            _FINDER = False
    return _FINDER or None
