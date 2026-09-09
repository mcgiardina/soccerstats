-- Machine pass estimates. Coverage is partial (the ball is only tracked part of the time), so
-- counts are lower bounds and the app shows ball coverage next to them.
create table if not exists pass_events (
  id           uuid primary key default gen_random_uuid(),
  game_id      uuid references games(id) on delete cascade,
  run_id       uuid references stat_runs(id) on delete cascade,
  t_seconds    numeric not null,
  team         text check (team in ('us','them')),
  completed    boolean not null,
  from_x       numeric, from_y numeric,      -- attack-normalised pitch coords when geometry existed
  to_x         numeric, to_y   numeric,
  third        text check (third in ('def','mid','att')),   -- origin third when located
  confidence   numeric
);
create index if not exists pass_events_game_idx on pass_events (game_id, t_seconds);
alter table pass_events enable row level security;
drop policy if exists pass_events_read on pass_events;
create policy pass_events_read on pass_events for select using (game_is_public(game_id) or is_admin());
drop policy if exists pass_events_insert on pass_events;
create policy pass_events_insert on pass_events for insert with check (is_admin());
drop policy if exists pass_events_update on pass_events;
create policy pass_events_update on pass_events for update using (is_admin()) with check (is_admin());
drop policy if exists pass_events_delete on pass_events;
create policy pass_events_delete on pass_events for delete using (is_admin());

alter table team_stats add column if not exists passes int;
alter table team_stats add column if not exists passes_completed int;
alter table team_stats add column if not exists ball_coverage numeric;   -- share of frames with the ball tracked

-- Thirds are measured from the left goal line of the video's pitch geometry; attack direction per
-- team is not known, so store left/mid/right rather than defensive/attacking.
alter table pass_events drop constraint if exists pass_events_third_check;
alter table pass_events add constraint pass_events_third_check check (third in ('left','mid','right'));
alter table pass_events add column if not exists outcome text check (outcome in ('completed','incomplete','unknown'));
