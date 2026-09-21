"""Match flow for the momentum graphic, from a FIXED wide camera.

Needs only what the fixed view gives reliably: where the players of each team stand (people rows,
see kickoffs.py) mapped onto the field (fieldmap.py), and the attack candidates of the motion
tracker (fixedcam.py). No ball position in open play is needed.

Per 15 s step, smoothed over ~45 s:
  h     where the players are: a coarse density grid over the field (the surface's height)
  seam  per lateral band, the midpoint between the two teams' centres of mass along the field. When
        one team pushes, both blocks move toward the other goal and the seam moves with them
  m     one number, -1..1: the seam averaged across the field, + toward THEIR goal
Everything is turned so that US ATTACK TO THE RIGHT in both halves, and times are in the clock of the
video people watch (raw clock - offset). This is a machine estimate of territory, not of possession.
"""
import base64
import json

import numpy as np

from . import fieldmap, kickoffs

NX, NY = 20, 10


def halves(rows, restart_list, x_mid=None, y_range=None, min_share=0.35, smooth_s=60.0, min_break_s=180.0, min_half_s=1200.0, walk_off_s=12.0):
    """[(kick_off, end, light_side), ...] in the rows' clock.

    Half time is read the way a person would: the stretch where the players are off the pitch for
    3+ minutes. The first half ends where that break starts; the second half starts at the first
    kick-off line-up after it (at the moment the kick is taken, see kickoffs.kick_time). The first
    half starts at the first line-up of the recording; the game ends when the pitch empties again."""
    if not restart_list:
        return []
    ts = np.array([r["t"] for r in rows])
    n = np.array([sum(1 for p in r["p"] if kickoffs.classify(p)) for r in rows], float)
    k = max(1, int(smooth_s / max(np.median(np.diff(ts)), 1e-6)))
    sm = np.convolve(n, np.ones(k) / k, mode="same")
    first = restart_list[0]
    full = np.median(sm[ts >= first["t"]])
    empty = sm < min_share * full
    # runs of "empty pitch" after the first half could have been played
    breaks, i = [], 0
    while i < len(ts):
        if empty[i]:
            j = i
            while j + 1 < len(ts) and empty[j + 1]:
                j += 1
            if ts[j] - ts[i] >= min_break_s and ts[i] > first["t"] + min_half_s:
                breaks.append((float(ts[i]), float(ts[j])))
            i = j + 1
        else:
            i += 1
    def whistle(t_empty):
        """The smoothed count lags: step back to the last sample that still had half the players on."""
        i = int(np.searchsorted(ts, t_empty))
        lo = max(0, i - 2 * k)
        busy = np.where(n[lo:i + 1] >= 0.5 * full)[0]
        # players need ~10-15 s to walk off after the whistle (first real game: 50:37 by this rule,
        # ~50:20 on the film), so lean a little early
        return float(ts[min(len(ts) - 1, lo + busy[-1] + 1)] - walk_off_s) if len(busy) else float(t_empty)

    kick = (lambda r: kickoffs.kick_time(rows, r, x_mid, y_range)) if x_mid is not None else (lambda r: r["t"])
    if not breaks:
        return [(kick(first), float(ts[-1]), first["light_side"])]
    ht0, ht1 = breaks[0]
    second = next((r for r in restart_list if r["t"] >= ht0), None)
    out = [(kick(first), whistle(ht0), first["light_side"])]
    if second is not None:
        after = ts > second["t"] + min_half_s
        gone = ts[after & empty]
        out.append((kick(second), whistle(gone[0]) if len(gone) else float(ts[-1]), second["light_side"]))
    return out


