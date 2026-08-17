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

`--batch-root` runs every clip under a directory (each holding `frames/` and
`gt.csv`) and pools them. That is what turns fifteen hand-aimed clips into a
dataset-level number: the aggregate MAE is computed over the pooled frames, not
by averaging per-clip MAEs, so a 60 s segment does not count the same as a 10 s
one. Batch mode needs `--auto-points`, since nobody is going to hand-aim
hundreds of segments.
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

from auto_odometer_points import pick_points
from dashcam_range_speed import dash_cycle_speeds, extract_odometer_signals


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--frames-dir", help="Single-clip mode: directory of frames.")
    ap.add_argument("--batch-root", help="Batch mode: directory of clip dirs, each with frames/ and gt.csv.")
    ap.add_argument("--fps", type=float, required=True)
    ap.add_argument("--odometer-points", default="", help="'x,y;x,y;...' on the lane dash line.")
    ap.add_argument("--auto-points", action="store_true", help="Pick the sampling points from the footage itself.")
    ap.add_argument("--gt-csv", help="Ground-truth CSV with columns t_s,speed_kmh.")
    ap.add_argument("--gt-file", default="gt.csv", help="Batch mode: truth filename inside each clip dir.")
    ap.add_argument("--gt-column", default="speed_kmh", help="Truth column to evaluate against.")
    ap.add_argument("--alt-column", default="",
                    help="Second truth column in the same file (e.g. comma2k19's pose_kmh next to can_kmh). "
                         "Evaluated from the same measurement pass, so the two truths can be arbitrated "
                         "against each other instead of one being assumed correct.")
    ap.add_argument("--kitti-oxts", help="KITTI raw sequence dir (contains oxts/ and image_02/); builds the GT itself.")
    ap.add_argument("--dash-cycle-m", type=float, default=None, help="Legal cycle length. Omit with --solve-cycle.")
    ap.add_argument("--solve-cycle", action="store_true", help="Infer the cycle from the truth instead of assuming it.")
    ap.add_argument("--window-s", type=float, default=3.0)
    ap.add_argument("--min-speed-kmh", type=float, default=25.0,
                    help="Ignore truth below this: the odometer needs >=2 cycles inside the window, so crawling "
                         "and stopped stretches are outside the method's domain by construction, not failures of it.")
    ap.add_argument("--road-top", type=float, default=0.62, help="--auto-points sampling band top (fraction of height).")
    ap.add_argument("--road-bottom", type=float, default=0.90, help="--auto-points sampling band bottom.")
    ap.add_argument("--sample-band-px", type=int, default=120,
                    help="Odometer lateral search half-width. The 120 px default suits 1920-wide "
                         "dashcams; a wide-FOV 1164-wide camera needs less or the band straddles "
                         "two lane lines and the speed reads double.")
    ap.add_argument("--cache", default="", help="Optional .pkl to cache the extracted pulse signals (single-clip mode).")
    ap.add_argument("--out-json", default="")
    ap.add_argument("--limit", type=int, default=0, help="Batch mode: stop after N clips.")
    ap.add_argument("--points-json", default="",
                    help="Batch mode: reuse the points from a previous run's --out-json instead of "
                         "re-picking them (the picker is the expensive half of a run).")
    ap.add_argument("--dump-dir", default="",
                    help="Batch mode: write per-clip per-frame arrays (1/T and both truths) as .npz, "
                         "so any later analysis of the error distribution is a re-read, not a re-run.")
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


def read_gt_csv(path: Path, column: str = "speed_kmh") -> list[tuple[float, float]]:
    rows = []
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            v = float(r[column])
            if np.isfinite(v):
                rows.append((float(r["t_s"]), v))
    return rows


def frames_in(d: Path) -> list[Path]:
    return sorted(d.glob("*.png")) or sorted(d.glob("*.jpg"))


