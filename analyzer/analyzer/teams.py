"""Two-cluster kit colour assignment. Returns a callable mapping (frame, player box) -> 'us'|'them'
or None when separation is poor."""
import os
import sys

import cv2
import numpy as np
from sklearn.cluster import KMeans

from analyzer import db

NEUTRAL_CHROMA = 9.0      # below this normalised chroma a cluster is white/grey/black
HUE_GAP_DEG = 30.0        # chromatic clusters within this hue angle are the same kit
NEUTRAL_LIGHT_GAP = 12.0  # neutral clusters closer than this in damped lightness are the same kit


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
    grass = is_field_pixel(hsv, field_colour(img))
    dark = hsv[:, 2] < 45
    keep = ~grass & ~dark
    if keep.sum() < 8:
        return None
    return np.median(lab[keep], axis=0)


_FIELD_CACHE = {}


def field_colour(img):
    """Median HSV of the playing surface, measured from the lower-middle of the frame where the
    pitch nearly always is. Handles green turf, yellowed grass and artificial surfaces alike."""
    key = id(img)
    hit = _FIELD_CACHE.get(key)
    if hit is not None and hit[0] is img:
        return hit[1]
    h, w = img.shape[:2]
    patch = img[int(h * 0.55):int(h * 0.9):4, int(w * 0.3):int(w * 0.7):4]
    hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV).reshape(-1, 3)
    med = tuple(int(v) for v in np.median(hsv, axis=0))
    if len(_FIELD_CACHE) > 8:
        _FIELD_CACHE.clear()
    _FIELD_CACHE[key] = (img, med)
    return med


def is_field_pixel(hsv, field):
    fh, fs, _ = field
    dh = np.abs(hsv[:, 0].astype(int) - fh)
    dh = np.minimum(dh, 180 - dh)
    return (dh <= 14) & (hsv[:, 1] >= max(25, 0.4 * fs)) & (hsv[:, 2] > 40)


