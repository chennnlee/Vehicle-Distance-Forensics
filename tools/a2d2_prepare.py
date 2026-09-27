#!/usr/bin/env python3
"""Turn an A2D2 front-centre drive into the frame folder the marking calibration expects.

Why this dataset.  The marking method has succeeded on exactly one camera family (Argoverse
2's ring cameras) and been refused on a second (KITTI).  A cross-camera claim needs a third,
and the three applicability conditions in docs/TERRY_RESEARCH_RECORD.md section 6.5 are
meant to be checkable from published specs BEFORE downloading anything.  For A2D2's
front_center they predict a pass with margin: fy 1783 px and a 1.69 m camera give A = h*fy
= 3019, so a 13-row sampling band covers 0.60 m of road at the far row (KITTI: 2.48 m, which
is what refused it), 30 Hz gives 19-24 frames per 18 m Autobahn cycle, and a row pair is 6-11
frames of travel.  Different vendor, different focal length, different country's markings.

This deliberately writes the SAME layout and the same meta keys as av2_prepare.py, so the
calibration itself runs through av2_marking_calib.py unchanged.  The cross-camera test is
then a test of the method, not of a second implementation of it.

Two numbers are for scoring only and never enter the measurement:

  A_factory = h * fy   what the marking method has to recover on its own.  A2D2 gives the
                       camera's position in the vehicle frame (view.origin) but that frame's
                       origin is NOT on the road: ego-dimensions z-range starts at -0.75,
                       i.e. the origin sits 0.75 m above the ground plane, so
                       h = origin_z + 0.75.  Taking origin_z alone understates A by 44% --
                       the same trap AV2 set with its rear-axle origin, which cost 15% there.
  cy                   the principal row; the lane-line vanishing point should land near it
                       if the camera has no pitch, so the difference measures the pitch.

A2D2 images are DISTORTED as shipped (Lens "Telecam", k1 = -0.261).  They are undistorted
here with cv2 using CamMatrixOriginal -> CamMatrix, because d = A/(py - y_h) assumes a
pinhole and lane markings must image as straight lines.  Verify independently rather than
trusting it: lane_line_fit.py's residual is a few px on a rectified image and tens on a
distorted one.

Ego speed comes from the drive's bus_signals json (vehicle CAN).  The measurement does not
use it; it is there to cross-check the assumed dash cycle, as CLAUDE.md requires.

Usage:
  python3 tools/a2d2_prepare.py --drive data/input/a2d2/camera_lidar/20190401_121727
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

CAM = "front_center"
FPS = 30.0                 # A2D2 front-centre camera rate
GROUND_FROM_EGO_Z = None   # taken from vehicle ego-dimensions z-range[0]


def load_calib(p: Path):
    d = json.loads(p.read_text())
    c = d["cameras"][CAM]
    K_new = np.array(c["CamMatrix"], dtype=float)
    K_old = np.array(c["CamMatrixOriginal"], dtype=float)
    dist = np.array(c["Distortion"], dtype=float).ravel()
    W, H = (int(x) for x in c["Resolution"])
    cam_z = float(c["view"]["origin"][2])
    ground = float(d["vehicle"]["ego-dimensions"]["z-range"][0])   # negative
    return K_new, K_old, dist, W, H, cam_z, -ground


def ego_speed(drive: Path):
    """Median speed and a per-timestamp lookup, from the drive's bus signals."""
    cands = sorted(drive.glob("bus_signals*.json")) + sorted(drive.glob("bus/*.json"))
    if not cands:
        return None, None
    raw = json.loads(cands[0].read_text())
    entries = raw if isinstance(raw, list) else [raw]
    ts, v = [], []
    for e in entries:
        sig = e.get("flexray", e) if isinstance(e, dict) else {}
        s = sig.get("vehicle_speed") or sig.get("VehicleSpeed") or {}
        if isinstance(s, dict) and "values" in s:
            kmh = "KiloMeter" in str(s.get("unit", ""))
            for t, val in s["values"]:
                ts.append(float(t)); v.append(float(val) / 3.6 if kmh else float(val))
    if not ts:
        return None, None
    ts, v = np.array(ts) / 1e6, np.array(v)      # bus timestamps are microseconds
    o = np.argsort(ts)
    return (ts[o], v[o]), float(np.median(v))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--drive", required=True, help="a drive folder holding camera/cam_front_center")
    ap.add_argument("--calib", default="data/input/a2d2/cams_lidars.json")
    ap.add_argument("--out-name", default="pinhole")
    ap.add_argument("--limit", type=int, default=0, help="stop after N frames (0 = all)")
    ap.add_argument("--quality", type=int, default=95)
    ap.add_argument("--allow-frame-gaps", action="store_true",
                    help="proceed although the source frame numbers skip; the dash timing "
                         "would then be measured on a timeline that is not uniform")
    args = ap.parse_args()

    import cv2

    drive = Path(args.drive)
    K_new, K_old, dist, W, H, cam_z, ground_off = load_calib(Path(args.calib))
    cam_h = cam_z + ground_off

    src = sorted((drive / "camera" / f"cam_{CAM}").glob("*.png"))
    if not src:
        src = sorted(drive.rglob(f"*{CAM.replace('_', '')}*.png"))
    if not src:
        raise SystemExit(f"{drive}: no front-centre png found")
    if args.limit:
        src = src[:args.limit]

    # The frames are renumbered f00001.. below, so a hole in the source numbering would not
    # show up anywhere -- it would silently shorten the timeline, and extract_odometer_signals
    # assumes one frame per 1/fps. That matters here more than usual: these files came out of
    # a 50 GB tar read over HTTP Range and re-aligned by searching for the ustar magic, so a
    # dropped member is a real possibility rather than a hypothetical one.
    idx_all = [int(q.stem.split("_")[-1]) for q in src]
    gaps = [(x, y) for x, y in zip(idx_all, idx_all[1:]) if y != x + 1]
    if gaps and not args.allow_frame_gaps:
        raise SystemExit(f"{drive}: source frame numbers are not consecutive -- "
                         f"{len(gaps)} gap(s), first {gaps[0][0]} -> {gaps[0][1]}. "
                         f"Re-extract, or pass --allow-frame-gaps if the timeline is not used.")

    out = drive / args.out_name
    out.mkdir(parents=True, exist_ok=True)
    map1, map2 = cv2.initUndistortRectifyMap(K_old, dist, None, K_new, (W, H), cv2.CV_16SC2)
    for i, p in enumerate(src, 1):
        dst = out / f"f{i:05d}.jpg"
        if dst.exists():
            continue
        im = cv2.imread(str(p))
        if im is None:                      # same reason as the gap check: a skipped frame
            raise SystemExit(f"{p}: unreadable, which would leave a hole in the timeline")
        im = cv2.remap(im, map1, map2, cv2.INTER_LINEAR)
        cv2.imwrite(str(dst), im, [cv2.IMWRITE_JPEG_QUALITY, args.quality])

    spd, v_med = ego_speed(drive)
    # The drive's median is not this window's median: a 947-frame slice of a 526 s drive can
    # be a 65 km/h country road inside a drive whose median is 28 km/h city. The cycle gate
    # needs the window, so take the bus signal over the span the extracted frames cover
    # (absolute frame index / fps after the drive's first sample).
    if spd is not None:
        idx = [int(q.stem.split("_")[-1]) for q in src]
        t0 = spd[0][0]
        lo, hi = t0 + min(idx) / FPS, t0 + max(idx) / FPS
        m = (spd[0] >= lo) & (spd[0] <= hi)
        if m.sum() >= 10:
            v_med = float(np.median(spd[1][m]))
    meta = dict(
        dataset="a2d2", drive=drive.name, camera=CAM, frames=len(src), fps=FPS, scale=1.0,
        width=W, height=H,
        fx=float(K_new[0, 0]), fy=float(K_new[1, 1]),
        cx=float(K_new[0, 2]), cy=float(K_new[1, 2]),
        cam_z_in_ego_m=cam_z, ego_origin_above_ground_m=ground_off, cam_height_m=cam_h,
        A_factory=cam_h * float(K_new[1, 1]),
        speed_mps_median=(v_med if v_med is not None else float("nan")),
        undistorted_with="CamMatrixOriginal -> CamMatrix, cv2.initUndistortRectifyMap",
    )
    (drive / f"{args.out_name}_meta.json").write_text(json.dumps(meta, indent=2))

    with open(drive / f"{args.out_name}_frames.csv", "w") as f:
        f.write("frame_idx,source,ego_speed_mps\n")
        for i, p in enumerate(src, 1):
            f.write(f"f{i:05d},{p.name},{v_med if v_med is not None else ''}\n")

    print(f"{drive.name}: {len(src)} frames -> {out}  {W}x{H}  fps {FPS}")
    print(f"  fy {meta['fy']:.1f}  cy {meta['cy']:.1f}  camera height {cam_h:.3f} m "
          f"(= view.origin.z {cam_z:.3f} + ground offset {ground_off:.2f})")
    print(f"  A_factory = h*fy = {meta['A_factory']:.0f}   (scoring only -- not an input)")
    if v_med is not None:
        print(f"  ego speed median {v_med:.1f} m/s ({v_med*3.6:.0f} km/h), "
              f"frames per 18 m cycle {FPS*18/max(v_med,1e-6):.1f}")
    else:
        print("  ⚠ no bus signals found: the cycle gate needs a speed reference")


if __name__ == "__main__":
    raise SystemExit(main())
