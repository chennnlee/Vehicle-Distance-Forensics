#!/usr/bin/env python3
"""Compare two detectors on the SAME measurement chain, against the radar truth.

Why this is not just "run the evaluator twice and diff the MAE".

`comma2k19_radar_eval.py` keeps ONE of our tracks per radar object (modal
one-to-one pairing). A different detector can win that mode with a track covering
a different stretch of the segment, and then the two runs are scored on different
cars, at different times, against different parts of the ego-speed record. Segment
21 does exactly that: v8m is scored on radar object 2 over frames 592-718 (7.4-23.5 m)
while 11x is scored on the same object over frames 734-1053 (24.6-44.2 m). The
resulting end-to-end MAEs (2.88 vs 11.05) differ almost entirely because of WHICH
frames were scored -- the ego-speed term alone moves 3.64 -> 11.49, and ego speed
never touches the detector at all (the two runs' ego_speed.csv are byte-identical).

So the comparison is made on the intersection of (frame, radar object): the same
instant, the same physical car, the same plane, the same scale, the same odometer.
The only thing that differs is which pixels the detector called "vehicle", which is
what we are trying to measure the effect of.

Reports, on that intersection:
  * |Δ ground-point row| -- the pixel the whole geometry hangs on
  * distance error vs radar for each detector, and the PAIRED difference with a CI
  * the correlation of the two runs' errors: if the detector were the error source,
    the two error series would be largely independent; if they track each other,
    the error is common to both and lives elsewhere (scale, plane, radar itself)
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import numpy as np


def load(root: Path, tag: str, seg: str) -> dict:
    p = root / f"{tag}_{seg}_pairs.csv"
    if not p.exists():
        return {}
    with p.open(encoding="utf-8") as fh:
        return {(int(r["frame_idx"]), int(r["radar_obj"])): r for r in csv.DictReader(fh)}


def num(row: dict, key: str) -> float:
    v = row.get(key, "")
    return float(v) if v not in ("", None, "nan") else float("nan")


def paired_ci(d: np.ndarray) -> tuple[float, float, float]:
    """Mean of a paired difference with a normal 95% interval."""
    d = d[np.isfinite(d)]
    if len(d) < 2:
        return float("nan"), float("nan"), float("nan")
    se = d.std(ddof=1) / np.sqrt(len(d))
    return d.mean(), d.mean() - 1.96 * se, d.mean() + 1.96 * se


def block_bootstrap(d: np.ndarray, block_len: int, n_boot: int, seed: int = 0) -> tuple[float, float, float]:
    """95% interval that does not pretend consecutive frames are independent.

    A paired difference measured on one car over a few hundred consecutive frames has
    far fewer independent samples than frames: the tracker, the plane and the car's own
    motion all vary slowly. Resampling whole blocks keeps that structure, and typically
    widens the interval by 2-3x versus the textbook formula.
    """
    d = d[np.isfinite(d)]
    nb = len(d) // block_len
    if nb < 2:
        return d.mean() if len(d) else float("nan"), float("nan"), float("nan")
    blocks = [d[i * block_len:(i + 1) * block_len] for i in range(nb)]
    rng = np.random.default_rng(seed)
    means = [np.concatenate([blocks[j] for j in rng.integers(0, nb, nb)]).mean() for _ in range(n_boot)]
    lo, hi = np.percentile(means, [2.5, 97.5])
    return float(d.mean()), float(lo), float(hi)


def block(name: str, keys: list, A: dict, B: dict, ta: str, tb: str) -> None:
    if not keys:
        return
    ra = np.array([num(A[k], "range_ours_m") for k in keys])
    rb = np.array([num(B[k], "range_ours_m") for k in keys])
    rr = np.array([num(A[k], "range_radar_m") for k in keys])
    ga = np.array([3.6 * (num(A[k], "rel_ours_ms") - num(A[k], "rel_radar_ms")) for k in keys])
    gb = np.array([3.6 * (num(B[k], "rel_ours_ms") - num(B[k], "rel_radar_ms")) for k in keys])
    pa = np.array([num(A[k], "py") for k in keys])
    pb = np.array([num(B[k], "py") for k in keys])
    print(f"  {name:20s} n={len(keys):4d} | dist relerr med {ta} {np.nanmedian(np.abs(ra-rr)/rr)*100:5.1f}%"
          f"  {tb} {np.nanmedian(np.abs(rb-rr)/rr)*100:5.1f}%"
          f" | geom MAE {ta} {np.nanmean(np.abs(ga)):5.2f}  {tb} {np.nanmean(np.abs(gb)):5.2f}"
          f" | |dpy| med {np.nanmedian(np.abs(pa-pb)):4.1f}px, identical {np.mean(np.abs(pa-pb) < 1e-9)*100:3.0f}%")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--eval-dir", required=True, help="Directory holding <tag>_<seg>_pairs.csv from comma2k19_radar_eval.py --dump-csv")
    ap.add_argument("--baseline", default="v8m")
    ap.add_argument("--candidate", default="11x")
    ap.add_argument("--segments", default="seg21,seg6,seg10")
    ap.add_argument("--near-m", type=float, default=32.0, help="Radar distance splitting near from far (the pipeline's 0.8 m/px flag lands here on this camera).")
    ap.add_argument("--block", type=int, default=20, help="Block length in frames for the bootstrap (20 = 1 s at 20 Hz).")
    ap.add_argument("--boot", type=int, default=5000)
    a = ap.parse_args()

    root = Path(a.eval_dir)
    segs = [s.strip() for s in a.segments.split(",") if s.strip()]
    A_all: dict = {}
    B_all: dict = {}
    for seg in segs:
        A, B = load(root, a.baseline, seg), load(root, a.candidate, seg)
        if not A or not B:
            print(f"--- {seg}: missing pairs for one side, skipped ---")
            continue
        common = sorted(set(A) & set(B))
        print(f"--- {seg}: {a.baseline} {len(A)} pairs, {a.candidate} {len(B)} pairs, common (frame,obj) {len(common)} ---")
        for k in common:
            A_all[(seg,) + k] = A[k]
            B_all[(seg,) + k] = B[k]
        block("common all", common, A, B, a.baseline, a.candidate)
        block("common near", [k for k in common if num(A[k], "range_radar_m") <= a.near_m], A, B, a.baseline, a.candidate)
        block("common far", [k for k in common if num(A[k], "range_radar_m") > a.near_m], A, B, a.baseline, a.candidate)

    keys = sorted(A_all)
    if not keys:
        return
    print(f"\n=== pooled: {len(keys)} common (frame, radar object) pairs ===")
    block("pooled all", keys, A_all, B_all, a.baseline, a.candidate)
    block("pooled near", [k for k in keys if num(A_all[k], "range_radar_m") <= a.near_m], A_all, B_all, a.baseline, a.candidate)
    block("pooled far", [k for k in keys if num(A_all[k], "range_radar_m") > a.near_m], A_all, B_all, a.baseline, a.candidate)

    ra = np.array([num(A_all[k], "range_ours_m") for k in keys])
    rb = np.array([num(B_all[k], "range_ours_m") for k in keys])
    rr = np.array([num(A_all[k], "range_radar_m") for k in keys])
    ga = np.array([3.6 * (num(A_all[k], "rel_ours_ms") - num(A_all[k], "rel_radar_ms")) for k in keys])
    gb = np.array([3.6 * (num(B_all[k], "rel_ours_ms") - num(B_all[k], "rel_radar_ms")) for k in keys])
    pa = np.array([num(A_all[k], "py") for k in keys])
    pb = np.array([num(B_all[k], "py") for k in keys])

    print("\n-- the ground point itself --")
    dpy = np.abs(pa - pb)
    print(f"   |dpy|: median {np.nanmedian(dpy):.2f} px, mean {np.nanmean(dpy):.2f}, p90 {np.nanpercentile(dpy,90):.1f}, max {np.nanmax(dpy):.1f}"
          f"  ({np.mean(dpy < 1e-9)*100:.0f}% of frames land on the identical row)")
    dr = np.abs(ra - rb)
    print(f"   |d range| between detectors: median {np.nanmedian(dr):.3f} m, p90 {np.nanpercentile(dr,90):.2f}, max {np.nanmax(dr):.2f}")

    print("\n-- is the detector the error source? --")
    print(f"   correlation of the two runs' distance error vs radar: r = {np.corrcoef(ra-rr, rb-rr)[0,1]:.4f}")
    print(f"   correlation of the two runs' geometry-term error:     r = {np.corrcoef(ga, gb)[0,1]:.4f}")
    print("   (a detector-driven error would be largely independent between two different detectors)")

    print("\n-- paired differences (candidate minus baseline; negative = candidate better) --")
    for name, sel in (("all", np.ones(len(keys), bool)),
                      ("near", rr <= a.near_m),
                      ("far", rr > a.near_m)):
        if sel.sum() < 2:
            continue
        m, lo, hi = paired_ci(np.abs(rb - rr)[sel] - np.abs(ra - rr)[sel])
        bm, blo, bhi = block_bootstrap(np.abs(rb - rr)[sel] - np.abs(ra - rr)[sel], a.block, a.boot)
        print(f"   {name:4s} distance |error|: {m:+.3f} m    naive CI {lo:+.3f}..{hi:+.3f}   block CI {blo:+.3f}..{bhi:+.3f}")
        m, lo, hi = paired_ci(np.abs(gb)[sel] - np.abs(ga)[sel])
        bm, blo, bhi = block_bootstrap(np.abs(gb)[sel] - np.abs(ga)[sel], a.block, a.boot)
        print(f"   {name:4s} geometry term   : {m:+.3f} km/h naive CI {lo:+.3f}..{hi:+.3f}   block CI {blo:+.3f}..{bhi:+.3f}")
    print(f"   (naive CI assumes independent frames, which these are not: consecutive frames of one car")
    print(f"    move together. The block CI resamples {a.block}-frame blocks, and is the one to quote.)")

    print("\n-- what the sample actually is --")
    from collections import Counter
    comp = Counter((k[0], k[2]) for k in keys)
    print("   (segment, radar object): " + ", ".join(f"{s}/obj{o}={n}" for (s, o), n in sorted(comp.items(), key=lambda kv: -kv[1])))
    near_comp = Counter((k[0], k[2]) for k, f_ in zip(keys, rr <= a.near_m) if f_)
    if near_comp:
        print("   near subset only:        " + ", ".join(f"{s}/obj{o}={n}" for (s, o), n in sorted(near_comp.items(), key=lambda kv: -kv[1])))


if __name__ == "__main__":
    main()
