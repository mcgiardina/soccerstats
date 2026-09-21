"""The fixed wide-view pipeline as one worker run: goals, halves and match flow for a game whose
camera also kept its full-field recording (videos.kind = 'wide_fixed' with a raw_url).

  1. fetch the raw file once (9 GB for 90 min of 4K; three passes over HTTP would move 27 GB and
     one dropped connection would lose the run) and delete it afterwards
  2. clock offset between the raw file and the film people watch, from the audio (clocks.py)
  3. ONE sequential pass: the ball-sized motion tracker at both goals on every frame (fixedcam.py)
     and the players every 2 s (people rows)
  4. restarts: the 0.5 fps rule, plus nominate -> dense re-sample -> own-half rule (kickoffs.py);
     only line-ups that then BREAK into play count, so a team warming up in its own half does not
  5. goals from the restarts, halves from the 3+ minute empty pitch, match flow (flow.py)
  6. write: goal proposals (in the watched film's clock), game_flow, periods if unset, and a
     comparison with any goals already on the game so accuracy can be read off the run

Needs a calibration for the recording (calib/fixed/<name>.json): the two goal boxes, the halfway
line and the camera model. One exists for the first real game; a new venue or tripod position needs
a new one until that step is automated. The two kits must be light v dark (kickoffs.classify).
"""
import json
import os
import subprocess
import time

import cv2
import numpy as np

from . import clocks, db, fetch, fieldmap, fixedcam, flow, kickoffs

CALIB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "calib", "fixed")
GOAL_LABEL = "machine goal (from the kick-off that followed; wide camera)"


def calibration(wide, game_id):
    for name in (wide.get("provider_ref"), game_id):
        p = os.path.join(CALIB_DIR, f"{name}.json") if name else None
        if p and os.path.exists(p):
            return json.load(open(p))
    return None


def _lum(hex_color):
    h = (hex_color or "").lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        return None
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def us_is_light(game):
    a, b = _lum(game.get("kit_color")), _lum(game.get("opp_kit_color"))
    if a is None or b is None or abs(a - b) < 0.35:
        raise RuntimeError("the wide-view pipeline tells the teams apart as light v dark shirts: set both kit colours on the game, "
                           "and they must differ clearly in brightness (e.g. white v black)")
    return a > b


def fetch_raw(url, key):
    os.makedirs(fetch.CACHE, exist_ok=True)
    out = os.path.join(fetch.CACHE, "raw_" + "".join(c if c.isalnum() or c in "-_." else "_" for c in key)[:100] + os.path.splitext(url.split("?")[0])[1])
    for attempt in range(6):   # resumes where it stopped
        r = subprocess.run(["curl", "-L", "-f", "-s", "-S", "-C", "-", "--retry", "5", "--retry-delay", "10", "-o", out, url])
        if r.returncode == 0 or r.returncode == 33:   # 33: server says the file is already complete
            return out
        print(f"raw download interrupted (curl {r.returncode}); resuming ({attempt + 1}/6)")
        time.sleep(20)
    raise RuntimeError("could not download the camera's full-field file; the share link may have been turned off")


def _tiles(width, n=3, overlap=180):
    w = int(np.ceil((width + (n - 1) * overlap) / n))
    return [(max(0, i * (w - overlap)), min(width, i * (w - overlap) + w)) for i in range(n)]


def people_in(img, model, device, band, zoom_band=None):
    """[[x, y_feet, height, V, S, cls], ...] in source pixels. The pitch band is cut into three
    overlapping tiles so far-side players keep enough pixels; zoom_band adds a 2x pass over the far
    side (used for the dense windows, where every player matters)."""
    from . import detect
    y0, y1 = band
    tiles = _tiles(img.shape[1])
    crops = [img[y0:y1, a:b] for a, b in tiles]; offs = [(a, y0, 1.0) for a, _ in tiles]
    if zoom_band:
        for a, _ in _tiles(img.shape[1], n=3, overlap=0):
            a = min(a + 300, img.shape[1] - 1200)
            crops.append(cv2.resize(img[zoom_band[0]:zoom_band[1], a:a + 1200], None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)); offs.append((a, zoom_band[0], 0.5))
    out = []
    for (ox, oy, sc), crop, r in zip(offs, crops, model.predict(crops, device=device, verbose=False, conf=0.3, imgsz=1280)):
        if r.boxes is None:
            continue
        for bx, c in zip(r.boxes.xyxy.tolist(), r.boxes.cls.tolist()):
            if int(c) not in (detect.RF_PLAYER, detect.RF_GK):
                continue
            x1, y1b, x2, y2 = bx; h = y2 - y1b
            if h * sc < 16:
                continue
            torso = crop[int(y1b + 0.2 * h):int(y1b + 0.5 * h), int(x1 + 0.25 * (x2 - x1)):int(x2 - 0.25 * (x2 - x1))]
            if torso.size == 0:
                continue
            hsv = cv2.cvtColor(torso, cv2.COLOR_BGR2HSV).reshape(-1, 3)
            out.append([round(float(ox + (x1 + x2) / 2 * sc), 1), round(float(oy + y2 * sc), 1), round(float(h * sc), 1),
                        int(np.median(hsv[:, 2])), int(np.median(hsv[:, 1])), int(c)])
    out.sort(); dd = []
    for p in out:   # the tile overlap sees some players twice
        if not dd or abs(p[0] - dd[-1][0]) > 14 or abs(p[1] - dd[-1][1]) > 14:
            dd.append(p)
    return dd


