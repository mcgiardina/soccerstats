"""Find the goal frame in the image near a detected keeper. Anchor on the crossbar: a long,
bright, near-horizontal line 1.2-2.6 keeper-heights above the keeper's feet, then look for the
posts (bright near-vertical lines) at its ends. Classic CV, no training.
Returns {"left","right","top","bottom","crossbar","score"} in image pixels or None."""
import cv2
import numpy as np


def _white_mask(roi):
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    m = cv2.inRange(hsv, (0, 0, 150), (180, 80, 255))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    return m


def find_goal(img, keeper_box, kh=None):
    x1, y1, x2, y2 = [int(v) for v in keeper_box[:4]]
    kh = float(kh or max(12, y2 - y1))
    cx, feet = (x1 + x2) / 2, float(y2)
    H, W = img.shape[:2]
    rx1, rx2 = max(0, int(cx - 6.5 * kh)), min(W, int(cx + 6.5 * kh))
    ry1, ry2 = max(0, int(feet - 3.2 * kh)), min(H, int(feet + 0.6 * kh))
    roi = img[ry1:ry2, rx1:rx2]
    if roi.size == 0 or roi.shape[0] < 8 or roi.shape[1] < 8:
        return None
    white = _white_mask(roi)
    lines = cv2.HoughLinesP(white, 1, np.pi / 180, threshold=max(12, int(0.5 * kh)), minLineLength=max(8, int(0.6 * kh)), maxLineGap=max(3, int(0.3 * kh)))
    if lines is None:
        return None
    bars, posts = [], []
    for ax, ay, bx, by in np.asarray(lines).reshape(-1, 4):
        dx, dy = bx - ax, by - ay
        length = float(np.hypot(dx, dy))
        ang = abs(np.degrees(np.arctan2(dy, dx))) % 180
        if ang < 12 or ang > 168:
            y = (ay + by) / 2 + ry1
            if feet - 2.8 * kh <= y <= feet - 1.0 * kh and length >= 2.0 * kh:
                bars.append((min(ax, bx) + rx1, max(ax, bx) + rx1, y, length))
        elif 70 < ang < 110:
            posts.append((min(ax, bx) + rx1, min(ay, by) + ry1, max(ay, by) + ry1, length))
    if not bars:
        return None
    # longest crossbar wins; merge collinear bar segments that overlap in y
    bars.sort(key=lambda b: -b[3])
    L, R, y, _ = bars[0]
    for b in bars[1:]:
        if abs(b[2] - y) < 0.2 * kh and (b[0] < R + 0.5 * kh and b[1] > L - 0.5 * kh):
            L, R = min(L, b[0]), max(R, b[1])
    width = R - L
    if not (2.5 * kh <= width <= 9.0 * kh):
        return None
    # posts near the bar ends, hanging down from the bar
    def post_near(x):
        cands = [p for p in posts if abs(p[0] - x) < 0.5 * kh and p[1] <= y + 0.5 * kh and p[2] >= y + 0.5 * kh]
        return max(cands, key=lambda p: p[3]) if cands else None
    lp, rp = post_near(L), post_near(R)
    n_posts = int(lp is not None) + int(rp is not None)
    # extend the mouth to the outermost posts hanging from the bar (the bar segment can be partial)
    hanging = [p for p in posts if p[1] <= y + 0.5 * kh and p[2] >= y + 0.5 * kh and (L - 3.0 * kh) <= p[0] <= (R + 3.0 * kh)]
    if hanging:
        L, R = min(L, min(p[0] for p in hanging)), max(R, max(p[0] for p in hanging))
        width = R - L
    bottom = max([p[2] for p in hanging] + [feet])
    # Net texture: the mouth below the bar should contain a fair share of bright pixels (net
    # mesh, posts). A crowd or a tent edge behind the keeper does not.
    ix1, ix2 = int(max(0, L - rx1)), int(min(roi.shape[1], R - rx1))
    iy1, iy2 = int(max(0, y - ry1)), int(min(roi.shape[0], bottom - ry1))
    inner = white[iy1:iy2, ix1:ix2]
    white_frac = float(inner.mean() / 255.0) if inner.size else 0.0
    # Ground lines (goal line, six-yard box) and rows of cars also give long bright horizontals.
    # A real goal has at least one post hanging down from the bar and a net mesh below it.
    if n_posts == 0 or white_frac < 0.07:
        return None
    # the keeper should stand within the mouth (plus a little), not beside a random white line
    if not (L - 1.0 * kh <= cx <= R + 1.0 * kh):
        return None
    score = min(1.0, 0.4 + 0.2 * n_posts + 0.1 * min(2.0, width / (4.5 * kh)) + min(0.2, white_frac))
    return {"left": float(L), "right": float(R), "top": float(y), "bottom": float(bottom), "crossbar": True, "posts": n_posts, "white": round(white_frac, 2), "score": round(score, 2), "kh": kh}
