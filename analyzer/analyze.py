#!/usr/bin/env python3
"""Match Film analyzer. Usage: python analyze.py --game-id <uuid> [--backend local|cloud]"""
import argparse
import collections
import json
import os
import sys
import time
import traceback

from dotenv import load_dotenv

load_dotenv()                                                            # analyzer/.env (may be Dropbox-synced)
load_dotenv(os.path.expanduser("~/.config/matchfilm/.env"), override=True)  # per-machine secrets, never synced

from analyzer import db, fetch, video, detect, teams, possession, shots, homography, shape, dewarp, passes, goalshots  # noqa: E402

MODEL_VERSION = "mf-analyzer-0.1"


def diagnostics(path, frames):
    """Versions, device and what the sampled video looked like, stored in the run params."""
    import platform
    d = {"python": platform.python_version(), "machine": platform.node()}
    try:
        import torch, ultralytics, cv2
        d.update({"torch": torch.__version__, "ultralytics": ultralytics.__version__, "opencv": cv2.__version__,
                  "mps": bool(getattr(torch.backends, "mps", None) and torch.backends.mps.is_available())})
        cap = cv2.VideoCapture(path)
        d.update({"video_fps": round(cap.get(cv2.CAP_PROP_FPS), 3), "video_frames": int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
                  "video_w": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), "video_h": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                  "video_bytes": os.path.getsize(path)})
        cap.release()
    except Exception as e:  # noqa: BLE001
        d["error"] = str(e)[:120]
    d.update({"sampled": len(frames), "first_t": round(frames[0].t, 3) if frames else None, "last_t": round(frames[-1].t, 3) if frames else None})
    return d