# Shares of a run's wall time, from the first full run on the mini (3 min download, 60 min first
# pass, ~50 min second pass): used only for the progress bar in the app.
P_FETCH, P_PASS1, P_PASS2 = 0.04, 0.56, 0.98


def analyse(raw_path, calib, light_is_us, progress=lambda msg, frac=None: None, limit_seconds=None):
    import contextlib, io
    from . import detect
    with contextlib.redirect_stdout(io.StringIO()):
        model, _ball, device, football = detect._model("local")
    if not football:
        raise RuntimeError("the football player weights are missing (run get_weights.sh)")
    cap = cv2.VideoCapture(raw_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    size = (int(cap.get(3)), int(cap.get(4)))
    if list(size) != list(calib["size"]):
        raise RuntimeError(f"the recording is {size[0]}x{size[1]} but the calibration was made for {calib['size'][0]}x{calib['size'][1]}")
    total_s = (cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0) / fps
    band, x_mid, y_range = calib["band"], calib["x_mid"], calib["y_range"]
    watchers = [fixedcam.GoalWatcher(n, g, size) for n, g in calib["goals"].items()]
    rows, i, step, began = [], 0, int(round(fps * 2)), time.time()
    while cap.grab():
        i += 1
        t = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
        if limit_seconds and t > limit_seconds:
            break
        ok, img = cap.retrieve()
        if not ok:
            break
        for w in watchers:
            w.feed(t, img)
        if i % step == 0:
            rows.append({"t": round(float(t), 2), "p": people_in(img, model, device, band)})
        if i % int(fps * 300) == 0:
            progress(f"pass 1 of 2: {int(t // 60)} of {int(total_s // 60)} min ({(time.time() - began) / 60:.0f} min so far)",
                     P_FETCH + (P_PASS1 - P_FETCH) * min(1.0, t / max(total_s, 1.0)))
    for w in watchers:
        w.finish()
    activity = {w.name: sorted(float(p[0]) for tr in w.done for p in tr) for w in watchers}
    attacks = []
    for w in watchers:
        attacks += w.candidates()

    # restarts: coarse rule, then the dense second stage on the nominated windows
    v1 = kickoffs.restarts(rows, x_mid, y_range)
    windows = []
    nominated = kickoffs.nominate(rows, x_mid, y_range)
    for k, c in enumerate(nominated):
        cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, c - 22) * 1000); seq, j = [], 0
        while True:
            ok, img = cap.read(); t = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
            if not ok or t > c + 14:
                break
            j += 1
            if j % max(1, int(round(fps / 2))) == 0:
                seq.append({"t": round(float(t), 2), "p": people_in(img, model, device, band, zoom_band=calib.get("far_band"))})
        windows.append(seq)
        progress(f"pass 2 of 2: window {k + 1} of {len(nominated)}", P_PASS1 + (P_PASS2 - P_PASS1) * (k + 1) / len(nominated))
    cap.release()
    to_field = lambda px: fieldmap.to_field(px, calib["cam"], size)
    v2 = kickoffs.own_half_restarts(windows, to_field, calib["field"])
    merged = kickoffs.merge(v1, v2)
    # a kick-off line-up BREAKS into play; teams warming up in their own halves just stay apart
    real = [r for r in merged if kickoffs.kick_time(rows, r, x_mid, y_range, with_break=True)[1]]
    half_list = flow.halves(rows, real, x_mid, y_range)
    in_play = [r for r in real if any(h[0] - 90 <= r["t"] <= h[1] for h in half_list)]
    goals = [g for g in kickoffs.goals(in_play, activity, us_is_light=light_is_us) if g["kind"] == "goal"]
    return {"rows": rows, "attacks": attacks, "restarts": real, "dropped_lineups": len(merged) - len(real), "halves": half_list,
            "goals": goals, "size": size, "nominated": len(nominated), "minutes": round((time.time() - began) / 60)}


