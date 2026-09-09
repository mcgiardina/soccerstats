-- Team identity, a coach share link, and which sections parents can see. One row.
create table if not exists team_settings (
  id              int primary key default 1 check (id = 1),
  team_name       text,
  short_name      text,
  logo_data_url   text,                       -- small image as a data: URL (kept under ~200 KB by the app)
  primary_color   text,
  accent_color    text,
  pitch_length_m  numeric,
  pitch_width_m   numeric,
  coach_token     text not null default encode(gen_random_bytes(16), 'hex'),
  hidden          jsonb not null default '[]'::jsonb,   -- keys of stats/sections hidden from the public view
  updated_at      timestamptz default now()
);
insert into team_settings (id) values (1) on conflict (id) do nothing;

alter table team_settings enable row level security;
drop policy if exists team_settings_admin on team_settings;
create policy team_settings_admin on team_settings for all using (is_admin()) with check (is_admin());

-- Everyone can read the branding and the hidden list, never the token.
create or replace view team_public with (security_invoker = false) as
  select id, team_name, short_name, logo_data_url, primary_color, accent_color, pitch_length_m, pitch_width_m, hidden, updated_at
  from team_settings;
grant select on team_public to anon, authenticated;

-- Coach link: the token is the credential. Check it, and let its holder change what parents see.
create or replace function coach_check(p_token text) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.team_settings where coach_token = p_token and length(p_token) >= 16)
$$;
create or replace function coach_set_hidden(p_token text, p_hidden jsonb) returns boolean
language plpgsql security definer set search_path = '' as $$
begin
  if not exists (select 1 from public.team_settings where coach_token = p_token and length(p_token) >= 16) then
    return false;
  end if;
  update public.team_settings set hidden = coalesce(p_hidden, '[]'::jsonb), updated_at = now() where id = 1;
  return true;
end $$;
grant execute on function coach_check(text) to anon, authenticated;
grant execute on function coach_set_hidden(text, jsonb) to anon, authenticated;
