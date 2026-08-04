"""Evaluate the dash-cycle odometer against a public dataset's own ego-speed truth.

Two modes, and the order matters:

  --solve-cycle   Do this FIRST on any new road network. The odometer converts a
                  measured period into a speed with v = cycle / T, so the legal
                  dash cycle is an input, not an output. Taiwan taught us not to
                  trust the spec sheet: the freeway spec says 4 m + 8 m = 12 m,
                  but every measured stretch of 國1/國3/台86 came out at 10 m.
                  This mode inverts the relation instead -- cycle = v_truth * T --
                  and reports the distribution, so a foreign road's real cycle is
                  measured rather than assumed.

  (default)       With --dash-cycle-m given, report accuracy: coverage, MAE,
                  bias, error percentiles and a bootstrap CI on the MAE.

Ground truth comes in as a CSV of `t_s,speed_kmh`; `--kitti-oxts` builds that CSV
straight from a KITTI raw sequence's OXTS records (field 8 = forward velocity).
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "tools"))

from dashcam_range_speed import dash_cycle_speeds, extract_odometer_signals


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--frames-dir", required=True)
    ap.add_argument("--fps", type=float, required=True)
    ap.add_argument("--odometer-points", required=True, help="'x,y;x,y;...' on the lane dash line.")
    ap.add_argument("--gt-csv", help="Ground-truth CSV with columns t_s,speed_kmh.")
    ap.add_argument("--kitti-oxts", help="KITTI raw sequence dir (contains oxts/ and image_02/); builds the GT itself.")
    ap.add_argument("--dash-cycle-m", type=float, default=None, help="Legal cycle length. Omit with --solve-cycle.")
    ap.add_argument("--solve-cycle", action="store_true", help="Infer the cycle from the truth instead of assuming it.")
    ap.add_argument("--window-s", type=float, default=3.0)
    ap.add_argument("--min-speed-kmh", type=float, default=25.0,
                    help="Ignore truth below this: the odometer needs >=2 cycles inside the window, so crawling "
                         "and stopped stretches are outside the method's domain by construction, not failures of it.")
    ap.add_argument("--cache", default="", help="Optional .pkl to cache the extracted pulse signals.")
    ap.add_argument("--out-json", default="")
    return ap.parse_args()


def kitti_gt(seq_dir: Path) -> list[tuple[float, float]]:
    """(t_s, km/h) from KITTI OXTS. dataformat.txt: field 8 is vf, forward
    velocity in m/s; fields 6/7 are the north/east components, kept as a
    cross-check that the record is what we think it is."""
    ts_file = seq_dir / "oxts" / "timestamps.txt"
    stamps = []
    for line in ts_file.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        hms = line.split(" ")[1]
        h, m, s = hms.split(":")
        stamps.append(int(h) * 3600 + int(m) * 60 + float(s))
    t0 = stamps[0]
    rows = []
    for i, f in enumerate(sorted((seq_dir / "oxts" / "data").glob("*.txt"))):
        v = [float(x) for x in f.read_text().split()]
        vf, vn, ve = v[8], v[6], v[7]
        if abs(np.hypot(vn, ve) - abs(vf)) > 1.5:
            print(f"  warn: frame {i} vf={vf:.2f} disagrees with |(vn,ve)|={np.hypot(vn, ve):.2f}")
        rows.append((stamps[i] - t0, abs(vf) * 3.6))
    return rows


def main() -> None:
    args = parse_args()
    points = [tuple(int(v) for v in c.split(",")) for c in args.odometer_points.split(";") if c.strip()]
    frames = sorted(Path(args.frames_dir).glob("*.png")) or sorted(Path(args.frames_dir).glob("*.jpg"))
    if not frames:
        raise SystemExit(f"no frames in {args.frames_dir}")

    if args.kitti_oxts:
        gt = kitti_gt(Path(args.kitti_oxts))
    elif args.gt_csv:
        gt = []
        with open(args.gt_csv, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                gt.append((float(r["t_s"]), float(r["speed_kmh"])))
    else:
        raise SystemExit("need --gt-csv or --kitti-oxts")
    gt_t = np.array([g[0] for g in gt])
    gt_v = np.array([g[1] for g in gt])
    print(f"frames {len(frames)}  truth points {len(gt)}  "
          f"truth speed median {np.median(gt_v):.1f} km/h  range {gt_v.min():.1f}-{gt_v.max():.1f}")

    cache = Path(args.cache) if args.cache else None
    if cache and cache.exists():
        import pickle
        sig = pickle.loads(cache.read_bytes())
    else:
        sig = extract_odometer_signals(frames, points)
        if cache:
            import pickle
            cache.write_bytes(pickle.dumps(sig))

    # Run with cycle = 1 m so the reported "speed" is literally 1/T; any cycle
    # then just scales it. That keeps one signal pass usable for both modes.
    inv_t, conf, _ = dash_cycle_speeds(frames, points, 1.0, args.fps, args.window_s, sig=sig)
    t = np.arange(len(frames)) / args.fps
    per_s = inv_t  # = 1/T in Hz (m/s per metre of cycle)

    v_truth = np.interp(t, gt_t, gt_v)
    usable = np.isfinite(per_s) & (v_truth >= args.min_speed_kmh)
    coverage = float(usable.sum() / max(1, np.sum(v_truth >= args.min_speed_kmh)))
    print(f"odometer locked on {int(usable.sum())} of {int(np.sum(v_truth >= args.min_speed_kmh))} "
          f"in-domain frames (coverage {coverage*100:.0f}%)")

    out: dict = {"frames": len(frames), "fps": args.fps, "coverage_in_domain": coverage,
                 "truth_median_kmh": float(np.median(gt_v))}

    if args.solve_cycle or args.dash_cycle_m is None:
        implied = (v_truth[usable] / 3.6) / per_s[usable]
        print("\n=== 反推週期(不套規範值) ===")
        for q in (10, 25, 50, 75, 90):
            print(f"  implied cycle p{q:<2d}: {np.percentile(implied, q):6.2f} m")
        print(f"  中位 {np.median(implied):.2f} m,四分位距 "
              f"{np.percentile(implied,75)-np.percentile(implied,25):.2f} m")
        print("  解讀:分布若集中在某個值附近,那就是這條路的實際週期;"
              "散開代表訊號不乾淨或取樣點沒落在虛線上。")
        out["implied_cycle_m"] = {f"p{q}": float(np.percentile(implied, q)) for q in (10, 25, 50, 75, 90)}
        out["implied_cycle_iqr"] = float(np.percentile(implied, 75) - np.percentile(implied, 25))
        if args.dash_cycle_m is None:
            Path(args.out_json).write_text(json.dumps(out, indent=2), encoding="utf-8") if args.out_json else None
            return

    v_est = per_s * args.dash_cycle_m * 3.6
    d = v_est[usable] - v_truth[usable]
    mae = float(np.mean(np.abs(d)))
    rng = np.random.default_rng(0)
    boot = [np.mean(np.abs(rng.choice(d, size=d.size))) for _ in range(2000)]
    lo, hi = np.percentile(boot, [2.5, 97.5])
    print(f"\n=== 準確度(cycle = {args.dash_cycle_m} m) ===")
    print(f"  MAE      {mae:.2f} km/h   95% CI [{lo:.2f}, {hi:.2f}]")
    print(f"  bias     {np.mean(d):+.2f} km/h")
    print(f"  |誤差| 分位數  p50 {np.percentile(np.abs(d),50):.2f}  p90 {np.percentile(np.abs(d),90):.2f}  "
          f"p95 {np.percentile(np.abs(d),95):.2f}  max {np.max(np.abs(d)):.2f}")
    print(f"  ±3 km/h 內   {np.mean(np.abs(d)<=3)*100:.1f}%")
    out.update({"dash_cycle_m": args.dash_cycle_m, "mae_kmh": mae, "mae_ci95": [float(lo), float(hi)],
                "bias_kmh": float(np.mean(d)),
                "abs_err_percentiles": {f"p{q}": float(np.percentile(np.abs(d), q)) for q in (50, 90, 95)},
                "within_3kmh_pct": float(np.mean(np.abs(d) <= 3) * 100), "n_compared": int(d.size)})
    if args.out_json:
        Path(args.out_json).write_text(json.dumps(out, indent=2), encoding="utf-8")
        print("wrote", args.out_json)


if __name__ == "__main__":
    main()
