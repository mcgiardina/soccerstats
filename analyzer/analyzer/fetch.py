"""yt-dlp at 720p, cached locally. The cache dir is gitignored."""
import os
import subprocess
import sys

# Videos are big; keep them out of the repo (and out of Dropbox). Override with ANALYZER_CACHE.
CACHE = os.environ.get("ANALYZER_CACHE") or os.path.expanduser("~/Library/Caches/match-film")


def download(youtube_id: str, max_height: int = 720) -> str:
    os.makedirs(CACHE, exist_ok=True)
    out = os.path.join(CACHE, f"{youtube_id}.mp4" if max_height == 720 else f"{youtube_id}_{max_height}p.mp4")
    if os.path.exists(out) and os.path.getsize(out) > 1_000_000:
        return out
    # Video-only: no audio needed for analysis and no ffmpeg merge step required.
    fmt = (f"bestvideo[height<={max_height}][ext=mp4][vcodec^=avc1]/bestvideo[height<={max_height}][ext=mp4]"
           f"/best[height<={max_height}][ext=mp4]")
    url = f"https://www.youtube.com/watch?v={youtube_id}"
    print("fetching", youtube_id)
    # Some uploads only answer to specific player clients (seen: a BallerCam upload that was
    # "not available" to the default client but served 360p via android). Try in order.
    attempts = [[], ["--extractor-args", "youtube:player_client=android"], ["--extractor-args", "youtube:player_client=ios"]]
    last = None
    for extra in attempts:
        cmd = [sys.executable, "-m", "yt_dlp", "-f", fmt, "--no-playlist", "-o", out, *extra, url]
        r = subprocess.run(cmd)
        if r.returncode == 0 and os.path.exists(out) and os.path.getsize(out) > 1_000_000:
            if extra:
                print(f"downloaded via {extra[-1]}; resolution may be limited")
            return out
        last = r.returncode
    raise RuntimeError(f"yt-dlp could not download {youtube_id} (last exit {last}); is the video public or unlisted, and finished processing?")
