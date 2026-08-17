"""Pick the dash-cycle odometer's sampling points automatically.

Every odometer case in this project so far was hand-aimed: draw the accumulated
ridge map, look at it, type four pixel coordinates. That is fine for fifteen
clips and impossible for a public dataset, where the professor's question is the
average error over the *whole* set. This module does the aiming from the footage
itself.

Three stages, and each one exists because of a specific way hand-picking failed:

  1. Ridge     Accumulate local contrast over the clip so intermittent dashes
               smear into a continuous ridge (tools/lane_ridge_probe.py), then
               take per-row peaks. Single frames cannot be used: the paint is
               only present where a dash happens to be.

  2. Lock      Score every candidate by running the real odometer on it alone.
               A point on a continuous longitudinal bright streak -- tyre polish
               or a repair seam -- is a perfect ridge with no period, and it is
               exactly what sank hs003s (31% coverage, MAE 25). It scores zero
               here because the prominence gate rejects it, so the trap is
               detected rather than warned about.

  3. Consensus Keep the largest group of candidates that agree on 1/T within a
               tolerance. Solid edge lines, adjacent-lane paint and ramp dashes
               all lock onto *something*; only the ego lane's statutory dashes
               agree with each other across depth. This is the automatic form of
               the split-lock gate the odometer already applies per frame.

The output is the `--odometer-points` string the pipeline takes, so a picked set
can be pasted into a hand-run or fed straight to the evaluator.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "tools"))

from dashcam_range_speed import dash_cycle_speeds, extract_odometer_signals


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--frames-dir", required=True)
    ap.add_argument("--fps", type=float, required=True)
    ap.add_argument("--road-top", type=float, default=0.62,
                    help="Top of the sampling band, as a fraction of image height (below the horizon).")
    ap.add_argument("--road-bottom", type=float, default=0.90,
                    help="Bottom of the band, as a fraction of image height (above the bonnet).")
    ap.add_argument("--rows", default="", help="Explicit rows instead of the band, e.g. '700,760,820'.")
    ap.add_argument("--n-rows", type=int, default=5)
    ap.add_argument("--peaks-per-row", type=int, default=4)
    ap.add_argument("--band-px", type=int, default=60, help="Non-max suppression half-width between peaks.")
    ap.add_argument("--sample-band-px", type=int, default=120,
                    help="Odometer lateral search half-width; must stay inside one lane at the sampling row.")
    ap.add_argument("--ridge-step", type=int, default=4, help="Frame stride when accumulating the ridge.")
    ap.add_argument("--window-s", type=float, default=3.0)
    ap.add_argument("--max-points", type=int, default=4)
    ap.add_argument("--agree-tol", type=float, default=0.12,
                    help="Relative 1/T tolerance for two candidates to count as agreeing.")
    ap.add_argument("--min-coverage", type=float, default=0.15,
                    help="Reject a candidate locking on fewer than this fraction of frames.")
    ap.add_argument("--out-ridge", default="", help="Optional ridge PNG with the chosen points drawn.")
    ap.add_argument("--verbose", action="store_true")
    return ap.parse_args()


def ridge_map(frames: list[Path], step: int) -> np.ndarray:
    acc = None
    for f in frames[::step]:
        g = cv2.cvtColor(cv2.imread(str(f)), cv2.COLOR_BGR2GRAY).astype(np.float32)
        diff = cv2.subtract(g, cv2.GaussianBlur(g, (51, 51), 0))
        acc = diff if acc is None else acc + diff
    return acc / max(1, len(frames[::step]))


def row_peaks(acc: np.ndarray, y: int, k: int, band_px: int) -> list[int]:
    prof = np.clip(acc[y], 0, None)
    work, out = prof.copy(), []
    for _ in range(k):
        x = int(np.argmax(work))
        if work[x] <= 0:
            break
        out.append(x)
        work[max(0, x - band_px): x + band_px + 1] = 0
    return sorted(out)


def pick_points(frames: list[Path], fps: float, *, road_top: float = 0.62, road_bottom: float = 0.90,
                rows: list[int] | None = None, n_rows: int = 5, peaks_per_row: int = 4,
                band_px: int = 60, ridge_step: int = 4, window_s: float = 3.0,
                max_points: int = 4, agree_tol: float = 0.12, min_coverage: float = 0.15,
                sample_band_px: int = 120, verbose: bool = False, with_signals: bool = False):
    """Return (points, diagnostics), or (points, diagnostics, signals) when
    `with_signals` -- scoring the candidates already walked every frame, so a
    caller that is about to run the odometer on the winners should reuse that
    pass rather than pay for it twice. Points are ordered far row first."""
    h, w = cv2.imread(str(frames[0])).shape[:2]
    acc = ridge_map(frames, ridge_step)
    if rows is None:
        y0, y1 = int(road_top * h), int(road_bottom * h)
        rows = [int(round(v)) for v in np.linspace(y0, y1, n_rows)]

    cands = [(x, y) for y in rows for x in row_peaks(acc, y, peaks_per_row, band_px)]
    if not cands:
        return ([], {"reason": "no ridge peaks"}, {}) if with_signals else ([], {"reason": "no ridge peaks"})
    sig = extract_odometer_signals(frames, cands, sample_band_px)

    scored = []
    for pt in cands:
        # Cycle 1 m makes the returned "speed" literally 1/T, so candidates at
        # different depths are directly comparable without any calibration.
        inv_t, conf, prom = dash_cycle_speeds(frames, [pt], 1.0, fps, window_s, sig={pt: sig[pt]},
                                              band_px=sample_band_px)
        ok = np.isfinite(inv_t)
        cov = float(ok.mean())
        if cov < min_coverage:
            continue
        scored.append({"pt": pt, "coverage": cov, "inv_t": float(np.median(inv_t[ok])),
                       "prom": float(np.median(prom[ok])), "conf": float(np.median(conf[ok]))})
    if verbose:
        for s in sorted(scored, key=lambda s: -s["coverage"]):
            print(f"    cand {s['pt']}  cov {s['coverage']:.2f}  1/T {s['inv_t']:.3f}  prom {s['prom']:.2f}")
    if not scored:
        miss = {"reason": "no candidate locked", "n_candidates": len(cands)}
        return ([], miss, sig) if with_signals else ([], miss)

    # Consensus: the biggest group agreeing on 1/T. Weight membership by
    # coverage so a long-locking point anchors the group rather than a lucky
    # short one; ties break on total coverage.
    best_group: list[dict] = []
    for anchor in scored:
        grp = [s for s in scored if abs(s["inv_t"] - anchor["inv_t"]) <= agree_tol * anchor["inv_t"]]
        key = (sum(g["coverage"] for g in grp), len(grp))
        if key > (sum(g["coverage"] for g in best_group), len(best_group)):
            best_group = grp

    # Spread the picks across rows: the odometer's anti-vibration phase gate
    # compares distinct rows, so a set collapsed onto one row disables it.
    by_row: dict[int, dict] = {}
    for s in sorted(best_group, key=lambda s: -(s["coverage"] * (0.5 + s["prom"]))):
        by_row.setdefault(s["pt"][1], s)
    chosen = sorted(by_row.values(), key=lambda s: -(s["coverage"] * (0.5 + s["prom"])))[:max_points]
    if len(chosen) < 2:
        chosen = sorted(best_group, key=lambda s: -s["coverage"])[:max_points]
    chosen.sort(key=lambda s: s["pt"][1])

    diag = {"n_candidates": len(cands), "n_locked": len(scored), "n_group": len(best_group),
            "rows": rows, "image_size": [w, h],
            "chosen": [{"pt": list(c["pt"]), "coverage": round(c["coverage"], 3),
                        "inv_t": round(c["inv_t"], 4), "prom": round(c["prom"], 3)} for c in chosen],
            "group_inv_t_spread": (round(max(g["inv_t"] for g in best_group) /
                                         max(1e-9, min(g["inv_t"] for g in best_group)), 3)
                                   if best_group else None)}
    pts = [c["pt"] for c in chosen]
    return (pts, diag, {p: sig[p] for p in pts}) if with_signals else (pts, diag)


def main() -> None:
    args = parse_args()
    frames = sorted(Path(args.frames_dir).glob("*.jpg")) or sorted(Path(args.frames_dir).glob("*.png"))
    if not frames:
        raise SystemExit(f"no frames in {args.frames_dir}")
    rows = [int(v) for v in args.rows.split(",") if v.strip()] or None
    pts, diag = pick_points(frames, args.fps, road_top=args.road_top, road_bottom=args.road_bottom,
                            rows=rows, n_rows=args.n_rows, peaks_per_row=args.peaks_per_row,
                            band_px=args.band_px, ridge_step=args.ridge_step, window_s=args.window_s,
                            max_points=args.max_points, agree_tol=args.agree_tol,
                            min_coverage=args.min_coverage, sample_band_px=args.sample_band_px,
                            verbose=args.verbose)
    print(f"candidates {diag.get('n_candidates')}  locked {diag.get('n_locked')}  "
          f"consensus group {diag.get('n_group')}  spread {diag.get('group_inv_t_spread')}")
    for c in diag.get("chosen", []):
        print(f"  ({c['pt'][0]},{c['pt'][1]})  coverage {c['coverage']:.2f}  1/T {c['inv_t']:.3f}  prom {c['prom']:.2f}")
    print("--odometer-points " + '"' + ";".join(f"{x},{y}" for x, y in pts) + '"')

    if args.out_ridge and pts:
        acc = ridge_map(frames, args.ridge_step)
        vis = cv2.applyColorMap(cv2.normalize(acc, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8),
                                cv2.COLORMAP_JET)
        for x, y in pts:
            cv2.circle(vis, (x, y), 7, (255, 255, 255), 2)
            cv2.line(vis, (x - 120, y), (x + 120, y), (255, 255, 255), 1)
        cv2.imwrite(args.out_ridge, vis)
        print("wrote", args.out_ridge)


if __name__ == "__main__":
    main()
