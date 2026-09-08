"""Frame sampling. Yields (t_seconds, frame_bgr) at a fixed rate."""
from dataclasses import dataclass

import cv2


@dataclass
class Frame:
    t: float
    img: "object"


def sample(path: str, fps: float = 5.0, limit_seconds=None, dewarp=None):
    """dewarp: optional callable applied to every frame (fisheye sources)."""
    cap = cv2.VideoCapture(path, cv2.CAP_AVFOUNDATION) if hasattr(cv2, "CAP_AVFOUNDATION") else cv2.VideoCapture(path)
    if not cap.isOpened():
        cap = cv2.VideoCapture(path)
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, int(round(src_fps / fps)))
    frames = []
    i = 0
    while True:
        ok = cap.grab()
        if not ok:
            break
        if i % step == 0:
            t = i / src_fps
            if limit_seconds is not None and t > limit_seconds:
                break
            ok, img = cap.retrieve()
            if ok:
                if dewarp is not None:
                    img = dewarp(img)
                frames.append(Frame(t=t, img=img))
        i += 1
    cap.release()
    print(f"sampled {len(frames)} frames at ~{fps} fps")
    return frames


def period_offsets(video_row):
    return {
        "kickoff": video_row.get("kickoff_offset_seconds") or 0,
        "halftime": video_row.get("halftime_offset_seconds"),
        "second_half": video_row.get("second_half_offset_seconds"),
        "fulltime": video_row.get("fulltime_offset_seconds"),
    }


def match_period(offsets, t):
    ko, ht, sh, ft = offsets["kickoff"], offsets["halftime"], offsets["second_half"], offsets["fulltime"]
    if t < ko:
        return None
    if ht is not None and t >= ht and (sh is None or t < sh):
        return None
    if sh is not None and t >= sh:
        if ft is not None and t >= ft:
            return None
        return "h2"
    return "h1"


def match_seconds(offsets, t):
    """Continuous match clock, halftime removed."""
    ko, ht, sh = offsets["kickoff"], offsets["halftime"], offsets["second_half"]
    h1 = (ht - ko) if ht is not None else None
    if sh is not None and t >= sh:
        return (h1 or 0) + (t - sh)
    return max(0.0, t - ko)
