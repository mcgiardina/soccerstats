-- Our kit colour for a game (hex, e.g. #1e5bd8). The analyzer worker on the Mac mini uses it to
-- decide which colour cluster is "us" without anyone at a terminal. Empty = team primary colour.
alter table games add column if not exists kit_color text;
