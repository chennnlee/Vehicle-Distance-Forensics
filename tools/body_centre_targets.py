#!/usr/bin/env python3
"""Move each benchmark target's sample pixel from its ground contact to its body centre.

Section 14 of docs/DEPTH_MODEL_BENCHMARK.md asks what happens when a car's ground
contact cannot be used.  Instead of hunting for real occlusions (almost none exist in
highway following footage), it keeps the same car, frame and radar value and only
moves the pixel: from the contact point (median of the mask's lowest 12% of rows) to
the median of every mask pixel.  The ground-plane formula d = A / (py - y_h) needs a
road pixel; a depth model does not.

For every row of paired_<seg>.csv this re-runs YOLO on that frame, recovers the same
instance (its contact point must land within 15 px of the stored px, py), and writes
the row back with px, py replaced by the body centre.  The radar columns are copied
through untouched.  Feed the output to `depth_model_benchmark.py run --targets` to get
body_pred_<seg>__<model>.csv.

Output columns: the paired_ columns, with px/py = body centre, plus
  contact_py  the original contact row
  mask_h      mask height in px

Usage:
  python3 tools/body_centre_targets.py --frames-root data/input/_frames_cache/c2k19 \
      --out-dir data/output/depth_benchmark
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
    ap.add_argument("--match-px", type=float, default=15.0,
                    help="max |dx| and |dy| between the recomputed and stored contact point")
    ap.add_argument("--out-dir", required=True, help="writes body_<seg>.csv here")
    args = ap.parse_args()

    from ultralytics import YOLO
    model = YOLO(args.yolo)
    for tag in args.segments:
        rows = list(csv.DictReader(open(Path(args.targets_dir) / f"paired_{tag}.csv", encoding="utf-8")))
        out = []
        for r in rows:
            fp = Path(args.frames_root) / tag / "frames" / f"{r['frame_idx']}.jpg"
            res = model.predict(str(fp), verbose=False, conf=args.conf)[0]
            if res.masks is None:
                continue
            h, w = res.orig_shape
            px, py = float(r["px"]), float(r["py"])
            for mk, cls in zip(res.masks.data.cpu().numpy(), res.boxes.cls.cpu().numpy()):
                if int(cls) not in VEHICLE:
                    continue
                ys, xs = np.nonzero(mk)
                if ys.size < 50:
                    continue
                ys, xs = ys * (h / mk.shape[0]), xs * (w / mk.shape[1])
                sel = ys >= np.percentile(ys, 100.0 - args.contact_pct)
                if abs(np.median(xs[sel]) - px) < args.match_px and abs(np.median(ys[sel]) - py) < args.match_px:
                    d = dict(r)
                    d["px"] = round(float(np.median(xs)), 1)
                    d["py"] = round(float(np.median(ys)), 1)
                    d["contact_py"] = r["py"]
                    d["mask_h"] = round(float(ys.max() - ys.min()), 1)
                    out.append(d)
                    break
        dy = np.array([float(o["contact_py"]) - float(o["py"]) for o in out])
        print(f"{tag}: {len(out)}/{len(rows)} rows recovered   "
              f"body centre above contact: median {np.median(dy):.0f} px, range {dy.min():.0f}..{dy.max():.0f}")
        dst = Path(args.out_dir) / f"body_{tag}.csv"
        dst.parent.mkdir(parents=True, exist_ok=True)
        with open(dst, "w", newline="", encoding="utf-8") as f:
            w_ = csv.DictWriter(f, fieldnames=list(out[0]))
            w_.writeheader()
            w_.writerows(out)
        print(f"wrote {dst}")


if __name__ == "__main__":
    raise SystemExit(main())
