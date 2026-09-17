#!/usr/bin/env python3
"""Build a (frame, target pixel, radar distance) table for the depth benchmark.

The benchmark needs three things to line up on every row: a frame, the pixel a
depth model should be read at, and an external distance for that same vehicle.
This produces all three without going through pipeline B at all, so the depth
models can be scored even where the geometric pipeline has not been set up.

How the lead vehicle is chosen
------------------------------
Per frame, among YOLO's car/bus/truck instances:

  * the mask's horizontal centre must sit within `--centre-tol-px` of the image
    centre column -- i.e. the vehicle is in our own lane, not a neighbour;
  * of those, the *nearest* one wins, taken as the lowest contact row (the largest
    mask can be a distant lorry).

The contact point is the median of the mask's lowest `--contact-pct` of rows.
⚠ This is NOT pipeline B's definition, although this docstring said so until
2026-09-17: `dashcam_range_speed.py` uses the lowest point of the mask polygon.
On comma2k19 the band median sits 8.4 px (seg10) / 5.9 px (seg21) above that
lowest point -- on the car body, not the road -- which moves a ground-plane range
by roughly 10-15% at 20-30 m.  `tools/contact_point_definitions.py` measures both.

How the radar row is chosen
---------------------------
In the same frame, the NEAREST radar return with |lateral| <= `--lane-half-width-m`
(the same in-lane test `comma2k19_radar_eval.py` applies).  Picking the most centred
return instead pairs the wrong car when two share the lane.

Two guards, both of which exist because the naive version is wrong
------------------------------------------------------------------
  * **Pixel continuity.**  Taking "the largest vehicle" independently per frame
    silently swaps targets: in the first 12-frame trial the pick jumped to a
    different car for exactly one frame, and every depth model jumped with it by
    ~2x.  Consecutive picks must therefore stay within `--max-jump-px`.
  * **Radar slot continuity.**  A radar slot is a reusable track id, so requiring
    the slot to persist stops one row of the table describing a different object
    from the row above it.

Rows that fail either guard are dropped, not patched.  The output carries
`slot` so the consumer can group by continuous runs.
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

import numpy as np


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--frames", required=True)
    ap.add_argument("--radar", required=True, help="CSV from comma2k19_radar_export.py")
    ap.add_argument("--out", required=True)
    ap.add_argument("--yolo", default="yolov8m-seg.pt")
    ap.add_argument("--conf", type=float, default=0.4)
    ap.add_argument("--centre-tol-px", type=float, default=200.0)
    ap.add_argument("--contact-pct", type=float, default=12.0,
                    help="percent of the mask's lowest rows that define the contact point")
    ap.add_argument("--lane-half-width-m", type=float, default=1.8)
    ap.add_argument("--max-jump-px", type=float, default=60.0)
    ap.add_argument("--hood-y", type=int, default=700,
                    help="image row where the ego bonnet starts; contact points below "
                         "it are the ego car's own hood, not a target")
    ap.add_argument("--max-frames", type=int, default=0, help="0 = all")
    ap.add_argument("--stride", type=int, default=1)
    args = ap.parse_args()

    # ---- radar, indexed by frame
    radar = defaultdict(list)
    with open(args.radar, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            radar[int(r["frame_idx"])].append(r)
    print(f"radar : {sum(len(v) for v in radar.values())} returns over {len(radar)} frames")

    frames = sorted(Path(args.frames).glob("*.jpg"))
    if args.stride > 1:
        frames = frames[::args.stride]
    if args.max_frames:
        frames = frames[:args.max_frames]
    print(f"frames: {len(frames)}")

    from ultralytics import YOLO
    model = YOLO(args.yolo)
    VEHICLE = {2, 5, 7}                      # car, bus, truck

    rows, prev_px = [], None
    n_no_det = n_off_centre = n_jump = n_no_radar = 0

    for i, fp in enumerate(frames, 1):
        res = model.predict(str(fp), verbose=False, conf=args.conf)[0]
        if res.masks is None:
            n_no_det += 1
            prev_px = None
            continue
        h, w = res.orig_shape
        cx_img = w / 2.0

        best = None
        for mk, box, cls in zip(res.masks.data.cpu().numpy(),
                                res.boxes.xyxy.cpu().numpy(),
                                res.boxes.cls.cpu().numpy()):
            if int(cls) not in VEHICLE:
                continue
            ys, xs = np.nonzero(mk)
            if ys.size < 50:
                continue
            # mask is at model resolution; rescale to the original frame
            sy, sx = h / mk.shape[0], w / mk.shape[1]
            ys, xs = ys * sy, xs * sx
            if abs(np.median(xs) - cx_img) > args.centre_tol_px:
                continue
            cut = np.percentile(ys, 100.0 - args.contact_pct)
            sel = ys >= cut
            px, py = float(np.median(xs[sel])), float(np.median(ys[sel]))
            if py > args.hood_y:
                continue          # the ego bonnet, not a vehicle ahead
            # Rank by the contact row, not by mask area: on a perspective view the
            # lowest contact point IS the nearest vehicle, whereas the largest mask
            # can be a distant lorry.  The radar side picks the nearest in-lane
            # return, so the two rankings must agree or the rows pair wrong objects.
            if best is None or py > best[0]:
                best = (py, px, py, int(cls))
        if best is None:
            n_off_centre += 1
            prev_px = None
            continue

        _, px, py, cls = best
        if prev_px is not None and abs(px - prev_px) > args.max_jump_px:
            n_jump += 1
            prev_px = px
            continue
        prev_px = px

        fid = int(fp.stem.lstrip("f") or 0)
        cands = [r for r in radar.get(fid, [])
                 if abs(float(r["radar_lat_m"])) <= args.lane_half_width_m]
        if not cands:
            n_no_radar += 1
            continue
        # The lead vehicle is the NEAREST in-lane one, which is also what the YOLO
        # pick above is (largest central mask).  Selecting the most *centred* radar
        # return instead pairs the wrong object whenever two cars share the lane at
        # different distances -- measured corr(py, 1/range) collapses to -0.27.
        rr = min(cands, key=lambda r: float(r["radar_range_m"]))

        rows.append(dict(frame_idx=fp.stem, px=round(px, 1), py=round(py, 1), cls=cls,
                         slot=rr["slot"],
                         radar_range_m=rr["radar_range_m"],
                         radar_lat_m=rr["radar_lat_m"],
                         radar_abs_kmh=rr["radar_abs_kmh"],
                         can_ego_kmh=rr["can_ego_kmh"]))
        if i % 200 == 0:
            print(f"  {i}/{len(frames)}  kept {len(rows)}")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w_ = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w_.writeheader()
        w_.writerows(rows)

    d = np.array([float(r["radar_range_m"]) for r in rows])
    print(f"\nwrote {args.out}  ({len(rows)} rows)")
    print(f"  dropped: no detection {n_no_det}, off-centre {n_off_centre}, "
          f"pixel jump {n_jump}, no in-lane radar {n_no_radar}")
    print(f"  radar distance: {d.min():.1f} .. {d.max():.1f} m  (median {np.median(d):.1f})")
    slots = defaultdict(int)
    for r in rows:
        slots[r["slot"]] += 1
    top = sorted(slots.items(), key=lambda kv: -kv[1])[:5]
    print(f"  radar slots used: {', '.join(f'{s}({n})' for s, n in top)}")


if __name__ == "__main__":
    raise SystemExit(main())
