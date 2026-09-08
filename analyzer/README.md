# Analyzer

Standalone CLI. Reads a game from Supabase, pulls the unlisted YouTube video at 720p (or
`--max-height 1080` for the BallerCam 1080p upload, which helps the tiny ball),
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
python results_to_sql.py ~/Library/Caches/match-film/<uuid>_results.json <uuid> [--swap-teams] > seed.sql
```

`--dry-run` needs only `SUPABASE_ANON_KEY` (reads published games) and writes
`<cache>/<game>_results.json` plus `<cache>/team_preview.jpg`. Look at the preview: A = yellow
boxes, B = magenta. If the cluster you called "us" is actually the opponent, either rerun
with the other `--us-cluster` or convert with `--swap-teams`.

Measured on an M5 Pro: detection runs ~60-100 frames/s at 1280 input, so a 75-minute game
at 5 fps takes roughly 6-8 minutes after the download.

Known limits of the stock COCO model (no Roboflow football weights), measured on two
sample games in Sept 2026:
- Ball found in ~24% of frames. Team attribution (hue-grouped kit colours) was correct in
  12/12 spot-checked frames on a red-vs-white game and 11/12 on white-vs-navy under harsh
  sun and shade. `python spotcheck.py <game-id> <youtube-id>` renders the montage for any cached game.
  Possession is a share of *attributed* frames and `ball_frames` records the denominator.
- **Shot detection is not possible** without a goal / goalkeeper / pitch model: the motion
  detector finds kicks (long balls, clearances, goal kicks). They land as machine tags
  labelled "kick candidate" for a human to reject or promote. Roboflow's football-players
  weights (adds goalkeeper + referee classes) or the pitch-keypoint model would unlock it.
- Spectators sitting on grass, and referees in kit-like colours, can leak into a team
  cluster; the four-cluster fit drops most of them.

Never runs automatically. The web app's "Queue analysis run" button only inserts a
`stat_runs` row with `status='queued'`; this CLI claims it (or creates one if none exists).

## Stages
1. `fetch.py` yt-dlp, 720p video-only mp4, cached under `~/Library/Caches/match-film/` (override with `ANALYZER_CACHE`). Keep it out of Dropbox.
2. `video.py` frame sampling at 5 fps with hardware decode where OpenCV supports it.
3. `detect.py` Ultralytics YOLO + ByteTrack. Roboflow football weights if `PLAYER_WEIGHTS` set, else COCO.
4. `teams.py` KMeans(2) on torso colours. Aborts possession if clusters are not separable.
5. `possession.py` nearest-player attribution, 1.5 s smoothing, per half + 5-minute buckets, turnovers.
6. `shots.py` ball acceleration toward a goal region → machine shot tags (recall-first).
7. `homography.py` pitch keypoints → homography (only if `PITCH_WEIGHTS` set). Feeds machine shot
   locations and `shape_snapshots`. Prefers a `wide_fixed` video when the game has one.
7b. `dewarp.py` fisheye de-warp for a raw wide-angle source such as the BallerCam 4K fisheye,
   applied to `wide_fixed` videos when `calib/<camera>.json` exists (default camera name
   `ballercam`). Calibrate once by eye: `python calibrate.py preview <video.mp4> ballercam`,
   look at the candidate images, then `python calibrate.py save ballercam <w> <h> <k1> <fov_scale>`.
8. `db.py` writes. Human rows are never overwritten.

Honesty: the BallerCam upload is an AI-panned crop that keeps the ball centred, so the
ball's pixel position says nothing about field position. Everything positional goes through the homography or is skipped.
No per-player data is ever persisted, including tracker IDs.
