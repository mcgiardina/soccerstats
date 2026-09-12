"""Two-cluster kit colour assignment. Returns a callable mapping (frame, player box) -> 'us'|'them'
or None when separation is poor."""
import os
import sys

import cv2
import numpy as np
from sklearn.cluster import KMeans

from analyzer import db

# Shirt sampling. Measured 2026-09-09: relaxing these (wider crop, DARK_V 28-35, MIN_KEEP 4-6) turned
# "unlabelled" into "wrong" for shaded dark kits (blue players read as white from skin/shorts pixels).
SMALL_WIDE = False  # widen the shirt crop horizontally for small boxes
DARK_V = 45         # HSV value below which a pixel is treated as shadow/black and ignored
MIN_KEEP = 8        # minimum usable shirt pixels
MERGE_DIST = 30.0   # feature-space distance below which two colour clusters are the same kit

NEUTRAL_CHROMA = 9.0      # below this normalised chroma a cluster is white/grey/black
HUE_GAP_DEG = 30.0        # chromatic clusters within this hue angle are the same kit
NEUTRAL_LIGHT_GAP = 12.0  # neutral clusters closer than this in damped lightness are the same kit


def torso_color(img, box):
    """Median LAB colour of the shirt, ignoring grass and shadow pixels. Returns [L, a, b] or None."""
    x1, y1, x2, y2 = [int(v) for v in box[:4]]
    h, w = y2 - y1, x2 - x1
    if h < 14 or w < 5:
        return None
    # Small (distant) players get a slightly wider crop so shadowed shirts still yield enough
    # pixels, but never below mid-torso: shorts are often the other colour.
    small = h < 40 and SMALL_WIDE
    ty1, ty2 = y1 + int(h * (0.16 if small else 0.18)), y1 + int(h * (0.48 if small else 0.50))
    tx1, tx2 = x1 + int(w * (0.15 if small else 0.25)), x2 - int(w * (0.15 if small else 0.25))
    crop = img[max(0, ty1):ty2, max(0, tx1):tx2]
    if crop.size == 0:
        return None
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV).reshape(-1, 3)
    lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB).reshape(-1, 3).astype(np.float32)
    grass = is_field_pixel(hsv, field_colour(img))
    dark = hsv[:, 2] < DARK_V
    keep = ~grass & ~dark
    if keep.sum() < MIN_KEEP:
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
    # Six patches across the lower-middle band; keep the ones that look like a playing surface
    # (green through yellowed grass), so a camera pole, the crowd or a tent can't hijack the estimate.
    meds = []
    for ry in ((0.45, 0.65), (0.65, 0.88)):
        for rx in ((0.12, 0.38), (0.38, 0.62), (0.62, 0.88)):
            patch = img[int(h * ry[0]):int(h * ry[1]):4, int(w * rx[0]):int(w * rx[1]):4]
            hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV).reshape(-1, 3)
            m = np.median(hsv, axis=0)
            if 15 <= m[0] <= 95 and m[1] >= 35 and m[2] >= 50:
                meds.append(m)
    if meds:
        med = tuple(int(v) for v in np.median(np.array(meds), axis=0))
    else:
        med = (50, 120, 130)   # generic green fallback
    if len(_FIELD_CACHE) > 8:
        _FIELD_CACHE.clear()
    _FIELD_CACHE[key] = (img, med)
    return med


ADAPTIVE_FIELD = True   # False = the original fixed green test (hue 30-95, sat > 40)


def is_field_pixel(hsv, field):
    """Field = the original green rule OR a band around the measured surface hue. The union keeps
    the validated behaviour on green pitches (adaptive-only skewed possession on the Dynamo game)
    and adds yellowed grass / turf."""
    green = (hsv[:, 0] > 30) & (hsv[:, 0] < 95) & (hsv[:, 1] > 40) & (hsv[:, 2] > 40)
    if not ADAPTIVE_FIELD:
        return green
    fh, fs, _ = field
    dh = np.abs(hsv[:, 0].astype(int) - fh)
    dh = np.minimum(dh, 180 - dh)
    adaptive = (dh <= 14) & (hsv[:, 1] >= max(40, 0.4 * fs)) & (hsv[:, 2] > 40)
    return green | adaptive


_PITCH_CACHE = {}


