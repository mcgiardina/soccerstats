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

from . import ballplay, clocks, db, fetch, fieldmap, fixedcam, flow, kickoffs

CALIB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "calib", "fixed")
OWNER_SHADE = lambda p: kickoffs.classify(p, dark_v=138)   # the valley between the two kits' brightness
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


def people_in(img, model, device, band, zoom_band=None, conf=0.3):
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
    for (ox, oy, sc), crop, r in zip(offs, crops, model.predict(crops, device=device, verbose=False, conf=conf, imgsz=1280)):
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
P_FETCH, P_PASS1, P_WINDOWS, P_DONE = 0.04, 0.55, 0.85, 0.98


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
    # the ball in open play, as flights (ballplay.py): possession, turnovers, passes
    ball = ballplay.FieldTracker(calib["cam"], size, calib.get("play_band") or band, field=calib["field"])
    flights = []
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
        ball.feed(t, img)
        if i % 60 == 0:
            flights += ball.pop_flights()
        if i % step == 0:
            rows.append({"t": round(float(t), 2), "p": people_in(img, model, device, band)})
        if i % int(fps * 300) == 0:
            progress(f"pass 1 of 3: {int(t // 60)} of {int(total_s // 60)} min ({(time.time() - began) / 60:.0f} min so far)",
                     P_FETCH + (P_PASS1 - P_FETCH) * min(1.0, t / max(total_s, 1.0)))
    for w in watchers:
        w.finish()
    activity = {w.name: sorted(float(p[0]) for tr in w.done for p in tr) for w in watchers}
    attacks = []
    for w in watchers:
        attacks += w.candidates()
    ball.finish(); flights += ball.pop_flights(); flights.sort(key=lambda f: f["t0"])

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
        progress(f"pass 2 of 3: window {k + 1} of {len(nominated)}", P_PASS1 + (P_WINDOWS - P_PASS1) * (k + 1) / len(nominated))
    to_field = lambda px: fieldmap.to_field(px, calib["cam"], size)
    v2 = kickoffs.own_half_restarts(windows, to_field, calib["field"])
    merged = kickoffs.merge(v1, v2)
    # a kick-off line-up BREAKS into play; teams warming up in their own halves just stay apart
    real = [r for r in merged if kickoffs.kick_time(rows, r, x_mid, y_range, with_break=True)[1]]
    half_list = flow.halves(rows, real, x_mid, y_range)
    in_play = [r for r in real if any(h[0] - 90 <= r["t"] <= h[1] for h in half_list)]
    goals = [g for g in kickoffs.goals(in_play, activity, us_is_light=light_is_us) if g["kind"] == "goal"]

    # who struck each flight and who it reached: look at the players at both ends
    flights = [f for f in flights if any(h[0] <= f["t0"] <= h[1] for h in half_list)]   # warm-ups and the break are not the game
    for k, f in enumerate(flights):
        for end in ("a", "b"):
            t_look, probes = ballplay.end_probes(f, end)
            cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, t_look) * 1000); ok, img = cap.read()
            # Looser than the kick-off rules on purpose: dark shirts on dark turf are found ~30% less often
            # than white ones at the usual settings, which would hand the white team possession it never had.
            f[end] = ballplay.owner_at(people_in(img, model, device, band, zoom_band=calib.get("far_band"), conf=0.15), probes, OWNER_SHADE)[0] if ok else None
        if k % 25 == 0:
            progress(f"pass 3 of 3: ball flight {k + 1} of {len(flights)}", P_WINDOWS + (P_DONE - P_WINDOWS) * (k + 1) / max(1, len(flights)))

    cap.release()
    return {"rows": rows, "attacks": attacks, "restarts": real, "dropped_lineups": len(merged) - len(real), "halves": half_list,
            "goals": goals, "size": size, "nominated": len(nominated), "minutes": round((time.time() - began) / 60), "flights": flights}


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
        play = play_stats(res["flights"], res["halves"], calib["field"], light_is_us, to_film)
        summary["ball"] = play["summary"]; summary["spot_check"] = play["spot_check"]
        if args.dry_run:
            print(json.dumps(summary, indent=1)); return 0
        summary["compare"] = write(game["id"], run["id"], main_video, goals, flow_doc, summary["halves"], play)
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


