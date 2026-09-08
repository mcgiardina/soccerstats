-- Match Film schema. Apply in the Supabase SQL editor or via `supabase db push`.
-- Video bytes never live here; only metadata, timestamps, and derived stats.

create table if not exists games (
  id              uuid primary key default gen_random_uuid(),
  played_on       date not null,
  opponent        text not null,
  home_away       text check (home_away in ('home','away','neutral')),
  competition     text,                     -- 'league' | 'tournament' | 'friendly'
  venue           text,
  score_us        int,
  score_them      int,
  pitch_length_m  numeric,                  -- null = use CONFIG default
  pitch_width_m   numeric,
  notes           text,
  published       boolean default false,
  created_at      timestamptz default now()
);

create table if not exists videos (
  id                         uuid primary key default gen_random_uuid(),
  game_id                    uuid references games(id) on delete cascade,
  youtube_id                 text not null,
  kind                       text,          -- 'stream_archive' | 'upload' | 'wide_fixed'
  title                      text,
  duration_seconds           int,
  kickoff_offset_seconds     int default 0,
  halftime_offset_seconds    int,           -- end of first half
  second_half_offset_seconds int,
  fulltime_offset_seconds    int,
  created_at                 timestamptz default now()
);

create table if not exists tags (
  id           uuid primary key default gen_random_uuid(),
  game_id      uuid references games(id) on delete cascade,
  video_id     uuid references videos(id) on delete cascade,
  t_seconds    numeric not null,
  type         text not null,               -- 'goal'|'shot'|'chance'|'save'|'turnover'|'corner'|'free_kick'|'throw_in'|'penalty'|'note'
  team         text check (team in ('us','them')),
  outcome      text,                        -- set pieces: 'goal'|'shot'|'cleared'|'lost'|null
  label        text,
  source       text default 'human',        -- 'human' | 'machine'
  confidence   numeric,
  confirmed    boolean,                     -- null = unreviewed
  confirmed_at timestamptz,
  created_at   timestamptz default now()
);

-- One row per shot. Pitch coords are normalized 0..1 along length (0 = own goal line,
-- 1 = attacking goal line) and width (0..1 left to right facing the attacking goal).
create table if not exists shots (
  id               uuid primary key default gen_random_uuid(),
  game_id          uuid references games(id) on delete cascade,
  tag_id           uuid references tags(id) on delete cascade,
  team             text check (team in ('us','them')),
  pitch_x          numeric,
  pitch_y          numeric,
  location_source  text,                    -- 'machine' | 'manual' | null
  location_confidence numeric,
  on_target        boolean,
  is_goal          boolean default false,
  body_part        text,                    -- 'foot'|'head'|null  (manual only)
  xg               numeric,
  xg_model_version text,
  created_at       timestamptz default now(),
  unique (tag_id)
);

create table if not exists stat_runs (
  id            uuid primary key default gen_random_uuid(),
  game_id       uuid references games(id) on delete cascade,
  video_id      uuid references videos(id) on delete cascade,
  model_version text,
  params        jsonb,
  status        text,                       -- 'queued'|'running'|'done'|'failed'
  started_at    timestamptz,
  finished_at   timestamptz,
  error         text,
  created_at    timestamptz default now()
);

create table if not exists team_stats (
  id              uuid primary key default gen_random_uuid(),
  game_id         uuid references games(id) on delete cascade,
  run_id          uuid references stat_runs(id) on delete set null,
  team            text check (team in ('us','them')),
  period          text check (period in ('full','h1','h2')),
  possession_pct  numeric,
  shots           int,
  shots_on_target int,
  turnovers       int,
  xg_total        numeric,
  source          text default 'machine',   -- 'machine' | 'human_adjusted'
  created_at      timestamptz default now()
);

