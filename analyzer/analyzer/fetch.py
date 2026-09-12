"""yt-dlp at 720p, cached locally. The cache dir is gitignored."""
import os
import subprocess
import sys

# Videos are big; keep them out of the repo (and out of Dropbox). Override with ANALYZER_CACHE.
CACHE = os.environ.get("ANALYZER_CACHE") or os.path.expanduser("~/Library/Caches/match-film")


# A 360p stream makes the ball a 3-pixel blob and the kits a smear; refuse it rather than analyse
# it (override with ANALYZER_MIN_HEIGHT for a genuinely low-res upload).
MIN_HEIGHT = int(os.environ.get("ANALYZER_MIN_HEIGHT", "700"))


def probe_height(path: str) -> int:
    try:
        import cv2
        cap = cv2.VideoCapture(path)
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()
        return h
    except Exception:  # noqa: BLE001
        return 0


def download(youtube_id: str, max_height: int = 720) -> str:
    os.makedirs(CACHE, exist_ok=True)
    out = os.path.join(CACHE, f"{youtube_id}.mp4" if max_height == 720 else f"{youtube_id}_{max_height}p.mp4")
    if os.path.exists(out) and os.path.getsize(out) > 1_000_000:
        h = probe_height(out)
        if h >= min(MIN_HEIGHT, max_height - 20):
            return out
        print(f"cached {youtube_id} is only {h}p; downloading again")
        os.remove(out)
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
            h = probe_height(out)
            if h < min(MIN_HEIGHT, max_height - 20):
                print(f"got only {h}p{' via ' + extra[-1] if extra else ''}; trying the next client")
                os.remove(out); last = f"{h}p"
                continue
            return out
        last = r.returncode
    raise RuntimeError(f"yt-dlp could not download {youtube_id} at >= {min(MIN_HEIGHT, max_height - 20)}p (last: {last}). "
                       f"Update yt-dlp (pip install -U yt-dlp) and check the video is public or unlisted and finished processing.")