def main(game, main_video, wide, run, args):
    calib = calibration(wide, game["id"])
    def say(msg, frac=None):
        print(msg, flush=True)
        db.update_run_params(run["id"], {"stage": msg, **({"progress": round(float(frac), 3)} if frac is not None else {})})
    try:
        try:
            import av  # noqa: F401
        except ImportError:   # a worker set up before this pipeline existed: add the one new dependency
            import sys
            say("installing the audio reader (first run only)")
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "av>=12"])
        light_is_us = us_is_light(game)
        ref = main_video.get("stream_url") or fetch.download_video(main_video)
        say("fetching the camera's full-field file", 0.0)
        raw = fetch_raw(wide["raw_url"], wide.get("provider_ref") or game["id"])
        say("matching the two clocks by their audio", P_FETCH - 0.01)
        offset, spread = clocks.offset(ref, raw)
        if spread > 1.0:
            raise RuntimeError(f"the audio of the two recordings does not line up (probes disagree by {spread:.1f} s)")
        res = analyse(raw, calib, light_is_us, progress=say, limit_seconds=args.limit_seconds)
        to_film = lambda t: round(float(t) - offset, 1)
        att = [{"goal": a["goal"], "t": a["t"], "score": a["score"]} for a in res["attacks"]]
        flow_doc = flow.build(res["rows"], calib["cam"], res["size"], calib["field"], res["halves"], us_is_light=light_is_us, attacks=att, clock_offset=offset) if res["halves"] else None
        goals = [{"t": to_film(g["t"]), "team": g["team"], "goal_end": g["goal_end"], "confidence": g["confidence"]} for g in res["goals"]]
        summary = {"pipeline": "fixed", "clock_offset_s": round(offset, 2), "minutes": res["minutes"], "nominated_windows": res["nominated"],
                   "restarts": [to_film(r["t"]) for r in res["restarts"]], "lineups_that_never_broke": res["dropped_lineups"],
                   "halves": [[to_film(h[0]), to_film(h[1])] for h in res["halves"]], "goals": goals}
        if args.dry_run:
            print(json.dumps(summary, indent=1)); return 0
        summary["compare"] = write(game["id"], run["id"], main_video, goals, flow_doc, summary["halves"])
        db.update_run_params(run["id"], {"fixed": summary, "stage": "done", "progress": 1.0})
        db.finish_run(run["id"], "done")
        print(json.dumps(summary, indent=1))
        return 0
    finally:
        # 9 GB: never leave it on the mini
        try:
            p = os.path.join(fetch.CACHE, "raw_" + "".join(c if c.isalnum() or c in "-_." else "_" for c in (wide.get("provider_ref") or game["id"]))[:100] + os.path.splitext(wide["raw_url"].split("?")[0])[1])
            if os.path.exists(p) and not os.environ.get("KEEP_RAW"):
                os.remove(p)
        except OSError:
            pass


def write(game_id, run_id, main_video, goals, flow_doc, halves):
    c = db.client()
    # only this pipeline's own unreviewed proposals are replaced; scoreboard goals and human tags stay
    c.table("tags").delete().eq("game_id", game_id).eq("source", "machine").is_("confirmed", "null").eq("label", GOAL_LABEL).execute()
    # goals already on the game: goal tags, and set pieces (free kick, corner, penalty...) marked as having gone in
    existing = [t for t in c.table("tags").select("t_seconds,type,team,source,confirmed,label,outcome").eq("game_id", game_id).execute().data
                if (t["type"] == "goal" or t.get("outcome") == "goal") and t.get("confirmed") is not False and t.get("label") != GOAL_LABEL]
    # how the machine did against the goals already on the game (scoreboard or human)
    compare = []
    for t in existing:
        near = min(goals, key=lambda g: abs(g["t"] - float(t["t_seconds"])), default=None)
        hit = near is not None and abs(near["t"] - float(t["t_seconds"])) <= 25
        compare.append({"known_t": float(t["t_seconds"]), "known_team": t["team"], "found": bool(hit),
                        "dt_s": round(near["t"] - float(t["t_seconds"]), 1) if hit else None, "team_right": bool(hit and near["team"] == t["team"])})
    extra = [g["t"] for g in goals if not any(abs(g["t"] - float(t["t_seconds"])) <= 25 for t in existing)]
    rows = [{"game_id": game_id, "video_id": main_video["id"], "source": "machine", "type": "goal", "team": g["team"], "t_seconds": g["t"],
             "confidence": g["confidence"], "label": GOAL_LABEL}
            for g in goals if not any(abs(g["t"] - float(t["t_seconds"])) <= 25 and (t["source"] == "human" or t.get("confirmed")) for t in existing)]
    if rows:
        c.table("tags").insert(rows).execute()
    if flow_doc:
        c.table("game_flow").delete().eq("game_id", game_id).execute()
        c.table("game_flow").insert({"game_id": game_id, "run_id": run_id, "data": flow_doc}).execute()
    if halves and main_video.get("halftime_offset_seconds") is None:
        patch = {"kickoff_offset_seconds": round(halves[0][0]), "halftime_offset_seconds": round(halves[0][1])}
        if len(halves) > 1:
            patch.update({"second_half_offset_seconds": round(halves[1][0]), "fulltime_offset_seconds": round(halves[1][1])})
        c.table("videos").update(patch).eq("id", main_video["id"]).execute()
    return {"known_goals": compare, "machine_goals_with_no_known_goal": extra}
