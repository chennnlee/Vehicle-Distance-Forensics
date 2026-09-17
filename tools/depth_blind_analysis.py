#!/usr/bin/env python3
"""Where a depth model's scale constant comes from, and what each choice costs.

`depth_model_benchmark.py eval` fits one global constant to the ground truth it is
then scored against, which is the median-scaling protocol of the depth literature.
That measures the relative geometry and says nothing about whether the chain could
be deployed, because in the field there is no radar to fit against.

This runs the four checks that answer the deployment question instead.  None of
them uses the radar to calibrate; it is only ever the thing being scored against.

  sources   Same predictions, three different calibration sets: road points, the
            targets' own ground-contact points, and (for reference only) the radar.
            Road and contact distances both come from the lane markings, so the
            first two columns are what a deployed system can actually do.

  samerow   Road pixel and vehicle target pixel on the *same image row*, together
            with what pure geometry says their ratio must be.  The target pixel is
            the median of the mask's lowest 12% of rows, which sits 6-8 px ABOVE the
            mask's lowest point -- on the car body, not on the road -- so at the same
            row the road really is farther away.  (Until 2026-09-17 this check assumed
            both pixels were on the road and read the 5-16% gap as the model
            contradicting itself; the geometry accounts for it.)  Needs
            `--contact-defs`, a CSV with py_band / py_max per target frame.

  holdout   Calibrate on the first half of the frames, score on the second (and the
            reverse), so the constant is never fitted on the rows it scores.

  transfer  Calibrate on one segment, score on another recorded on a different day
            with the same camera -- "calibrate the camera once and reuse it".

  methodc   Method C itself against the radar, under both contact-point definitions
            and both mounting offsets, because its accuracy depends on both and
            neither is pinned independently (docs section 18).

Usage:
  python3 tools/depth_blind_analysis.py --all
  python3 tools/depth_blind_analysis.py sources --near-m 32
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import numpy as np

D = Path("data/output/depth_benchmark")

# Method C geometry per segment: A = h*f from the dash cycle's time lag between image
# rows (tools/vanishing_point_range_calib.py), y_h from the lane-line vanishing point.
# Both solved without a neural network; see docs sections 15 and 18.
# The A values used before 2026-09-17 (1153 / 1139) were an artefact of the old
# single-frame tool's read band, not a measurement -- see docs section 18.
SEGMENTS = {
    "seg10": dict(tag="b0c9d2329ad1606b_2018-07-30--13-44-30_10", A=1238.0, y_h=383.2),
    "seg21": dict(tag="b0c9d2329ad1606b_2018-08-15--09-01-03_21", A=1242.0, y_h=378.7),
}
MODELS = ["metric3d_v2", "unidepth_v2", "da3_metric", "depth_anything_v2_vits", "depth_pro"]
DELTA_M = 2.0          # radar sits on the bumper, the camera is behind it; set by --delta-m.
                       # Not pinned independently -- the results depend on it (section 18).


def _rows(fp: Path) -> list[dict]:
    return list(csv.DictReader(open(fp, newline="", encoding="utf-8")))


def _med(x) -> float:
    return float(np.median(x))


def _err(pred, gt) -> float:
    """Median relative error in %, this project's reporting convention."""
    return _med(np.abs(pred - gt) / gt) * 100


def _fit(pred, truth, kind):
    """One constant for metric backends, the two-parameter inverse fit for disparity."""
    if kind == "metric":
        k = _med(truth / pred)
        return (lambda x: x * k), f"k={k:.3f}", k
    A = np.stack([pred, np.ones_like(pred)], 1)
    c, *_ = np.linalg.lstsq(A, 1.0 / truth, rcond=None)

    def apply(x):
        conv = c[0] * x + c[1]
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.where(conv > 0, 1.0 / conv, np.nan)

    return apply, f"a={c[0]:.4f}", float("nan")