def run_clip(frames: list[Path], fps: float, points: list[tuple[int, int]], gt: list[tuple[float, float]],
             window_s: float, min_speed_kmh: float, sig: dict | None = None,
             band_px: int = 120) -> dict:
    """Per-frame 1/T against interpolated truth. Cycle is left out on purpose:
    the odometer runs with cycle = 1 m so the returned value is literally 1/T,
    and any cycle then just scales it. One signal pass therefore serves both
    the cycle-solving and the accuracy modes."""
    gt_t = np.array([g[0] for g in gt])
    gt_v = np.array([g[1] for g in gt])
    inv_t, _, _ = dash_cycle_speeds(frames, points, 1.0, fps, window_s, sig=sig, band_px=band_px)
    t = np.arange(len(frames)) / fps
    v_truth = np.interp(t, gt_t, gt_v)
    in_domain = v_truth >= min_speed_kmh
    usable = np.isfinite(inv_t) & in_domain
    return {"inv_t": inv_t, "v_truth": v_truth, "usable": usable, "in_domain": in_domain,
            "coverage": float(usable.sum() / max(1, in_domain.sum())),
            "truth_median_kmh": float(np.median(gt_v))}


def report_cycle(implied: np.ndarray, label: str = "") -> dict:
    print(f"\n=== 反推週期(不套規範值){label} ===")
    for q in (10, 25, 50, 75, 90):
        print(f"  implied cycle p{q:<2d}: {np.percentile(implied, q):6.2f} m")
    iqr = float(np.percentile(implied, 75) - np.percentile(implied, 25))
    print(f"  中位 {np.median(implied):.2f} m,四分位距 {iqr:.2f} m  (n={implied.size})")
    print("  解讀:分布若集中在某個值附近,那就是這條路的實際週期;"
          "散開代表訊號不乾淨或取樣點沒落在虛線上。")
    return {"implied_cycle_m": {f"p{q}": float(np.percentile(implied, q)) for q in (10, 25, 50, 75, 90)},
            "implied_cycle_iqr": iqr, "implied_n": int(implied.size)}


def report_accuracy(d: np.ndarray, cycle_m: float, label: str = "") -> dict:
    mae = float(np.mean(np.abs(d)))
    rng = np.random.default_rng(0)
    boot = [np.mean(np.abs(rng.choice(d, size=d.size))) for _ in range(2000)]
    lo, hi = np.percentile(boot, [2.5, 97.5])
    print(f"\n=== 準確度(cycle = {cycle_m} m){label} ===")
    print(f"  MAE      {mae:.2f} km/h   95% CI [{lo:.2f}, {hi:.2f}]")
    print(f"  bias     {np.mean(d):+.2f} km/h")
    print(f"  |誤差| 分位數  p50 {np.percentile(np.abs(d),50):.2f}  p90 {np.percentile(np.abs(d),90):.2f}  "
          f"p95 {np.percentile(np.abs(d),95):.2f}  max {np.max(np.abs(d)):.2f}")
    print(f"  ±3 km/h 內   {np.mean(np.abs(d)<=3)*100:.1f}%")
    return {"dash_cycle_m": cycle_m, "mae_kmh": mae, "mae_ci95": [float(lo), float(hi)],
            "bias_kmh": float(np.mean(d)),
            "abs_err_percentiles": {f"p{q}": float(np.percentile(np.abs(d), q)) for q in (50, 90, 95)},
            "within_3kmh_pct": float(np.mean(np.abs(d) <= 3) * 100), "n_compared": int(d.size)}


def resolve_points(args, frames: list[Path]) -> tuple[list[tuple[int, int]], dict, dict | None]:
    if args.auto_points:
        return pick_points(frames, args.fps, road_top=args.road_top, road_bottom=args.road_bottom,
                           window_s=args.window_s, sample_band_px=args.sample_band_px,
                           with_signals=True)
    pts = [tuple(int(v) for v in c.split(",")) for c in args.odometer_points.split(";") if c.strip()]
    return pts, {"source": "manual"}, None


