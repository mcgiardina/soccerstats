"""Two-cluster kit colour assignment. Returns a callable mapping (frame, player box) -> 'us'|'them'
or None when separation is poor."""
import os
import sys

import cv2
import numpy as np
from sklearn.cluster import KMeans

from analyzer import db


def torso_color(img, box):
    """Median LAB colour of the shirt, ignoring grass and shadow pixels. Returns [L, a, b] or None."""
    x1, y1, x2, y2 = [int(v) for v in box[:4]]
    h, w = y2 - y1, x2 - x1
    if h < 14 or w < 5:
        return None
    ty1, ty2 = y1 + int(h * 0.18), y1 + int(h * 0.50)
    tx1, tx2 = x1 + int(w * 0.25), x2 - int(w * 0.25)
    crop = img[max(0, ty1):ty2, max(0, tx1):tx2]
    if crop.size == 0:
        return None
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV).reshape(-1, 3)
    lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB).reshape(-1, 3).astype(np.float32)
    grass = (hsv[:, 0] > 30) & (hsv[:, 0] < 95) & (hsv[:, 1] > 50)
    dark = hsv[:, 2] < 45
    keep = ~grass & ~dark
    if keep.sum() < 8:
        return None
    return np.median(lab[keep], axis=0)


def _feat(c):
    # chroma dominates; lightness separates white from dark kits
    return np.array([c[1] - 128, c[2] - 128, (c[0] - 128) * 0.6], dtype=np.float32)


def assign(dets, game_id, force_confirm=False, us_cluster=None):
    samples, refs = [], []
    for fi, d in enumerate(dets[::3]):
        for p in d.players:
            if (p[3] - p[1]) < 28:   # fit only on players big enough to have a clean shirt crop
                continue
            c = torso_color(d.img, p)
            if c is not None:
                samples.append(_feat(c)); refs.append((fi * 3, p[4]))
    if len(samples) < 200:
        print("too few player samples for team assignment", file=sys.stderr)
        return None
    feats = np.array(samples)
    km = KMeans(n_clusters=2, n_init=10, random_state=0).fit(feats)
    centers = km.cluster_centers_
    sep = np.linalg.norm(centers[0] - centers[1])
    spread = np.mean([np.linalg.norm(feats[km.labels_ == k] - centers[k], axis=1).mean() for k in (0, 1)])
    ratio = sep / max(spread, 1e-6)
    print(f"kit separation ratio {ratio:.2f} (need > 1.6)")
    if ratio < 1.6:
        return None

    _write_preview(dets, refs, km.labels_)
    if us_cluster is None and not force_confirm:
        us_cluster = db.get_team_choice(game_id)
    if us_cluster is None:
        us_cluster = _confirm()
    # persist answer in this run's params happens through write_results caller; keep simple: stash on module
    assign.us_cluster = us_cluster

    centers = km.cluster_centers_
    def label_of(img, box):
        c = torso_color(img, box)
        if c is None:
            return None
        f = _feat(c)
        d = np.linalg.norm(centers - f, axis=1)
        # refuse ambiguous colours (referee, keeper, bystander): must be clearly closer to one centre
        if d.min() > 0.8 * sep or d.max() - d.min() < 0.25 * sep:
            return None
        return "us" if int(d.argmin()) == us_cluster else "them"

    return label_of


PREVIEW = os.path.join(os.path.dirname(os.path.dirname(__file__)), "cache", "team_preview.jpg")


def _write_preview(dets, refs, labels):
    """Preview frame with cluster-coloured boxes: A = yellow (cluster 0), B = magenta (cluster 1)."""
    idx = {r: l for r, l in zip(refs, labels)}
    # frame (among the sampled ones) with the most labelled players
    def score(i):
        return sum(1 for p in dets[i].players if (i, p[4]) in idx)
    best = max(range(0, len(dets), 3), key=score)
    img = dets[best].img.copy()
    for p in dets[best].players:
        k = idx.get((best, p[4]))
        if k is None:
            continue
        col = (0, 200, 255) if k == 0 else (255, 80, 200)
        cv2.rectangle(img, (int(p[0]), int(p[1])), (int(p[2]), int(p[3])), col, 2)
        cv2.putText(img, "A" if k == 0 else "B", (int(p[0]), int(p[1]) - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.6, col, 2)
    os.makedirs(os.path.dirname(PREVIEW), exist_ok=True)
    cv2.imwrite(PREVIEW, img)
    print(f"team preview written to {PREVIEW} (A = yellow, B = magenta)")


def _confirm():
    while True:
        ans = input("Which cluster is us? [A/B]: ").strip().upper()
        if ans in ("A", "B"):
            return 0 if ans == "A" else 1
