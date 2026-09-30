#!/usr/bin/env python3
"""Pick the vehicles to measure in an Argoverse 2 log, using nothing but the image.

The comma2k19 target builder (`depth_benchmark_targets.py`) needs a radar CSV to decide
which vehicle to measure.  Here the ground truth must not be opened until the predictions
are sealed, so the choice is made from the lane geometry the marking calibration already
produced: a detection counts if its contact point falls inside the ego lane widened by one
lane on each side, which is the "car we are following, or the one in the next lane" the
report talks about.  Lane width is read off the two fitted lines at that row, so it needs
no metric scale.

Both contact-point definitions go in the same row, because the project notes record that they are
not interchangeable and that confusing them cost a 10-15% range error on comma2k19:

  py_max    lowest point of the mask -- where the tyre meets the road.  This is pipeline
            B's definition and the only one the ground-plane formula d = A/(py - y_h) is
            entitled to, since it is the only one actually on the road.
  py_band   median of the mask's lowest `--contact-pct` of rows.  Sits on the bodywork a
            few px higher; it is what the depth models are sampled at, because a depth
            model reading the road surface under a car is reading the wrong surface.

Truncated detections are dropped (a mask touching the frame edge has no reliable bottom),
as are masks below `--min-area-px`.

Usage:
  python3 tools/av2_targets.py --log data/input/av2/<log> --calib data/output/av2_marking/calib.json \
      --out data/output/av2_depth/targets_<log>.csv

For a log the marking calibration refused, the ego-lane lines can come instead from a sealed
depth_dash_scale result (`--lanes-json`): the lines of the detection window nearest each
frame, with that window's line crossing as y_h. Same selection rule otherwise.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np

VEHICLE = {2, 5, 7}                      # car, bus, truck -- as depth_benchmark_targets.py


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--log", required=True)
    ap.add_argument("--calib", default="", help="calib.json from av2_marking_calib.py")
    ap.add_argument("--lanes-json", default="", help="depth_dash_scale result whose windows give the lanes")
    ap.add_argument("--no-lanes", action="store_true",
                    help="2026-09-30: keep every vehicle detection (no lane test, no lane fitting of any kind); "
                         "the scoring then picks the lanes from the lidar cuboid's lateral offset")
    ap.add_argument("--device", default=None, help="YOLO device, e.g. cpu (default: ultralytics' choice)")
    ap.add_argument("--frames-name", default="pinhole")
    ap.add_argument("--yolo", default="checkpoints/yolov8m-seg.pt")
    ap.add_argument("--conf", type=float, default=0.4)
    ap.add_argument("--contact-pct", type=float, default=12.0)
    ap.add_argument("--min-area-px", type=float, default=600.0)
    ap.add_argument("--edge-px", type=int, default=3, help="drop masks touching the frame border")
    ap.add_argument("--lane-widths", type=float, default=1.0,
                    help="how many lane widths either side of the ego lane still counts")
    ap.add_argument("--stride", type=int, default=1)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    from ultralytics import YOLO

    log = Path(args.log)
    cal = None
    if args.no_lanes:
        def lanes_at(pos):
            return "all"
    elif args.lanes_json:
        dash = json.loads(Path(args.lanes_json).read_text())

        def lanes_at(pos):
            wd = min(dash["windows"], key=lambda w: abs(w["center"] - pos / dash["step"]))
            if not (wd.get("left") and wd.get("right") and wd.get("vp_row")):
                return None
            return (wd["left"]["a"], wd["left"]["b"]), (wd["right"]["a"], wd["right"]["b"]), wd["vp_row"]
    else:
        cal = {c["log"]: c for c in json.loads(Path(args.calib).read_text())}[log.name]
        if cal.get("status") != "ok":
            raise SystemExit(f"{log.name}: marking calibration did not pass ({cal.get('status')})")
        fixed = (tuple(cal["lines"][0]["line"]), tuple(cal["lines"][1]["line"]), cal["y_h"])

        def lanes_at(pos):
            return fixed

    all_frames = sorted((log / args.frames_name).glob("*.jpg"))
    frames = all_frames[::args.stride]
    model = YOLO(args.yolo)
    rows = []
    for pos, fp in zip(range(0, len(all_frames), args.stride), frames):
        lanes = lanes_at(pos)
        if lanes is None:
            continue
        if lanes != "all":
            (la, lb), (ra, rb), y_h = lanes
        res = model.predict(str(fp), verbose=False, conf=args.conf, device=args.device)[0]
        if res.masks is None:
            continue
        H, W = res.orig_shape
        for mk, poly, cls, box, cf in zip(res.masks.data.cpu().numpy(), res.masks.xy,
                                          res.boxes.cls.cpu().numpy(), res.boxes.xyxy.cpu().numpy(),
                                          res.boxes.conf.cpu().numpy()):
            if int(cls) not in VEHICLE or poly is None or len(poly) < 3:
                continue
            ys, xs = np.nonzero(mk)
            if ys.size < 50:
                continue
            ys, xs = ys * (H / mk.shape[0]), xs * (W / mk.shape[1])
            if xs.size < args.min_area_px:
                continue
            x0, y0, x1, y1 = box
            if x0 < args.edge_px or y0 < args.edge_px or x1 > W - args.edge_px or y1 > H - args.edge_px:
                continue
            sel = ys >= np.percentile(ys, 100.0 - args.contact_pct)
            px, py_band = float(np.median(xs[sel])), float(np.median(ys[sel]))
            py_max = float(poly[:, 1].max())
            if lanes != "all":
                if py_max <= y_h + 1:
                    continue
                left, right = la * py_max + lb, ra * py_max + rb
                lane_w = right - left
                if not (left - args.lane_widths * lane_w <= px <= right + args.lane_widths * lane_w):
                    continue
            rows.append(dict(frame_idx=fp.stem, px=round(px, 1), py=round(py_band, 2),
                             py_max=round(py_max, 2), cls=int(cls), conf=round(float(cf), 3),
                             x0=round(float(x0), 1), y0=round(float(y0), 1),
                             x1=round(float(x1), 1), y1=round(float(y1), 1),
                             mask_px=int(xs.size)))

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise SystemExit(f"{log.name}: no target passed the selection; nothing written")
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"{log.name}: {len(rows)} targets over {len(frames)} frames")
    if cal is not None:
        d = np.array([cal["A_marking"] / (r["py_max"] - cal["y_h"]) for r in rows])
        print(f"  marking range at the contact point: median {np.median(d):.1f} m, "
              f"10-90% {np.percentile(d, 10):.1f}-{np.percentile(d, 90):.1f} m")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    raise SystemExit(main())
