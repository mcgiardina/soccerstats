"""Crowd-noise cue from the game audio. Parents and players react to shots and goals, so short
loudness bursts above the running background are a cheap, camera-independent signal. Decoded
with PyAV (no system ffmpeg needed). Returns an RMS envelope at `hop` seconds."""
import numpy as np


def envelope(path, hop=0.5):
    import av
    container = av.open(path)
    stream = next(s for s in container.streams if s.type == "audio")
    sr = stream.rate or 48000
    resampler = av.AudioResampler(format="fltp", layout="mono", rate=sr)
    chunk = int(sr * hop)
    buf = np.zeros(0, np.float32)
    rms = []
    for frame in container.decode(stream):
        for f in resampler.resample(frame):
            a = f.to_ndarray()[0].astype(np.float32)
            buf = np.concatenate([buf, a])
            while len(buf) >= chunk:
                seg, buf = buf[:chunk], buf[chunk:]
                rms.append(float(np.sqrt(np.mean(seg * seg)) + 1e-9))
    container.close()
    return np.array(rms), hop


def peaks(env, hop, window_s=20.0, z=2.5, min_gap_s=8.0):
    """Times where loudness jumps well above the local background. Returns [(t, z_score)]."""
    db = 20 * np.log10(env)
    w = max(3, int(window_s / hop))
    # running median + MAD as the background
    from numpy.lib.stride_tricks import sliding_window_view
    pad = np.pad(db, (w // 2, w - 1 - w // 2), mode="edge")
    win = sliding_window_view(pad, w)
    med = np.median(win, axis=1)
    mad = np.median(np.abs(win - med[:, None]), axis=1) * 1.4826 + 1e-6
    zs = (db - med) / mad
    out, last = [], -1e9
    for i in np.argsort(-zs):
        t = i * hop
        if zs[i] < z:
            break
        if all(abs(t - u) >= min_gap_s for u, _ in out):
            out.append((round(float(t), 1), round(float(zs[i]), 1)))
    return sorted(out)
