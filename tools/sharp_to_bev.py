from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from utils.ipm_bev import (
    GroundPlaneModel,
    PointCloudBEVConfig,
    align_points_to_ground,
    fit_ground_plane_ransac,
    save_ground_aligned_pointcloud_bev_from_points,
    save_pointcloud_bev_from_points,
)
from utils.pointcloud_io import load_point_cloud_points


SUPPORTED_POINT_CLOUD_EXTENSIONS = {".ply", ".npy", ".npz", ".xyz", ".txt", ".csv"}
SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}


def build_intrinsics(width: int, height: int, metadata: dict[str, object], fov_deg: float) -> tuple[float, float, float, float, str]:
    ply_intrinsics = metadata.get("intrinsics") if metadata is not None else None
    if isinstance(ply_intrinsics, dict) and ply_intrinsics.get("fx") is not None:
        image_size = metadata.get("image_size") if metadata is not None else None
        source_width = width
        source_height = height
        if isinstance(image_size, dict):
            source_width = int(image_size.get("width", width) or width)
            source_height = int(image_size.get("height", height) or height)

        sx = width / max(1, source_width)
        sy = height / max(1, source_height)
        fx = float(ply_intrinsics["fx"]) * sx
        fy_value = ply_intrinsics.get("fy")
        fy = float(fy_value if fy_value is not None else ply_intrinsics["fx"]) * sy
        cx_value = ply_intrinsics.get("cx")
        cy_value = ply_intrinsics.get("cy")
        cx = float(cx_value) * sx if cx_value is not None else (width - 1) * 0.5
        cy = float(cy_value) * sy if cy_value is not None else (height - 1) * 0.5
        return fx, fy, cx, cy, "ply_intrinsic_3x3"

    fov_rad = np.deg2rad(float(fov_deg))
    fx = width / (2.0 * np.tan(fov_rad / 2.0))
    fy = fx
    cx = (width - 1) * 0.5
    cy = (height - 1) * 0.5
    return fx, fy, cx, cy, "fallback_fov"


def project_points(points_xyz: np.ndarray, fx: float, fy: float, cx: float, cy: float) -> tuple[np.ndarray, np.ndarray]:
    z = points_xyz[:, 2]
    valid = np.isfinite(points_xyz).all(axis=1) & (z > 1e-6)
    uv = np.full((points_xyz.shape[0], 2), np.nan, dtype=np.float32)
    uv[valid, 0] = fx * (points_xyz[valid, 0] / z[valid]) + cx
    uv[valid, 1] = fy * (points_xyz[valid, 1] / z[valid]) + cy
    return uv, valid


def parse_pair(text: str, label: str) -> tuple[float, float]:
    parts = [part.strip() for part in text.split(",") if part.strip()]
    if len(parts) != 2:
        raise ValueError(f"{label} must use min,max")
    return float(parts[0]), float(parts[1])


def parse_size(text: str) -> tuple[int, int]:
    parts = [part.strip() for part in text.split(",") if part.strip()]
    if len(parts) != 2:
        raise ValueError("--output-size must use width,height")
    return int(parts[0]), int(parts[1])


def resolve_reference_image(reference_root: Path, stem: str) -> Path | None:
    if reference_root.is_file():
        return reference_root
    if not reference_root.is_dir():
        return None

    for candidate in sorted(reference_root.glob(f"{stem}.*")):
        if candidate.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS:
            return candidate
    return None


def normalize_cli_args(argv: list[str]) -> list[str]:
    normalized: list[str] = []
    index = 0
    range_options = {"--x-range", "--y-range", "--height-range"}

    while index < len(argv):
        token = argv[index]
        if token in range_options and index + 1 < len(argv):
            next_token = argv[index + 1]
            if next_token.startswith("-") and not next_token.startswith("--"):
                normalized.append(f"{token}={next_token}")
                index += 2
                continue

        normalized.append(token)
        index += 1

    return normalized


def collect_point_cloud_files(input_path: Path) -> list[Path]:
    if input_path.is_file():
        return [input_path]
    if input_path.is_dir():
        return sorted(path for path in input_path.rglob("*") if path.suffix.lower() in SUPPORTED_POINT_CLOUD_EXTENSIONS)
    raise FileNotFoundError(f"Point cloud path not found: {input_path}")


