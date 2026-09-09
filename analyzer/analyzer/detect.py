"""YOLO detection. No tracker: ByteTrack drops sub-0.25 detections, which is exactly where the
tiny ball lives. Per-frame player ids are just list indices and are never written anywhere."""
import os
from dataclasses import dataclass, field

import cv2
import numpy as np
from tqdm import tqdm

# COCO fallback class ids
COCO_PERSON, COCO_BALL = 0, 32
# Roboflow football-players-detection class order: ball, goalkeeper, player, referee
RF_BALL, RF_GK, RF_PLAYER, RF_REF = 0, 1, 2, 3


@dataclass
class FrameDet:
    t: float
    players: list = field(default_factory=list)   # [(x1,y1,x2,y2,track_id)] outfield players only
    keepers: list = field(default_factory=list)
    ball: tuple = None                            # (cx, cy) or None
    img: object = None
    labels: list = None                           # per-player 'us'|'them'|None once teams are assigned
    size: tuple = None                            # (h, w)


WEIGHTS_DIR = os.path.join(os.environ.get("ANALYZER_CACHE") or os.path.expanduser("~/Library/Caches/match-film"), "weights")


def find_weights(env_key: str, filename: str):
    """Env var wins; else the file downloaded by get_weights.sh; else None."""
    if os.environ.get(env_key):
        return os.environ[env_key]
    p = os.path.join(WEIGHTS_DIR, filename)
    return p if os.path.exists(p) else None


def _model(backend: str):
    """Returns (people_model, ball_model_or_None, device, football).
    With the Roboflow football weights: people (player/keeper/referee) and the ball come from
    that model, and the stock COCO model is run as a second ball detector. Measured on an
    AI-panned 720p game: COCO alone saw the ball in 34% of frames, the football model in 19%,
    the union in 45%. Without the football weights only the COCO model runs."""
    from ultralytics import YOLO
    football = find_weights("PLAYER_WEIGHTS", "football-player-detection.pt")
    coco = "yolo11m.pt" if backend == "cloud" else "yolo11s.pt"
    device = "mps" if backend == "local" else 0
    if football:
        print(f"people + ball: {football}; extra ball detector: {coco}")
        return YOLO(football), YOLO(coco), device, True
    print(f"people + ball: {coco} (no football weights; run get_weights.sh)")
    return YOLO(coco), None, device, False


# The ball is tiny at 720p. Run the net at 1280 and keep a low threshold for the ball only;
# people need a higher one or spectators and signage creep in.
IMGSZ = 1280
BALL_CONF = 0.10
PERSON_CONF = 0.35


def ball_on_pitch(img, cx, cy, half=None, min_field=0.35):
    """A ball is on the playing surface: the ring around it is mostly grass. Rejects the sky,
    the tree line, floodlight heads and spectators' white shoes, which the ball detectors
    mistake for the ball on panned footage (Lady Revo game: most cached balls were in the sky)."""
    from analyzer.teams import field_colour, is_field_pixel, in_pitch
    if not in_pitch(img, cx, cy):
        return False
    h, w = img.shape[:2]
    half = int(half or 18)
    x1, x2 = max(0, int(cx) - 2 * half), min(w, int(cx) + 2 * half)
    y1, y2 = max(0, int(cy) - 2 * half), min(h, int(cy) + 2 * half)
    if x2 - x1 < 4 or y2 - y1 < 4:
        return False
    patch = img[y1:y2, x1:x2]
    hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV).reshape(-1, 3)
    return float(is_field_pixel(hsv, field_colour(img)).mean()) >= min_field


def _pick_ball(img, cands):
    """cands: (cx, cy, conf, half_size). Highest-confidence ball that is on the pitch."""
    for cx, cy, cf, half in sorted(cands, key=lambda c: -c[2]):
        if ball_on_pitch(img, cx, cy, half):
            return (cx, cy, cf)
    return None


