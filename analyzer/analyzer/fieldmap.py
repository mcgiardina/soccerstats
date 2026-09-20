"""Pixel <-> field for a FIXED wide (fisheye) camera on the touchline.

Model: camera at (cx, -d, h) feet, X along the touchline (0 at halfway), Y across the field from the
near touchline, Z up; looking across the field, tilted down, with a little yaw and roll; equidistant
fisheye with one radial term, r = f * theta * (1 + k * theta^2) from the image centre.

Fit from landmarks whose field position is known. On a football-lined pitch the yard lines and
numerals are ideal: they are exactly 15 / 30 ft apart. First real game (2026-09-20, 3840x2160
panoramic): 16 landmarks fitted to a median of 6 px (worst 24 px); players then map onto a
~290 x 200 ft rectangle, as they should. The camera figures from the BallerCam app are used as soft
priors only; the fit moved them a little (height 12.8 ft, tilt 15.2 deg, 14.7 ft from the line).
"""
import numpy as np

PARAMS = ("f", "k", "tilt", "yaw", "roll", "cx", "d", "h")


def _basis(tilt, yaw):
    ct, st, cy, sy = np.cos(tilt), np.sin(tilt), np.cos(yaw), np.sin(yaw)
    fwd = np.array([sy * ct, cy * ct, -st]); right = np.array([cy, -sy, 0.0])
    return right, np.cross(right, fwd), fwd


def project(points, cam, size):
    """Field points (X, Y, Z) in feet -> pixels."""
    f, k, tilt, yaw, roll, cx, d, h = (cam[n] for n in PARAMS)
    v = np.asarray(points, float) - np.array([cx, -d, h]); right, up, fwd = _basis(tilt, yaw)
    th = np.arccos((v @ fwd) / np.linalg.norm(v, axis=1)); ph = np.arctan2(-(v @ up), v @ right)
    r = f * th * (1 + k * th * th)
    u, w = r * np.cos(ph), r * np.sin(ph); cr, sr = np.cos(roll), np.sin(roll)
    return np.stack([size[0] / 2 + cr * u - sr * w, size[1] / 2 + sr * u + cr * w], 1)


def to_field(pixels, cam, size):
    """Pixels of points ON THE GROUND (feet, not heads) -> field (X, Y) in feet; nan above the horizon."""
    f, k, tilt, yaw, roll, cx, d, h = (cam[n] for n in PARAMS)
    q = np.asarray(pixels, float).reshape(-1, 2) - np.array([size[0] / 2, size[1] / 2])
    cr, sr = np.cos(roll), np.sin(roll)
    u, w = cr * q[:, 0] + sr * q[:, 1], -sr * q[:, 0] + cr * q[:, 1]
    r = np.hypot(u, w); th = r / f
    for _ in range(8):
        th = r / (f * (1 + k * th * th))
    ph = np.arctan2(w, u); right, up, fwd = _basis(tilt, yaw)
    ray = np.sin(th)[:, None] * (np.cos(ph)[:, None] * right - np.sin(ph)[:, None] * up) + np.cos(th)[:, None] * fwd
    with np.errstate(divide="ignore", invalid="ignore"):
        s = np.where(ray[:, 2] < -1e-6, -h / ray[:, 2], np.nan)
    return np.stack([cx + ray[:, 0] * s, -d + ray[:, 1] * s], 1)


def fit(landmarks, size, prior=None, free=()):
    """landmarks: [((X, Y, Z) or callable(extra) -> (X, Y, Z), (px, py)), ...]. `free` names extra
    unknown lengths (e.g. the gap between the soccer touchline and the football sideline) handed to
    the callables as a dict. prior: {"h": (12.33, 0.05), ...} = (value, tolerance in the same unit).
    Returns (cam, extra, residuals in px)."""
    from scipy.optimize import least_squares
    prior = prior or {}
    x0 = [1100, 0.0, np.radians(17), 0, 0, 0, 10, 12] + [10.0] * len(free)
    for n, (v, _) in prior.items():
        x0[PARAMS.index(n)] = v
    px = np.array([b for _, b in landmarks], float)

    def world(extra):
        return [a(extra) if callable(a) else a for a, _ in landmarks]

    def res(p):
        cam = dict(zip(PARAMS, p[:8])); extra = dict(zip(free, p[8:]))
        r = (project(world(extra), cam, size) - px).ravel()
        return np.concatenate([r, [(cam[n] - v) / tol for n, (v, tol) in prior.items()]])

    s = least_squares(res, x0)
    cam = {n: float(v) for n, v in zip(PARAMS, s.x[:8])}; extra = {n: float(v) for n, v in zip(free, s.x[8:])}
    return cam, extra, np.hypot(*(project(world(extra), cam, size) - px).T)
