#!/usr/bin/env python3
"""Turn a dry-run results JSON into SQL you can paste into the Supabase SQL editor.
Only needed when the analyzer has no service key; with one, analyze.py writes directly."""
import json
import sys
import uuid

path, game_id = sys.argv[1], sys.argv[2]
swap = "--swap-teams" in sys.argv   # use if the cluster you called "us" turned out to be them
top_n = int(sys.argv[sys.argv.index("--top") + 1]) if "--top" in sys.argv else None   # keep only the N most confident shot candidates
r = json.load(open(path))
run_id = str(uuid.uuid4())
video_id = r["video_id"]
def team(t):
    if t is None: return "null"
    if swap: t = "them" if t == "us" else "us"
    return f"'{t}'"

out = [f"insert into stat_runs (id, game_id, video_id, model_version, params, status, started_at, finished_at) values "
       f"('{run_id}', '{game_id}', '{video_id}', '{r['model_version']}', '{json.dumps(r['params'])}'::jsonb, 'done', now(), now());",
       f"delete from team_stats where game_id = '{game_id}' and source = 'machine';",
       f"delete from stat_buckets where game_id = '{game_id}';",
       f"delete from tags where game_id = '{game_id}' and source = 'machine' and confirmed is null;"]
def nz(v):
    return "null" if v is None else v
for s in r["team_stats"]:
    out.append(f"insert into team_stats (game_id, run_id, team, period, possession_pct, turnovers, passes, passes_completed, ball_coverage, source) values "
               f"('{game_id}', '{run_id}', {team(s['team'])}, '{s['period']}', {s['possession_pct']}, {s['turnovers']}, {nz(s.get('passes'))}, {nz(s.get('passes_completed'))}, {nz(s.get('ball_coverage'))}, 'machine');")
out.append(f"delete from pass_events where game_id = '{game_id}';")
for e in r.get("pass_events", []):
    q = lambda v: "null" if v is None else (f"'{v}'" if isinstance(v, str) else v)
    out.append(f"insert into pass_events (game_id, run_id, t_seconds, team, completed, outcome, from_x, from_y, to_x, to_y, third, confidence) values "
               f"('{game_id}', '{run_id}', {e['t']}, {team(e['team'])}, {'true' if e['completed'] else 'false'}, {q(e.get('outcome'))}, {q(e.get('from_x'))}, {q(e.get('from_y'))}, {q(e.get('to_x'))}, {q(e.get('to_y'))}, {q(e.get('third'))}, {e.get('confidence')});")
for b in r["buckets"]:
    p = "null" if b["possession_us_pct"] is None else (100 - b["possession_us_pct"] if swap else b["possession_us_pct"])
    tu, tt = (b["turnovers_them"], b["turnovers_us"]) if swap else (b["turnovers_us"], b["turnovers_them"])
    out.append(f"insert into stat_buckets (game_id, run_id, bucket_start_s, bucket_end_s, possession_us_pct, ball_frames, turnovers_us, turnovers_them) values "
               f"('{game_id}', '{run_id}', {b['bucket_start_s']}, {b['bucket_end_s']}, {p}, {b['ball_frames']}, {tu}, {tt});")
from analyzer.xg import compute_xg, MODEL_VERSION
L, W = float(r.get("pitch_length_m") or 105), float(r.get("pitch_width_m") or 68)

from analyzer.db import machine_tag_rows
# Shot candidates become machine tags (shot, plus save / goal proposals from the outcome) and,
# when geometry located them, a machine-located shot row.
shots_ = sorted(r.get("shot_candidates", []), key=lambda c: c["t"])
for c in shots_:
    tid = str(uuid.uuid4())
    for row in machine_tag_rows(c, "machine shot candidate"):
        rid = tid if row["type"] == "shot" else str(uuid.uuid4())
        out.append(f"insert into tags (id, game_id, video_id, t_seconds, type, team, label, source, confidence) values "
                   f"('{rid}', '{game_id}', '{video_id}', {row['t_seconds']}, '{row['type']}', {team(row['team'])}, '{row['label']}', 'machine', {row['confidence']});")
    loc = c.get("location")
    if loc:
        xg = compute_xg(loc["x"], loc["y"], L, W)
        out.append(f"insert into shots (game_id, tag_id, team, pitch_x, pitch_y, location_source, location_confidence, is_goal, xg, xg_model_version) values "
                   f"('{game_id}', '{tid}', {team(c.get('team'))}, {round(loc['x'], 3)}, {round(loc['y'], 3)}, 'machine', {loc['confidence']}, false, {xg}, '{MODEL_VERSION}');")

# Kick candidates stay plain tags so a reviewer can promote or reject them.
kicks = sorted(r.get("kick_candidates", []), key=lambda c: -c["confidence"])
if top_n:
    kicks = sorted(kicks[:top_n], key=lambda c: c["t"])
for c in kicks:
    out.append(f"insert into tags (game_id, video_id, t_seconds, type, team, label, source, confidence) values "
               f"('{game_id}', '{video_id}', {round(c['t'], 1)}, 'shot', {team(c.get('team'))}, 'machine kick candidate', 'machine', {round(c['confidence'], 3)});")
print("\n".join(out))
