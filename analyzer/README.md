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

Measured on a public BallerCam game (65 min, 720p) in Sept 2026 with the Roboflow weights:
ball seen in 56% of frames, a goalkeeper visible in 70%, 61% of frames attributed to a team,
usable homography on 11% of one-per-second frames. Shot candidates come from a kick detector
plus a keeper-approach test (kick within ~22 keeper-heights of a visible keeper, ball moving
at the keeper, ending within ~6 keeper-heights): 22 candidates for the game, roughly half of
which looked like real attempts on review. They are proposals; a human confirms.

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

## Running it on a spare Mac (worker mode)
A Mac mini in the garage can do all of this so your laptop never has to. It only ever
processes runs a human queued from the app's **Analysis** tab, so nothing starts on its own.

If the mini shares this Dropbox folder, it already has the code. On the mini, open a
terminal in this `analyzer` folder and run `./setup_mini.sh` twice: the first pass creates
`~/.config/matchfilm/.env` for you to paste the Supabase service key into (outside Dropbox,
so the key never syncs); the second pass installs the weights and the login agent.
The virtualenv, caches and weights are marked Dropbox-ignored so they stay on the mini.

Without Dropbox: `git clone https://github.com/mcgiardina/soccerstats.git` and run the same
script. Logs go to `~/Library/Logs/matchfilm-analyzer.log`. Keep the mini awake (System
Settings → Energy → prevent sleeping when the display is off). Code edits sync via Dropbox;
the worker picks them up on its next run. `launchctl kickstart -k gui/$(id -u)/com.matchfilm.analyzer`
restarts it by hand.

Weekly flow: upload the game, add it in the app, press **Queue analysis run**. The mini
picks it up within a minute, and the machine tags appear in the app when it finishes.
The first run of a new season asks which kit is "us": run `analyze.py --game-id <id>`
once by hand on the mini (or set `params.us_cluster` on the queued run) and it remembers.

## Better models (recommended, no account needed)
Roboflow publishes pre-trained football weights in the MIT-licensed `roboflow/sports` repo:
a player/goalkeeper/referee/ball detector, a ball-only detector, and the 32-landmark pitch
keypoint model. `./get_weights.sh` downloads the same Google Drive files their own setup
script uses into `~/Library/Caches/match-film/weights/`, and the analyzer picks them up
automatically. This is what unlocks referee/keeper exclusion by class, real shot detection
(ball toward the goal region), and machine shot locations + shape snapshots via homography.

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