def load(seg: str, model: str, near_m: float):
    """Predictions at the targets, restricted to the geometry-gated pairing set."""
    s = SEGMENTS[seg]
    keep = {(r["frame_idx"], r["px"], r["py"]) for r in _rows(D / f"paired_{s['tag']}.csv")}
    rows = [r for r in _rows(D / f"unf_{s['tag']}__{model}.csv")
            if (r["frame_idx"], r["px"], r["py"]) in keep]
    pred = np.array([float(r["pred"]) for r in rows])
    py = np.array([float(r["py"]) for r in rows])
    gt = np.array([float(r["radar_range_m"]) for r in rows]) + DELTA_M
    mark = s["A"] / (py - s["y_h"])            # Method C distance at the same pixel
    frame = np.array([int(r["frame_idx"].lstrip("f")) for r in rows])
    near = gt < near_m
    return dict(pred=pred, gt=gt, mark=mark, frame=frame, near=near,
                kind=rows[0]["kind"] if rows else "metric")


def cmd_sources(args):
    print("校正常數的三個來源(路面/接地點皆由標線幾何給,全程不用雷達;雷達欄只是上限參考)")
    print(f"評分:近場 < {args.near_m:.0f} m,中位相對誤差 %,真值 = 雷達 + {DELTA_M} m\n")
    for seg, s in SEGMENTS.items():
        print(f"===== {seg}")
        print(f"{'model':<24}{'k路面':>9}{'k接地':>9}{'k雷達':>9} | "
              f"{'@路面':>8}{'@接地':>8}{'@雷達':>8} | {'車身@接地':>10}")
        for m in MODELS:
            d = load(seg, m, args.near_m)
            an = _rows(D / f"anchor_{s['tag']}__{m}.csv")
            ap = np.array([float(r["pred"]) for r in an])
            # Recomputed from the pixel row rather than read from the CSV: the stored
            # marking_d_m column was written with the withdrawn A values.
            ad = s["A"] / (np.array([float(r["py"]) for r in an]) - s["y_h"])
            bd = _rows(D / f"body_pred_{s['tag']}__{m}.csv")
            bp = np.array([float(r["pred"]) for r in bd])
            bg = np.array([float(r["radar_range_m"]) for r in bd]) + DELTA_M
            nb = bg < args.near_m
            n = d["near"]
            f_road, l1, _ = _fit(ap, ad, d["kind"])
            f_mark, l2, _ = _fit(d["pred"][n], d["mark"][n], d["kind"])
            f_rad, l3, _ = _fit(d["pred"][n], d["gt"][n], d["kind"])
            # the deployable split: fit the constant where the geometry works (the
            # contact point) and spend it where it does not (the body centre)
            print(f"{m:<24}{l1:>9}{l2:>9}{l3:>9} | "
                  f"{_err(f_road(d['pred'][n]), d['gt'][n]):>7.2f}%"
                  f"{_err(f_mark(d['pred'][n]), d['gt'][n]):>7.2f}%"
                  f"{_err(f_rad(d['pred'][n]), d['gt'][n]):>7.2f}% | "
                  f"{_err(f_mark(bp[nb]), bg[nb]):>9.2f}%")
        d = load(seg, MODELS[0], args.near_m)
        n = d["near"]
        print(f"{'方法 C 純幾何':<22}{'':>27} | {_err(d['mark'][n], d['gt'][n]):>7.2f}%   n={int(n.sum())}")
        print()


