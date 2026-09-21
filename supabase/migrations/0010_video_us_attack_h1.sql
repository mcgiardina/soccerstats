-- Which way WE attack in the first half as seen on the film ('left' | 'right'); the second half is the other way.
-- The shot placer uses it to show the pitch the way the film shows it, then stores the shot in the usual
-- "towards the goal being attacked" coordinates.
alter table videos add column if not exists us_attack_h1 text check (us_attack_h1 in ('left','right'));