def pitch_mask(img, scale=4, dilate_px=40):
    """Coarse mask of the playing surface: the largest connected grass component, closed so
    players and lines are filled, then dilated (goal frame, ball in the air near the goal).
    The tree line, the sky and the far side of a parking lot are separate components."""
    key = id(img)
    hit = _PITCH_CACHE.get(key)
    if hit is not None and hit[0] is img:
        return hit[1]
    h, w = img.shape[:2]
    small = cv2.resize(img, (w // scale, h // scale), interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV).reshape(-1, 3)
    m = is_field_pixel(hsv, field_colour(img)).reshape(small.shape[:2]).astype(np.uint8)
    k = max(3, 24 // scale)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((k, k), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    if n <= 1:
        out = np.ones(small.shape[:2], dtype=bool)
    else:
        biggest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        out = lab == biggest
        d = max(1, dilate_px // scale)
        out = cv2.dilate(out.astype(np.uint8), np.ones((d, d), np.uint8)).astype(bool)
    _PITCH_CACHE.clear()
    _PITCH_CACHE[key] = (img, (out, scale))
    return out, scale


def in_pitch(img, x, y):
    mask, scale = pitch_mask(img)
    yy, xx = int(y) // scale, int(x) // scale
    if 0 <= yy < mask.shape[0] and 0 <= xx < mask.shape[1]:
        return bool(mask[yy, xx])
    return False


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
    samples, refs, raw_bgr = [], [], []
    for fi, d in enumerate(dets[::3]):
        for p in d.players:
            if (p[3] - p[1]) < 28 or not on_grass(d.img, p):   # big enough for a clean shirt crop, and on the pitch
                continue
            c = torso_color(d.img, p)
            if c is not None:
                samples.append(_feat(c)); refs.append((fi * 3, p[4])); raw_bgr.append(c)
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
    raw_all = np.array(raw_bgr, dtype=float)
    assign.kits = [{"cluster": "AB"[k], "lab": [int(v) for v in np.median(raw_all[labels == k], axis=0)], "samples": int((labels == k).sum())} for k in (0, 1)]
    assign.kits.append({"separation": round(float(ratio), 2), "samples_total": int(len(feats))})
    assign.method = "flag" if us_cluster is not None else None
    kits = [np.median(raw_all[labels == k], axis=0) for k in (0, 1)]
    if us_cluster is None and not force_confirm:
        # 1) the kit colour set on the game (or the team colour): decided by shirt colour
        kit = db.get_kit_color(game_id)
        pick = _pick_by_colour(kits, kit) if kit else None
        if pick is not None:
            us_cluster = pick
            assign.method = f"kit colour {kit}"
            print(f"us = cluster {'AB'[pick]} (closest to kit colour {kit})")
    if us_cluster is None and not force_confirm:
        # 2) what an earlier run of this game decided, matched by the shirt colour it recorded
        prev = db.get_team_choice(game_id)
        if prev.get("lab"):
            d = [float(np.linalg.norm(k - np.array(prev["lab"], dtype=float))) for k in kits]
            us_cluster = int(np.argmin(d))
            assign.method = "remembered kit colour"
            print(f"us = cluster {'AB'[us_cluster]} (nearest the remembered shirt colour LAB {prev['lab']})")
        elif prev.get("letter") is not None:
            us_cluster = prev["letter"]
            assign.method = "remembered letter (unreliable across runs)"
    if us_cluster is None:
        us_cluster = _confirm()
        assign.method = assign.method or ("confirmed" if sys.stdin.isatty() else "assumed A")
    assign.us_kit_lab = [int(v) for v in kits[us_cluster]]
    # persisted into this run's params by the caller (get_team_choice reads it back next time)
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


def _hex_bgr(h):
    h = h.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    if len(h) != 6:
        return None
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return np.array([b, g, r], dtype=float)


def _lab_to_bgr(lab):
    return cv2.cvtColor(np.uint8([[np.clip(lab, 0, 255)]]), cv2.COLOR_LAB2BGR)[0, 0]


def _pick_by_colour(kits_lab, kit_hex):
    """Index (0/1) of the kit whose median shirt colour (LAB, as torso_color returns it) is closest
    to the named colour. Coloured kits compare by hue; a white / black / grey kit compares by
    saturation and lightness so that 'white' picks the pale kit even under a warm evening sky."""
    target = _hex_bgr(kit_hex)
    if target is None:
        return None
    t_hsv = cv2.cvtColor(np.uint8([[target]]), cv2.COLOR_BGR2HSV)[0, 0].astype(float)
    k_hsv = [cv2.cvtColor(np.uint8([[_lab_to_bgr(k)]]), cv2.COLOR_BGR2HSV)[0, 0].astype(float) for k in kits_lab]
    if t_hsv[1] < 60:                                   # neutral target: white / grey / black
        scores = [abs(k[1] - t_hsv[1]) / 255.0 + abs(k[2] - t_hsv[2]) / 255.0 for k in k_hsv]
    else:
        def hue_d(a, b):
            d = abs(a - b) % 180
            return min(d, 180 - d) / 90.0
        # Shade and white trim wash a coloured shirt toward grey in the median, so a neutral
        # kit is "unknown" (0.5) rather than ruled out; a saturated kit of another hue is ruled out.
        scores = [hue_d(k[0], t_hsv[0]) if k[1] >= 50 else 0.5 for k in k_hsv]
    best = int(np.argmin(scores))
    other = 1 - best
    # the named colour must actually be on the pitch: a neutral target needs a pale/dark kit; a
    # coloured target needs either a kit of that hue, or a kit that is clearly some other colour
    # so the remaining one must be ours
    if t_hsv[1] < 60:
        plausible = k_hsv[best][1] < 90
    else:
        plausible = scores[best] < 0.45 or (k_hsv[other][1] >= 50 and scores[other] > 0.6)
    if not plausible or abs(scores[0] - scores[1]) < 0.05:
        print(f"kit colour {kit_hex} does not match either kit (scores {[round(x, 2) for x in scores]}); not deciding by colour")
        return None
    return best


def _confirm():
    if not sys.stdin.isatty():
        print("no terminal to confirm the team: assuming cluster A is us (check team_preview.jpg; "
              "pass --us-cluster or --relabel to fix)")
        return 0
    while True:
        ans = input("Which cluster is us? [A/B]: ").strip().upper()
        if ans in ("A", "B"):
            return 0 if ans == "A" else 1
