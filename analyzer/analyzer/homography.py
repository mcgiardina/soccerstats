"""Pitch keypoints -> homography. Only active when PITCH_WEIGHTS points at a model trained on
Roboflow's 32-landmark soccer pitch keypoint dataset. Everything positional depends on this."""
import os

import numpy as np

# Landmark order of Roboflow's football-pitch-detection model (32 keypoints), taken verbatim
# from roboflow/sports `sports/configs/soccer.py` (SoccerPitchConfiguration.vertices), which
# models a 120 m x 70 m pitch in cm. Normalised here to 0..1 along length and width; the
# analyzer's own pitch dims come from the game record, so only the proportions matter.
_L, _W = 12000.0, 7000.0
_PB_W, _PB_L, _GB_W, _GB_L, _CC_R, _PS = 4100.0, 2015.0, 1832.0, 550.0, 915.0, 1100.0
_V = [
    (0, 0), (0, (_W - _PB_W) / 2), (0, (_W - _GB_W) / 2), (0, (_W + _GB_W) / 2), (0, (_W + _PB_W) / 2), (0, _W),
    (_GB_L, (_W - _GB_W) / 2), (_GB_L, (_W + _GB_W) / 2), (_PS, _W / 2),
    (_PB_L, (_W - _PB_W) / 2), (_PB_L, (_W - _GB_W) / 2), (_PB_L, (_W + _GB_W) / 2), (_PB_L, (_W + _PB_W) / 2),
    (_L / 2, 0), (_L / 2, _W / 2 - _CC_R), (_L / 2, _W / 2 + _CC_R), (_L / 2, _W),
    (_L - _PB_L, (_W - _PB_W) / 2), (_L - _PB_L, (_W - _GB_W) / 2), (_L - _PB_L, (_W + _GB_W) / 2), (_L - _PB_L, (_W + _PB_W) / 2),
    (_L - _PS, _W / 2), (_L - _GB_L, (_W - _GB_W) / 2), (_L - _GB_L, (_W + _GB_W) / 2),
    (_L, 0), (_L, (_W - _PB_W) / 2), (_L, (_W - _GB_W) / 2), (_L, (_W + _GB_W) / 2), (_L, (_W + _PB_W) / 2), (_L, _W),
    (_L / 2 - _CC_R, _W / 2), (_L / 2 + _CC_R, _W / 2),
]
PITCH_POINTS = [(x / _L, y / _W) for x, y in _V]
assert len(PITCH_POINTS) == 32


def weights_path():
    from analyzer.detect import find_weights
    return find_weights("PITCH_WEIGHTS", "football-pitch-detection.pt")


def available():
    return bool(weights_path())


def fit(frames, min_points=5, conf_thresh=0.5):
    """Returns {t: (H, confidence)} for frames where a homography could be estimated."""
    import cv2
    from ultralytics import YOLO
    model = YOLO(weights_path())
    out = {}
    for f in frames:
        r = model(f.img, verbose=False)[0]
        if r.keypoints is None or len(r.keypoints) == 0:
            continue
        kp = r.keypoints.xy[0].cpu().numpy()
        kc = r.keypoints.conf[0].cpu().numpy() if r.keypoints.conf is not None else np.ones(len(kp))
        src, dst = [], []
        for i, (p, c) in enumerate(zip(kp, kc)):
            if c >= conf_thresh and i < len(PITCH_POINTS) and (p[0] > 0 or p[1] > 0):
                src.append(p); dst.append(PITCH_POINTS[i])
        if len(src) < min_points:
            continue
        H, mask = cv2.findHomography(np.array(src, np.float32), np.array(dst, np.float32), cv2.RANSAC, 0.02)
        if H is None:
            continue
        inliers = int(mask.sum())
        conf = min(1.0, inliers / 8) * float(np.mean([c for c in kc if c >= conf_thresh]))
        out[f.t] = (H, conf)
    print(f"homography on {len(out)} / {len(frames)} frames")
    return out


def project(H, px, py):
    import cv2
    p = cv2.perspectiveTransform(np.array([[[px, py]]], np.float32), H)[0][0]
    return float(p[0]), float(p[1])


def locate_shots(cands, dets, H, window_s=1.0, min_conf=0.5):
    """For each shot candidate, project the ball from the best homography frame within ±window."""
    out = {}
    by_t = {round(d.t, 1): d for d in dets}
    for c in cands:
        best = None
        for t, (Hm, conf) in H.items():
            if abs(t - c["t"]) <= window_s and conf >= min_conf and (best is None or conf > best[1]):
                d = by_t.get(round(t, 1))
                if d and d.ball:
                    best = (Hm, conf, d.ball)
        if not best:
            continue
        x, y = project(best[0], *best[2])
        if 0 <= x <= 1 and 0 <= y <= 1:
            # attack-normalise: without knowing which goal we attack this half we leave x as-is;
            # the reviewer can drag it. Flag it via confidence so the UI treats it as a proposal.
            out[round(c["t"], 1)] = {"x": x, "y": y, "confidence": round(best[1], 2)}
    return out
