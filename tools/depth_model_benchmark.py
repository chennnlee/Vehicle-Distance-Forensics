#!/usr/bin/env python3
"""Stage-1 error-quantification benchmark for monocular metric depth models.

What this answers (the proposal's 階段一): given the *same* frames, the *same*
target pixels and the *same* external ground truth, how far off is each depth
model -- and does the error come from the scale or from the geometry?

Three subcommands:

  smoke   Run every backend on one image.  Prints load time, inference time, peak
          VRAM, predicted focal length and depth range.  Use this to check the
          install before spending hours on a dataset.

  run     Run one backend over a directory of frames, sampling depth at the target
          pixels listed in a targets CSV.  Writes one row per (frame, target).

  eval    Join those rows against a ground-truth CSV and report the error table.

Why the error table has two halves
----------------------------------
`raw` uses the model's own metres.  `scaled` first multiplies every prediction by
one global constant chosen to minimise error against the ground truth, which is
the standard median-scaling protocol in the depth literature.

Reporting both separates two failure modes that are usually reported as one:

  raw bad  + scaled good  -> the geometry is fine, only the absolute scale is wrong.
                             That is exactly what a legal-marking scale anchor fixes.
  raw bad  + scaled bad   -> the model's relative geometry is wrong too, and no
                             amount of anchoring will rescue it.

Affine-invariant backends (Depth Anything V2) have no metres at all, so they are
only ever reported in the `scaled` column, fitted as disparity = a/depth + b.

Example
-------
    P=~/venvs/depthbench/bin/python
    $P tools/depth_model_benchmark.py smoke --image data/input/sample.jpg
    $P tools/depth_model_benchmark.py run --model depth_pro \\
         --frames /tmp/seg21_frames --targets seg21_targets.csv \\
         --out data/output/depth_benchmark/seg21_depth_pro.csv
    $P tools/depth_model_benchmark.py eval \\
         --pred data/output/depth_benchmark/seg21_*.csv \\
         --gt data/output/comma2k19_radar_eval/seg21_pairs.csv \\
         --gt-frame-col frame_idx --gt-dist-col radar_dist_m
"""

from __future__ import annotations

import argparse
import csv
import glob
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import depth_backends as DB  # noqa: E402


# --------------------------------------------------------------------------- utils

def _imread(p):
    import cv2
    im = cv2.imread(str(p))
    if im is None:
        raise IOError(f"cannot read image: {p}")
    return im


def _peak_vram_mb():
    try:
        import torch
        if torch.cuda.is_available():
            return torch.cuda.max_memory_allocated() / 1024 ** 2
    except Exception:
        pass
    return float("nan")


def _reset_vram():
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.reset_peak_memory_stats()
    except Exception:
        pass


def sample_depth(depth: np.ndarray, px: float, py: float, patch: int = 5) -> float:
    """Median of a small patch around (px, py).

    A single pixel on a vehicle's lower edge sits on a strong depth discontinuity,
    so one bad pixel can move the reading by metres.  The median over a patch is
    stable without smearing across the boundary the way a mean would.
    """
    h, w = depth.shape
    x, y = int(round(px)), int(round(py))
    r = patch // 2
    x0, x1 = max(0, x - r), min(w, x + r + 1)
    y0, y1 = max(0, y - r), min(h, y + r + 1)
    if x0 >= x1 or y0 >= y1:
        return float("nan")
    win = depth[y0:y1, x0:x1].astype(np.float64)
    win = win[np.isfinite(win) & (win > 0)]
    return float(np.median(win)) if win.size else float("nan")


# --------------------------------------------------------------------------- smoke