create table if not exists stat_buckets (
  id                uuid primary key default gen_random_uuid(),
  game_id           uuid references games(id) on delete cascade,
  run_id            uuid references stat_runs(id) on delete cascade,
  bucket_start_s    int not null,           -- match time
  bucket_end_s      int not null,
  possession_us_pct numeric,
  ball_frames       int,                    -- denominator, for honesty
  turnovers_us      int,
  turnovers_them    int
);

create table if not exists shape_snapshots (
  id                    uuid primary key default gen_random_uuid(),
  game_id               uuid references games(id) on delete cascade,
  run_id                uuid references stat_runs(id) on delete cascade,
  t_seconds             numeric,
  period                text,
  team                  text,
  players_visible       int,
  homography_confidence numeric,
  positions             jsonb                -- [{x, y}] normalized pitch coords, no identity
);

create index if not exists tags_game_idx on tags (game_id, t_seconds);
create index if not exists shots_game_idx on shots (game_id);
create index if not exists videos_game_idx on videos (game_id);
create index if not exists games_played_idx on games (played_on desc);
create index if not exists buckets_game_idx on stat_buckets (game_id, bucket_start_s);

-- ---------------------------------------------------------------------------
-- Access model: anyone can read published games. The single admin (one Supabase
-- auth user, logging in with a password only) can do everything.
-- ---------------------------------------------------------------------------

create or replace function is_admin() returns boolean
language sql stable as $$
  select coalesce(auth.role() = 'authenticated', false)
$$;

create or replace function game_is_public(gid uuid) returns boolean
language sql stable security definer as $$
  select exists (select 1 from games g where g.id = gid and g.published)
$$;

alter table games           enable row level security;
alter table videos          enable row level security;
alter table tags            enable row level security;
alter table shots           enable row level security;
alter table stat_runs       enable row level security;
alter table team_stats      enable row level security;
alter table stat_buckets    enable row level security;
alter table shape_snapshots enable row level security;

drop policy if exists games_read on games;
create policy games_read on games for select using (published or is_admin());
drop policy if exists games_write on games;
create policy games_write on games for all using (is_admin()) with check (is_admin());

drop policy if exists videos_read on videos;
create policy videos_read on videos for select using (game_is_public(game_id) or is_admin());
drop policy if exists videos_write on videos;
create policy videos_write on videos for all using (is_admin()) with check (is_admin());

-- Parents never see unreviewed machine proposals.
drop policy if exists tags_read on tags;
create policy tags_read on tags for select
  using (is_admin() or (game_is_public(game_id) and (source = 'human' or confirmed = true)));
drop policy if exists tags_write on tags;
create policy tags_write on tags for all using (is_admin()) with check (is_admin());

drop policy if exists shots_read on shots;
create policy shots_read on shots for select using (game_is_public(game_id) or is_admin());
drop policy if exists shots_write on shots;
create policy shots_write on shots for all using (is_admin()) with check (is_admin());

drop policy if exists stat_runs_read on stat_runs;
create policy stat_runs_read on stat_runs for select using (game_is_public(game_id) or is_admin());
drop policy if exists stat_runs_write on stat_runs;
create policy stat_runs_write on stat_runs for all using (is_admin()) with check (is_admin());

drop policy if exists team_stats_read on team_stats;
create policy team_stats_read on team_stats for select using (game_is_public(game_id) or is_admin());
drop policy if exists team_stats_write on team_stats;
create policy team_stats_write on team_stats for all using (is_admin()) with check (is_admin());

drop policy if exists stat_buckets_read on stat_buckets;
create policy stat_buckets_read on stat_buckets for select using (game_is_public(game_id) or is_admin());
drop policy if exists stat_buckets_write on stat_buckets;
create policy stat_buckets_write on stat_buckets for all using (is_admin()) with check (is_admin());

drop policy if exists shape_read on shape_snapshots;
create policy shape_read on shape_snapshots for select using (game_is_public(game_id) or is_admin());
drop policy if exists shape_write on shape_snapshots;
create policy shape_write on shape_snapshots for all using (is_admin()) with check (is_admin());
