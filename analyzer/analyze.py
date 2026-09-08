#!/usr/bin/env python3
"""Match Film analyzer. Usage: python analyze.py --game-id <uuid> [--backend local|cloud]"""
import argparse
import sys
import time
import traceback

from dotenv import load_dotenv

load_dotenv()

from analyzer import db, fetch, video, detect, teams, possession, shots, homography, shape  # noqa: E402

MODEL_VERSION = "mf-analyzer-0.1"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game-id", required=True)
    ap.add_argument("--backend", choices=["local", "cloud"], default="local")
    ap.add_argument("--fps", type=float, default=5.0)
    ap.add_argument("--confirm-team", action="store_true", help="Re-ask which colour cluster is us")
    ap.add_argument("--limit-seconds", type=int, default=None, help="Analyze only the first N seconds (debug)")
    args = ap.parse_args()

    game = db.get_game(args.game_id)
    vids = db.get_videos(args.game_id)
    if not vids:
        print("No video attached to this game.", file=sys.stderr)
        return 2
    # Prefer a fixed wide camera for anything positional; the tracking archive for everything else.
    wide = next((v for v in vids if v.get("kind") == "wide_fixed"), None)
    main_video = next((v for v in vids if v.get("kind") != "wide_fixed"), vids[0])
    params = {"backend": args.backend, "fps": args.fps, "wide_source": bool(wide), "limit_seconds": args.limit_seconds}
    run = db.claim_run(args.game_id, main_video["id"], MODEL_VERSION, params)
    print(f"run {run['id']} started for game {args.game_id}")

    try:
        path = fetch.download(main_video["youtube_id"])
        frames = video.sample(path, fps=args.fps, limit_seconds=args.limit_seconds)
        dets = detect.run(frames, backend=args.backend)
        assign = teams.assign(dets, game_id=args.game_id, force_confirm=args.confirm_team)
        if assign is None:
            raise RuntimeError("Kit colours too similar to separate teams; possession not reported.")

        offsets = video.period_offsets(main_video)
        poss = possession.compute(dets, assign, offsets, fps=args.fps)
        cands = shots.candidates(dets, fps=args.fps)

        H = None
        if homography.available():
            src_path = fetch.download(wide["youtube_id"]) if wide else path
            src_frames = video.sample(src_path, fps=1.0, limit_seconds=args.limit_seconds) if wide else frames
            H = homography.fit(src_frames)
        snaps = shape.snapshots(dets, assign, H, offsets) if H else []
        located = homography.locate_shots(cands, dets, H) if H else {}

        db.write_results(
            game_id=args.game_id, run_id=run["id"], video_id=main_video["id"],
            team_stats=poss["team_stats"], buckets=poss["buckets"],
            shot_tags=cands, shot_locations=located, snapshots=snaps,
            pitch=(game.get("pitch_length_m"), game.get("pitch_width_m")),
        )
        db.finish_run(run["id"], "done")
        print("done")
        return 0
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        db.finish_run(run["id"], "failed", error=str(e)[:500])
        return 1
    finally:
        time.sleep(0.1)


if __name__ == "__main__":
    sys.exit(main())
