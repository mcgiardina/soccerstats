-- A picture for the game card when the film is not on YouTube (BallerCam publishes one per game).
alter table videos add column if not exists thumbnail_url text;

-- BallerCam names it after the stream: .../<name>_HD/playlist.m3u8 -> uploads/streams/<name>.jpg
update videos set thumbnail_url = 'https://baller-assets.s3.amazonaws.com/uploads/streams/' || substring(stream_url from 'b-cdn\.net/(.+)_HD/playlist\.m3u8') || '.jpg'
where provider = 'ballercam' and kind <> 'wide_fixed' and thumbnail_url is null and stream_url ~ 'b-cdn\.net/.+_HD/playlist\.m3u8';
