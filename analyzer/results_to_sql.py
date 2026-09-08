#!/usr/bin/env python3
"""Turn a dry-run results JSON into SQL you can paste into the Supabase SQL editor.
Only needed when the analyzer has no service key; with one, analyze.py writes directly."""
import json
import sys
import uuid

path, game_id = sys.argv[1], sys.argv[2]
swap = "--swap-teams" in sys.argv   # use if the cluster you called "us" turned out to be them
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
for s in r["team_stats"]:
    out.append(f"insert into team_stats (game_id, run_id, team, period, possession_pct, turnovers, source) values "
               f"('{game_id}', '{run_id}', {team(s['team'])}, '{s['period']}', {s['possession_pct']}, {s['turnovers']}, 'machine');")
for b in r["buckets"]:
    p = "null" if b["possession_us_pct"] is None else (100 - b["possession_us_pct"] if swap else b["possession_us_pct"])
    tu, tt = (b["turnovers_them"], b["turnovers_us"]) if swap else (b["turnovers_us"], b["turnovers_them"])
    out.append(f"insert into stat_buckets (game_id, run_id, bucket_start_s, bucket_end_s, possession_us_pct, ball_frames, turnovers_us, turnovers_them) values "
               f"('{game_id}', '{run_id}', {b['bucket_start_s']}, {b['bucket_end_s']}, {p}, {b['ball_frames']}, {tu}, {tt});")
for c in r["shot_candidates"]:
    out.append(f"insert into tags (game_id, video_id, t_seconds, type, team, label, source, confidence) values "
               f"('{game_id}', '{video_id}', {round(c['t'], 1)}, 'shot', {team(c.get('team'))}, 'machine shot candidate', 'machine', {round(c['confidence'], 3)});")
print("\n".join(out))
