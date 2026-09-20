-- Match flow for the momentum graphic: one jsonb document per analysed game, built by
-- analyzer/analyzer/flow.py from the fixed wide camera. Kept out of the game bundle because it is
-- ~100 KB; the page fetches it only when it draws the graphic.
create table if not exists game_flow (
  id         uuid primary key default gen_random_uuid(),
  game_id    uuid not null references games(id) on delete cascade,
  run_id     uuid references stat_runs(id) on delete set null,
  data       jsonb not null,
  created_at timestamptz default now()
);
create index if not exists game_flow_game_idx on game_flow (game_id, created_at desc);

alter table game_flow enable row level security;
drop policy if exists game_flow_read on game_flow;
create policy game_flow_read on game_flow for select using (game_is_public(game_id) or is_admin());
drop policy if exists game_flow_write on game_flow;
create policy game_flow_write on game_flow for all using (is_admin()) with check (is_admin());
