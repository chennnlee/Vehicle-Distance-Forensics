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

  samerow   Road pixel and vehicle contact pixel on the *same image row*.  Both lie
            on the road surface about 1.5 m apart, so their true distance is equal
            and any difference in the model's reading is the model contradicting
            itself.  Needs no ground truth at all.

  holdout   Calibrate on the first half of the frames, score on the second (and the
            reverse), so the constant is never fitted on the rows it scores.

  transfer  Calibrate on one segment, score on another recorded on a different day
            with the same camera -- "calibrate the camera once and reuse it".

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

# Method C geometry per segment: A = h*f from the dash cycle, y_h from the lane-line
# vanishing point.  Both solved without a neural network; see docs section 15.
SEGMENTS = {
    "seg10": dict(tag="b0c9d2329ad1606b_2018-07-30--13-44-30_10", A=1153.0, y_h=383.2),
    "seg21": dict(tag="b0c9d2329ad1606b_2018-08-15--09-01-03_21", A=1139.0, y_h=378.7),
}
MODELS = ["metric3d_v2", "unidepth_v2", "da3_metric", "depth_anything_v2_vits", "depth_pro"]
DELTA_M = 2.0          # radar sits on the bumper, the camera is behind it (section 15.4)


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
            ad = np.array([float(r["marking_d_m"]) for r in an])
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
    print("同一影像列上,路面像素 vs 車輛接地像素的模型讀值比(|Δpy| ≤ 6 px)")
    print("兩點都在路面上、橫向差約 1.5 m,真實距離相同 → 偏離 1.0 即模型自相矛盾,不需要真值\n")
    print(f"{'seg':<7}{'model':<24}{'n':>5}{'路面/車輛 中位':>16}{'IQR':>18}")
    for seg, s in SEGMENTS.items():
        for m in MODELS:
            by_frame: dict[str, list] = {}
            for r in _rows(D / f"anchor_{s['tag']}__{m}.csv"):
                by_frame.setdefault(r["frame_idx"], []).append((float(r["py"]), float(r["pred"])))
            rat = []
            for r in _rows(D / f"unf_{s['tag']}__{m}.csv"):
                cand = by_frame.get(r["frame_idx"])
                vpy, vp = float(r["py"]), float(r["pred"])
                if not cand or vp <= 0:
                    continue
                gap, _, q = min((abs(p - vpy), p, q) for p, q in cand)
                if gap <= 6 and q > 0:
                    # disparity rises as depth falls, so the relative backend inverts
                    rat.append(q / vp if r["kind"] == "metric" else vp / q)
            if len(rat) < 5:
                print(f"{seg:<7}{m:<24}{len(rat):>5}   (配對不足)")
                continue
            a = np.asarray(rat)
            print(f"{seg:<7}{m:<24}{len(a):>5}{np.median(a):>16.3f}"
                  f"      [{np.percentile(a, 25):.3f}, {np.percentile(a, 75):.3f}]")
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


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("check", nargs="?", choices=["sources", "samerow", "holdout", "transfer"])
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--near-m", type=float, default=32.0)
    args = ap.parse_args()
    checks = [cmd_sources, cmd_samerow, cmd_holdout, cmd_transfer] if args.all or not args.check \
        else [dict(sources=cmd_sources, samerow=cmd_samerow,
                   holdout=cmd_holdout, transfer=cmd_transfer)[args.check]]
    for fn in checks:
        fn(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
