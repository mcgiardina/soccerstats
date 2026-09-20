"""Clock offset between two recordings of the same game, from their soundtracks.

BallerCam's Smart View (what people watch, what tags are timed against) and its raw panoramic
file (what the fixed-camera analysis runs on) do not share a clock: on the first real game the raw
file ran 21.21 s ahead. Both carry the same microphone audio, so cross-correlating the loudness
envelopes gives the offset to a hundredth of a second. Reads only audio packets, so it works on a
URL without downloading the video (a few seconds per probe).
"""
import numpy as np


def _envelope(src, t0, dur, rate=8000, hop=80):
    import av
    c = av.open(src)
    a = next((s for s in c.streams if s.type == "audio"), None)
    if a is None:
        raise RuntimeError(f"no audio stream in {src}")
    rs = av.audio.resampler.AudioResampler(format="s16", layout="mono", rate=rate)
    c.seek(int(max(0.0, t0) / a.time_base), stream=a, any_frame=False, backward=True)
    out, first = [], None
    for pkt in c.demux(a):
        for fr in pkt.decode():
            if fr.pts is None:
                continue
            t = float(fr.pts * a.time_base)
            if first is None:
                first = t
            if t > t0 + dur:
                break
            for r in rs.resample(fr):
                out.append(r.to_ndarray().ravel())
        else:
            continue
        break
    c.close()
    x = np.concatenate(out).astype(np.float32)
    n = len(x) // hop * hop
    return np.abs(x[:n]).reshape(-1, hop).mean(axis=1), first, rate / hop


def offset(reference, other, probes=(600.0, 2400.0, 4200.0), clip_s=120.0, search_s=90.0):
    """Seconds to ADD to a time on `reference`'s clock to get the same moment on `other`'s clock.
    Probes several points; returns (offset, agreement) where agreement is the spread between probes
    (should be well under 0.1 s). Raises if no probe correlates clearly."""
    found = []
    for t0 in probes:
        try:
            es, fs, hz = _envelope(reference, t0, clip_s)
            eo, fo, _ = _envelope(other, t0 - search_s, clip_s + 2 * search_s)
        except Exception as e:  # noqa: BLE001
            print(f"clock probe at {t0:.0f}s skipped: {str(e)[:80]}")
            continue
        if len(es) < hz * 30 or len(eo) <= len(es):
            continue
        es = (es - es.mean()) / (es.std() + 1e-9); eo = (eo - eo.mean()) / (eo.std() + 1e-9)
        corr = np.correlate(eo, es, mode="valid") / len(es)
        k = int(np.argmax(corr))
        rest = np.delete(corr, slice(max(0, k - int(hz)), k + int(hz)))
        if corr[k] >= 0.4 and corr[k] >= 1.5 * (rest.max() if len(rest) else 0.0):
            found.append(fo + k / hz - fs)
    if not found:
        raise RuntimeError("the two soundtracks did not correlate; are they the same game?")
    return float(np.median(found)), float(np.max(found) - np.min(found))


if __name__ == "__main__":
    import sys
    off, spread = offset(sys.argv[1], sys.argv[2])
    print(f"other = reference {off:+.2f} s (probes agree within {spread:.2f} s)")
