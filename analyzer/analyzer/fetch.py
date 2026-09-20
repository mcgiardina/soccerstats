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
    # a stale yt-dlp is the usual reason for a 360p-only result: refresh it once, then retry the clients
    attempts = attempts + ["upgrade"] + attempts
    last = None
    for extra in attempts:
        if extra == "upgrade":
            print("refreshing yt-dlp before retrying")
            subprocess.call([sys.executable, "-m", "pip", "install", "-q", "--upgrade", "yt-dlp"])
            continue
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


def download_stream(url: str, key: str, max_height: int = 720) -> str:
    """A camera vendor's own stream (BallerCam HLS) or a direct file, fetched with yt-dlp's generic
    extractor. Only one rendition is offered (1080p), so max_height picks nothing; the analyzer
    resizes as it reads. Without ffmpeg the result is MPEG-TS in an .mp4 name, which OpenCV reads."""
    os.makedirs(CACHE, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in key)[:120]
    out = os.path.join(CACHE, f"{safe}.mp4")
    if os.path.exists(out) and os.path.getsize(out) > 1_000_000 and probe_height(out) >= MIN_HEIGHT:
        return out
    print("fetching stream", key)
    r = subprocess.run([sys.executable, "-m", "yt_dlp", "--no-playlist", "--fixup", "never", "-f", "bestvideo/best", "-o", out, url])
    if r.returncode != 0 or not os.path.exists(out) or os.path.getsize(out) < 1_000_000:
        raise RuntimeError(f"could not download the stream for {key} (yt-dlp exit {r.returncode}); the share link may have been turned off")
    h = probe_height(out)
    if h < MIN_HEIGHT:
        os.remove(out)
        raise RuntimeError(f"the stream for {key} is only {h}p; need >= {MIN_HEIGHT}p")
    return out


def download_video(v: dict, max_height: int = 720) -> str:
    """Any row of the videos table: YouTube by id, anything else by its stream address."""
    if v.get("youtube_id"):
        return download(v["youtube_id"], max_height=max_height)
    if v.get("stream_url"):
        return download_stream(v["stream_url"], f"{v.get('provider') or 'file'}_{v.get('provider_ref') or v['id']}", max_height=max_height)
    raise RuntimeError("this video has neither a YouTube id nor a stream address")
