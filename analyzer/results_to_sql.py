#!/usr/bin/env python3
"""Turn a dry-run results JSON into compact SQL for the Supabase SQL editor.
Only needed when the analyzer has no service key; with one, analyze.py writes directly.
Usage: results_to_sql.py <results.json> <game-id> [--swap-teams] [--top N] [--located-only]"""
import json
import sys
import uuid

from analyzer.db import machine_tag_rows, machine_on_target
from analyzer.xg import compute_xg, MODEL_VERSION

path, game_id = sys.argv[1], sys.argv[2]
swap = "--swap-teams" in sys.argv
top_n = int(sys.argv[sys.argv.index("--top") + 1]) if "--top" in sys.argv else None
located_only = "--located-only" in sys.argv
r = json.load(open(path))
run_id = str(uuid.uuid4())
video_id = r["video_id"]
L, W = float(r.get("pitch_length_m") or 105), float(r.get("pitch_width_m") or 68)


def team(t):
    if t is None:
        return "null"
    if swap:
        t = "them" if t == "us" else "us"
    return f"'{t}'"


def q(v):
    return "null" if v is None else (f"'{v}'" if isinstance(v, str) else ("true" if v is True else "false" if v is False else v))


out = [f"insert into stat_runs (id, game_id, video_id, model_version, params, status, started_at, finished_at) values "
       f"('{run_id}', '{game_id}', '{video_id}', '{r['model_version']}', '{json.dumps(r['params'])}'::jsonb, 'done', now(), now());",
       f"delete from team_stats where game_id = '{game_id}' and source = 'machine';",
       f"delete from stat_buckets where game_id = '{game_id}';",
       f"delete from tags where game_id = '{game_id}' and source = 'machine' and confirmed is null;",
       f"delete from pass_events where game_id = '{game_id}';"]

rows = [f"('{game_id}','{run_id}',{team(s['team'])},'{s['period']}',{s['possession_pct']},{s['turnovers']},{q(s.get('passes'))},{q(s.get('passes_completed'))},{q(s.get('ball_coverage'))},'machine')" for s in r["team_stats"]]
if rows:
    out.append("insert into team_stats (game_id, run_id, team, period, possession_pct, turnovers, passes, passes_completed, ball_coverage, source) values\n " + ",\n ".join(rows) + ";")

rows = []
for b in r["buckets"]:
    p = "null" if b["possession_us_pct"] is None else (round(100 - b["possession_us_pct"], 1) if swap else b["possession_us_pct"])
    tu, tt = (b["turnovers_them"], b["turnovers_us"]) if swap else (b["turnovers_us"], b["turnovers_them"])
    rows.append(f"('{game_id}','{run_id}',{b['bucket_start_s']},{b['bucket_end_s']},{p},{b['ball_frames']},{tu},{tt})")
if rows:
    out.append("insert into stat_buckets (game_id, run_id, bucket_start_s, bucket_end_s, possession_us_pct, ball_frames, turnovers_us, turnovers_them) values\n " + ",\n ".join(rows) + ";")

tag_rows, shot_rows = [], []
for c in sorted(r.get("shot_candidates", []), key=lambda c: c["t"]):
    tid = str(uuid.uuid4())
    for row in machine_tag_rows(c, "machine shot candidate"):
        rid = tid if row["type"] == "shot" else str(uuid.uuid4())
        tag_rows.append(f"('{rid}','{game_id}','{video_id}',{row['t_seconds']},'{row['type']}',{team(row['team'])},'{row['label']}','machine',{row['confidence']})")
    ot = machine_on_target(c)
    loc = c.get("location")
    if loc:
        shot_rows.append(f"('{game_id}','{tid}',{team(c.get('team'))},{round(loc['x'], 3)},{round(loc['y'], 3)},'machine',{loc['confidence']},{q(ot)},false,{compute_xg(loc['x'], loc['y'], L, W)},'{MODEL_VERSION}')")
    elif ot is not None:
        shot_rows.append(f"('{game_id}','{tid}',{team(c.get('team'))},null,null,null,null,{q(ot)},false,null,null)")
# kicks the goal-mouth judge ruled out (goal in view, ball tracked, never near it) are not proposed
kicks = sorted([c for c in r.get("kick_candidates", []) if c.get("outcome") != "kick"], key=lambda c: -c["confidence"])
if top_n:
    kicks = kicks[:top_n]
for c in sorted(kicks, key=lambda c: c["t"]):
    lab = "machine cross candidate" if c.get("outcome") == "cross" else "machine kick candidate"
    tag_rows.append(f"('{uuid.uuid4()}','{game_id}','{video_id}',{round(c['t'], 1)},'shot',{team(c.get('team'))},'{lab}','machine',{round(c['confidence'], 3)})")
if tag_rows:
    # Same rule as db.write_results: never propose within 4 s of a shot a human tagged or already
    # reviewed (an accepted or rejected proposal from an earlier run is a human decision).
    guard = (f"where not exists (select 1 from tags x where x.game_id = '{game_id}' and x.type in ('shot','goal','penalty') "
             f"and (x.source = 'human' or x.confirmed is not null) and abs(x.t_seconds - v.t_seconds) < 4)")
    out.append("insert into tags (id, game_id, video_id, t_seconds, type, team, label, source, confidence)\n"
               "select v.* from (values\n " + ",\n ".join(tag_rows) + "\n) as v(id, game_id, video_id, t_seconds, type, team, label, source, confidence) " + guard + ";")
if shot_rows:
    out.append("insert into shots (game_id, tag_id, team, pitch_x, pitch_y, location_source, location_confidence, on_target, is_goal, xg, xg_model_version) values\n " + ",\n ".join(shot_rows) + ";")

rows = []
for e in r.get("pass_events", []):
    if located_only and e.get("from_x") is None:
        continue
    rows.append(f"('{game_id}','{run_id}',{e['t']},{team(e['team'])},{q(bool(e['completed']))},{q(e.get('outcome'))},{q(e.get('from_x'))},{q(e.get('from_y'))},{q(e.get('to_x'))},{q(e.get('to_y'))},{q(e.get('third'))},{e.get('confidence')})")
if rows:
    out.append("insert into pass_events (game_id, run_id, t_seconds, team, completed, outcome, from_x, from_y, to_x, to_y, third, confidence) values\n " + ",\n ".join(rows) + ";")
print("\n".join(out))
