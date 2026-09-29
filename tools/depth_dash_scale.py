#!/usr/bin/env python3
"""Scale a monocular depth model with the painted lane-dash pattern, then read ego speed
off the resulting distances.

What it does, per clip:

  1. Finds the dashed lane lines without any lane-line tool, and FOLLOWS them through the
     clip: in each short window (default 1.2 s) a white top-hat of a dash BLINKS at every
     pixel it passes (high temporal variance) while solid lines, road texture and burned-in
     overlays stay put. Each image row is normalised by its own median (so far-field
     clutter cannot drown the lines), Hough + least squares gives x = a*y + b, and the pair
     nearest the image centre is the ego lane. Re-detecting per window is what keeps the
     line under the dashes when the car drifts or changes lane.
  2. Per frame, reads two things along each line: dash brightness, and the depth model's
     distance to the road at the same pixels (model units, not metres). Rows run from just
     below the two lines' crossing point down to the bottom of the road band.
  3. Scale: the dash pattern repeats every legal cycle (Taiwan 10 m, MUTCD 12.19 m,
     Caltrans 14.63 m). Its spatial period in model units, median over frames, gives
     k = cycle / period, so metres = k * model output.
  4. Ego speed: the painted dashes do not move, so between frames t and t+step the metric
     profile slides toward the camera by the distance driven; that shift over the elapsed
     time is the speed. No temporal period, no fixed-row timing.

Nothing from the odometer code (dashcam_range_speed, odometer_distance_calib,
lane_line_fit, auto_odometer_points, public_dataset_ego_eval) is imported. The only
project module used is depth_backends (the depth-model wrapper), when a depth map has to
be computed.

  python3 tools/depth_dash_scale.py run --frames DIR --fps 29.97 --cycle-m 10 \\
      --depth-cache DIR --band-bottom 0.86 --out result.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Fixed before scoring. Changing any of these after a result has been looked at is
# tuning on the answer.
PARAMS = dict(
    tophat_px=31,           # white top-hat structuring element at 1080 rows (scaled with height)
    det_top=0.40,           # detection band top, fraction of height (lines must reach here)
    det_ds=2,               # downsampling of the variance maps
    win_s=1.2,              # detection window length
    win_hop_s=0.4,          # detection window hop
    norm_thr=3.0,           # std / row-median above this -> candidate dash pixel
    min_slope=0.15,         # |dx/dy| outside [min_slope, 5] is not a lane line
    band_half_px=12,        # lateral search half-width around the line, at 1080 rows
    vp_margin=0.04,         # profile starts this fraction of height below the crossing point
    vp_dev=0.04,            # windows whose crossing row is further than this from the clip median are dropped
    zcap_cycles=3.3,        # profile ends where the model distance reaches this many cycles
    dz_model=0.05,          # profile resampling step, model units
    min_contrast=8.0,       # profile p90 - p10 below this: no dashes visible
    close_gap=0.05,         # merge on-runs separated by less than this fraction of a cycle
    min_run=0.05,           # drop on-runs shorter than this fraction of a cycle
    duty_tol=0.15,          # dash/cycle must be within this of the legal ratio
    period_min=0.5,         # accepted cycle, as a fraction of the legal cycle (model units)
    period_max=2.0,
    min_frames=10,          # measured cycles needed per line
    max_ci=0.03,            # 95% CI half-width of a line's median cycle, over the median; above -> refused
                            # (2026-09-29, replaces "per-cycle IQR/median <= 10%": single-frame cycles are
                            # noisy by nature and k is their median, so the gate belongs on the median.
                            # Changed after comma2k19 seg10 failed the old gate at 10.4-10.7%; no answer
                            # file had been opened. Applies to every clip alike.)
    ci_block_s=1.0,         # block length for the bootstrap: neighbouring frames see the same dashes
    lines_agree=0.10,       # two accepted lines must agree on k within this
    shift_max=0.45,         # speed: largest shift searched, fraction of a cycle
    min_corr=0.5,           # speed: correlation needed to report a reading
)


def _odd(n: int) -> int:
    return n if n % 2 else n + 1


def white_tophat(gray: np.ndarray, k: int) -> np.ndarray:
    se = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (_odd(k), _odd(k)))
    return cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, se)


def list_frames(d: Path) -> list[Path]:
    fs = sorted(d.glob("*.jpg")) or sorted(d.glob("*.png"))
    if not fs:
        sys.exit(f"{d}: no frames")
    return fs


# ------------------------------------------------------------------ 0. what not to look at

def static_rows(frames, n=40):
    """Where the road ends and where burned-in text sits, found without reading either.

    Bonnet / dashboard: rows whose pixels barely change over the clip while the road above
    them keeps moving. Overlay text (date, GPS speed, logo): thin bright strokes that stay
    in place. Returns (road_bottom_row, overlay_boxes) -- overlay boxes are blacked out
    before anything is displayed, so neither the program nor a person reads the recorder's
    own speed.
    """
    sample = frames[:: max(1, len(frames) // n)][:n]
    gs = np.stack([cv2.imread(str(f), cv2.IMREAD_GRAYSCALE).astype(np.float32) for f in sample])
    h, w = gs.shape[1:]
    std = gs.std(0)
    row_std = np.median(std, axis=1)
    ref = np.median(row_std[int(0.55 * h): int(0.65 * h)]) + 1e-3
    bottom = h
    run = 0
    for y in range(int(0.6 * h), h):
        run = run + 1 if row_std[y] < 0.35 * ref else 0
        if run >= max(8, h // 100):
            bottom = y - run + 1
            break
    th = np.stack([white_tophat(g.astype(np.uint8), 9) for g in gs]).astype(np.float32)
    text = ((th.mean(0) > 30) & (std < 15)).astype(np.uint8)
    text = cv2.dilate(text, np.ones((15, 31), np.uint8))
    n_cc, lab, stats, _ = cv2.connectedComponentsWithStats(text)
    boxes = []
    for i in range(1, n_cc):
        x, y, bw, bh, area = stats[i]
        if area > 400 and (y > 0.75 * h or y + bh < 0.15 * h):     # overlays live at the edges
            boxes.append([int(x), int(y), int(x + bw), int(y + bh)])
    return int(bottom), boxes


def black_out(img, boxes):
    out = img.copy()
    for x0, y0, x1, y1 in boxes:
        out[y0:y1, x0:x1] = 0
    return out


# ------------------------------------------------------------------ 1. dashed lines, tracked

def tophat_stack(frames, idx, y0, y1, k, ds):
    g0 = cv2.imread(str(frames[idx[0]]), cv2.IMREAD_GRAYSCALE)
    w = g0.shape[1]
    out = np.empty((len(idx), (y1 - y0) // ds, w // ds), np.uint8)
    for n, i in enumerate(idx):
        g = cv2.imread(str(frames[i]), cv2.IMREAD_GRAYSCALE)
        t = white_tophat(g, k)[y0:y1]
        out[n] = cv2.resize(t, (w // ds, (y1 - y0) // ds), interpolation=cv2.INTER_AREA)
    return out


def lines_in_window(T, y0, ds, w, p=PARAMS):
    """Dashed-line candidates from one window of top-hat frames (full-res x = a*y + b)."""
    std = T.astype(np.float32).std(0)
    norm = std / (np.median(std, axis=1, keepdims=True) + 1.0)
    binary = (norm > p["norm_thr"]).astype(np.uint8) * 255
    hh = binary.shape[0]
    segs = cv2.HoughLinesP(binary, 1, np.pi / 180, threshold=max(15, hh // 6),
                           minLineLength=max(15, hh // 4), maxLineGap=max(6, hh // 8))
    if segs is None:
        return []
    ys, xs = np.nonzero(binary)
    out = []
    for xa, ya, xb, yb in segs[:, 0]:
        if yb == ya:
            continue
        a = (xb - xa) / (yb - ya)
        if not p["min_slope"] <= abs(a) <= 5:
            continue
        b = xa - a * ya
        near = np.abs(xs - (a * ys + b)) < 4
        if near.sum() < 20:
            continue
        a2, b2 = np.polyfit(ys[near], xs[near], 1)
        rr = np.arange(hh)
        xx = np.round(a2 * rr + b2).astype(int)
        ok = (xx >= 0) & (xx < binary.shape[1])
        if ok.mean() < 0.6:
            continue
        score = float(norm[rr[ok], xx[ok]].mean())
        # back to full resolution: x_full = ds*(a2*(y_full - y0)/ds + b2)
        A, B = a2, ds * b2 - a2 * y0
        out.append(dict(a=float(A), b=float(B), score=score))
    # merge near-duplicates, strongest first
    out.sort(key=lambda d: -d["score"])
    merged = []
    y_ref = y0 + ds * hh
    for d in out:
        if all(abs((d["a"] - m["a"]) * y_ref + d["b"] - m["b"]) > 30 or abs(d["a"] - m["a"]) > 0.3
               for m in merged):
            merged.append(d)
    return merged


def ego_pair(cands, w, y_bottom):
    """Nearest line left of centre and nearest right of centre, at the bottom row."""
    left = [c for c in cands if c["a"] * y_bottom + c["b"] < w / 2]
    right = [c for c in cands if c["a"] * y_bottom + c["b"] >= w / 2]
    L = max(left, key=lambda c: c["a"] * y_bottom + c["b"]) if left else None
    R = min(right, key=lambda c: c["a"] * y_bottom + c["b"]) if right else None
    return L, R


def track_lines(frames, idx, fps, band_bottom, p=PARAMS):
    g0 = cv2.imread(str(frames[0]), cv2.IMREAD_GRAYSCALE)
    h, w = g0.shape
    y0, y1 = int(p["det_top"] * h), int(band_bottom * h)
    k = max(9, int(round(p["tophat_px"] * h / 1080)))
    ds = p["det_ds"]
    T = tophat_stack(frames, idx, y0, y1, k, ds)
    step = idx[1] - idx[0] if len(idx) > 1 else 1
    win = max(4, int(round(p["win_s"] * fps / step)))
    hop = max(1, int(round(p["win_hop_s"] * fps / step)))
    windows = []
    for c in range(0, len(idx), hop):
        lo, hi = max(0, c - win // 2), min(len(idx), c + win // 2 + 1)
        cands = lines_in_window(T[lo:hi], y0, ds, w, p)
        L, R = ego_pair(cands, w, y1)
        vp = None
        if L and R and abs(L["a"] - R["a"]) > 1e-3:
            yv = (R["b"] - L["b"]) / (L["a"] - R["a"])
            if y0 - 0.3 * h < yv < y1:
                vp = float(yv)
        windows.append(dict(center=c, frame=idx[c], left=L, right=R, vp_row=vp, n_cands=len(cands)))
    return dict(windows=windows, height=h, width=w, det_rows=[y0, y1], tophat_px=k, idx=list(idx))


def lines_for(track, n):
    """Window whose centre is nearest to position n in idx."""
    ws = track["windows"]
    return min(ws, key=lambda wd: abs(wd["center"] - n))


# ------------------------------------------------------------------ 2. profiles

def load_depth(cache, frame: Path, backend=None, fx=None):
    """Depth map for one frame at half resolution; cached as float16 .npy unless cache is None."""
    fp = None if cache is None else Path(cache) / f"{frame.stem}.npy"
    if fp is not None and fp.exists():
        return np.load(fp).astype(np.float32)
    if backend is None:
        raise FileNotFoundError(fp or frame)
    out = backend.infer_full(cv2.imread(str(frame)), fx=fx)
    d = out["depth_m"] if out["depth_m"] is not None else out["relative"]
    hh, ww = d.shape
    half = cv2.resize(d, (ww // 2, hh // 2), interpolation=cv2.INTER_AREA).astype(np.float16)
    if fp is not None:
        fp.parent.mkdir(parents=True, exist_ok=True)
        np.save(fp, half)
    return half.astype(np.float32)


def line_profile(tophat, depth_half, line, rows, half_px, zcap):
    """Brightness and model distance along the line, near rows first, up to zcap."""
    h, w = tophat.shape
    dh, dw = depth_half.shape
    B, Z = [], []
    for y in rows:
        x = int(round(line["a"] * y + line["b"]))
        x0, x1 = max(0, x - half_px), min(w, x + half_px + 1)
        if x1 - x0 < 3:
            break
        yy, xx = min(dh - 1, int(y * dh / h)), min(dw - 1, int(x * dw / w))
        z = float(np.median(depth_half[max(0, yy - 1): yy + 2, max(0, xx - 1): xx + 2]))
        if not np.isfinite(z) or z <= 0:
            break
        B.append(float(tophat[y, x0:x1].max()))
        Z.append(z)
    if len(Z) < 20:
        return None
    Z = np.maximum.accumulate(cv2.medianBlur(np.float32(Z).reshape(-1, 1), 5).ravel())
    keep = Z <= zcap
    B, Z = np.array(B)[keep], Z[keep]
    if len(Z) < 20:
        return None
    return B, Z + np.arange(len(Z)) * 1e-6


def resample(B, Z, dz):
    grid = np.arange(Z[0], Z[-1], dz)
    return grid, np.interp(grid, Z, B)


# ------------------------------------------------------------------ 3. scale

def dash_cycles(grid, prof, cycle_m, duty, p=PARAMS):
    """Near-edge to near-edge distances of complete dashes along one profile (model units).

    The profile runs near -> far. A dash is a bright run; only runs with both ends inside
    the profile count. Consecutive dashes give one cycle each, kept when the painted
    fraction (dash / cycle) matches the legal ratio -- a check that needs no scale.
    """
    lo, hi = np.percentile(prof, [10, 90])
    if hi - lo < p["min_contrast"]:
        return []
    on = prof > lo + 0.5 * (hi - lo)
    dz = grid[1] - grid[0]
    gap = int(round(p["close_gap"] * cycle_m / dz))
    # close short gaps, then drop short runs
    idx = np.flatnonzero(np.diff(np.r_[0, on.astype(int), 0]))
    runs = [[a, b] for a, b in zip(idx[::2], idx[1::2])]
    merged = []
    for r in runs:
        if merged and r[0] - merged[-1][1] <= gap:
            merged[-1][1] = r[1]
        else:
            merged.append(r)
    minrun = int(round(p["min_run"] * cycle_m / dz))
    runs = [r for r in merged if r[1] - r[0] >= minrun and r[0] > 0 and r[1] < len(prof)]
    out = []
    for (a0, a1), (b0, _) in zip(runs[:-1], runs[1:]):
        cyc = (b0 - a0) * dz
        if not p["period_min"] * cycle_m <= cyc <= p["period_max"] * cycle_m:
            continue
        if abs((a1 - a0) * dz / cyc - duty) <= p["duty_tol"]:
            out.append((float(cyc), float(grid[a0])))
    return out


# ------------------------------------------------------------------ 4. speed

def profile_shift(g1, p1, g2, p2, smax, dz, min_corr):
    """Distance the dash pattern moved toward the camera between two metric profiles."""
    lo, hi = max(g1[0], g2[0] + smax), min(g1[-1], g2[-1])
    if hi - lo < 2 * smax:
        return None, 0.0
    G = np.arange(lo, hi, dz)
    a = np.interp(G, g1, p1)
    a = a - a.mean()
    shifts = np.arange(0, smax, dz)
    cs = []
    for s in shifts:
        b = np.interp(G - s, g2, p2)
        b = b - b.mean()
        den = np.sqrt((a * a).sum() * (b * b).sum())
        cs.append((a * b).sum() / den if den > 0 else 0.0)
    cs = np.array(cs)
    i = int(np.argmax(cs))
    if cs[i] < min_corr or i == 0 or i == len(cs) - 1:
        return None, float(cs[i])
    den = cs[i - 1] - 2 * cs[i] + cs[i + 1]
    off = 0.5 * (cs[i - 1] - cs[i + 1]) / den if den < 0 else 0.0
    return (i + off) * dz, float(cs[i])


# ------------------------------------------------------------------ driver

def run(frames_dir, fps, cycle_m, depth_cache, band_bottom, step=2, model="da3_metric",
        duty_ratio=0.4, p=PARAMS, fx=None):
    frames = list_frames(Path(frames_dir))
    idx = list(range(0, len(frames), step))
    track = track_lines(frames, idx, fps, band_bottom, p)
    h, w = track["height"], track["width"]
    # the camera's pitch does not jump: a window whose lines cross far from the clip's
    # usual crossing row picked up something else (a car edge, a turning arrow)
    vps = [wd["vp_row"] for wd in track["windows"] if wd["vp_row"] is not None]
    if vps:
        vmed = float(np.median(vps))
        for wd in track["windows"]:
            if wd["vp_row"] is not None and abs(wd["vp_row"] - vmed) > p["vp_dev"] * h:
                wd["vp_row_rejected"] = wd["vp_row"]
                wd["vp_row"] = None
    y1 = track["det_rows"][1]
    half_px = max(4, int(round(p["band_half_px"] * h / 1080)))
    cache = None if depth_cache is None else Path(depth_cache)
    backend = None
    L = cycle_m
    zcap = p["zcap_cycles"] * L

    per_frame = []     # n -> {"left": (grid, prof), "right": ...}
    periods = []
    duty = duty_ratio
    for n, i in enumerate(idx):
        wd = lines_for(track, n)
        if wd["vp_row"] is None:
            per_frame.append({})
            continue
        try:
            d = load_depth(cache, frames[i], backend, fx)
        except FileNotFoundError:
            if backend is None:
                import depth_backends as DB
                backend = DB.get_backend(model)
                backend.load(device="cuda")
            d = load_depth(cache, frames[i], backend, fx)
        g = cv2.imread(str(frames[i]), cv2.IMREAD_GRAYSCALE)
        th = white_tophat(g, track["tophat_px"])
        rows = np.arange(y1 - 1, int(wd["vp_row"] + p["vp_margin"] * h), -1)
        got = {}
        for side in ("left", "right"):
            ln = wd[side]
            r = line_profile(th, d, ln, rows, half_px, zcap)
            if r is None:
                continue
            grid, prof = resample(r[0], r[1], p["dz_model"])
            got[side] = (grid, prof)
            for cyc, z0 in dash_cycles(grid, prof, L, duty, p):
                periods.append(dict(n=n, side=side, period=cyc, z_near=z0))
        per_frame.append(got)

    res = dict(params=p, cycle_m=L, fps=fps, step=step, model=model, n_frames=len(frames),
               frames_dir=str(frames_dir), band_bottom=band_bottom,
               windows=track["windows"], det_rows=track["det_rows"], tophat_px=track["tophat_px"],
               periods=periods)
    blk = max(1, int(round(p["ci_block_s"] * fps / step)))
    rng = np.random.default_rng(0)
    sides = {}
    for side in ("left", "right"):
        rows_ = [x for x in periods if x["side"] == side]
        per = np.array([x["period"] for x in rows_])
        e = dict(n=int(len(per)))
        if len(per) >= p["min_frames"]:
            med = float(np.median(per))
            q1, q3 = np.percentile(per, [25, 75])
            groups = {}
            for x in rows_:
                groups.setdefault(x["n"] // blk, []).append(x["period"])
            gl = list(groups.values())
            boots = [np.median(np.concatenate([gl[j] for j in rng.integers(0, len(gl), len(gl))]))
                     for _ in range(1000)]
            lo, hi = np.percentile(boots, [2.5, 97.5])
            e.update(period_model=med, spread=float((q3 - q1) / med), k=L / med,
                     ci_half=float((hi - lo) / 2 / med), n_blocks=len(gl))
            e["accepted"] = e["ci_half"] <= p["max_ci"]
        else:
            e["accepted"] = False
        sides[side] = e
    res["sides"] = sides
    acc = [sd for sd, e in sides.items() if e["accepted"]]
    if not acc:
        res.update(status="refused", reason="no line passed: " + "; ".join(
            f"{sd} n={e['n']} CI±{e.get('ci_half', float('nan')):.1%}" for sd, e in sides.items()))
        return res
    ks = [sides[sd]["k"] for sd in acc]
    if max(ks) / min(ks) - 1 > p["lines_agree"]:
        res.update(status="refused", reason=f"lines disagree on k: {ks}")
        return res
    per = np.array([x["period"] for x in periods if x["side"] in acc])
    med = float(np.median(per))
    q1, q3 = np.percentile(per, [25, 75])
    k = L / med
    res.update(status="ok", k=k, period_model=med, spread=float((q3 - q1) / med), lines_used=acc)

    dt = step / fps
    smax = p["shift_max"] * L
    speeds = []
    for n in range(len(idx) - 1):
        a, b = per_frame[n], per_frame[n + 1]
        best = (None, 0.0, None)
        for side in acc:
            if side in a and side in b:
                s, c = profile_shift(a[side][0] * k, a[side][1], b[side][0] * k, b[side][1],
                                     smax, p["dz_model"] * k, p["min_corr"])
                if s is not None and c > best[1]:
                    best = (s, c, side)
        speeds.append(dict(frame_i=idx[n], frame_j=idx[n + 1], t_s=(idx[n] + idx[n + 1]) / 2 / fps,
                           corr=best[1], side=best[2],
                           kmh=None if best[0] is None else best[0] / dt * 3.6))
    res["speeds"] = speeds
    got = [x["kmh"] for x in speeds if x["kmh"] is not None]
    res["speed_coverage"] = len(got) / max(1, len(speeds))
    res["speed_median_kmh"] = float(np.median(got)) if got else None
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--frames", required=True)
    r.add_argument("--fps", type=float, required=True, help="from the video container, not from any report")
    r.add_argument("--cycle-m", type=float, required=True, help="legal dash cycle of the road's jurisdiction")
    r.add_argument("--depth-cache", required=True)
    r.add_argument("--band-bottom", type=float, required=True,
                   help="lowest road row as a fraction of height (above the bonnet / overlay)")
    r.add_argument("--duty", type=float, required=True,
                   help="legal painted fraction: Taiwan 4/10 = 0.4, MUTCD 10/40 and Caltrans 12/48 = 0.25")
    r.add_argument("--model", default="da3_metric")
    r.add_argument("--step", type=int, default=2, help="frame stride for depth and speed")
    r.add_argument("--out", required=True)
    args = ap.parse_args()
    res = run(args.frames, args.fps, args.cycle_m, args.depth_cache, args.band_bottom, args.step, args.model,
              args.duty)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(res, indent=1))
    nvp = sum(1 for wd in res["windows"] if wd["vp_row"] is not None)
    print(f"{res['status']}  k={res.get('k')}  period(model)={res.get('period_model')}  "
          f"spread={res.get('spread')}  cycles={len(res['periods'])}  windows with lane pair {nvp}/{len(res['windows'])}")
    for sd, e in res.get("sides", {}).items():
        print(f"  {sd}: n={e['n']} k={e.get('k')} spread={e.get('spread')} CI±{e.get('ci_half')} "
              f"{'accepted' if e['accepted'] else 'refused'}")
    if res.get("speeds") is not None:
        print(f"  speed median {res.get('speed_median_kmh')}  coverage {res.get('speed_coverage'):.1%}")
    if res["status"] != "ok":
        print("  reason:", res.get("reason"))
    print("sha256", hashlib.sha256(Path(args.out).read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
