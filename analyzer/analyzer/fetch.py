"""yt-dlp at 720p, cached locally. The cache dir is gitignored."""
import os
import subprocess
import sys

# Videos are big; keep them out of the repo (and out of Dropbox). Override with ANALYZER_CACHE.
CACHE = os.environ.get("ANALYZER_CACHE") or os.path.expanduser("~/Library/Caches/match-film")


def download(youtube_id: str) -> str:
    os.makedirs(CACHE, exist_ok=True)
    out = os.path.join(CACHE, f"{youtube_id}.mp4")
    if os.path.exists(out) and os.path.getsize(out) > 1_000_000:
        return out
    # Video-only: no audio needed for analysis and no ffmpeg merge step required.
    fmt = "bestvideo[height<=720][ext=mp4][vcodec^=avc1]/bestvideo[height<=720][ext=mp4]/best[height<=720][ext=mp4]"
    cmd = [sys.executable, "-m", "yt_dlp", "-f", fmt, "--no-playlist", "-o", out, f"https://www.youtube.com/watch?v={youtube_id}"]
    print("fetching", youtube_id)
    subprocess.run(cmd, check=True)
    return out
