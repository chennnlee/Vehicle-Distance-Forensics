"""Scale anchor for dashcam clips: the legal lane width.

SHARP reconstructs with a fixed-FOV assumption, so its point cloud is correct
in shape but arbitrary in absolute size -- every rig needs one metric anchor.
The CCTV pipeline gets that from 3D dash-length sampling, but at the dashcam's
grazing viewing angle dash endpoints sit in the depth noise (a 4 m dash has
measured anywhere from 0.3 to 6.7 m), so length along the road is unusable.

The lane WIDTH is measured across the road instead of along it: both lane
lines are at similar depth, so the badly-conditioned direction drops out. Feed
pairs of pixels on the left and right boundary of the ego lane, and the scale
that makes their on-plane separation equal the legal width is the anchor.

The camera height it prints back is the independent sanity check: solving for
scale from a lane width also fixes the height of the camera above the road, and
that must land in the plausible 1.1-1.5 m range for a windscreen-mounted
dashcam. A scale that implies a 0.6 m or 2.5 m mounting height is wrong even if
the lane-width residuals look tight.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from tools.lane_dash_calibration import fit_ground_plane_raw
from utils.pointcloud_io import load_point_cloud_points


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pointcloud", required=True, help="SHARP PLY of the reference frame.")
    ap.add_argument("--image-size", required=True, help="WIDTHxHEIGHT of the frame, e.g. 1920x1080.")
    ap.add_argument("--hood-y", type=int, required=True,
                    help="Image row where the hood begins; the plane fit must stop above it.")
    ap.add_argument("--pairs", required=True,
                    help="Semicolon-separated left/right lane-line pixel pairs at matching depth, "
                         "'lx,ly,rx,ry;...' (e.g. '728,700,1073,700;703,720,1116,720').")
    ap.add_argument("--lane-width-m", type=float, default=3.5,
                    help="Legal lane width: 3.5 m on Taiwan freeways/expressways.")
    ap.add_argument("--out-json", default="", help="Optional path to write the calibration report.")
    return ap.parse_args()


def build_plane(ply_path: Path, image_shape: tuple[int, int], hood_y: int):
    """Ground plane + unscaled pixel->plane map, mirroring the pipeline's geometry."""
    points_xyz, _, metadata = load_point_cloud_points(ply_path)
    intr = metadata.get("intrinsics") or {}
    fx = float(intr["fx"])
    fy = float(intr.get("fy") or fx)
    h, w = image_shape
    cx = float(intr.get("cx", (w - 1) * 0.5))
    cy = float(intr.get("cy", (h - 1) * 0.5))

    z = points_xyz[:, 2]
    valid = np.isfinite(points_xyz).all(axis=1) & (z > 1e-6)
    u = np.where(valid, fx * (points_xyz[:, 0] / z) + cx, np.nan)
    v = np.where(valid, fy * (points_xyz[:, 1] / z) + cy, np.nan)
    ground = fit_ground_plane_raw(points_xyz, u, v, (0, int(h * 0.45), w, hood_y))
    if ground is None:
        raise RuntimeError("Ground plane fit failed.")
    a, b, c = ground["a"], ground["b"], ground["c"]

    n = np.array([a, -1.0, b], dtype=np.float64)
    n /= np.linalg.norm(n)
    fwd = np.array([0.0, 0.0, 1.0]) - n * float(n @ np.array([0.0, 0.0, 1.0]))
    e_fwd = fwd / np.linalg.norm(fwd)
    e_lat = np.cross(n, e_fwd)
    e_lat /= np.linalg.norm(e_lat)

    def pixel_to_plane(px: float, py: float) -> np.ndarray | None:
        dx = (px - cx) / fx
        dy = (py - cy) / fy
        denom = dy - a * dx - b
        if abs(denom) < 1e-9:
            return None
        t = c / denom
        if t <= 0:
            return None
        p = np.array([dx * t, dy * t, t], dtype=np.float64)
        return np.array([float(p @ e_lat), float(p @ e_fwd)])

    height_raw = abs(c) / float(np.linalg.norm(np.array([a, -1.0, b])))
    # The intrinsics travel with the plane: the horizon row of y = ax + bz + c is
    # cy + fy*b, and a caller that assumes 1920x1080 gets it wrong on any other
    # sensor (comma2k19 is 1164x874). Hand them back rather than re-deriving.
    intrinsics = {"fx": fx, "fy": fy, "cx": cx, "cy": cy}
    return pixel_to_plane, ground, height_raw, intrinsics


def main() -> None:
    args = parse_args()
    w, h = (int(v) for v in args.image_size.lower().split("x"))
    pixel_to_plane, ground, height_raw, _ = build_plane(Path(args.pointcloud), (h, w), args.hood_y)

    rows = []
    for chunk in args.pairs.split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        lx, ly, rx, ry = (float(v) for v in chunk.split(","))
        pl = pixel_to_plane(lx, ly)
        pr = pixel_to_plane(rx, ry)
        if pl is None or pr is None:
            print(f"  pair {chunk}: ray misses the plane, skipped")
            continue
        width_raw = abs(float(pr[0] - pl[0]))
        rows.append({"left_px": [lx, ly], "right_px": [rx, ry],
                     "fwd_m_raw": float(0.5 * (pl[1] + pr[1])),
                     "width_raw": width_raw,
                     "scale": args.lane_width_m / width_raw})
        print(f"  pair L({lx:.0f},{ly:.0f}) R({rx:.0f},{ry:.0f}): "
              f"raw width {width_raw:.4f}  fwd_raw {0.5*(pl[1]+pr[1]):.3f}  -> scale {rows[-1]['scale']:.4f}")

    if not rows:
        raise SystemExit("No usable pairs.")

    scales = np.array([r["scale"] for r in rows])
    scale = float(np.median(scales))
    cv = float(scales.std(ddof=1) / scales.mean()) if len(scales) > 1 else 0.0
    height_m = height_raw * scale

    print(f"\nplane: y = {ground['a']:.5f}x + {ground['b']:.5f}z + {ground['c']:.5f}")
    print(f"scale     : {scale:.6f}   (median of {len(scales)} pairs)")
    print(f"scale CV  : {cv:.4f}")
    print(f"cam height: {height_m:.3f} m   <- sanity check, expect ~1.1-1.5 m for a windscreen mount")
    if not 1.0 <= height_m <= 1.6:
        print("  WARNING: implied mounting height is outside the plausible range; "
              "check the lane-line pixels or whether the ego lane is really the legal width.")

    report = {"scale": scale, "scale_cv": cv, "camera_height_m": height_m,
              "lane_width_m": args.lane_width_m, "hood_y": args.hood_y,
              "plane": {k: float(ground[k]) for k in ("a", "b", "c")}, "pairs": rows}
    if args.out_json:
        Path(args.out_json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out_json).write_text(json.dumps(report, indent=2), encoding="utf-8")
        print("wrote", args.out_json)


if __name__ == "__main__":
    main()