def build(rows, cam, size, field, half_list, us_is_light=True, attacks=(), clock_offset=0.0,
          step=15.0, smooth_s=45.0, gain=1.3):
    """field: (x0, x1, y0, y1) in feet: goal lines and touchlines. attacks: fixedcam candidates as
    dicts {"goal": "left"/"right", "t": raw seconds, "score": float}."""
    x0, x1, y0, y1 = field
    P = []  # t, u (0..1 along, us -> right), v (0..1 across), is_us
    for r in rows:
        hf = next((h for h in half_list if h[0] - 5 <= r["t"] <= h[1]), None)
        if hf is None:
            continue
        people = [(p, kickoffs.classify(p)) for p in r["p"]]
        people = [(p, c) for p, c in people if c]
        if not people:
            continue
        g = fieldmap.to_field([[p[0], p[1]] for p, _ in people], cam, size)
        us_left = (hf[2] == "left") == us_is_light
        for (gx, gy), (_, c) in zip(g, people):
            u, v = (gx - x0) / (x1 - x0), (gy - y0) / (y1 - y0)
            if not (np.isfinite(u) and -0.03 <= u <= 1.03 and -0.03 <= v <= 1.03):
                continue
            if not us_left:
                u, v = 1 - u, 1 - v
            P.append((r["t"], u, v, (c == "light") == us_is_light))
    P = np.array(P, float)
    t_first, t_last = half_list[0][0], half_list[-1][1]
    steps = np.arange(t_first, t_last + step, step)
    gx, gy = (np.arange(NX) + 0.5) / NX, (np.arange(NY) + 0.5) / NY
    H = np.zeros((len(steps), NY, NX)); seam = np.full((len(steps), NY), 0.5); live = np.zeros(len(steps), bool)
    sig_t, sig_c, sig_band = smooth_s / 2, 1.0 / NX, 0.22
    for i, t in enumerate(steps):
        live[i] = any(h[0] <= t <= h[1] for h in half_list)
        m = np.abs(P[:, 0] - t) < 2 * sig_t
        if not live[i] or m.sum() < 20:
            continue
        q = P[m]; w = np.exp(-0.5 * ((q[:, 0] - t) / sig_t) ** 2)
        ax = np.exp(-0.5 * ((q[:, 1, None] - gx[None]) / sig_c) ** 2)
        ay = np.exp(-0.5 * ((q[:, 2, None] - gy[None]) / (sig_c * 2)) ** 2)
        H[i] = np.einsum("n,ny,nx->yx", w, ay, ax) / w.sum()
        us = q[:, 3] > 0.5
        whole = 0.5 * (np.average(q[us, 1], weights=w[us]) + np.average(q[~us, 1], weights=w[~us])) if us.any() and (~us).any() else 0.5
        for j, v in enumerate(gy):
            b = w * np.exp(-0.5 * ((q[:, 2] - v) / sig_band) ** 2)
            wu, wt = b[us].sum(), b[~us].sum()
            if min(wu, wt) < 0.5:
                seam[i, j] = whole
                continue
            local = 0.5 * ((b[us] * q[us, 1]).sum() / wu + (b[~us] * q[~us, 1]).sum() / wt)
            trust = min(1.0, min(wu, wt) / 4.0)
            seam[i, j] = trust * local + (1 - trust) * whole
    seam = np.clip(0.5 + (seam - 0.5) * gain, 0.06, 0.94)
    seam[~live] = 0.5
    top = np.percentile(H[live], 99.5) if live.any() else 1.0
    H8 = np.clip(H / max(top, 1e-9) * 255, 0, 255).astype(np.uint8)
    mom = np.clip((seam.mean(1) - 0.5) * 2.2, -1, 1)

    ev = []
    for a in attacks:
        hf = next((h for h in half_list if h[0] <= a["t"] <= h[1]), None)
        if hf is None:
            continue
        us_left = (hf[2] == "left") == us_is_light
        by_us = (a["goal"] == "right") == us_left  # we attack the goal we do not defend
        ev.append({"t": round(a["t"] - clock_offset, 1), "team": "us" if by_us else "them", "score": round(float(a["score"]), 1)})
    return {
        "v": 1, "step": step, "t0": round(float(steps[0] - clock_offset), 1), "n": int(len(steps)), "nx": NX, "ny": NY,
        "halves": [[round(h[0] - clock_offset, 1), round(h[1] - clock_offset, 1)] for h in half_list],
        # we defend the side our shirts line up on at the first kick-off, so we attack the other way
        "us_attack_h1": "right" if ((half_list[0][2] == "left") == us_is_light) else "left",
        "h": base64.b64encode(H8.tobytes()).decode(),
        "seam": base64.b64encode((seam * 255).astype(np.uint8).tobytes()).decode(),
        "m": [round(float(v), 3) for v in mom],
        "attacks": sorted(ev, key=lambda e: e["t"]),
    }


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Build the flow series for the momentum graphic")
    ap.add_argument("people"); ap.add_argument("camera", help="json: {cam, size, field, x_mid, y_range}")
    ap.add_argument("--cands", help="fixedcam candidates json"); ap.add_argument("--offset", type=float, default=0.0)
    ap.add_argument("--them-light", action="store_true"); ap.add_argument("-o", "--out", default="flow.json")
    a = ap.parse_args()
    rows = json.load(open(a.people)); c = json.load(open(a.camera))
    rs = kickoffs.restarts(rows, c["x_mid"], c["y_range"])
    hl = halves(rows, rs, c["x_mid"], c["y_range"])
    att = []
    if a.cands:
        for k in json.load(open(a.cands)):
            att.append({"goal": k[0], "score": k[1], "t": k[2]} if isinstance(k, list) else {"goal": k["goal"], "score": k["score"], "t": k["t"]})
    out = build(rows, c["cam"], c["size"], c["field"], hl, us_is_light=not a.them_light, attacks=att, clock_offset=a.offset)
    json.dump(out, open(a.out, "w"), separators=(",", ":"))
    print(f"{out['n']} steps, halves {out['halves']}, {len(out['attacks'])} attacks, {len(json.dumps(out)) // 1024} KB")
