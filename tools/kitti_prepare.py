#!/usr/bin/env python3
"""Turn a KITTI raw drive into the frame folder the marking tools expect, and work out the
two reference numbers the marking measurement will be scored against.

Why KITTI after Argoverse 2.  AV2's whole fleet carries one camera model, so agreeing with
its factory calibration four times over says little about a different sensor.  KITTI is a
genuinely different camera (PointGrey Flea2, 1242x375, f ~ 721 px against AV2's 1781) on a
different continent with different markings, and it publishes its rectified intrinsics and
the sensor rig's geometry.

It also sits below this project's own sampling floor, deliberately.  The odometer needs
roughly eight frames per dash cycle; KITTI runs at 10 Hz, so a German 12 m cycle survives
only up to about 54 km/h.  CLAUDE.md recorded that floor from a KITTI ego-speed run that
failed at 85 km/h.  A refusal here is a result, not a waste.

Reference numbers, neither of which the measurement may use:

  fy         from P_rect_02 in calib_cam_to_cam.txt (the rectified left colour camera).
  h          the camera's height above the road.  KITTI publishes the rig, not the height,
             so this takes the velodyne's documented 1.73 m and subtracts the camera's
             offset from it along the vertical, via calib_velo_to_cam.  The result should
             land near the 1.65 m the setup diagram gives; it is printed so it can be
             checked rather than trusted.
  A_factory = h * fy.

Ego speed comes from OXTS (`vf`, forward velocity), and is used the same way as AV2's
poses: to convert a locked dash period into the cycle length it implies, so the legal
cycle is verified instead of assumed.  German lane markings are not the American 12.19 m --
outside built-up areas the Leitlinie is 6 m of paint and 12 m of gap -- so assuming a
constant here without checking would repeat the mistake AV2's f668074d exposed.

Usage:
  python3 tools/kitti_prepare.py --drive data/input/kitti/2011_09_26/2011_09_26_drive_0015_sync
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def read_calib(p):
    out = {}
    for line in Path(p).read_text().splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        try:
            out[k.strip()] = np.array([float(x) for x in v.split()])
        except ValueError:
            pass
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--drive", required=True, help="…/2011_09_26_drive_00NN_sync")
    ap.add_argument("--calib-dir", default="", help="defaults to the drive's date folder")
    ap.add_argument("--camera", default="image_02")
    ap.add_argument("--velo-height-m", type=float, default=1.73,
                    help="KITTI's documented velodyne height above the road")
    ap.add_argument("--out-name", default="pinhole")
    args = ap.parse_args()

    import cv2

    drive = Path(args.drive)
    calib_dir = Path(args.calib_dir) if args.calib_dir else drive.parent
    cam = read_calib(calib_dir / "calib_cam_to_cam.txt")
    v2c = read_calib(calib_dir / "calib_velo_to_cam.txt")

    idx = args.camera.split("_")[1]
    P = cam[f"P_rect_{idx}"].reshape(3, 4)
    fx, fy, cx, cy = P[0, 0], P[1, 1], P[0, 2], P[1, 2]

    # camera height above the road: the velodyne's documented height, less the camera's
    # offset from it along the road normal.  R|T take velodyne points into camera 0; the
    # camera's own position in the velodyne frame is -R^T T, whose z is its height above
    # the velodyne.
    R, T = v2c["R"].reshape(3, 3), v2c["T"]
    cam0_in_velo = -R.T @ T
    h = args.velo_height_m + float(cam0_in_velo[2])

    src = sorted((drive / args.camera / "data").glob("*.png"))
    if not src:
        raise SystemExit(f"{drive}/{args.camera}/data: no png")
    out = drive / args.out_name
    out.mkdir(parents=True, exist_ok=True)
    for i, p in enumerate(src, 1):
        dst = out / f"f{i:05d}.jpg"
        if not dst.exists():
            cv2.imwrite(str(dst), cv2.imread(str(p)), [cv2.IMWRITE_JPEG_QUALITY, 95])
    im = cv2.imread(str(out / "f00001.jpg"))
    H, W = im.shape[:2]

    oxts = sorted((drive / "oxts/data").glob("*.txt"))
    vf = np.array([float(Path(p).read_text().split()[8]) for p in oxts])   # forward velocity
    yaw = np.array([float(Path(p).read_text().split()[5]) for p in oxts])
    fps = 10.0

    meta = dict(drive=drive.name, camera=args.camera, frames=len(src), fps=fps,
                width=W, height=H, fx=float(fx), fy=float(fy), cx=float(cx), cy=float(cy),
                cam_height_m=h, A_factory=h * float(fy),
                speed_mps_median=float(np.median(vf)),
                speed_mps_p10_p90=[float(np.percentile(vf, 10)), float(np.percentile(vf, 90))],
                yaw_rate_deg_s_p90=float(np.percentile(np.abs(np.degrees(np.diff(np.unwrap(yaw)))) * fps, 90)))
    (drive / f"{args.out_name}_meta.json").write_text(json.dumps(meta, indent=2))
    with open(drive / f"{args.out_name}_frames.csv", "w") as f:
        f.write("frame_idx,ego_speed_mps\n")
        for i, v in enumerate(vf[:len(src)], 1):
            f.write(f"f{i:05d},{v:.4f}\n")

    print(f"{drive.name}: {len(src)} frames -> {out}  {W}x{H}  fps {fps:g}")
    print(f"  fx {fx:.1f}  fy {fy:.1f}  cy {cy:.1f}   camera height {h:.3f} m "
          f"(setup diagram says ~1.65)")
    print(f"  A_factory = h*fy = {meta['A_factory']:.0f}   (scoring only -- not an input)")
    print(f"  ego speed median {meta['speed_mps_median']:.1f} m/s "
          f"({meta['speed_mps_median'] * 3.6:.0f} km/h), p10-p90 "
          f"{meta['speed_mps_p10_p90'][0] * 3.6:.0f}-{meta['speed_mps_p10_p90'][1] * 3.6:.0f} km/h, "
          f"|yaw rate| p90 {meta['yaw_rate_deg_s_p90']:.1f} deg/s")
    for c in (9.0, 12.0, 18.0):
        print(f"    frames per {c:.0f} m cycle: {fps * c / max(meta['speed_mps_median'], 1e-6):.1f}"
              + ("   (below the 8-frame floor)" if fps * c / max(meta['speed_mps_median'], 1e-6) < 8 else ""))


if __name__ == "__main__":
    raise SystemExit(main())