def write_report(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Render SHARP 3DGS point clouds into BEV images.")
    parser.add_argument("--input", required=True, help="SHARP output folder or a single point-cloud file.")
    parser.add_argument("--out-dir", required=True, help="Output directory for BEV images and report.json.")
    parser.add_argument("--reference-image", type=str, default="", help="Optional original image folder/file to save as a separate reference copy.")
    parser.add_argument("--fov-deg", type=float, default=70.0, help="Fallback horizontal FOV used when PLY metadata lacks intrinsics.")
    parser.add_argument("--x-range", type=str, default="0,40", help="Forward range in meters: min,max")
    parser.add_argument("--y-range", type=str, default="-12,12", help="Left/right range in meters: min,max")
    parser.add_argument("--output-size", type=str, default="800,800", help="Output size in pixels: width,height")
    parser.add_argument("--camera-height", type=float, default=1.6, help="Camera height in meters used for the BEV projection")
    parser.add_argument("--pitch-deg", type=float, default=15.0, help="Camera pitch in degrees; positive means looking down")
    parser.add_argument("--height-range", type=str, default="-1,3", help="Height range in meters: min,max")
    parser.add_argument("--grid-resolution", type=float, default=0.05, help="Internal BEV grid resolution in meters.")
    parser.add_argument("--blur-kernel", type=int, default=1, help="Odd blur kernel in internal grid pixels; 1 disables blur.")
    parser.add_argument("--sample-stride", type=int, default=1, help="Keep every Nth point before BEV projection")
    parser.add_argument("--scale-factor", type=float, default=1.0, help="Optional metric scale multiplier applied before BEV projection.")
    parser.add_argument("--align-ground", dest="align_ground", action="store_true", help="Fit and align the dominant ground plane before BEV projection.")
    parser.add_argument("--no-align-ground", dest="align_ground", action="store_false", help="Skip ground-plane alignment and keep the original camera-frame BEV projection.")
    parser.set_defaults(align_ground=True)
    args = parser.parse_args(normalize_cli_args(sys.argv[1:]))

    input_path = Path(args.input)
    if not input_path.is_absolute():
        input_path = PROJECT_ROOT / input_path

    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = PROJECT_ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    reference_root: Path | None = None
    if args.reference_image.strip():
        reference_root = Path(args.reference_image)
        if not reference_root.is_absolute():
            reference_root = PROJECT_ROOT / reference_root

    config = PointCloudBEVConfig(
        x_range_m=parse_pair(args.x_range, "--x-range"),
        y_range_m=parse_pair(args.y_range, "--y-range"),
        output_size=parse_size(args.output_size),
        camera_height_m=args.camera_height,
        pitch_deg=args.pitch_deg,
        height_range_m=parse_pair(args.height_range, "--height-range"),
        sampling_stride=max(1, int(args.sample_stride)),
        grid_resolution_m=float(args.grid_resolution),
        blur_kernel_px=max(1, int(args.blur_kernel)),
    )

    files = collect_point_cloud_files(input_path)
    if not files:
        raise FileNotFoundError(f"No supported point cloud files found under: {input_path}")

    outputs: list[dict[str, object]] = []
    for file_path in files:
        try:
            points, colors_rgb, metadata = load_point_cloud_points(file_path)
            colors_bgr = None if colors_rgb is None else colors_rgb[:, ::-1].astype(np.float32, copy=False)
            points = points.astype(np.float32, copy=False)

            if not np.isfinite(args.scale_factor) or args.scale_factor <= 0:
                raise ValueError("--scale-factor must be a positive finite number")
            if args.scale_factor != 1.0:
                points = points * float(args.scale_factor)

            alignment_report: dict[str, object] | None = None
            bev_output = None
            output_path = out_dir / f"{file_path.stem}_bev.png"

            if args.align_ground:
                if isinstance(metadata.get("intrinsics"), dict):
                    image_size = metadata.get("image_size") if isinstance(metadata.get("image_size"), dict) else {}
                    width = int(image_size.get("width", 0) or 0)
                    height = int(image_size.get("height", 0) or 0)
                    if width > 0 and height > 0:
                        fx, fy, cx, cy, intrinsics_source = build_intrinsics(width, height, metadata, args.fov_deg)
                        uv, valid_projection = project_points(points, fx, fy, cx, cy)
                        plane = fit_ground_plane_ransac(points, uv, valid_projection, (height, width))
                        if plane is not None:
                            aligned_points, rotation, anchor_point = align_points_to_ground(points, plane)
                            bev_output, stats = save_ground_aligned_pointcloud_bev_from_points(aligned_points, output_path, colors_bgr, config)
                            alignment_report = {
                                "enabled": True,
                                "intrinsics_source": intrinsics_source,
                                "plane": {
                                    "model": "y = a*x + b*z + c",
                                    "a": plane.a,
                                    "b": plane.b,
                                    "c": plane.c,
                                    "residual_median_m": plane.residual_median_m,
                                    "inlier_ratio": plane.inlier_ratio,
                                    "sample_count": plane.sample_count,
                                },
                                "rotation_matrix": rotation.tolist(),
                                "anchor_point": anchor_point.tolist(),
                            }
                        else:
                            alignment_report = {"enabled": True, "status": "ground_fit_failed"}
                    else:
                        alignment_report = {"enabled": True, "status": "missing_intrinsics_metadata"}
                else:
                    alignment_report = {"enabled": True, "status": "missing_intrinsics_metadata"}

            if bev_output is None:
                bev_output, stats = save_pointcloud_bev_from_points(points, output_path, colors_bgr, config)
                if alignment_report is None:
                    alignment_report = {"enabled": False}

            ply_output = out_dir / f"{file_path.stem}.ply"
            shutil.copy2(file_path, ply_output)

            reference_output = None
            reference_image_path = None
            if reference_root is not None:
                reference_image_path = resolve_reference_image(reference_root, file_path.stem)
                if reference_image_path is not None:
                    reference_output = out_dir / f"{file_path.stem}_reference{reference_image_path.suffix.lower()}"
                    shutil.copy2(reference_image_path, reference_output)

            outputs.append({
                "input": str(file_path),
                "ply_output": str(ply_output),
                "output": str(output_path),
                "status": "ok",
                "metadata": metadata,
                "reference_image": str(reference_image_path) if reference_image_path is not None else None,
                "reference_output": str(reference_output) if reference_output is not None else None,
                "pcd_coverage": float(stats["pcd_coverage"]),
                "pcd_points": float(stats["pcd_points"]),
                "pcd_peak_height_m": float(stats["pcd_peak_height_m"]),
                "pcd_mean_height_m": float(stats["pcd_mean_height_m"]),
                "pcd_height_min_m": float(stats["pcd_height_min_m"]),
                "pcd_height_max_m": float(stats["pcd_height_max_m"]),
                "alignment": alignment_report,
            })
        except Exception as exc:
            outputs.append({
                "input": str(file_path),
                "status": "error",
                "error": str(exc),
            })

    report = {
        "input": str(input_path),
        "output_dir": str(out_dir),
        "mode": "sharp_to_bev",
        "config": {
            "x_range_m": list(config.x_range_m),
            "y_range_m": list(config.y_range_m),
            "output_size_px": {"width": int(config.output_size[0]), "height": int(config.output_size[1])},
            "camera_height_m": float(config.camera_height_m),
            "pitch_deg": float(config.pitch_deg),
            "height_range_m": list(config.height_range_m),
            "sampling_stride": int(config.sampling_stride),
            "grid_resolution_m": float(config.grid_resolution_m),
            "blur_kernel_px": int(config.blur_kernel_px),
            "scale_factor": float(args.scale_factor),
            "align_ground": bool(args.align_ground),
            "fov_deg": float(args.fov_deg),
        },
        "outputs": outputs,
    }
    write_report(out_dir / "report.json", report)
    print(f"Wrote BEV report to {out_dir / 'report.json'}")


if __name__ == "__main__":
    main()
