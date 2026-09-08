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
python analyze.py --game-id <uuid> --dry-run --limit-seconds 180   # pilot: computes, writes nothing
python analyze.py --game-id <uuid> --us-cluster A    # skip the "which cluster is us" prompt
python results_to_sql.py cache/<uuid>_results.json <uuid> [--swap-teams] > seed.sql
```

`--dry-run` needs only `SUPABASE_ANON_KEY` (reads published games) and writes
`cache/<game>_results.json` plus `cache/team_preview.jpg`. Look at the preview: A = yellow
boxes, B = magenta. If the cluster you called "us" is actually the opponent, either rerun
with the other `--us-cluster` or convert with `--swap-teams`.

Measured on an M5 Pro: detection runs ~60-100 frames/s at 1280 input, so a 75-minute game
at 5 fps takes roughly 6-8 minutes after the download.

Known limits of the stock COCO model (no Roboflow football weights): the ball is found in
roughly a quarter of frames, the referee sometimes lands in a team cluster, and spectators
behind a fence can be counted as players. Possession is still a share of *attributed*
frames, and `ball_frames` records the denominator so the app can show how thin it is.

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