def play_stats(flights, half_list, field, light_is_us, to_film):
    """team_stats rows, pass_events rows and a spot-check sample from the ball flights.
    Coordinates of a pass are attack-normalised for the passing team, like shots: x toward the goal
    being attacked, y down the screen of a map drawn with that team attacking to the right."""
    side = lambda shade: ("us" if (shade == "light") == light_is_us else "them") if shade else None
    x0, x1, y0, y1 = field
    per_half = ballplay.read_play(flights, [(h[0], h[1]) for h in half_list])
    rows, summary = [], {"flights": len(flights), "ends_read": sum(1 for f in flights for e in ("a", "b") if f.get(e))}
    periods = [("h1", per_half[:1]), ("h2", per_half[1:2]), ("full", per_half)]
    lengths = {"h1": [h[1] - h[0] for h in half_list[:1]], "h2": [h[1] - h[0] for h in half_list[1:2]], "full": [h[1] - h[0] for h in half_list]}
    for name, parts in periods:
        if not parts:
            continue
        held = {k: sum(p["held_s"][k] for p in parts) for k in ("light", "dark")}
        known = held["light"] + held["dark"]
        for shade in ("light", "dark"):
            rows.append({"team": side(shade), "period": name,
                         "possession_pct": round(100 * held[shade] / known, 1) if known > 60 else None,
                         "turnovers": sum(len(p["turnovers"][shade]) for p in parts),
                         "passes": sum(p["passes"][shade][1] for p in parts), "passes_completed": sum(p["passes"][shade][0] for p in parts),
                         "ball_coverage": round(known / max(1.0, sum(lengths[name])), 3)})
        summary[name] = {"possession_us": next((r["possession_pct"] for r in rows if r["period"] == name and r["team"] == "us"), None),
                         "read_share": round(known / max(1.0, sum(lengths[name])), 2)}
    passes = []
    for f in flights:
        hf = next((h for h in half_list if h[0] <= f["t0"] <= h[1]), None)
        if hf is None or not f.get("a") or not f.get("b"):
            continue
        attacks_right = (hf[2] == "left") == (f["a"] == "light")   # a team attacks away from the side it lines up on
        def norm(xy):
            u, v = (xy[0] - x0) / (x1 - x0), (xy[1] - y0) / (y1 - y0)
            u, v = float(np.clip(u, 0, 1)), float(np.clip(v, 0, 1))
            return (round(u, 3), round(1 - v, 3)) if attacks_right else (round(1 - u, 3), round(v, 3))
        (fx, fy), (tx, ty) = norm(f["xy0"]), norm(f["xy1"])
        passes.append({"t": to_film(f["t0"]), "team": side(f["a"]), "completed": f["a"] == f["b"], "outcome": "completed" if f["a"] == f["b"] else "intercepted",
                       "from_x": fx, "from_y": fy, "to_x": tx, "to_y": ty, "third": "def" if fx < 1 / 3 else "mid" if fx < 2 / 3 else "att", "confidence": 0.6})
    both = [f for f in flights if f.get("a") and f.get("b") and any(h[0] <= f["t0"] <= h[1] for h in half_list)]
    pick = [both[int(k * len(both) / 16)] for k in range(16)] if len(both) >= 16 else both
    spot = [{"t": to_film(f["t0"]), "from": side(f["a"]), "to": side(f["b"])} for f in pick]
    return {"team_stats": rows, "passes": passes, "summary": summary, "spot_check": spot}


def write(game_id, run_id, main_video, goals, flow_doc, halves, play=None):
    c = db.client()
    # only this pipeline's own unreviewed proposals are replaced; scoreboard goals and human tags stay
    c.table("tags").delete().eq("game_id", game_id).eq("source", "machine").is_("confirmed", "null").eq("label", GOAL_LABEL).execute()
    # goals already on the game: goal tags, and set pieces (free kick, corner, penalty...) marked as having gone in
    existing = [t for t in c.table("tags").select("t_seconds,type,team,source,confirmed,label,outcome").eq("game_id", game_id).execute().data
                if (t["type"] == "goal" or t.get("outcome") == "goal") and t.get("confirmed") is not False]
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
    if flow_doc and flow_doc.get("us_attack_h1") and not main_video.get("us_attack_h1"):
        c.table("videos").update({"us_attack_h1": flow_doc["us_attack_h1"]}).eq("id", main_video["id"]).execute()
    if halves and main_video.get("halftime_offset_seconds") is None:
        patch = {"kickoff_offset_seconds": round(halves[0][0]), "halftime_offset_seconds": round(halves[0][1])}
        if len(halves) > 1:
            patch.update({"second_half_offset_seconds": round(halves[1][0]), "fulltime_offset_seconds": round(halves[1][1])})
        c.table("videos").update(patch).eq("id", main_video["id"]).execute()
    if play:
        # machine possession / turnovers / passes replace the last machine figures; human-adjusted rows stay
        c.table("team_stats").delete().eq("game_id", game_id).eq("source", "machine").execute()
        if play["team_stats"]:
            c.table("team_stats").insert([{**r, "game_id": game_id, "run_id": run_id, "source": "machine"} for r in play["team_stats"]]).execute()
        c.table("pass_events").delete().eq("game_id", game_id).execute()
        rows_p = db.pass_rows(game_id, run_id, play["passes"])
        for k in range(0, len(rows_p), 200):
            c.table("pass_events").insert(rows_p[k:k + 200]).execute()
    return {"known_goals": compare, "machine_goals_with_no_known_goal": extra}
