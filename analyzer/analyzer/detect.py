"""YOLO detection + ByteTrack. Tracker IDs are used only within this process for smoothing
and are never written to the database."""
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


def run(frames, backend="local"):
    model, device, football = _model(backend)
    out = []
    for f in tqdm(frames, desc="detect"):
        res = model.track(f.img, persist=True, tracker="bytetrack.yaml", device=device, verbose=False, conf=0.25)[0]
        fd = FrameDet(t=f.t, img=f.img)
        if res.boxes is None:
            out.append(fd); continue
        xyxy = res.boxes.xyxy.cpu().numpy()
        cls = res.boxes.cls.cpu().numpy().astype(int)
        ids = res.boxes.id.cpu().numpy().astype(int) if res.boxes.id is not None else np.full(len(cls), -1)
        conf = res.boxes.conf.cpu().numpy()
        for box, c, tid, cf in zip(xyxy, cls, ids, conf):
            x1, y1, x2, y2 = box
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