def cmd_smoke(args):
    bgr = _imread(args.image)
    h, w = bgr.shape[:2]
    print(f"image: {args.image}  ({w}x{h})")
    print(f"device: {args.device}")
    print()
    names = args.models or DB.available()
    rows = []
    for name in names:
        print(f"--- {name}")
        try:
            be = DB.get_backend(name)
        except KeyError as e:
            print(f"    ✗ {e}")
            continue
        try:
            _reset_vram()
            t0 = time.time()
            be.load(device=args.device)
            t_load = time.time() - t0

            t0 = time.time()
            out = be.infer_full(bgr)
            t_inf = time.time() - t0

            d = out["depth_m"] if out["depth_m"] is not None else out["relative"]
            unit = "m" if out["depth_m"] is not None else "(relative, no unit)"
            fin = d[np.isfinite(d)]
            K = out["intrinsics"]
            fx = f"{K[0, 0]:.1f}" if K is not None else "-"
            fx_ratio = f"{K[0, 0] / w:.4f}" if K is not None else "-"
            vram = _peak_vram_mb()
            print(f"    ✓ load {t_load:6.1f}s | infer {t_inf:6.2f}s | VRAM {vram:7.0f} MB")
            print(f"      range {fin.min():.2f} .. {fin.max():.2f} {unit}   median {np.median(fin):.2f}")
            print(f"      predicted fx {fx} px  (fx/width = {fx_ratio}; SHARP assumes 0.7955)")
            rows.append(dict(model=name, kind=be.kind, ok=True, load_s=round(t_load, 1),
                             infer_s=round(t_inf, 3), vram_mb=round(vram),
                             fx_px=None if K is None else round(float(K[0, 0]), 1),
                             fx_over_width=None if K is None else round(float(K[0, 0]) / w, 4),
                             depth_median=round(float(np.median(fin)), 3)))
        except Exception as e:
            print(f"    ✗ {type(e).__name__}: {e}")
            rows.append(dict(model=name, kind=getattr(be, "kind", "?"), ok=False, error=f"{type(e).__name__}: {e}"))
        finally:
            try:
                be.unload()
            except Exception:
                pass
        print()
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"wrote {args.out}")
    ok = sum(1 for r in rows if r.get("ok"))
    print(f"== {ok}/{len(rows)} backends ran ==")
    return 0 if ok else 1


# ----------------------------------------------------------------------------- run

