"""Supabase reads/writes. Uses the service role key; never runs in a browser."""
import os
from datetime import datetime, timezone

from supabase import create_client

_client = None


def client():
    global _client
    if _client is None:
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_ANON_KEY")
        if not url or not key:
            raise SystemExit("Set SUPABASE_URL and SUPABASE_SERVICE_KEY (or SUPABASE_ANON_KEY for --dry-run) in analyzer/.env")
        if not os.environ.get("SUPABASE_SERVICE_KEY"):
            print("no SUPABASE_SERVICE_KEY: reads only (published games); use --dry-run")
        _client = create_client(url, key)
    return _client


def now():
    return datetime.now(timezone.utc).isoformat()


def get_game(game_id):
    return client().table("games").select("*").eq("id", game_id).single().execute().data


def get_videos(game_id):
    return client().table("videos").select("*").eq("game_id", game_id).order("created_at").execute().data


def claim_run(game_id, video_id, model_version, params):
    """Take the oldest queued run for this game, or create one. Never auto-triggered."""
    q = client().table("stat_runs").select("*").eq("game_id", game_id).eq("status", "queued").order("created_at").limit(1).execute().data
    patch = {"status": "running", "started_at": now(), "model_version": model_version, "params": params, "video_id": video_id}
    # keep whatever the app put in params (e.g. us_cluster) alongside ours
    if q and isinstance(q[0].get("params"), dict):
        patch["params"] = {**q[0]["params"], **params}
    # supabase-py returns the affected rows from update/insert directly (no .select().single() chain,
    # which older releases don't support).
    if q:
        rows = client().table("stat_runs").update(patch).eq("id", q[0]["id"]).execute().data
    else:
        rows = client().table("stat_runs").insert({"game_id": game_id, **patch}).execute().data
    return rows[0]


def finish_run(run_id, status, error=None):
    client().table("stat_runs").update({"status": status, "finished_at": now(), "error": error}).eq("id", run_id).execute()


def get_team_choice(game_id):
    """Persisted 'which cluster is us' answer lives in the run params of the last done run."""
    rows = client().table("stat_runs").select("params").eq("game_id", game_id).eq("status", "done").order("finished_at", desc=True).limit(1).execute().data
    return (rows[0]["params"] or {}).get("us_cluster") if rows else None


def other(team):
    return None if team is None else ("them" if team == "us" else "us")


def machine_tag_rows(s, label):
    """One shot candidate can become up to two tags: the shot itself and, when the ball ended
    on the keeper, a 'save' for the defending team; a ball that carried past the keeper is
    proposed as a goal with the shot. All proposals; a human confirms."""
    t = round(float(s["t"]), 1)
    conf = round(float(s["confidence"]), 3)
    out = s.get("outcome", "shot")
    rows = []
    if out == "goal?":
        rows.append({"t_seconds": t, "type": "goal", "team": s.get("team"), "confidence": round(conf * 0.8, 3),
                     "label": "machine goal candidate (ball carried past keeper)"})
    rows.append({"t_seconds": t, "type": "shot", "team": s.get("team"), "confidence": conf, "label": label})
    if out == "save":
        rows.append({"t_seconds": t, "type": "save", "team": other(s.get("team")), "confidence": conf,
                     "label": "machine save candidate"})
    return rows


def write_results(*, game_id, run_id, video_id, team_stats, buckets, shot_tags, shot_locations, snapshots, pitch, kick_tags=()):
    c = client()
    # Replace prior machine stats for this game; human_adjusted rows are untouched.
    c.table("team_stats").delete().eq("game_id", game_id).eq("source", "machine").execute()
    if team_stats:
        c.table("team_stats").insert([{**r, "game_id": game_id, "run_id": run_id, "source": "machine"} for r in team_stats]).execute()
    c.table("stat_buckets").delete().eq("game_id", game_id).execute()
    if buckets:
        c.table("stat_buckets").insert([{**b, "game_id": game_id, "run_id": run_id} for b in buckets]).execute()

    # Machine shot tags: only remove earlier unreviewed machine tags. Reviewed ones (confirmed
    # true/false) are human decisions and stay.
    c.table("tags").delete().eq("game_id", game_id).eq("source", "machine").is_("confirmed", "null").execute()
    existing = c.table("tags").select("t_seconds,type").eq("game_id", game_id).execute().data
    taken = [float(t["t_seconds"]) for t in existing if t["type"] in ("shot", "goal", "penalty")]
    rows = []
    for s, label in [(x, "machine shot candidate") for x in shot_tags] + [(x, "machine kick candidate") for x in kick_tags]:
        # Don't propose a shot within 4 s of one a human already tagged.
        if any(abs(s["t"] - t) < 4 for t in taken):
            continue
        for r in machine_tag_rows(s, label):
            rows.append({"game_id": game_id, "video_id": video_id, "source": "machine", **r})
    inserted = c.table("tags").insert(rows).execute().data if rows else []
    # Machine locations go on the shots table as proposals, marked 'machine'.
    from analyzer.xg import compute_xg, MODEL_VERSION
    L = float(pitch[0] or 105); W = float(pitch[1] or 68)
    for tag in inserted:
        loc = shot_locations.get(round(float(tag["t_seconds"]), 1))
        if not loc:
            continue
        c.table("shots").upsert({
            "game_id": game_id, "tag_id": tag["id"], "team": tag["team"],
            "pitch_x": loc["x"], "pitch_y": loc["y"], "location_source": "machine",
            "location_confidence": loc["confidence"], "is_goal": False,
            "xg": compute_xg(loc["x"], loc["y"], L, W), "xg_model_version": MODEL_VERSION,
        }, on_conflict="tag_id").execute()

    c.table("shape_snapshots").delete().eq("game_id", game_id).execute()
    if snapshots:
        for i in range(0, len(snapshots), 200):
            c.table("shape_snapshots").insert([{**s, "game_id": game_id, "run_id": run_id} for s in snapshots[i:i + 200]]).execute()


def fail_queued(run_id, error):
    client().table("stat_runs").update({"status": "failed", "finished_at": now(), "error": str(error)[:500]}).eq("id", run_id).execute()
