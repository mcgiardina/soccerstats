"""YOLO detection. No tracker: ByteTrack drops sub-0.25 detections, which is exactly where the
tiny ball lives. Per-frame player ids are just list indices and are never written anywhere."""
import os
from dataclasses import dataclass, field

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


def _model(backend: str):
    from ultralytics import YOLO
    weights = os.environ.get("PLAYER_WEIGHTS") or ("yolo11m.pt" if backend == "cloud" else "yolo11s.pt")
    device = "mps" if backend == "local" else 0
    m = YOLO(weights)
    return m, device, bool(os.environ.get("PLAYER_WEIGHTS"))


# The ball is tiny at 720p. Run the net at 1280 and keep a low threshold for the ball only;
# people need a higher one or spectators and signage creep in.
IMGSZ = 1280
BALL_CONF = 0.10
PERSON_CONF = 0.35


def run(frames, backend="local"):
    model, device, football = _model(backend)
    out = []
    for f in tqdm(frames, desc="detect"):
        res = model.predict(f.img, device=device, verbose=False, conf=BALL_CONF, imgsz=IMGSZ)[0]
        fd = FrameDet(t=f.t, img=f.img)
        if res.boxes is None:
            out.append(fd); continue
        xyxy = res.boxes.xyxy.cpu().numpy()
        cls = res.boxes.cls.cpu().numpy().astype(int)
        ids = np.arange(len(cls))
        conf = res.boxes.conf.cpu().numpy()
        for box, c, tid, cf in zip(xyxy, cls, ids, conf):
            x1, y1, x2, y2 = box
            is_ball = c == (RF_BALL if football else COCO_BALL)
            if not is_ball and cf < PERSON_CONF:
                continue
            if football:
                if c == RF_BALL:
                    if fd.ball is None or cf > fd.ball[2]:
                        fd.ball = ((x1 + x2) / 2, (y1 + y2) / 2, cf)
                elif c == RF_PLAYER:
                    fd.players.append((x1, y1, x2, y2, int(tid)))
                elif c == RF_GK:
                    fd.keepers.append((x1, y1, x2, y2, int(tid)))
                # referees dropped
            else:
                if c == COCO_BALL:
                    if fd.ball is None or cf > fd.ball[2]:
                        fd.ball = ((x1 + x2) / 2, (y1 + y2) / 2, cf)
                elif c == COCO_PERSON:
                    fd.players.append((x1, y1, x2, y2, int(tid)))
        if fd.ball is not None:
            fd.ball = fd.ball[:2]
        out.append(fd)
    return out
