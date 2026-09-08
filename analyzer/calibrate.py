#!/usr/bin/env python3
"""Pick a fisheye de-warp for a wide-angle camera by eye.

  python calibrate.py preview <video.mp4> <camera-name> [--t 600]
      writes <cache>/calib_<camera-name>_<i>.jpg for a grid of distortion strengths
  python calibrate.py save <camera-name> <width> <height> <k1> [fov_scale] [balance]
      saves calib/<camera-name>.json; the analyzer applies it to videos of kind 'wide_fixed'

Look for the candidate where the touchlines and penalty box edges are straight. Straight lines
matter more than the edges of the frame going black."""
import os
import sys

import cv2

from analyzer import dewarp
from analyzer.fetch import CACHE


def main():
    cmd = sys.argv[1]
    if cmd == "preview":
        path, name = sys.argv[2], sys.argv[3]
        t = float(sys.argv[sys.argv.index("--t") + 1]) if "--t" in sys.argv else 600.0
        cap = cv2.VideoCapture(path)
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(t * (cap.get(cv2.CAP_PROP_FPS) or 30)))
        ok, img = cap.read()
        if not ok:
            sys.exit("could not read a frame")
        h, w = img.shape[:2]
        os.makedirs(CACHE, exist_ok=True)
        grid = [(k1, fov) for fov in (0.8, 1.0, 1.2) for k1 in (0.05, 0.12, 0.2, 0.3)]
        for i, (k1, fov) in enumerate(grid):
            dewarp.save(f"_preview_{name}", dewarp.make_params((w, h), k1, fov_scale=fov))
            fn = dewarp.load(f"_preview_{name}")
            out = fn(img)
            cv2.putText(out, f"#{i} k1={k1} fov_scale={fov}", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 255), 3)
            cv2.imwrite(os.path.join(CACHE, f"calib_{name}_{i}.jpg"), cv2.resize(out, (1280, int(1280 * h / w))))
        os.remove(dewarp.calib_path(f"_preview_{name}"))
        print(f"wrote {len(grid)} previews to {CACHE}/calib_{name}_*.jpg; then run: python calibrate.py save {name} {w} {h} <k1> <fov_scale>")
    elif cmd == "save":
        name, w, h, k1 = sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), float(sys.argv[5])
        fov = float(sys.argv[6]) if len(sys.argv) > 6 else 1.0
        bal = float(sys.argv[7]) if len(sys.argv) > 7 else 0.0
        print("saved", dewarp.save(name, dewarp.make_params((w, h), k1, fov_scale=fov, balance=bal)))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
