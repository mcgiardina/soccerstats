"""Two-cluster kit colour assignment. Returns a callable mapping (frame, player box) -> 'us'|'them'
or None when separation is poor."""
import os
import sys

import cv2
import numpy as np
from sklearn.cluster import KMeans

from analyzer import db


def torso_color(img, box):
    x1, y1, x2, y2 = [int(v) for v in box[:4]]
    h = y2 - y1
    w = x2 - x1
    if h < 12 or w < 6:
        return None
    # upper-middle of the box: shirt, avoiding head and legs
    ty1, ty2 = y1 + int(h * 0.2), y1 + int(h * 0.55)
    tx1, tx2 = x1 + int(w * 0.2), x2 - int(w * 0.2)
    crop = img[max(0, ty1):ty2, max(0, tx1):tx2]
    if crop.size == 0:
        return None
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV).reshape(-1, 3).astype(np.float32)
    # drop very dark / very bright pixels (shadows, glare)
    m = (hsv[:, 2] > 40) & (hsv[:, 2] < 240)
    if m.sum() < 10:
        return None
    return np.median(hsv[m], axis=0)


def assign(dets, game_id, force_confirm=False):
    samples, refs = [], []
    for fi, d in enumerate(dets[::3]):
        for p in d.players:
            c = torso_color(d.img, p)
            if c is not None:
                samples.append(c); refs.append((fi * 3, p[4]))
    if len(samples) < 200:
        print("too few player samples for team assignment", file=sys.stderr)
        return None
    X = np.array(samples)
    # weight hue on the circle so red/orange don't split
    feats = np.column_stack([np.cos(np.radians(X[:, 0] * 2)) * X[:, 1], np.sin(np.radians(X[:, 0] * 2)) * X[:, 1], X[:, 2] * 0.5])
    km = KMeans(n_clusters=2, n_init=10, random_state=0).fit(feats)
    centers = km.cluster_centers_
    sep = np.linalg.norm(centers[0] - centers[1])
    spread = np.mean([np.linalg.norm(feats[km.labels_ == k] - centers[k], axis=1).mean() for k in (0, 1)])
    ratio = sep / max(spread, 1e-6)
    print(f"kit separation ratio {ratio:.2f} (need > 1.6)")
    if ratio < 1.6:
        return None

    us_cluster = None if force_confirm else db.get_team_choice(game_id)
    if us_cluster is None:
        us_cluster = _confirm(dets, refs, km.labels_, feats)
    # persist answer in this run's params happens through write_results caller; keep simple: stash on module
    assign.us_cluster = us_cluster

    def label_of(img, box):
        c = torso_color(img, box)
        if c is None:
            return None
        f = np.array([[np.cos(np.radians(c[0] * 2)) * c[1], np.sin(np.radians(c[0] * 2)) * c[1], c[2] * 0.5]])
        k = int(km.predict(f)[0])
        return "us" if k == us_cluster else "them"

    return label_of


def _confirm(dets, refs, labels, feats):
    """Write a preview frame with cluster-coloured boxes and ask once which is us."""
    # pick the frame with most players
    best = max(range(len(dets)), key=lambda i: len(dets[i].players))
    img = dets[best].img.copy()
    from sklearn.cluster import KMeans  # noqa: F401 (type hint only)
    idx = {r: l for r, l in zip(refs, labels)}
    for p in dets[best].players:
        k = idx.get((best - best % 3, p[4]))
        if k is None:
            continue
        col = (0, 200, 255) if k == 0 else (255, 80, 200)
        cv2.rectangle(img, (int(p[0]), int(p[1])), (int(p[2]), int(p[3])), col, 2)
        cv2.putText(img, "A" if k == 0 else "B", (int(p[0]), int(p[1]) - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.6, col, 2)
    out = os.path.join(os.path.dirname(os.path.dirname(__file__)), "cache", "team_preview.jpg")
    cv2.imwrite(out, img)
    print(f"Open {out}. Yellow boxes = A, magenta = B.")
    while True:
        ans = input("Which cluster is us? [A/B]: ").strip().upper()
        if ans in ("A", "B"):
            return 0 if ans == "A" else 1
