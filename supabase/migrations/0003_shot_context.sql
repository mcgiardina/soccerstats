-- Shot context for the ASA xG 3.0 model: pattern of play and assist type. Manual entry only.
alter table shots add column if not exists context text;   -- 'regular'|'corner'|'free_kick'|'indirect_free_kick'|'fastbreak'|'penalty'
alter table shots add column if not exists assist text;    -- 'none'|'cross'|'through_ball'
