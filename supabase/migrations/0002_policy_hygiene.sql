-- Advisor follow-ups: invoker-safe helper, one policy per action, FK indexes.

create or replace function game_is_public(gid uuid) returns boolean
language sql stable security invoker set search_path = '' as $$
  select exists (select 1 from public.games g where g.id = gid and g.published)
$$;

do $$
declare t text;
begin
  foreach t in array array['games','videos','tags','shots','stat_runs','team_stats','stat_buckets','shape_snapshots'] loop
    execute format('drop policy if exists %I on %I', case when t = 'shape_snapshots' then 'shape_write' else t || '_write' end, t);
    execute format('create policy %I on %I for insert with check (is_admin())', t || '_insert', t);
    execute format('create policy %I on %I for update using (is_admin()) with check (is_admin())', t || '_update', t);
    execute format('create policy %I on %I for delete using (is_admin())', t || '_delete', t);
  end loop;
end $$;

create index if not exists stat_runs_game_idx on stat_runs (game_id);
create index if not exists team_stats_game_idx on team_stats (game_id);
create index if not exists shape_game_idx on shape_snapshots (game_id);
create index if not exists tags_video_idx on tags (video_id);
