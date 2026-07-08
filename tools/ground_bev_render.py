from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "tools"))

from utils.pointcloud_io import load_point_cloud_points
from lane_dash_calibration import fit_ground_plane_raw


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render a METRIC bird's-eye orthophoto of the road by ray-casting every BEV grid "
        "cell onto the SHARP-derived ground plane. Fulfils the original 'top-down view where the 4m "
        "dash is exactly 4m' idea without manual homography points: the plane IS the homography."
    )
    parser.add_argument("--image", required=True, help="Reference frame image.")
    parser.add_argument("--pointcloud", required=True, help="SHARP PLY of the same view.")
    parser.add_argument("--pointcloud-scale", type=float, required=True, help="Anchor-derived scale factor.")
    parser.add_argument("--out", required=True, help="Output BEV png path.")
    parser.add_argument("--lateral-range", default="-18,18", help="BEV lateral extent in meters, min,max.")
    parser.add_argument("--forward-range", default="4,70", help="BEV forward extent in meters, min,max.")
    parser.add_argument("--meters-per-pixel", type=float, default=0.05, help="BEV resolution.")
    parser.add_argument("--anchors-json", default="", help="Optional lane_dash_calibration.json to draw the calibrated dashes.")
    parser.add_argument("--tracks-json", default="", help="Optional tracks.json from cctv_speed_estimation to draw trajectories.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    image_path = Path(args.image)
    if not image_path.is_absolute():
        image_path = PROJECT_ROOT / image_path
    image = cv2.imread(str(image_path))
    if image is None:
        raise RuntimeError(f"Unable to read image: {image_path}")
    img_h, img_w = image.shape[:2]

    ply_path = Path(args.pointcloud)
    if not ply_path.is_absolute():
        ply_path = PROJECT_ROOT / ply_path
    points_xyz, _, metadata = load_point_cloud_points(ply_path)
    intr = metadata["intrinsics"]
    fx = float(intr["fx"])
    fy = float(intr.get("fy") or fx)
    cx = float(intr.get("cx", (img_w - 1) * 0.5))
    cy = float(intr.get("cy", (img_h - 1) * 0.5))

    z = points_xyz[:, 2]
    valid = np.isfinite(points_xyz).all(axis=1) & (z > 1e-6)
    u = np.where(valid, fx * (points_xyz[:, 0] / z) + cx, np.nan)
    v = np.where(valid, fy * (points_xyz[:, 1] / z) + cy, np.nan)
    ground = fit_ground_plane_raw(points_xyz, u, v, (0, int(img_h * 0.35), img_w, img_h))
    if ground is None:
        raise RuntimeError("Ground plane fit failed.")
    a, b, c = ground["a"], ground["b"], ground["c"]
    scale = float(args.pointcloud_scale)

    # Orthonormal basis on the plane (camera coords). Plane normal for
    # y = a x + b z + c is (a, -1, b); e_fwd is the camera viewing axis
    # projected onto the plane, e_lat completes the right-handed frame.
    n = np.array([a, -1.0, b], dtype=np.float64)
    n /= np.linalg.norm(n)
    fwd = np.array([0.0, 0.0, 1.0]) - n * float(n @ np.array([0.0, 0.0, 1.0]))
    e_fwd = fwd / np.linalg.norm(fwd)
    e_lat = np.cross(n, e_fwd)
    e_lat /= np.linalg.norm(e_lat)

    def ray_to_plane(px: float, py: float) -> np.ndarray | None:
        dx = (px - cx) / fx
        dy = (py - cy) / fy
        denom = dy - a * dx - b
        if abs(denom) < 1e-9:
            return None
        t = c / denom
        if t <= 0:
            return None
        return np.array([dx * t, dy * t, t], dtype=np.float64)

    origin = ray_to_plane((img_w - 1) * 0.5, img_h - 1.0)
    if origin is None:
        raise RuntimeError("Bottom-center ray does not hit the plane.")

    def plane_uv_m(p_raw: np.ndarray) -> tuple[float, float]:
        d = p_raw - origin
        return float(d @ e_lat) * scale, float(d @ e_fwd) * scale

    lat_min, lat_max = (float(s) for s in args.lateral_range.split(","))
    fwd_min, fwd_max = (float(s) for s in args.forward_range.split(","))
    mpp = args.meters_per_pixel
    bev_w = int(round((lat_max - lat_min) / mpp))
    bev_h = int(round((fwd_max - fwd_min) / mpp))

    cols, rows = np.meshgrid(np.arange(bev_w), np.arange(bev_h))
    lat = lat_min + (cols + 0.5) * mpp
    fwdm = fwd_max - (rows + 0.5) * mpp  # far at top of the image
    # BEV cell -> 3D point on plane (raw units) -> source pixel
    P = (
        origin[None, None, :]
        + e_lat[None, None, :] * (lat / scale)[..., None]
        + e_fwd[None, None, :] * (fwdm / scale)[..., None]
    )
    Pz = P[..., 2]
    with np.errstate(divide="ignore", invalid="ignore"):
        map_x = (fx * (P[..., 0] / Pz) + cx).astype(np.float32)
        map_y = (fy * (P[..., 1] / Pz) + cy).astype(np.float32)
    behind = Pz <= 1e-6
    map_x[behind] = -1
    map_y[behind] = -1
    bev = cv2.remap(image, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(30, 30, 30))

    def to_bev_px(lat_m: float, fwd_m: float) -> tuple[int, int]:
        cxp = int(round((lat_m - lat_min) / mpp - 0.5))
        cyp = int(round((fwd_max - fwd_m) / mpp - 0.5))
        return cxp, cyp

    # Meter grid: thin line each 5 m, labels on the left/bottom
    grid_color = (90, 90, 90)
    for gm in range(int(np.ceil(fwd_min / 5.0)) * 5, int(fwd_max) + 1, 5):
        x0, y0 = to_bev_px(lat_min, gm)
        x1, y1 = to_bev_px(lat_max, gm)
        cv2.line(bev, (x0, y0), (x1, y1), grid_color, 1)
        cv2.putText(bev, f"{gm}m", (6, y0 - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
    for gm in range(int(np.ceil(lat_min / 5.0)) * 5, int(lat_max) + 1, 5):
        x0, y0 = to_bev_px(gm, fwd_min)
        x1, y1 = to_bev_px(gm, fwd_max)
        cv2.line(bev, (x0, y0), (x1, y1), grid_color, 1)

    # Scale bar: 4 m reference (the legal dash length)
    sb_x0, sb_y = 20, bev_h - 30
    sb_x1 = sb_x0 + int(round(4.0 / mpp))
    cv2.line(bev, (sb_x0, sb_y), (sb_x1, sb_y), (255, 255, 255), 3)
    cv2.putText(bev, "4 m", (sb_x0, sb_y - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

    # Calibrated dashes from lane_dash_calibration.json, drawn where they land
    # on the plane -- on a correct metric BEV they must measure their legal length.
    if args.anchors_json:
        d = json.loads(Path(args.anchors_json).read_text())
        for row in d.get("dashes", []):
            p1 = ray_to_plane(*row["tip_near_px"])
            p2 = ray_to_plane(*row["tip_far_px"])
            if p1 is None or p2 is None:
                continue
            l1 = plane_uv_m(p1)
            l2 = plane_uv_m(p2)
            q1 = to_bev_px(*l1)
            q2 = to_bev_px(*l2)
            cv2.line(bev, q1, q2, (0, 255, 0), 3)
            if row.get("length_3d_raw_m") is not None:
                mid = ((q1[0] + q2[0]) // 2 + 8, (q1[1] + q2[1]) // 2)
                text = f"{row['length_3d_raw_m'] * scale:.2f}m"
                cv2.putText(bev, text, mid, cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 4)
                cv2.putText(bev, text, mid, cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

    # Vehicle trajectories from the speed pipeline, top-down with speed labels
    if args.tracks_json:
        d = json.loads(Path(args.tracks_json).read_text())
        reported = {r["track_id"]: r for r in d.get("speeds", [])}
        rng = np.random.default_rng(11)
        for tid_s, rec in d.get("tracks", {}).items():
            tid = int(tid_s)
            if tid not in reported:
                continue
            hcol = int(rng.integers(0, 180))
            col = cv2.cvtColor(np.uint8([[[hcol, 220, 255]]]), cv2.COLOR_HSV2BGR)[0, 0]
            color = (int(col[0]), int(col[1]), int(col[2]))
            pts = []
            for o in rec["obs"]:
                p_raw = np.array(o["pos_m"], dtype=np.float64) / scale
                pts.append(to_bev_px(*plane_uv_m(p_raw)))
            for p, q in zip(pts[:-1], pts[1:]):
                cv2.line(bev, p, q, color, 2)
            if pts:
                r = reported[tid]
                cv2.circle(bev, pts[-1], 5, color, -1)
                label = f"id{tid} {r['speed_kmh']:.0f}km/h"
                cv2.putText(bev, label, (pts[-1][0] + 6, pts[-1][1] - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 4)
                cv2.putText(bev, label, (pts[-1][0] + 6, pts[-1][1] - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)

    out = Path(args.out)
    if not out.is_absolute():
        out = PROJECT_ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), bev)
    print(f"saved: {out}  ({bev_w}x{bev_h}px @ {mpp}m/px)")


if __name__ == "__main__":
    main()