def cmd_run(args):
    targets = []
    with open(args.targets, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            targets.append(r)
    if not targets:
        print("targets CSV is empty", file=sys.stderr)
        return 1

    fcol, xcol, ycol = args.frame_col, args.px_col, args.py_col
    by_frame: dict[str, list[dict]] = {}
    for r in targets:
        by_frame.setdefault(str(r[fcol]), []).append(r)

    frames_dir = Path(args.frames)
    pattern = args.frame_glob
    print(f"backend : {args.model}")
    print(f"frames  : {frames_dir}  (pattern {pattern})")
    print(f"targets : {len(targets)} rows over {len(by_frame)} frames")

    be = DB.get_backend(args.model)
    be.load(device=args.device)
    print(f"loaded {args.model} ({be.kind}) -- {be.paper}")

    out_rows = []
    t_start = time.time()
    for i, (fid, rows) in enumerate(sorted(by_frame.items(), key=lambda kv: kv[0]), 1):
        matches = sorted(frames_dir.glob(pattern.replace("{frame}", str(fid))))
        if not matches:
            print(f"  ! no frame file for {fid}")
            continue
        bgr = _imread(matches[0])
        out = be.infer_full(bgr, fx=args.fx)
        d = out["depth_m"] if out["depth_m"] is not None else out["relative"]
        K = out["intrinsics"]
        for r in rows:
            v = sample_depth(d, float(r[xcol]), float(r[ycol]), args.patch)
            rec = dict(r)
            rec["model"] = args.model
            rec["kind"] = be.kind
            rec["pred"] = v                       # metres for metric, disparity for relative
            rec["fx_px"] = None if K is None else round(float(K[0, 0]), 2)
            out_rows.append(rec)
        if i % 20 == 0 or i == len(by_frame):
            el = time.time() - t_start
            print(f"  {i}/{len(by_frame)} frames  ({el:.0f}s, {el/i:.2f}s/frame)")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        w.writerows(out_rows)
    print(f"wrote {args.out}  ({len(out_rows)} rows)")
    return 0


# ---------------------------------------------------------------------------- eval

def _metrics(pred: np.ndarray, gt: np.ndarray) -> dict:
    """Standard monocular-depth metrics plus the two this project reports."""
    ok = np.isfinite(pred) & np.isfinite(gt) & (pred > 0) & (gt > 0)
    p, g = pred[ok], gt[ok]
    if p.size == 0:
        return dict(n=0)
    ratio = np.maximum(p / g, g / p)
    return dict(
        n=int(p.size),
        abs_rel=float(np.mean(np.abs(p - g) / g)),           # 文獻標準
        rmse=float(np.sqrt(np.mean((p - g) ** 2))),
        delta1=float(np.mean(ratio < 1.25)),
        mae_m=float(np.mean(np.abs(p - g))),
        med_err_pct=float(np.median(np.abs(p - g) / g) * 100),  # 本專案報法
        bias_m=float(np.mean(p - g)),
    )


def cmd_eval(args):
    gt = {}
    with open(args.gt, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                gt[str(r[args.gt_frame_col])] = float(r[args.gt_dist_col])
            except (KeyError, ValueError):
                continue
    if not gt:
        print(f"no usable ground truth in {args.gt} "
              f"(cols {args.gt_frame_col}/{args.gt_dist_col})", file=sys.stderr)
        return 1
    print(f"ground truth: {len(gt)} frames from {Path(args.gt).name}")
    print()

    files = []
    for pat in args.pred:
        files.extend(sorted(glob.glob(pat)))
    if not files:
        print("no prediction files matched", file=sys.stderr)
        return 1

    hdr = (f"{'model':<20} {'kind':<9} {'protocol':<8} {'n':>6} "
           f"{'AbsRel':>8} {'RMSE':>8} {'δ1':>7} {'MAE(m)':>8} {'中位誤差%':>10} {'bias(m)':>9}")
    print(hdr)
    print("-" * len(hdr))

    for fp in files:
        rows = list(csv.DictReader(open(fp, newline="", encoding="utf-8")))
        if not rows:
            continue
        model = rows[0].get("model", Path(fp).stem)
        kind = rows[0].get("kind", "metric")
        pred, truth = [], []
        for r in rows:
            k = str(r[args.frame_col])
            if k not in gt:
                continue
            try:
                v = float(r["pred"])
            except (TypeError, ValueError):
                continue
            pred.append(v)
            truth.append(gt[k])
        pred, truth = np.asarray(pred, float), np.asarray(truth, float)
        if pred.size == 0:
            print(f"{model:<20} {kind:<9} {'-':<8} {0:>6}   (no overlap with ground truth)")
            continue

        if kind == "metric":
            m = _metrics(pred, truth)
            print(f"{model:<20} {kind:<9} {'raw':<8} {m['n']:>6} {m['abs_rel']:>8.4f} "
                  f"{m['rmse']:>8.3f} {m['delta1']:>7.3f} {m['mae_m']:>8.3f} "
                  f"{m['med_err_pct']:>10.2f} {m['bias_m']:>9.3f}")
            k = float(np.median(truth / pred))          # one global constant
            m = _metrics(pred * k, truth)
            print(f"{'':<20} {'':<9} {'scaled':<8} {m['n']:>6} {m['abs_rel']:>8.4f} "
                  f"{m['rmse']:>8.3f} {m['delta1']:>7.3f} {m['mae_m']:>8.3f} "
                  f"{m['med_err_pct']:>10.2f} {m['bias_m']:>9.3f}   (k={k:.4f})")
        else:
            # affine-invariant disparity: fit depth = 1/(a*disp + b) by least squares on 1/gt
            A = np.stack([pred, np.ones_like(pred)], 1)
            coef, *_ = np.linalg.lstsq(A, 1.0 / truth, rcond=None)
            conv = A @ coef
            with np.errstate(divide="ignore", invalid="ignore"):
                depth = np.where(conv > 0, 1.0 / conv, np.nan)
            m = _metrics(depth, truth)
            print(f"{model:<20} {kind:<9} {'scaled':<8} {m['n']:>6} {m['abs_rel']:>8.4f} "
                  f"{m['rmse']:>8.3f} {m['delta1']:>7.3f} {m['mae_m']:>8.3f} "
                  f"{m['med_err_pct']:>10.2f} {m['bias_m']:>9.3f}   "
                  f"(a={coef[0]:.5f}, b={coef[1]:.5f})")
            print(f"{'':<20} {'':<9} {'raw':<8} {'-':>6}   "
                  f"(affine-invariant 視差,無絕對尺度,只能報 scaled)")
    print()
    print("AbsRel/RMSE/δ1 = 深度文獻標準指標;中位誤差% = 本專案報法(可與雷達近場 7.0% 直接比)")
    return 0


# ---------------------------------------------------------------------------- main

# ------------------------------------------------------------------ blind protocol

def _read_pred(fp):
    rows = list(csv.DictReader(open(fp, newline="", encoding="utf-8")))
    return rows


def _cols(rows, dist_col):
    """(prediction, truth) arrays for the rows that carry both."""
    p, d = [], []
    for r in rows:
        try:
            v, t = float(r["pred"]), float(r[dist_col])
        except (KeyError, TypeError, ValueError):
            continue
        if np.isfinite(v) and np.isfinite(t) and t > 0:
            p.append(v)
            d.append(t)
    return np.asarray(p, float), np.asarray(d, float)


def _fit(pred, truth, kind):
    """Calibrate a backend against a set of known distances.

    Metric backends get one global constant, which is the median-scaling protocol
    of the depth literature.  Affine-invariant ones get the two-parameter inverse
    fit their output requires.  Returns (apply, label).
    """
    if kind == "metric":
        k = float(np.median(truth / pred))
        return (lambda x: x * k), f"k={k:.4f}"
    A = np.stack([pred, np.ones_like(pred)], 1)
    coef, *_ = np.linalg.lstsq(A, 1.0 / truth, rcond=None)

    def apply(x):
        conv = coef[0] * x + coef[1]
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.where(conv > 0, 1.0 / conv, np.nan)

    return apply, f"a={coef[0]:.5f} b={coef[1]:.5f}"


def _by_model(patterns):
    out = {}
    for pat in patterns:
        for fp in sorted(glob.glob(pat)):
            rows = _read_pred(fp)
            if rows:
                out.setdefault(rows[0].get("model", Path(fp).stem), []).extend(rows)
    return out


def cmd_blind(args):
    """Score predictions whose scale constant never saw the ground truth.

    `eval` takes its one global constant from the truth itself, so its `scaled`
    column answers "is the relative geometry right?" and nothing about whether the
    model could be deployed.  Here the constant comes from road points whose
    distance was solved from the lane markings (Method C), so the whole chain --
    frames in, metres out -- is free of the radar it is then scored against.

    Both constants are printed side by side: the difference between them is
    exactly what the blind protocol costs.
    """
    cal = _by_model(args.calib)
    prd = _by_model(args.pred)
    if not cal or not prd:
        print("blind: no calibration or prediction rows matched", file=sys.stderr)
        return 1

    print(f"calibration: {sum(len(v) for v in cal.values())} rows over {len(cal)} models "
          f"({args.calib_dist_col}, 標線幾何)")
    print(f"scored on  : {sum(len(v) for v in prd.values())} rows ({args.gt_dist_col}, 雷達)"
          f"   Δ={args.delta_m:+.2f} m 安裝偏移   近場 < {args.near_m:.0f} m")
    print()
    hdr = (f"{'model':<24} {'n_cal':>6} {'標線常數':>18} {'n':>5} "
           f"{'近場中位%':>10} {'近場p90%':>9} {'全體中位%':>10} | "
           f"{'雷達常數':>18} {'近場中位%':>10} {'常數差%':>8}")
    print(hdr)
    print("-" * len(hdr))

    for model in sorted(prd):
        if model not in cal:
            print(f"{model:<24}   (no calibration rows)")
            continue
        kind = cal[model][0].get("kind", "metric")
        cp, cd = _cols(cal[model], args.calib_dist_col)
        pp, pg = _cols(prd[model], args.gt_dist_col)
        if cp.size == 0 or pp.size == 0:
            print(f"{model:<24}   (no usable rows)")
            continue
        gt = pg + args.delta_m                  # radar sits at the bumper, camera behind it
        near = gt < args.near_m

        blind, blabel = _fit(cp, cd, kind)
        oracle, olabel = _fit(pp, gt, kind)
        mb, mba, mo = (_metrics(f(pp)[m], gt[m])
                       for f, m in ((blind, near), (blind, np.ones_like(near, bool)), (oracle, near)))
        err = np.abs(blind(pp)[near] - gt[near]) / gt[near] * 100
        p90 = float(np.percentile(err, 90)) if err.size else float("nan")
        drift = ""
        if kind == "metric":
            kb, ko = float(np.median(cd / cp)), float(np.median(gt / pp))
            drift = f"{(kb / ko - 1) * 100:+7.1f}%"
        print(f"{model:<24} {cp.size:>6} {blabel:>18} {mb.get('n', 0):>5} "
              f"{mb.get('med_err_pct', float('nan')):>10.2f} {p90:>9.2f} "
              f"{mba.get('med_err_pct', float('nan')):>10.2f} | "
              f"{olabel:>18} {mo.get('med_err_pct', float('nan')):>10.2f} {drift:>8}")
    print()
    print("標線常數 = 由車道標線幾何(方法 C)定出,全程未用雷達;雷達常數 = 由真值反推的上限參考")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("smoke", help="run every backend on one image")
    s.add_argument("--image", default="data/input/sample.jpg")
    s.add_argument("--models", nargs="*", help="default: all registered")
    s.add_argument("--device", default="cuda")
    s.add_argument("--out", help="write a JSON summary here")
    s.set_defaults(func=cmd_smoke)

    s = sub.add_parser("run", help="run one backend over frames at target pixels")
    s.add_argument("--model", required=True, choices=DB.available())
    s.add_argument("--frames", required=True)
    s.add_argument("--frame-glob", default="*{frame}*",
                   help="{frame} is replaced by the frame id from the targets CSV")
    s.add_argument("--targets", required=True, help="CSV with frame id and target pixel")
    s.add_argument("--frame-col", default="frame_idx")
    s.add_argument("--px-col", default="px")
    s.add_argument("--py-col", default="py")
    s.add_argument("--patch", type=int, default=5)
    s.add_argument("--fx", type=float, default=None,
                   help="focal length in px handed to the backends that consume intrinsics "
                        "(metric3d_v2, da3_metric); default is SHARP's fixed-FOV assumption "
                        "0.7955*width, so this flag measures what that assumption costs")
    s.add_argument("--device", default="cuda")
    s.add_argument("--out", required=True)
    s.set_defaults(func=cmd_run)

    s = sub.add_parser("eval", help="score predictions against ground truth")
    s.add_argument("--pred", nargs="+", required=True, help="CSV(s) from `run`; globs allowed")
    s.add_argument("--gt", required=True)
    s.add_argument("--frame-col", default="frame_idx")
    s.add_argument("--gt-frame-col", default="frame_idx")
    s.add_argument("--gt-dist-col", required=True)
    s.set_defaults(func=cmd_eval)

    s = sub.add_parser("blind", help="score with a scale constant taken from the road markings")
    s.add_argument("--calib", nargs="+", required=True,
                   help="CSV(s) from `run` on marking-derived road anchors; globs allowed")
    s.add_argument("--calib-dist-col", default="marking_d_m")
    s.add_argument("--pred", nargs="+", required=True, help="CSV(s) from `run` on the targets")
    s.add_argument("--gt-dist-col", default="radar_range_m")
    s.add_argument("--delta-m", type=float, default=0.0,
                   help="added to the truth to bring it into the camera frame (radar is at "
                        "the bumper); 2.0 for this car, see docs/DEPTH_MODEL_BENCHMARK.md")
    s.add_argument("--near-m", type=float, default=32.0)
    s.set_defaults(func=cmd_blind)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
