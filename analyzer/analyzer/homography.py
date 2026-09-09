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


AREA_MIN_FRAC = float(os.environ.get("HOMOG_AREA_MIN", "0.01"))   # measured: 0.03 keeps ~1% of frames, 0.005 ~8%


def _plausible(H, src, dst, feet):
    """Gate a homography with checks that don't depend on the keypoint model being right:
    the source points must span a real area (not a line), reprojection must be tight, and
    the players' feet must land on the pitch. Returns (ok, confidence, detail)."""
    import cv2
    if len(src) < 5:
        return False, 0.0, "few points"
    hull = cv2.convexHull(src.astype(np.float32))
    area = cv2.contourArea(hull)
    if area < AREA_MIN_FRAC * (1280 * 720):
        return False, 0.0, "points collinear / tiny span"
    proj = cv2.perspectiveTransform(src.reshape(-1, 1, 2).astype(np.float32), H).reshape(-1, 2)
    err = float(np.median(np.linalg.norm(proj - dst, axis=1)))
    if err > 0.02:
        return False, 0.0, f"reprojection {err:.3f}"
    if len(feet) >= 4:
        pf = cv2.perspectiveTransform(np.asarray(feet, np.float32).reshape(-1, 1, 2), H).reshape(-1, 2)
        inside = float(((pf[:, 0] > -0.03) & (pf[:, 0] < 1.03) & (pf[:, 1] > -0.03) & (pf[:, 1] < 1.03)).mean())
        if inside < 0.9:
            return False, 0.0, f"feet inside {inside:.2f}"
    else:
        inside = 0.5   # not enough players to check; keep but don't trust much
    conf = min(1.0, len(src) / 10) * (1 - err / 0.02) * inside
    return True, float(conf), "ok"


def fit(frames, dets_by_t=None, min_points=5, conf_thresh=0.5, device="mps"):
    """Returns {t: (H, confidence)} for frames whose homography passes the plausibility gate.
    dets_by_t (optional): {round(t,1): FrameDet} so player feet can be used as the on-pitch check."""
    import cv2
    from ultralytics import YOLO
    model = YOLO(weights_path())
    out = {}
    rejected = {}
    for f in frames:
        r = model(f.img, verbose=False, imgsz=1280, conf=0.3, device=device)[0]
        if r.keypoints is None or len(r.keypoints) == 0 or r.keypoints.conf is None:
            continue
        kp = r.keypoints.xy[0].cpu().numpy()
        kc = r.keypoints.conf[0].cpu().numpy()
        idx = [i for i in range(min(32, len(kp))) if kc[i] >= conf_thresh and (kp[i][0] > 0 or kp[i][1] > 0)]
        if len(idx) < min_points:
            continue
        src = np.array([kp[i] for i in idx], np.float32)
        dst = np.array([PITCH_POINTS[i] for i in idx], np.float32)
        H, mask = cv2.findHomography(src, dst, cv2.RANSAC, 0.02)
        if H is None:
            continue
        inl = mask.ravel().astype(bool)
        feet = []
        d = dets_by_t.get(round(f.t, 1)) if dets_by_t else None
        if d is not None:
            feet = [((p[0] + p[2]) / 2, p[3]) for p in d.players]
        ok, conf, why = _plausible(H, src[inl], dst[inl], feet)
        if ok:
            out[f.t] = (H, conf)
        else:
            rejected[why.split()[0]] = rejected.get(why.split()[0], 0) + 1
    print(f"homography kept on {len(out)} / {len(frames)} frames; rejected: {rejected}")
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


def save_cache(path, H):
    import json
    with open(path, "w") as f:
        json.dump({str(round(t, 3)): {"H": np.asarray(Hm).tolist(), "conf": conf} for t, (Hm, conf) in H.items()}, f)


def load_cache(path):
    import json
    if not os.path.exists(path):
        return {}
    data = json.load(open(path))
    return {float(t): (np.array(v["H"], np.float64), float(v["conf"])) for t, v in data.items()}
