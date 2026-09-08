#!/bin/bash
# Downloads the three pre-trained YOLO weights published by Roboflow in roboflow/sports
# (MIT licence): player/goalkeeper/referee/ball detector, dedicated ball detector, and the
# 32-landmark pitch keypoint model. Same Google Drive files as their examples/soccer/setup.sh.
# No Roboflow account or API key is needed. Files land outside the repo and outside Dropbox.
set -e
DIR="${ANALYZER_CACHE:-$HOME/Library/Caches/match-film}/weights"
mkdir -p "$DIR"
VENV="$(cd "$(dirname "$0")" && pwd)/.venv/bin"
"$VENV/pip" install -q gdown
"$VENV/gdown" -O "$DIR/football-player-detection.pt" "https://drive.google.com/uc?id=17PXFNlx-jI7VjVo_vQnB1sONjRyvoB-q"
"$VENV/gdown" -O "$DIR/football-ball-detection.pt"   "https://drive.google.com/uc?id=1isw4wx-MK9h9LMr36VvIWlJD6ppUvw7V"
"$VENV/gdown" -O "$DIR/football-pitch-detection.pt"  "https://drive.google.com/uc?id=1Ma5Kt86tgpdjCTKfum79YMgNnSjcoOyf"
ls -la "$DIR"
echo "done: the analyzer picks these up automatically (env PLAYER_WEIGHTS / PITCH_WEIGHTS still override)."
