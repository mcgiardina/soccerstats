-- Videos from sources other than YouTube (BallerCam first; Veo, Trace, XbotGo, or any direct file).
-- provider      where it is hosted: 'youtube' | 'ballercam' | 'veo' | 'trace' | 'xbot' | 'file'
-- provider_ref  the provider's own id for it (BallerCam stream slug), used to look the stream up again
-- source_url    the share link a person opens
-- stream_url    what the in-app player plays when it is not YouTube (HLS playlist or mp4)
-- raw_url       the camera's full-field file for the analyzer (BallerCam panoramic .mov), never played
alter table videos alter column youtube_id drop not null;
alter table videos add column if not exists provider     text not null default 'youtube';
alter table videos add column if not exists provider_ref text;
alter table videos add column if not exists source_url   text;
alter table videos add column if not exists stream_url   text;
alter table videos add column if not exists raw_url      text;
alter table videos drop constraint if exists videos_playable;
alter table videos add constraint videos_playable check (youtube_id is not null or stream_url is not null);
