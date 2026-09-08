"""yt-dlp at 720p, cached locally. The cache dir is gitignored."""
import os
import subprocess

CACHE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "cache")


def download(youtube_id: str) -> str:
    os.makedirs(CACHE, exist_ok=True)
    out = os.path.join(CACHE, f"{youtube_id}.mp4")
    if os.path.exists(out) and os.path.getsize(out) > 1_000_000:
        return out
    cmd = ["yt-dlp", "-f", "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best[height<=720]",
           "--merge-output-format", "mp4", "-o", out, f"https://www.youtube.com/watch?v={youtube_id}"]
    print("fetching", youtube_id)
    subprocess.run(cmd, check=True)
    return out
