"""Pitch keypoints -> homography. Only active when PITCH_WEIGHTS points at a model trained on
Roboflow's 32-landmark soccer pitch keypoint dataset. Everything positional depends on this."""
import os

import numpy as np

# Normalised pitch coordinates (x along length, y across width, both 0..1) for the 32
# landmark order used by Roboflow's football pitch keypoint dataset. Left half then right half.
_L, _W = 105.0, 68.0
def _n(x, y): return (x / _L, y / _W)
PITCH_POINTS = [
    _n(0, 0), _n(0, 13.84), _n(0, 24.84), _n(0, 43.16), _n(0, 54.16), _n(0, 68),
    _n(5.5, 24.84), _n(5.5, 43.16), _n(11, 34), _n(16.5, 13.84), _n(16.5, 24.84), _n(16.5, 43.16), _n(16.5, 54.16),
    _n(52.5, 0), _n(52.5, 24.85), _n(52.5, 43.15), _n(52.5, 68),
    _n(88.5, 13.84), _n(88.5, 24.84), _n(88.5, 43.16), _n(88.5, 54.16), _n(94, 34), _n(99.5, 24.84), _n(99.5, 43.16),
    _n(105, 0), _n(105, 13.84), _n(105, 24.84), _n(105, 43.16), _n(105, 54.16), _n(105, 68),
    _n(43.35, 34), _n(61.65, 34),
]


def available():
    return bool(os.environ.get("PITCH_WEIGHTS"))


def fit(frames, min_points=5, conf_thresh=0.5):
    """Returns {t: (H, confidence)} for frames where a homography could be estimated."""
    import cv2
    from ultralytics import YOLO
    model = YOLO(os.environ["PITCH_WEIGHTS"])
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