def batch(args) -> None:
    root = Path(args.batch_root)
    clips = sorted(p for p in root.iterdir()
                   if p.is_dir() and (p / args.gt_file).exists() and (p / "frames").is_dir())
    if args.limit:
        clips = clips[: args.limit]
    print(f"batch: {len(clips)} clips under {root}  (truth {args.gt_file}:{args.gt_column}"
          + (f", alt {args.alt_column}" if args.alt_column else "") + ")")

    reuse = {}
    if args.points_json:
        prev = json.loads(Path(args.points_json).read_text())
        reuse = {c["clip"]: [tuple(p) for p in c["points"]] for c in prev.get("per_clip", []) if c.get("points")}
        print(f"  reusing points for {len(reuse)} clips from {args.points_json}")
    dump = Path(args.dump_dir) if args.dump_dir else None
    if dump:
        dump.mkdir(parents=True, exist_ok=True)

    per_clip, pooled_d, pooled_implied, pooled_truth = [], [], [], []
    pooled_d_alt, pooled_implied_alt = [], []
    n_in_domain = n_usable = 0
    for cp in clips:
        frames = frames_in(cp / "frames")
        gt = read_gt_csv(cp / args.gt_file, args.gt_column)
        if not frames or not gt:
            print(f"  {cp.name}: no frames or truth, skipped")
            continue
        if cp.name in reuse:
            pts, diag, sig = reuse[cp.name], {"source": "reused"}, None
        else:
            pts, diag, sig = resolve_points(args, frames)
        if len(pts) < 2:
            print(f"  {cp.name}: point picker found {len(pts)} usable point(s), skipped "
                  f"({diag.get('reason', 'no consensus')})")
            per_clip.append({"clip": cp.name, "skipped": True, "picker": diag})
            continue
        r = run_clip(frames, args.fps, pts, gt, args.window_s, args.min_speed_kmh, sig=sig,
                     band_px=args.sample_band_px)
        u = r["usable"]
        n_in_domain += int(r["in_domain"].sum())
        n_usable += int(u.sum())
        row = {"clip": cp.name, "points": [list(p) for p in pts], "coverage": r["coverage"],
               "truth_median_kmh": r["truth_median_kmh"], "n_frames": len(frames),
               "picker_group_spread": diag.get("group_inv_t_spread")}
        pooled_truth.append(r["v_truth"][r["in_domain"]])
        if u.sum():
            implied = (r["v_truth"][u] / 3.6) / r["inv_t"][u]
            pooled_implied.append(implied)
            row["implied_cycle_median_m"] = float(np.median(implied))
            if args.dash_cycle_m:
                d = r["inv_t"][u] * args.dash_cycle_m * 3.6 - r["v_truth"][u]
                pooled_d.append(d)
                row.update({"mae_kmh": float(np.mean(np.abs(d))), "bias_kmh": float(np.mean(d))})
        v_alt = None
        if args.alt_column:
            alt = read_gt_csv(cp / args.gt_file, args.alt_column)
            v_alt = np.interp(np.arange(len(frames)) / args.fps,
                              [a[0] for a in alt], [a[1] for a in alt])
            row["alt_truth_median_kmh"] = float(np.median(v_alt))
            if u.sum():
                pooled_implied_alt.append((v_alt[u] / 3.6) / r["inv_t"][u])
                if args.dash_cycle_m:
                    pooled_d_alt.append(r["inv_t"][u] * args.dash_cycle_m * 3.6 - v_alt[u])
        if dump:
            np.savez_compressed(dump / f"{cp.name}.npz", inv_t=r["inv_t"], v_truth=r["v_truth"],
                                v_alt=v_alt if v_alt is not None else np.zeros(0),
                                usable=r["usable"], points=np.asarray(pts))
        per_clip.append(row)
        msg = (f"  {cp.name}: cov {r['coverage']*100:5.1f}%  truth median {r['truth_median_kmh']:5.1f}"
               f"  implied cycle {row.get('implied_cycle_median_m', float('nan')):5.2f} m")
        if "mae_kmh" in row:
            msg += f"  MAE {row['mae_kmh']:5.2f}  bias {row['bias_kmh']:+.2f}"
        print(msg)

    out: dict = {"mode": "batch", "root": str(root), "fps": args.fps, "n_clips": len(clips),
                 "coverage_in_domain": float(n_usable / max(1, n_in_domain)),
                 "per_clip": per_clip}
    if pooled_truth:
        allt = np.concatenate(pooled_truth)
        print(f"\n資料集速度分布(in-domain 幀):中位 {np.median(allt):.1f} km/h  "
              f"p10 {np.percentile(allt,10):.1f}  p90 {np.percentile(allt,90):.1f}  n={allt.size}")
        out["truth_speed_kmh"] = {"median": float(np.median(allt)), "p10": float(np.percentile(allt, 10)),
                                  "p90": float(np.percentile(allt, 90)), "n": int(allt.size)}
    print(f"pooled coverage {out['coverage_in_domain']*100:.1f}%  ({n_usable}/{n_in_domain} in-domain frames)")
    if pooled_implied and (args.solve_cycle or args.dash_cycle_m is None):
        out.update(report_cycle(np.concatenate(pooled_implied), f" — 全批次匯總(truth={args.gt_column})"))
        if pooled_implied_alt:
            out["alt"] = report_cycle(np.concatenate(pooled_implied_alt),
                                      f" — 全批次匯總(truth={args.alt_column})")
    if pooled_d:
        out.update(report_accuracy(np.concatenate(pooled_d), args.dash_cycle_m,
                                   f" — 全批次匯總(truth={args.gt_column})"))
        maes = [c["mae_kmh"] for c in per_clip if "mae_kmh" in c]
        print(f"  逐片段 MAE 中位 {np.median(maes):.2f}(最好 {min(maes):.2f} / 最差 {max(maes):.2f},n={len(maes)})")
        out["per_clip_mae_median"] = float(np.median(maes))
        if pooled_d_alt:
            out.setdefault("alt", {}).update(
                report_accuracy(np.concatenate(pooled_d_alt), args.dash_cycle_m,
                                f" — 全批次匯總(truth={args.alt_column})"))
    if args.out_json:
        Path(args.out_json).write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
        print("wrote", args.out_json)


