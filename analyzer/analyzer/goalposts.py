"""Find the goal frame in the image near a detected keeper: two tall bright near-vertical lines
(posts) roughly 5 keeper-heights apart with a bright horizontal line (crossbar) on top.
Returns the goal mouth as an image-space quad or None. Classic CV, no training."""
import cv2
import numpy as np


def find_goal(img, keeper_box, kh=None):
    x1, y1, x2, y2 = [int(v) for v in keeper_box[:4]]
    kh = kh or max(12, y2 - y1)
    cx, feet = (x1 + x2) // 2, y2
    H, W = img.shape[:2]
    # search window: ~4 keeper-heights each side, from feet up 2.6 kh
    rx1, rx2 = max(0, int(cx - 4.5 * kh)), min(W, int(cx + 4.5 * kh))
    ry1, ry2 = max(0, int(feet - 2.6 * kh)), min(H, int(feet + 0.4 * kh))
    roi = img[ry1:ry2, rx1:rx2]
    if roi.size == 0:
        return None
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    white = cv2.inRange(hsv, (0, 0, 170), (180, 60, 255))
    white = cv2.morphologyEx(white, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    lines = cv2.HoughLinesP(white, 1, np.pi / 180, threshold=int(0.6 * kh), minLineLength=int(0.9 * kh), maxLineGap=int(0.25 * kh))
    if lines is None:
        return None
    verts, horiz = [], []
    for l in np.asarray(lines).reshape(-1, 4):
        ax, ay, bx, by = l
        dx, dy = bx - ax, by - ay
        length = np.hypot(dx, dy)
        if length < 0.9 * kh:
            continue
        ang = abs(np.degrees(np.arctan2(dy, dx)))
        if ang > 75 and ang < 105:
            verts.append((min(ax, bx) + rx1, min(ay, by) + ry1, max(ay, by) + ry1, length))
        elif ang < 15 or ang > 165:
            horiz.append((min(ax, bx) + rx1, max(ax, bx) + rx1, (ay + by) / 2 + ry1, length))
    if len(verts) < 2:
        return None
    # pick the pair of posts with plausible spacing (3..7 kh) and similar tops
    best = None
    for i in range(len(verts)):
        for j in range(i + 1, len(verts)):
            a, b = sorted([verts[i], verts[j]], key=lambda v: v[0])
            gap = b[0] - a[0]
            if not (2.5 * kh <= gap <= 7.5 * kh):
                continue
            top = min(a[1], b[1]); bot = max(a[2], b[2])
            if bot - top < 1.0 * kh:
                continue
            # a crossbar near the top spanning most of the gap is strong confirmation
            bar = any(abs(h[2] - top) < 0.35 * kh and h[0] <= a[0] + 0.5 * kh and h[1] >= b[0] - 0.5 * kh for h in horiz)
            score = (a[3] + b[3]) / kh + (3.0 if bar else 0.0)
            if best is None or score > best[0]:
                best = (score, a[0], b[0], top, bot, bar)
    if best is None:
        return None
    _, lx, rx, top, bot, bar = best
    return {"left": float(lx), "right": float(rx), "top": float(top), "bottom": float(bot), "crossbar": bool(bar), "kh": float(kh)}
