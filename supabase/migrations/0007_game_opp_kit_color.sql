-- The opponent's kit colour for a game (hex). Event pills, timeline markers and shot dots on the game
-- page take both kit colours so an event reads as the shirt you see on the film.
alter table games add column if not exists opp_kit_color text;
