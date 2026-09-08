# Analyzer

Standalone CLI. Reads a game from Supabase, pulls the unlisted YouTube video at 720p,
samples 5 fps, detects players and ball, assigns teams by kit colour, attributes possession
to the nearest player, and writes `team_stats`, `stat_buckets`, and machine `tags` back.
Everything it writes is a proposal; the web app renders it distinctly for a human to confirm.

```bash
cd analyzer
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in
python analyze.py --game-id <uuid>              # local, Apple Silicon MPS
python analyze.py --game-id <uuid> --backend cloud   # same code, meant for a GPU box
python analyze.py --game-id <uuid> --confirm-team    # re-pick which colour cluster is "us"
```

Never runs automatically. The web app's "Queue analysis run" button only inserts a
`stat_runs` row with `status='queued'`; this CLI claims it (or creates one if none exists).

## Stages
1. `fetch.py` yt-dlp, 720p mp4, cached under `cache/`.
2. `video.py` frame sampling at 5 fps with hardware decode where OpenCV supports it.
3. `detect.py` Ultralytics YOLO + ByteTrack. Roboflow football weights if `PLAYER_WEIGHTS` set, else COCO.
4. `teams.py` KMeans(2) on torso colours. Aborts possession if clusters are not separable.
5. `possession.py` nearest-player attribution, 1.5 s smoothing, per half + 5-minute buckets, turnovers.
6. `shots.py` ball acceleration toward a goal region → machine shot tags (recall-first).
7. `homography.py` pitch keypoints → homography (only if `PITCH_WEIGHTS` set). Feeds machine shot
   locations and `shape_snapshots`.
8. `db.py` writes. Human rows are never overwritten.

Honesty: the tracking camera keeps the ball centred, so the ball's pixel position says
nothing about field position. Everything positional goes through the homography or is skipped.
No per-player data is ever persisted, including tracker IDs.
