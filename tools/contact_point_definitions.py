#!/usr/bin/env python3
"""Measure how far apart two "ground contact point" definitions land on the same cars.

`depth_benchmark_targets.py` takes a vehicle's contact point as the median of its
mask's lowest 12% of rows.  Pipeline B (`dashcam_range_speed.py`) takes the lowest
point of the mask polygon.  The benchmark's docstring used to say the two were the
same definition; they are not, and on this camera the difference decides whether a
row is on the road or on the car body:

    d = A / (py - y_h)

treats every pixel as road.  A pixel on the body sits above the road, so the road
distance of its row is longer than the car's own distance.  At 20 m, 8 px is about
13%.

For every row of targets_<seg>.csv this re-runs YOLO on that frame, recovers the
same instance (its band-median point must reproduce the stored px, py within 1 px)
and writes both rows.  Nothing here reads the radar value except to copy it through.

Output columns: tag, frame_idx, px, py_band, py_max, radar_range_m

Usage:
  python3 tools/contact_point_definitions.py \
      --frames-root data/input/_frames_cache/c2k19 \
      --out data/output/depth_benchmark/contact_defs.csv
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import numpy as np

SEGMENTS = ["b0c9d2329ad1606b_2018-07-30--13-44-30_10", "b0c9d2329ad1606b_2018-08-15--09-01-03_21"]
VEHICLE = {2, 5, 7}                      # car, bus, truck -- as depth_benchmark_targets.py


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--frames-root", required=True, help="holds <seg>/frames/fNNNNN.jpg")
    ap.add_argument("--targets-dir", default="data/output/depth_benchmark")
    ap.add_argument("--segments", nargs="+", default=SEGMENTS)
    ap.add_argument("--yolo", default="checkpoints/yolov8m-seg.pt")
    ap.add_argument("--conf", type=float, default=0.4)
    ap.add_argument("--contact-pct", type=float, default=12.0)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    from ultralytics import YOLO
    model = YOLO(args.yolo)
    out = []
    for tag in args.segments:
        rows = list(csv.DictReader(open(Path(args.targets_dir) / f"targets_{tag}.csv", encoding="utf-8")))
        miss = 0
        for r in rows:
            fp = Path(args.frames_root) / tag / "frames" / f"{r['frame_idx']}.jpg"
            res = model.predict(str(fp), verbose=False, conf=args.conf)[0]
            best = None
            if res.masks is not None:
                h, w = res.orig_shape
                for mk, poly, cls in zip(res.masks.data.cpu().numpy(), res.masks.xy,
                                         res.boxes.cls.cpu().numpy()):
                    if int(cls) not in VEHICLE or poly is None or len(poly) < 3:
                        continue
                    ys, xs = np.nonzero(mk)
                    if ys.size < 50:
                        continue
                    ys, xs = ys * (h / mk.shape[0]), xs * (w / mk.shape[1])
                    sel = ys >= np.percentile(ys, 100.0 - args.contact_pct)
                    px, py = float(np.median(xs[sel])), float(np.median(ys[sel]))
                    gap = abs(px - float(r["px"])) + abs(py - float(r["py"]))
                    if gap < 1.0 and (best is None or gap < best[0]):
                        best = (gap, px, py, float(poly[:, 1].max()))
            if best is None:
                miss += 1
                continue
            out.append(dict(tag=tag, frame_idx=r["frame_idx"], px=round(best[1], 1),
                            py_band=round(best[2], 2), py_max=round(best[3], 2),
                            radar_range_m=r["radar_range_m"]))
        d = np.array([o["py_max"] - o["py_band"] for o in out if o["tag"] == tag])
        print(f"{tag}: {len(rows) - miss}/{len(rows)} rows recovered   "
              f"py_max - py_band median {np.median(d):.2f} px  IQR {np.percentile(d, 25):.2f}..{np.percentile(d, 75):.2f}")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w_ = csv.DictWriter(f, fieldnames=list(out[0]))
        w_.writeheader()
        w_.writerows(out)
    print(f"wrote {args.out}  ({len(out)} rows)")


if __name__ == "__main__":
    raise SystemExit(main())