def on_grass(img, box, min_field=0.45):
    """True when the strip just below the box is mostly playing surface: a player on the pitch,
    not a spectator under a tent or someone behind the fence. Surface colour is measured
    from the frame itself, so dry yellow grass and artificial turf work too."""
    x1, y1, x2, y2 = [int(v) for v in box[:4]]
    h, w = img.shape[:2]
    cx = (x1 + x2) // 2
    strip = img[min(h - 1, y2 + 1):min(h, y2 + 8), max(0, cx - max(4, (x2 - x1) // 3)):min(w, cx + max(4, (x2 - x1) // 3))]
    if strip.size == 0:
        return False
    hsv = cv2.cvtColor(strip, cv2.COLOR_BGR2HSV).reshape(-1, 3)
    return is_field_pixel(hsv, field_colour(img)).mean() >= min_field


def _feat(c):
    """Lightness-normalised chromaticity plus damped lightness. A navy shirt in shade and in
    sun land near each other; white stays neutral; black stays dark."""
    L = max(float(c[0]), 20.0)
    return np.array([(c[1] - 128) / L * 100, (c[2] - 128) / L * 100, (c[0] - 128) * 0.15], dtype=np.float32)


def _same_kit(ci, cj):
    """Two cluster centres are the same kit if they share a hue (both chromatic), or are both
    neutral with similar lightness. A neutral (white/grey) centre never merges with a coloured one."""
    chroma_i, chroma_j = np.hypot(ci[0], ci[1]), np.hypot(cj[0], cj[1])
    if chroma_i >= NEUTRAL_CHROMA and chroma_j >= NEUTRAL_CHROMA:
        hue_gap = abs((np.degrees(np.arctan2(ci[1], ci[0]) - np.arctan2(cj[1], cj[0])) + 180) % 360 - 180)
        return hue_gap < HUE_GAP_DEG
    if chroma_i < NEUTRAL_CHROMA and chroma_j < NEUTRAL_CHROMA:
        return abs(ci[2] - cj[2]) < NEUTRAL_LIGHT_GAP
    return False


def assign(dets, game_id, force_confirm=False, us_cluster=None):
    samples, refs = [], []
    for fi, d in enumerate(dets[::3]):
        for p in d.players:
            if (p[3] - p[1]) < 28 or not on_grass(d.img, p):   # big enough for a clean shirt crop, and on the pitch
                continue
            c = torso_color(d.img, p)
            if c is not None:
                samples.append(_feat(c)); refs.append((fi * 3, p[4]))
    if len(samples) < 200:
        print("too few player samples for team assignment", file=sys.stderr)
        return None
    feats = np.array(samples)
    # Four centres: two teams plus room for keepers / referee / stragglers. The two most
    # populous clusters are the teams; everything else is "nobody".
    km4 = KMeans(n_clusters=4, n_init=10, random_state=0).fit(feats)
    raw_labels = km4.labels_.copy()
    C = km4.cluster_centers_.copy()
    counts = np.bincount(raw_labels, minlength=4).astype(float)
    # Group clusters that are the same kit under different light. Raw centres are kept for
    # assignment; only the group -> team mapping is merged.
    group = list(range(4))
    for i in range(4):
        for j in range(i + 1, 4):
            if group[i] != group[j] and _same_kit(C[i], C[j]):
                gi, gj = group[i], group[j]
                keep, drop = (gi, gj) if counts[gi] >= counts[gj] else (gj, gi)
                counts[keep] += counts[drop]; counts[drop] = 0
                group = [keep if g == drop else g for g in group]
    merged = np.array([group[l] for l in raw_labels])
    sizes_all = np.bincount(merged, minlength=4)
    top = np.argsort(sizes_all)[::-1][:2]
    centers = np.array([feats[merged == k].mean(axis=0) for k in top])
    sizes = sizes_all[top]
    sep = np.linalg.norm(centers[0] - centers[1])
    spread = np.mean([np.linalg.norm(feats[raw_labels == k] - C[k], axis=1).mean() for k in range(4) if group[k] in top])
    ratio = sep / max(spread, 1e-6)
    print(f"kit clusters: raw sizes {np.bincount(raw_labels, minlength=4).tolist()}, merged {sizes_all.tolist()}, teams = {top.tolist()}, separation ratio {ratio:.2f} (need > 1.6)")
    if ratio < 1.6 or sizes[1] < 0.25 * sizes[0]:
        return None
    labels = np.full(len(feats), -1)
    labels[merged == top[0]] = 0
    labels[merged == top[1]] = 1
    cluster_centers = C

    _write_preview(dets, refs, labels)
    if us_cluster is None and not force_confirm:
        us_cluster = db.get_team_choice(game_id)
    if us_cluster is None:
        us_cluster = _confirm()
    # persist answer in this run's params happens through write_results caller; keep simple: stash on module
    assign.us_cluster = us_cluster

    team_of_cluster = {int(top[0]): 0, int(top[1]): 1}
    for g_from, g_to in enumerate(group):        # merged clusters map to their surviving team
        if g_to in team_of_cluster and g_from not in team_of_cluster:
            team_of_cluster[g_from] = team_of_cluster[g_to]

    def label_of(img, box):
        if not on_grass(img, box):
            return None
        c = torso_color(img, box)
        if c is None:
            return None
        f = _feat(c)
        d = np.linalg.norm(cluster_centers - f, axis=1)
        k = int(d.argmin())
        if k not in team_of_cluster:          # keeper / referee / straggler cluster
            return None
        if d[k] > 0.9 * sep:                  # far from every centre: don't guess
            return None
        return "us" if team_of_cluster[k] == us_cluster else "them"

    return label_of


from analyzer.fetch import CACHE
PREVIEW = os.path.join(CACHE, "team_preview.jpg")


def _write_preview(dets, refs, labels):
    """Preview frame with cluster-coloured boxes: A = yellow (cluster 0), B = magenta (cluster 1)."""
    idx = {r: l for r, l in zip(refs, labels) if l >= 0}
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