def cmd_samerow(args):
    print("同一影像列上,路面像素 vs 目標車取樣像素的模型讀值比(|Δpy| ≤ 6 px),以及純幾何的預期值")
    print("目標取樣點(遮罩最低 12% 列的中位)在遮罩最低點上方 6–8 px,位於車身上而不是路面上,")
    print("所以同一列的路面本來就比較遠:預期比 = (最低點列 − y_h)/(路面列 − y_h)。實測/預期 ≈ 1 表示模型讀對了\n")
    defs = {}
    if Path(args.contact_defs).exists():
        for r in _rows(Path(args.contact_defs)):
            defs[(r["tag"], r["frame_idx"])] = (float(r["py_band"]), float(r["py_max"]))
    else:
        print(f"  (找不到 {args.contact_defs},只印實測比;產生方式見 tools/contact_point_definitions.py)\n")
    print(f"{'seg':<7}{'model':<24}{'n':>5}{'實測 路面/車輛':>16}{'幾何預期':>10}{'實測/預期':>10}")
    for seg, s in SEGMENTS.items():
        for m in MODELS:
            by_frame: dict[str, list] = {}
            for r in _rows(D / f"anchor_{s['tag']}__{m}.csv"):
                by_frame.setdefault(r["frame_idx"], []).append((float(r["py"]), float(r["pred"])))
            rat, exp = [], []
            for r in _rows(D / f"unf_{s['tag']}__{m}.csv"):
                cand = by_frame.get(r["frame_idx"])
                vpy, vp = float(r["py"]), float(r["pred"])
                if not cand or vp <= 0:
                    continue
                gap, p, q = min((abs(p - vpy), p, q) for p, q in cand)
                if gap <= 6 and q > 0:
                    # disparity rises as depth falls, so the relative backend inverts
                    rat.append(q / vp if r["kind"] == "metric" else vp / q)
                    d = defs.get((s["tag"], r["frame_idx"]))
                    exp.append((d[1] - s["y_h"]) / (p - s["y_h"]) if d else np.nan)
            if len(rat) < 5:
                print(f"{seg:<7}{m:<24}{len(rat):>5}   (配對不足)")
                continue
            a, e = np.asarray(rat), np.asarray(exp)
            ok = np.isfinite(e)
            tail = (f"{np.median(e[ok]):>10.3f}{np.median(a[ok] / e[ok]):>10.3f}" if ok.sum() >= 5 else "")
            print(f"{seg:<7}{m:<24}{len(a):>5}{np.median(a):>16.3f}{tail}")
    print()


def cmd_holdout(args):
    print("留出驗證:前半幀用標線定 k → 後半幀評分(以及反向)。k 從不擬在它要評分的那些列上\n")
    print(f"{'seg':<7}{'model':<24}{'前定後測':>10}{'後定前測':>10}{'同批擬合':>10}{'雷達oracle':>11}")
    for seg in SEGMENTS:
        for m in MODELS:
            d = load(seg, m, args.near_m)
            n, fi = d["near"], d["frame"]
            cut = np.median(fi)
            h1, h2 = n & (fi <= cut), n & (fi > cut)
            if h1.sum() < 8 or h2.sum() < 8:
                print(f"{seg:<7}{m:<24}   (半段樣本不足 {int(h1.sum())}/{int(h2.sum())})")
                continue
            p, mk, g, k = d["pred"], d["mark"], d["gt"], d["kind"]
            print(f"{seg:<7}{m:<24}"
                  f"{_err(_fit(p[h1], mk[h1], k)[0](p[h2]), g[h2]):>9.2f}%"
                  f"{_err(_fit(p[h2], mk[h2], k)[0](p[h1]), g[h1]):>9.2f}%"
                  f"{_err(_fit(p[n], mk[n], k)[0](p[n]), g[n]):>9.2f}%"
                  f"{_err(_fit(p[n], g[n], k)[0](p[n]), g[n]):>10.2f}%")
    print()