def run_queue(poll_seconds: int, backend: str) -> int:
    """Worker mode for a spare Mac: process runs the admin has queued from the app, oldest first.
    Nothing starts unless a human pressed "Queue analysis run"; this just executes that queue.
    Needs SUPABASE_SERVICE_KEY. Ctrl-C to stop."""
    import subprocess
    print(f"watching for queued runs every {poll_seconds}s (backend={backend})")
    last_update = 0.0
    here = os.path.dirname(os.path.abspath(__file__))
    watched = [os.path.abspath(__file__)] + [os.path.join(here, "analyzer", f) for f in os.listdir(os.path.join(here, "analyzer")) if f.endswith(".py")]
    stamp = lambda: max(os.path.getmtime(f) for f in watched if os.path.exists(f))
    started_stamp = stamp()
    while True:
        # The code arrives through Dropbox. When it changes, exit and let launchd (KeepAlive)
        # restart the worker on the new code instead of running yesterday's loop forever.
        if stamp() != started_stamp:
            print("analyzer code changed on disk; restarting the worker"); return 0
        # YouTube changes often; a stale yt-dlp silently falls back to a 360p stream (seen on the
        # mini: 640x360 while the laptop got 1280x720). Refresh it once a day.
        if time.time() - last_update > 86400:
            subprocess.call([sys.executable, "-m", "pip", "install", "-q", "--upgrade", "yt-dlp"])
            last_update = time.time()
        try:
            q = db.client().table("stat_runs").select("id,game_id,params").eq("status", "queued").order("created_at").limit(1).execute().data
        except Exception as e:  # noqa: BLE001
            print("queue check failed:", str(e)[:120]); q = []
        if q:
            gid = q[0]["game_id"]
            us = (q[0].get("params") or {}).get("us_cluster")
            args = [sys.executable, "-u", os.path.abspath(__file__), "--game-id", gid, "--backend", backend]
            if us in ("A", "B"):
                args += ["--us-cluster", us]
            print(f"--- run for game {gid} at {time.strftime('%H:%M:%S')}")
            rc = subprocess.call(args, cwd=os.path.dirname(os.path.abspath(__file__)))
            print(f"--- finished with code {rc}")
            if rc != 0:
                # Don't spin on a broken run: mark it failed so the queue moves on. The app shows the status.
                # The run usually recorded its own traceback already; only fill in when it did not.
                try:
                    db.fail_queued(q[0]["id"], f"worker exit code {rc}; see the worker log", keep_existing=True)
                except Exception as e:  # noqa: BLE001
                    print("could not mark run failed:", str(e)[:120])
                time.sleep(15)
            continue
        time.sleep(poll_seconds)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game-id")
    ap.add_argument("--watch", action="store_true", help="Worker mode: keep processing runs queued from the app")
    ap.add_argument("--poll", type=int, default=60, help="Seconds between queue checks in --watch mode")
    ap.add_argument("--backend", choices=["local", "cloud"], default="local")
    ap.add_argument("--fps", type=float, default=5.0)
    ap.add_argument("--confirm-team", action="store_true", help="Re-ask which colour cluster is us")
    ap.add_argument("--limit-seconds", type=int, default=None, help="Analyze only the first N seconds (debug)")
    ap.add_argument("--dry-run", action="store_true", help="Compute everything, write nothing to Supabase; dump results JSON")
    ap.add_argument("--us-cluster", choices=["A", "B"], default=None, help="Which kit-colour cluster is us (skips the prompt)")
    ap.add_argument("--from-cache", action="store_true", help="Reuse cached detections + team labels; skip download/detect")
    ap.add_argument("--relabel", action="store_true", help="With --from-cache: redo team assignment (re-decodes frames, no re-detection)")
    ap.add_argument("--max-height", type=int, default=720, help="Download resolution cap (720 default; 1080 helps the tiny ball)")
    ap.add_argument("--refit-homography", action="store_true", help="With --from-cache: re-run the pitch model (re-decodes frames at 1 fps)")
    ap.add_argument("--camera", default="ballercam", help="Calibration name under calib/ used to de-warp a wide_fixed source")
    args = ap.parse_args()
    if args.watch:
        return run_queue(args.poll, args.backend)
    if not args.game_id:
        ap.error("--game-id is required unless --watch")

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
            # what this machine saw: lets two runs of the same game (laptop vs mini) be compared
            if not args.dry_run:
                db.update_run_params(run["id"], {"diag": diagnostics(path, frames)})
            dets = detect.run(frames, backend=args.backend)
            if args.limit_seconds is None:
                # detections are the expensive part: cache them before anything that can fail
                detect.save_cache(cache_path, dets, args.fps)
            us_cluster = {"A": 0, "B": 1}.get(args.us_cluster) if args.us_cluster else None
            assign = teams.assign(dets, game_id=args.game_id, force_confirm=args.confirm_team, us_cluster=us_cluster)
            if assign is None:
                raise RuntimeError("Kit colours too similar to separate teams; possession not reported.")
            for d in dets:
                d.labels = [assign(d.img, p) for p in d.players]
            if args.limit_seconds is None:
                detect.save_cache(cache_path, dets, args.fps)

        if assign is not None and getattr(teams.assign, "us_cluster", None) is not None:
            choice = {"us_cluster": "AB"[teams.assign.us_cluster], "team_pick": getattr(teams.assign, "method", None),
                      "us_kit_lab": getattr(teams.assign, "us_kit_lab", None),
                      "kits": getattr(teams.assign, "kits", None),
                      "ball_frames": sum(1 for d in dets if d.ball), "attributed_frames": sum(1 for d in dets if any(d.labels or []))}
            params.update(choice)
            if not args.dry_run:
                db.update_run_params(run["id"], choice)
        offsets = video.period_offsets(main_video)
        poss = possession.compute(dets, assign, offsets, fps=args.fps)
        cands = shots.candidates(dets, fps=args.fps, sequence=poss["sequence"])
        # second trigger: the ball arriving fast at a keeper (catches strikes the sparse ball track hides)
        cands = sorted(cands + shots.approach_candidates(dets, fps=args.fps, sequence=poss["sequence"], existing=cands), key=lambda c: c["t"])

        H = {}
        if homography.available() and frames:
            # Prefer the wide-angle source for anything positional; de-warp it if a calibration exists.
            by_t = {round(d.t, 1): d for d in dets}
            if wide:
                src_path = fetch.download(wide["youtube_id"], max_height=args.max_height)
                fn = dewarp.load(args.camera)
                print(f"wide source {'de-warped with ' + args.camera if fn else 'used as-is (no calib/' + args.camera + '.json)'}")
                src_frames = video.sample(src_path, fps=1.0, limit_seconds=args.limit_seconds, dewarp=fn)
                H = homography.fit(src_frames)
            else:
                # pitch model at ~1 fps on the panned video; gate with player feet from the same frames
                step = max(1, int(round(args.fps)))
                H = homography.fit(frames[::step], dets_by_t=by_t)
            homography.save_cache(os.path.join(fetch.CACHE, f"{args.game_id}_homog.json"), H)
        elif args.from_cache and args.refit_homography and homography.available():
            by_t = {round(d.t, 1): d for d in dets}
            path = fetch.download(main_video["youtube_id"], max_height=args.max_height)
            step = max(1, int(round(args.fps)))
            fr = video.sample(path, fps=args.fps, limit_seconds=args.limit_seconds)
            H = homography.fit(fr[::step], dets_by_t=by_t)
            homography.save_cache(os.path.join(fetch.CACHE, f"{args.game_id}_homog.json"), H)
            del fr
        elif args.from_cache:
            H = homography.load_cache(os.path.join(fetch.CACHE, f"{args.game_id}_homog.json"))
        pass_events, pass_summary, ball_cov = passes.detect(dets, poss["sequence"], fps=args.fps, H=H or None)
        for ts_row in poss["team_stats"]:
            if ts_row["period"] == "full":
                ts_row.update({"passes": pass_summary[ts_row["team"]]["passes"], "passes_completed": pass_summary[ts_row["team"]]["passes_completed"], "ball_coverage": ball_cov})
        shot_cands, kick_cands = shots.classify(cands, dets, H) if H else ([], cands)
        # Goal-mouth classification against the goal frame found in the image (best precision).
        try:
            vpath = path or fetch.download(main_video["youtube_id"], max_height=args.max_height)
            import cv2
            cap = cv2.VideoCapture(vpath); src_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            fcache = {}
            def frame_at(t):
                k = round(t, 1)
                if k not in fcache:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, int(round(t * src_fps))); ok, img = cap.read(); fcache[k] = img if ok else None
                    if len(fcache) > 80: fcache.pop(next(iter(fcache)))
                return fcache[k]
            gres = goalshots.classify(kick_cands, dets, frame_at, fps=args.fps)
            cap.release()
        except Exception as e:  # noqa: BLE001
            print("goal-mouth classification skipped:", str(e)[:120]); gres = [{**c, "outcome": "kick"} for c in kick_cands]
        geo_shots = [g for g in gres if g["outcome"] in ("on_target", "off_target", "save", "goal?")]
        geo_unresolved = [g for g in gres if g["outcome"] == "shot"]
        # goal in view and the ball tracked through the window but never near the goal: a
        # trusted "not a shot", so the weaker keeper-approach test must not override it
        trusted_kicks = [g for g in gres if g["outcome"] == "kick" and g.get("ball_track")]
        # (approach-triggered candidates never take the keeper fallback: it would confirm its own trigger)
        rest = [g for g in gres if g["outcome"] == "kick" and not g.get("ball_track") and g.get("trigger") != "approach"]
        crosses = [g for g in gres if g["outcome"] == "cross"]
        for g in geo_shots:
            g["confidence"] = round(min(0.95, 0.55 + 0.1 * min(3, g.get("goal_hits", 1))), 3)
            g["source"] = "goal_mouth"
        for g in geo_unresolved:
            g["confidence"] = 0.6
            g["source"] = "goal_mouth"
        print(f"goal-mouth: {len(geo_shots)} shots ({collections.Counter(g['outcome'] for g in geo_shots)}), {len(geo_unresolved)} unresolved shots, "
              f"{len(crosses)} crosses, {len(trusted_kicks)} kicks ruled out, {len(rest)} without a goal in view")
        # keeper-approach fallback only for kicks where the goal was not in view
        more, kick_cands = shots.classify_by_keeper([{k: v for k, v in g.items() if k not in ('outcome',)} for g in rest], dets, fps=args.fps)
        for m in more:
            m["source"] = "keeper"
        shot_cands = sorted(shot_cands + geo_shots + geo_unresolved + more, key=lambda c: c["t"])
        dropped = [g for g in gres if g["outcome"] == "kick" and not g.get("ball_track") and g.get("trigger") == "approach"]
        kick_cands = kick_cands + [{**c, "outcome": "cross"} for c in crosses] + [{k: v for k, v in g.items() if k != "ball_track"} for g in trusted_kicks] + [{**g, "outcome": "kick"} for g in dropped]
        snaps = shape.snapshots(dets, assign, H, offsets) if H else []
        located = {round(s["t"], 1): s["location"] for s in shot_cands if s.get("location")}

        results = {
            "game_id": args.game_id, "video_id": main_video["id"], "model_version": MODEL_VERSION, "params": params,
            "frames": len(dets), "team_stats": poss["team_stats"], "buckets": poss["buckets"],
            "shot_candidates": shot_cands, "kick_candidates": kick_cands, "shot_locations": located,
            "pass_events": pass_events, "ball_coverage": ball_cov,
            "homography_frames": len(H), "shape_snapshots": len(snaps),
        }
        out_path = os.path.join(fetch.CACHE, f"{args.game_id}_results.json")
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(results, f, indent=1, default=float)
        print(f"results written to {out_path}")
        if args.dry_run:
            print(json.dumps({k: results[k] for k in ("frames", "team_stats")}, indent=1, default=float))
            print(f"{len(shot_cands)} shot + {len(kick_cands)} kick candidates; {len(H)} homography frames; {len(snaps)} shape snapshots; dry run, nothing written")
            return 0
        db.write_results(
            game_id=args.game_id, run_id=run["id"], video_id=main_video["id"],
            team_stats=poss["team_stats"], buckets=poss["buckets"],
            shot_tags=shot_cands, kick_tags=kick_cands, shot_locations=located, snapshots=snaps, pass_events=pass_events,
            pitch=(game.get("pitch_length_m"), game.get("pitch_width_m")),
        )
        db.finish_run(run["id"], "done")
        print("done")
        return 0
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        if not args.dry_run:
            # the worker's log lives on the other machine: keep the tail of the traceback with the run
            tb = traceback.format_exc().strip().splitlines()
            detail = (f"{type(e).__name__}: {e} | " + " | ".join(tb[-4:-1]))[:1500]
            db.finish_run(run["id"], "failed", error=detail)
            try:
                db.update_run_params(run["id"], {"error_detail": detail})   # survives the worker's own status update
            except Exception:  # noqa: BLE001
                pass
        return 1
    finally:
        time.sleep(0.1)


if __name__ == "__main__":
    sys.exit(main())
