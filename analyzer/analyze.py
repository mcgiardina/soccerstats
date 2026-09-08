#!/usr/bin/env python3
"""Match Film analyzer. Usage: python analyze.py --game-id <uuid> [--backend local|cloud]"""
import argparse
import json
import os
import sys
import time
import traceback

from dotenv import load_dotenv

load_dotenv()

from analyzer import db, fetch, video, detect, teams, possession, shots, homography, shape, dewarp  # noqa: E402

MODEL_VERSION = "mf-analyzer-0.1"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game-id", required=True)
    ap.add_argument("--backend", choices=["local", "cloud"], default="local")
    ap.add_argument("--fps", type=float, default=5.0)
    ap.add_argument("--confirm-team", action="store_true", help="Re-ask which colour cluster is us")
    ap.add_argument("--limit-seconds", type=int, default=None, help="Analyze only the first N seconds (debug)")
    ap.add_argument("--dry-run", action="store_true", help="Compute everything, write nothing to Supabase; dump results JSON")
    ap.add_argument("--us-cluster", choices=["A", "B"], default=None, help="Which kit-colour cluster is us (skips the prompt)")
    ap.add_argument("--from-cache", action="store_true", help="Reuse cached detections + team labels; skip download/detect")
    ap.add_argument("--relabel", action="store_true", help="With --from-cache: redo team assignment (re-decodes frames, no re-detection)")
    ap.add_argument("--max-height", type=int, default=720, help="Download resolution cap (720 default; 1080 helps the tiny ball)")
    ap.add_argument("--camera", default="ballercam", help="Calibration name under calib/ used to de-warp a wide_fixed source")
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
    run = {"id": "dry-run"} if args.dry_run else db.claim_run(args.game_id, main_video["id"], MODEL_VERSION, params)
    print(f"run {run['id']} started for game {args.game_id}")

    try:
        cache_path = os.path.join(fetch.CACHE, f"{args.game_id}_dets.json.gz")
        if args.from_cache and os.path.exists(cache_path):
            args.fps, dets = detect.load_cache(cache_path)
            frames, assign, path = [], None, None
            if args.relabel:
                path = fetch.download(main_video["youtube_id"])
                frames = video.sample(path, fps=args.fps, limit_seconds=args.limit_seconds)
                if len(frames) != len(dets):
                    raise RuntimeError(f"frame count mismatch: {len(frames)} sampled vs {len(dets)} cached")
                for f, d in zip(frames, dets):
                    d.img = f.img
                us_cluster = {"A": 0, "B": 1}.get(args.us_cluster) if args.us_cluster else None
                assign = teams.assign(dets, game_id=args.game_id, force_confirm=args.confirm_team, us_cluster=us_cluster)
                if assign is None:
                    raise RuntimeError("Kit colours too similar to separate teams; possession not reported.")
                for d in dets:
                    d.labels = [assign(d.img, p) for p in d.players]
                detect.save_cache(cache_path, dets, args.fps)
                for d in dets:
                    d.img = None
                frames = []
        else:
            path = fetch.download(main_video["youtube_id"], max_height=args.max_height)
            frames = video.sample(path, fps=args.fps, limit_seconds=args.limit_seconds)
            dets = detect.run(frames, backend=args.backend)
            us_cluster = {"A": 0, "B": 1}.get(args.us_cluster) if args.us_cluster else None
            assign = teams.assign(dets, game_id=args.game_id, force_confirm=args.confirm_team, us_cluster=us_cluster)
            if assign is None:
                raise RuntimeError("Kit colours too similar to separate teams; possession not reported.")
            for d in dets:
                d.labels = [assign(d.img, p) for p in d.players]
            if args.limit_seconds is None:
                detect.save_cache(cache_path, dets, args.fps)

        offsets = video.period_offsets(main_video)
        poss = possession.compute(dets, assign, offsets, fps=args.fps)
        cands = shots.candidates(dets, fps=args.fps, sequence=poss["sequence"])

        H = None
        if homography.available() and frames:
            # Prefer the wide-angle source for anything positional; de-warp it if a calibration exists.
            if wide:
                src_path = fetch.download(wide["youtube_id"], max_height=args.max_height)
                fn = dewarp.load(args.camera)
                print(f"wide source {'de-warped with ' + args.camera if fn else 'used as-is (no calib/' + args.camera + '.json)'}")
                src_frames = video.sample(src_path, fps=1.0, limit_seconds=args.limit_seconds, dewarp=fn)
            else:
                src_frames = frames
            H = homography.fit(src_frames)
        snaps = shape.snapshots(dets, assign, H, offsets) if H else []
        located = homography.locate_shots(cands, dets, H) if H else {}

        results = {
            "game_id": args.game_id, "video_id": main_video["id"], "model_version": MODEL_VERSION, "params": params,
            "frames": len(dets), "team_stats": poss["team_stats"], "buckets": poss["buckets"],
            "shot_candidates": cands, "shot_locations": located, "shape_snapshots": len(snaps),
        }
        out_path = os.path.join(fetch.CACHE, f"{args.game_id}_results.json")
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(results, f, indent=1, default=float)
        print(f"results written to {out_path}")
        if args.dry_run:
            print(json.dumps({k: results[k] for k in ("frames", "team_stats")}, indent=1, default=float))
            print(f"{len(cands)} shot candidates; dry run, nothing written to Supabase")
            return 0
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
        if not args.dry_run:
            db.finish_run(run["id"], "failed", error=str(e)[:500])
        return 1
    finally:
        time.sleep(0.1)


if __name__ == "__main__":
    sys.exit(main())
