#!/usr/bin/env python3
"""Visual sanity check for a cached game: a 3x4 montage of random frames where the ball was
attributed to a player, showing the ball (yellow) and the nearest player's box coloured by
team label. Usage: python spotcheck.py <game-id> <youtube-id> [seed]"""
import os
import random
import sys

import cv2
import numpy as np

from analyzer import detect

game, yt = sys.argv[1], sys.argv[2]
seed = int(sys.argv[3]) if len(sys.argv) > 3 else 1
cache = os.path.expanduser("~/Library/Caches/match-film")
fps, dets = detect.load_cache(os.path.join(cache, f"{game}_dets.json.gz"))
cap = cv2.VideoCapture(os.path.join(cache, f"{yt}.mp4"))
src_fps = cap.get(cv2.CAP_PROP_FPS)

rows = []
for d in dets:
    if not d.ball or not d.players:
        continue
    bx, by = d.ball
    best, bd = None, 1e9
    for p in d.players:
        dist = np.hypot((p[0] + p[2]) / 2 - bx, p[3] - by)
        if dist < bd:
            best, bd = p, dist
    if best is not None and bd <= 90 and d.labels[best[4]]:
        rows.append((d, best, bd))
random.seed(seed)
pick = sorted(random.sample(rows, 12), key=lambda x: x[0].t)
tiles = []
for d, p, bd in pick:
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(round(d.t * src_fps)))
    ok, img = cap.read()
    if not ok:
        continue
    lab = d.labels[p[4]]
    col = (255, 255, 255) if lab == "us" else (255, 0, 255)
    cv2.rectangle(img, (int(p[0]), int(p[1])), (int(p[2]), int(p[3])), col, 3)
    cv2.circle(img, (int(d.ball[0]), int(d.ball[1])), 12, (0, 255, 255), 3)
    cx, cy = int(d.ball[0]), int(d.ball[1])
    x0, y0 = max(0, cx - 240), max(0, cy - 160)
    crop = img[y0:y0 + 320, x0:x0 + 480]
    crop = cv2.copyMakeBorder(crop, 0, 320 - crop.shape[0], 0, 480 - crop.shape[1], cv2.BORDER_CONSTANT)
    cv2.putText(crop, f"t={d.t:.0f}s {lab}", (6, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
    tiles.append(crop)
out = os.path.join(cache, f"spotcheck_{game[:8]}.jpg")
cv2.imwrite(out, np.vstack([np.hstack(tiles[i:i + 4]) for i in range(0, 12, 4)]))
print(f"{len(rows)} attributable frames; montage at {out} (white box = us, magenta = them)")
