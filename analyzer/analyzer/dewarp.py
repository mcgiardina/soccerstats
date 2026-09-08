"""Fisheye de-warp for a raw wide-angle source (BallerCam 4K fisheye, if exportable).

Calibration is a small JSON file per camera holding OpenCV fisheye intrinsics (K, D). We do
not run a chessboard calibration; `calibrate.py` renders candidate undistortions of one frame
with visible pitch lines and the operator picks the one where the lines come out straight.
That single choice is reused for every game shot with that camera.
"""
import json
import os

import cv2
import numpy as np

CALIB_DIR = os.environ.get("ANALYZER_CALIB") or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "calib")


def calib_path(name: str) -> str:
    return os.path.join(CALIB_DIR, f"{name}.json")


def load(name: str):
    """Returns a de-warper callable or None if no calibration exists for this camera name."""
    path = calib_path(name)
    if not os.path.exists(path):
        return None
    data = json.load(open(path))
    K = np.array(data["K"], np.float64)
    D = np.array(data["D"], np.float64).reshape(4, 1)
    size = tuple(data["size"])                      # (w, h) the calibration was made for
    balance = float(data.get("balance", 0.0))
    new_K = cv2.fisheye.estimateNewCameraMatrixForUndistortRectify(K, D, size, np.eye(3), balance=balance)
    maps = {}

    def dewarp(img):
        h, w = img.shape[:2]
        if (w, h) != size:
            # scale intrinsics to this frame size (e.g. 720p download of a 4K calibration)
            sx, sy = w / size[0], h / size[1]
            Ks = K.copy(); Ks[0] *= sx; Ks[1] *= sy
            nKs = new_K.copy(); nKs[0] *= sx; nKs[1] *= sy
            key = (w, h)
        else:
            Ks, nKs, key = K, new_K, size
        if key not in maps:
            maps[key] = cv2.fisheye.initUndistortRectifyMap(Ks, D, np.eye(3), nKs, key, cv2.CV_16SC2)
        m1, m2 = maps[key]
        return cv2.remap(img, m1, m2, interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)

    dewarp.name = name
    return dewarp


def make_params(size, k1, fov_scale=1.0, balance=0.0):
    """A plausible fisheye model for a phone-style 180° lens from a single strength knob.
    K assumes the optical centre is the frame centre and a focal length of ~0.5*width*fov_scale."""
    w, h = size
    f = 0.5 * w * fov_scale
    K = [[f, 0, w / 2], [0, f, h / 2], [0, 0, 1]]
    D = [k1, 0.0, 0.0, 0.0]
    return {"size": [w, h], "K": K, "D": D, "balance": balance}


def save(name: str, params: dict):
    os.makedirs(CALIB_DIR, exist_ok=True)
    with open(calib_path(name), "w") as f:
        json.dump(params, f, indent=1)
    return calib_path(name)
