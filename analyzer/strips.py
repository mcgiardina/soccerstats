#!/usr/bin/env python3
"""Frame strips around machine candidates so a human can judge them quickly.
Usage: python strips.py <game-id> <youtube-id> [shot|kick] [max]
Writes <cache>/strips_<game8>_<kind>_N.jpg, four frames per candidate (t, +0.6, +1.2, +1.8 s),
ball circled when the cache saw it."""
import json
import os
import sys

import cv2
import numpy as np

from analyzer import detect

game, yt = sys.argv[1], sys.argv[2]
kind = sys.argv[3] if len(sys.argv) > 3 else "shot"
limit = int(sys.argv[4]) if len(sys.argv) > 4 else 8
cache = os.path.expanduser("~/Library/Caches/match-film")
r = json.load(open(os.path.join(cache, f"{game}_results.json")))
cands = r.get("shot_candidates" if kind == "shot" else "kick_candidates", [])
fps, dets = detect.load_cache(os.path.join(cache, f"{game}_dets.json.gz"))
by_t = {round(d.t, 1): d for d in dets}
cap = cv2.VideoCapture(os.path.join(cache, f"{yt}.mp4"))
src_fps = cap.get(cv2.CAP_PROP_FPS)
pick = cands[:: max(1, len(cands) // limit)][:limit]
rows = []
for c in pick:
    tiles = []
    for dt in (0.0, 0.6, 1.2, 1.8):
        t = c["t"] + dt
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(round(t * src_fps)))
        ok, img = cap.read()
        if not ok:
            continue
        d = by_t.get(round(round(t * fps) / fps, 1))
        if d and d.ball:
            cv2.circle(img, (int(d.ball[0]), int(d.ball[1])), 14, (0, 0, 255), 3)
        if d:
            for k in getattr(d, "keepers", []) or []:
                cv2.rectangle(img, (int(k[0]), int(k[1])), (int(k[2]), int(k[3])), (255, 0, 255), 3)
        img = cv2.resize(img, (480, 270))
        extra = f" appr {c['keeper_approach']}" if "keeper_approach" in c else ""
        cv2.putText(img, f"t={t:.1f}s {c.get('team')} conf {c['confidence']:.2f}{extra}", (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        tiles.append(img)
    if len(tiles) == 4:
        rows.append(np.hstack(tiles))
for i in range(0, len(rows), 4):
    out = os.path.join(cache, f"strips_{game[:8]}_{kind}_{i // 4}.jpg")
    cv2.imwrite(out, np.vstack(rows[i:i + 4]))
    print("wrote", out)
print(f"{len(cands)} {kind} candidates total; showed {len(rows)}")