def run(frames, backend="local"):
    model, ball_model, device, football = _model(backend)
    out = []
    for f in tqdm(frames, desc="detect"):
        res = model.predict(f.img, device=device, verbose=False, conf=BALL_CONF, imgsz=IMGSZ)[0]
        fd = FrameDet(t=f.t, img=f.img, size=f.img.shape[:2])
        ball_cands = []
        if ball_model is not None:
            rb = ball_model.predict(f.img, device=device, verbose=False, conf=BALL_CONF, imgsz=IMGSZ, classes=[COCO_BALL])[0]
            if rb.boxes is not None and len(rb.boxes):
                for (x1, y1, x2, y2), cf in zip(rb.boxes.xyxy.tolist(), rb.boxes.conf.tolist()):
                    ball_cands.append(((x1 + x2) / 2, (y1 + y2) / 2, float(cf), max(x2 - x1, y2 - y1)))
        if res.boxes is None:
            fd.ball = _pick_ball(f.img, ball_cands)
            if fd.ball is not None:
                fd.ball = fd.ball[:2]
            out.append(fd); continue
        xyxy = res.boxes.xyxy.cpu().numpy()
        cls = res.boxes.cls.cpu().numpy().astype(int)
        ids = np.zeros(len(cls), dtype=int)   # replaced below by the index within fd.players
        conf = res.boxes.conf.cpu().numpy()
        for box, c, _tid, cf in zip(xyxy, cls, ids, conf):
            x1, y1, x2, y2 = box
            is_ball = c == (RF_BALL if football else COCO_BALL)
            if not is_ball and cf < PERSON_CONF:
                continue
            if football:
                if c == RF_BALL:
                    ball_cands.append(((x1 + x2) / 2, (y1 + y2) / 2, float(cf), max(x2 - x1, y2 - y1)))
                elif c == RF_PLAYER:
                    fd.players.append((x1, y1, x2, y2, len(fd.players)))
                elif c == RF_GK:
                    fd.keepers.append((x1, y1, x2, y2, len(fd.keepers)))
                # referees dropped
            else:
                if c == COCO_BALL:
                    ball_cands.append(((x1 + x2) / 2, (y1 + y2) / 2, float(cf), max(x2 - x1, y2 - y1)))
                elif c == COCO_PERSON:
                    fd.players.append((x1, y1, x2, y2, len(fd.players)))
        fd.ball = _pick_ball(f.img, ball_cands)
        if fd.ball is not None:
            fd.ball = fd.ball[:2]
        out.append(fd)
    return out


# ---- local detection cache -------------------------------------------------------------
# Lets possession / shot heuristics be re-tuned without re-running the network. Stays on the
# operator's machine; nothing here is written to the database. No identities, no tracking.
import gzip
import json


def save_cache(path, dets, fps):
    rows = []
    for d in dets:
        rows.append({
            "t": round(d.t, 3),
            "ball": [round(float(d.ball[0]), 1), round(float(d.ball[1]), 1)] if d.ball else None,
            "players": [[round(float(p[0]), 1), round(float(p[1]), 1), round(float(p[2]), 1), round(float(p[3]), 1)] for p in d.players],
            "keepers": [[round(float(p[0]), 1), round(float(p[1]), 1), round(float(p[2]), 1), round(float(p[3]), 1)] for p in d.keepers],
            "labels": d.labels,
        })
    with gzip.open(path, "wt") as f:
        json.dump({"fps": fps, "size": list(dets[0].size) if dets else None, "frames": rows}, f)
    print(f"detections cached to {path}")


def load_cache(path):
    with gzip.open(path, "rt") as f:
        data = json.load(f)
    dets = []
    size = tuple(data["size"]) if data.get("size") else None
    for r in data["frames"]:
        players = [(b[0], b[1], b[2], b[3], i) for i, b in enumerate(r["players"])]
        keepers = [(b[0], b[1], b[2], b[3], i) for i, b in enumerate(r.get("keepers", []))]
        dets.append(FrameDet(t=r["t"], players=players, keepers=keepers, ball=tuple(r["ball"]) if r["ball"] else None,
                             labels=r["labels"], size=size))
    print(f"loaded {len(dets)} cached frames from {path}")
    return data["fps"], dets