def single(args) -> None:
    frames = frames_in(Path(args.frames_dir))
    if not frames:
        raise SystemExit(f"no frames in {args.frames_dir}")
    if args.kitti_oxts:
        gt = kitti_gt(Path(args.kitti_oxts))
    elif args.gt_csv:
        gt = read_gt_csv(Path(args.gt_csv))
    else:
        raise SystemExit("need --gt-csv or --kitti-oxts")
    gt_v = np.array([g[1] for g in gt])
    print(f"frames {len(frames)}  truth points {len(gt)}  "
          f"truth speed median {np.median(gt_v):.1f} km/h  range {gt_v.min():.1f}-{gt_v.max():.1f}")

    points, diag, auto_sig = resolve_points(args, frames)
    if args.auto_points:
        print("auto points: " + ";".join(f"{x},{y}" for x, y in points) +
              f"  (consensus group {diag.get('n_group')} of {diag.get('n_locked')} locked, "
              f"spread {diag.get('group_inv_t_spread')})")
    if len(points) < 2:
        raise SystemExit(f"need >=2 sampling points, got {len(points)}")

    cache = Path(args.cache) if args.cache else None
    if auto_sig:
        sig = auto_sig  # the picker already walked every frame for these points
    elif cache and cache.exists():
        import pickle
        sig = pickle.loads(cache.read_bytes())
    else:
        sig = extract_odometer_signals(frames, points, args.sample_band_px)
        if cache:
            import pickle
            cache.write_bytes(pickle.dumps(sig))

    r = run_clip(frames, args.fps, points, gt, args.window_s, args.min_speed_kmh, sig=sig,
                 band_px=args.sample_band_px)
    u = r["usable"]
    print(f"odometer locked on {int(u.sum())} of {int(r['in_domain'].sum())} "
          f"in-domain frames (coverage {r['coverage']*100:.0f}%)")

    out: dict = {"frames": len(frames), "fps": args.fps, "coverage_in_domain": r["coverage"],
                 "truth_median_kmh": r["truth_median_kmh"],
                 "points": [list(p) for p in points], "picker": diag if args.auto_points else "manual"}

    if args.solve_cycle or args.dash_cycle_m is None:
        out.update(report_cycle((r["v_truth"][u] / 3.6) / r["inv_t"][u]))
        if args.dash_cycle_m is None:
            if args.out_json:
                Path(args.out_json).write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
            return

    out.update(report_accuracy(r["inv_t"][u] * args.dash_cycle_m * 3.6 - r["v_truth"][u], args.dash_cycle_m))
    if args.out_json:
        Path(args.out_json).write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
        print("wrote", args.out_json)


def main() -> None:
    args = parse_args()
    if args.batch_root:
        if not args.auto_points:
            raise SystemExit("--batch-root implies --auto-points (hand-aiming every clip is the thing it removes)")
        batch(args)
    elif args.frames_dir:
        if not (args.auto_points or args.odometer_points):
            raise SystemExit("need --odometer-points or --auto-points")
        single(args)
    else:
        raise SystemExit("need --frames-dir or --batch-root")


if __name__ == "__main__":
    main()