def cmd_transfer(args):
    a, b = list(SEGMENTS)
    print(f"跨片段轉移:在一段用標線定 k,搬到另一段評分(同一台相機、不同日期)\n")
    print(f"{'model':<24}{'k(%s)' % a:>10}{'k(%s)' % b:>10}{'k漂移':>9} | "
          f"{'%s@%s的k' % (b, a):>14}{'%s@%s的k' % (a, b):>14} | {'各自oracle':>13}")
    for m in MODELS:
        da, db = load(a, m, args.near_m), load(b, m, args.near_m)
        na, nb = da["near"], db["near"]
        fa, la, ka = _fit(da["pred"][na], da["mark"][na], da["kind"])
        fb, lb, kb = _fit(db["pred"][nb], db["mark"][nb], db["kind"])
        oa = _fit(da["pred"][na], da["gt"][na], da["kind"])[0]
        ob = _fit(db["pred"][nb], db["gt"][nb], db["kind"])[0]
        drift = "" if np.isnan(ka) else f"{(kb / ka - 1) * 100:+.1f}%"
        print(f"{m:<24}{la:>10}{lb:>10}{drift:>9} | "
              f"{_err(fa(db['pred'][nb]), db['gt'][nb]):>13.2f}%"
              f"{_err(fb(da['pred'][na]), da['gt'][na]):>13.2f}% | "
              f"{_err(oa(da['pred'][na]), da['gt'][na]):>5.2f}%/"
              f"{_err(ob(db['pred'][nb]), db['gt'][nb]):>5.2f}%")
    print()


def cmd_methodc(args):
    print("方法 C 對雷達:兩種接地點定義 × 兩種安裝偏移 Δ(配對集,近場 < %.0f m)" % args.near_m)
    print("band = 遮罩最低 12% 列的中位(本 benchmark 的目標像素);lowest = 遮罩最低點(管線 B 的定義)\n")
    if not Path(args.contact_defs).exists():
        print(f"  找不到 {args.contact_defs}:先跑 tools/contact_point_definitions.py\n")
        return
    lowest = {(r["tag"], r["frame_idx"]): float(r["py_max"]) for r in _rows(Path(args.contact_defs))}
    print(f"{'seg':<7}{'定義':<8}{'Δ':>5}{'n':>6}{'中位誤差':>10}{'p90':>8}{'真值/我方':>11}")
    for seg, s in SEGMENTS.items():
        rows = [r for r in _rows(D / f"paired_{s['tag']}.csv") if (s["tag"], r["frame_idx"]) in lowest]
        rad = np.array([float(r["radar_range_m"]) for r in rows])
        band = np.array([float(r["py"]) for r in rows])
        low = np.array([lowest[(s["tag"], r["frame_idx"])] for r in rows])
        for name, py in (("band", band), ("lowest", low)):
            for delta in (0.0, 2.0):
                gt = rad + delta
                n = gt < args.near_m
                d = s["A"] / (py[n] - s["y_h"])
                e = np.abs(d - gt[n]) / gt[n] * 100
                print(f"{seg:<7}{name:<8}{delta:>5.1f}{int(n.sum()):>6}{np.median(e):>9.2f}%"
                      f"{np.percentile(e, 90):>7.1f}%{np.median(gt[n] / d):>11.3f}")
    print()


def main():
    global DELTA_M
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("check", nargs="?", choices=["sources", "samerow", "holdout", "transfer", "methodc"])
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--near-m", type=float, default=32.0)
    ap.add_argument("--delta-m", type=float, default=DELTA_M,
                    help="added to the radar range to put it in the camera frame; not pinned "
                         "independently, so run 0 and 2 and report both (docs section 18)")
    ap.add_argument("--contact-defs", default=str(D / "contact_defs.csv"),
                    help="CSV from tools/contact_point_definitions.py, used by samerow")
    args = ap.parse_args()
    DELTA_M = args.delta_m
    checks = [cmd_methodc, cmd_sources, cmd_samerow, cmd_holdout, cmd_transfer] if args.all or not args.check \
        else [dict(sources=cmd_sources, samerow=cmd_samerow, holdout=cmd_holdout,
                   transfer=cmd_transfer, methodc=cmd_methodc)[args.check]]
    for fn in checks:
        fn(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
