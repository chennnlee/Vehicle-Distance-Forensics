from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from utils.pointcloud_io import load_point_cloud_points


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}
POINT_CLOUD_EXTENSIONS = {".ply", ".npy", ".npz", ".xyz", ".txt", ".csv"}


@dataclass(frozen=True)
class CameraIntrinsics:
    fx: float
    fy: float
    cx: float
    cy: float


@dataclass(frozen=True)
class GroundPlane:
    a: float
    b: float
    c: float
    residual_median_m: float
    inlier_ratio: float
    sample_count: int

    def ground_y(self, points_xyz: np.ndarray) -> np.ndarray:
        return self.a * points_xyz[:, 0] + self.b * points_xyz[:, 2] + self.c

    def height_above_ground(self, points_xyz: np.ndarray, y_axis_convention: str) -> np.ndarray:
        ground_y = self.ground_y(points_xyz)
        if y_axis_convention == "opencv-y-down":
            return ground_y - points_xyz[:, 1]
        if y_axis_convention == "opengl-y-up":
            return points_xyz[:, 1] - ground_y
        raise ValueError(f"Unsupported y-axis convention: {y_axis_convention}")


@dataclass(frozen=True)
class Detection:
    xyxy: np.ndarray
    score: float
    label: int
    name: str
    mask: np.ndarray | None = None  # (H, W) bool silhouette from YOLO-seg, if available


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Measure vehicle distances by fusing YOLO detections with SHARP point-cloud PLY output."
    )
    parser.add_argument("--image", required=True, help="Input image file or image folder.")
    parser.add_argument("--pointcloud", required=True, help="Matching SHARP point cloud file or folder.")
    parser.add_argument("--out-dir", required=True, help="Output directory for overlays and CSV/JSON reports.")
    parser.add_argument(
        "--yolo-model",
        default="checkpoints/yolov8m-seg.pt",
        help="Ultralytics YOLO model name or local path. Segmentation (-seg) checkpoints enable precise "
        "mask-based point selection; plain detection checkpoints fall back to --bbox-vertical-slice.",
    )
    parser.add_argument("--conf", type=float, default=0.25, help="YOLO confidence threshold.")
    parser.add_argument("--iou", type=float, default=0.45, help="YOLO NMS IoU threshold.")
    parser.add_argument(
        "--classes",
        default="2,3,5,7",
        help="COCO class IDs to keep, comma separated. Default keeps car, motorcycle, bus, truck.",
    )
    parser.add_argument("--fov-deg", type=float, default=70.0, help="Fallback horizontal FOV used to project PLY points.")
    parser.add_argument("--fx", type=float, default=0.0, help="Optional camera fx. Overrides --fov-deg when set.")
    parser.add_argument("--fy", type=float, default=0.0, help="Optional camera fy. Defaults to fx when omitted.")
    parser.add_argument("--cx", type=float, default=-1.0, help="Optional camera cx. Defaults to image center.")
    parser.add_argument("--cy", type=float, default=-1.0, help="Optional camera cy. Defaults to image center.")
    parser.add_argument(
        "--pointcloud-scale",
        type=float,
        default=1.0,
        help="Multiply PLY xyz coordinates by this factor before measuring. Use this for anchor-based scale correction.",
    )
    parser.add_argument("--min-depth", type=float, default=0.2, help="Minimum usable z depth in meters.")
    parser.add_argument("--max-depth", type=float, default=120.0, help="Maximum usable z depth in meters.")
    parser.add_argument("--bbox-padding-frac", type=float, default=0.04, help="Expand YOLO boxes before collecting points.")
    parser.add_argument(
        "--bbox-vertical-slice",
        type=float,
        default=0.55,
        help="Keep only the lower fraction of each vehicle box when collecting points. 1.0 uses the full box.",
    )
    parser.add_argument(
        "--y-axis-convention",
        choices=("opencv-y-down", "opengl-y-up"),
        default="opencv-y-down",
        help="PLY vertical axis convention. SHARP/OpenCV uses y down, z forward.",
    )
    parser.add_argument(
        "--ground-mode",
        choices=("auto", "none"),
        default="auto",
        help="Use auto ground-plane fit to handle non-flat y-axis point clouds.",
    )
    parser.add_argument(
        "--ground-lower-frac",
        type=float,
        default=0.45,
        help="Use projected points in the lower image fraction for automatic ground fitting.",
    )
    parser.add_argument(
        "--ground-ransac-threshold",
        type=float,
        default=0.18,
        help="RANSAC inlier threshold in meters. Values <= 0 skip RANSAC and use least-squares on all candidates.",
    )
    parser.add_argument("--ground-ransac-iters", type=int, default=240, help="RANSAC iterations for ground fitting.")
    parser.add_argument(
        "--object-height-range",
        default="0.05,4.0",
        help="Height above fitted ground plane to keep inside vehicle boxes, min,max meters.",
    )
    parser.add_argument("--min-object-points", type=int, default=20, help="Minimum points required for ok status.")
    parser.add_argument(
        "--max-distance-iqr",
        type=float,
        default=8.0,
        help="Maximum allowed distance interquartile range in meters before marking a detection unstable.",
    )
    parser.add_argument("--overlay-max-points", type=int, default=1200, help="Maximum projected points drawn per detection overlay.")
    parser.add_argument(
        "--align-ground",
        action="store_true",
        help="Rotate point cloud to make fitted ground plane horizontal (BEV alignment).",
    )
    parser.add_argument(
        "--anchor-pt1",
        default=None,
        help="Comma-separated pixel coordinates x,y for anchor point 1 used for scale calibration.",
    )
    parser.add_argument(
        "--anchor-pt2",
        default=None,
        help="Comma-separated pixel coordinates x,y for anchor point 2 used for scale calibration.",
    )
    parser.add_argument(
        "--anchor-length-m",
        type=float,
        default=0.0,
        help="Real-world length in meters between anchor-pt1 and anchor-pt2 for scale calibration.",
    )
    return parser.parse_args()


def parse_classes(text: str) -> set[int]:
    return {int(part.strip()) for part in text.split(",") if part.strip()}


def parse_pair(text: str, label: str) -> tuple[float, float]:
    parts = [part.strip() for part in text.split(",") if part.strip()]
    if len(parts) != 2:
        raise ValueError(f"{label} must use min,max")
    lo, hi = float(parts[0]), float(parts[1])
    if hi <= lo:
        raise ValueError(f"{label} must satisfy max > min")
    return lo, hi


def collect_files(path: Path, extensions: set[str]) -> list[Path]:
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted(p for p in path.rglob("*") if p.suffix.lower() in extensions)
    raise FileNotFoundError(f"Path not found: {path}")


def pair_inputs(image_path: Path, pointcloud_path: Path) -> list[tuple[Path, Path]]:
    images = collect_files(image_path, IMAGE_EXTENSIONS)
    clouds = collect_files(pointcloud_path, POINT_CLOUD_EXTENSIONS)

    if len(images) == 1 and len(clouds) == 1:
        return [(images[0], clouds[0])]

    if len(images) != len(clouds) and (len(images) == 1 or len(clouds) == 1):
        raise RuntimeError(
            "Ambiguous image/pointcloud pairing: provide one image with one point cloud, "
            "or folders with matching file stems."
        )

    clouds_by_stem = {p.stem: p for p in clouds}
    pairs: list[tuple[Path, Path]] = []
    for img in images:
        cloud = clouds_by_stem.get(img.stem)
        if cloud is not None:
            pairs.append((img, cloud))

    if not pairs:
        raise RuntimeError("No matching image/pointcloud stem pairs found. Filenames must share the same stem.")
    return pairs


def build_intrinsics(width: int, height: int, args: argparse.Namespace, metadata: dict[str, object] | None = None) -> CameraIntrinsics:
    if args.fx > 0:
        fx = float(args.fx)
        fy = float(args.fy) if args.fy > 0 else fx
        cx = float(args.cx) if args.cx >= 0 else (width - 1) * 0.5
        cy = float(args.cy) if args.cy >= 0 else (height - 1) * 0.5
        return CameraIntrinsics(fx=fx, fy=fy, cx=cx, cy=cy)

    ply_intrinsics = None if metadata is None else metadata.get("intrinsics")
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
    else:
        fov_rad = np.deg2rad(float(args.fov_deg))
        fx = width / (2.0 * np.tan(fov_rad / 2.0))
        fy = fx
        cx = (width - 1) * 0.5
        cy = (height - 1) * 0.5

    if args.fy > 0:
        fy = float(args.fy)
    if args.cx >= 0:
        cx = float(args.cx)
    if args.cy >= 0:
        cy = float(args.cy)
    return CameraIntrinsics(fx=fx, fy=fy, cx=cx, cy=cy)


def project_points(points_xyz: np.ndarray, intr: CameraIntrinsics) -> tuple[np.ndarray, np.ndarray]:
    z = points_xyz[:, 2]
    # Keep only points in front of the camera; negative z is behind the camera.
    valid = np.isfinite(points_xyz).all(axis=1) & (z > 1e-6)
    uv = np.full((points_xyz.shape[0], 2), np.nan, dtype=np.float32)
    uv[valid, 0] = intr.fx * (points_xyz[valid, 0] / z[valid]) + intr.cx
    uv[valid, 1] = intr.fy * (points_xyz[valid, 1] / z[valid]) + intr.cy
    return uv, valid


def rotation_matrix_from_vectors(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    # Return rotation matrix that rotates vector a to vector b
    a = a / np.linalg.norm(a)
    b = b / np.linalg.norm(b)
    v = np.cross(a, b)
    c = float(np.dot(a, b))
    s = np.linalg.norm(v)
    if s <= 1e-8:
        if c > 0.0:
            return np.eye(3, dtype=np.float32)
        # a and b are antiparallel: no unique rotation axis from cross(a, b).
        # Pick any axis perpendicular to a and rotate 180 degrees about it.
        helper = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        if abs(float(np.dot(helper, a))) > 0.9:
            helper = np.array([0.0, 0.0, 1.0], dtype=np.float32)
        axis = np.cross(a, helper)
        axis /= max(1e-8, float(np.linalg.norm(axis)))
        x, y, z = axis
        return np.array(
            [
                [-1.0 + 2.0 * x * x, 2.0 * x * y, 2.0 * x * z],
                [2.0 * x * y, -1.0 + 2.0 * y * y, 2.0 * y * z],
                [2.0 * x * z, 2.0 * y * z, -1.0 + 2.0 * z * z],
            ],
            dtype=np.float32,
        )
    kmat = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]], dtype=np.float32)
    r = np.eye(3, dtype=np.float32) + kmat + kmat.dot(kmat) * ((1 - c) / (s * s))
    return r.astype(np.float32)


def align_point_cloud_to_ground(points_xyz: np.ndarray, ground: GroundPlane) -> tuple[np.ndarray, GroundPlane, dict[str, float]]:
    # ground: y = a*x + b*z + c  => plane normal (a, -1, b) points "up" in the
    # OpenCV y-down convention (smaller y = higher).
    a, b = ground.a, ground.b
    n = np.array([a, -1.0, b], dtype=np.float32)
    target = np.array([0.0, 1.0, 0.0], dtype=np.float32)
    R = rotation_matrix_from_vectors(n, target)
    rotated = points_xyz.dot(R.T)
    # The ground plane is now horizontal in the rotated frame: every point that
    # was on the original plane rotates to the same y value. Re-derive that
    # constant instead of reusing the pre-rotation (a, b, c), which no longer
    # applies to the rotated x/z coordinates.
    origin_on_plane = np.array([0.0, ground.c, 0.0], dtype=np.float32)
    rotated_c = float(R.dot(origin_on_plane)[1])
    rotated_ground = GroundPlane(
        a=0.0,
        b=0.0,
        c=rotated_c,
        residual_median_m=ground.residual_median_m,
        inlier_ratio=ground.inlier_ratio,
        sample_count=ground.sample_count,
    )
    return rotated, rotated_ground, {"rotation_applied": True, "rotation_matrix": R.tolist()}


def fit_plane_least_squares(points_xyz: np.ndarray) -> tuple[float, float, float]:
    design = np.column_stack([points_xyz[:, 0], points_xyz[:, 2], np.ones(points_xyz.shape[0], dtype=np.float32)])
    target = points_xyz[:, 1]
    coeff, *_ = np.linalg.lstsq(design, target, rcond=None)
    return float(coeff[0]), float(coeff[1]), float(coeff[2])


# Reject a fitted "ground" plane tilted more than 45 degrees from horizontal
# (tan(45 deg) == 1.0). A close-following vehicle body or a wall filling the
# lower-image candidate window can otherwise win RANSAC and be accepted as
# ground, corrupting height-above-ground for every detection in the frame.
MAX_GROUND_TILT_SLOPE_SQ = 1.0


def _is_plausible_ground_tilt(a: float, b: float) -> bool:
    return (a * a + b * b) <= MAX_GROUND_TILT_SLOPE_SQ


def fit_ground_plane(
    points_xyz: np.ndarray,
    uv: np.ndarray,
    valid_projection: np.ndarray,
    image_shape: tuple[int, int],
    lower_frac: float,
    threshold_m: float,
    iterations: int,
) -> GroundPlane | None:
    height, width = image_shape
    lower_start = height * (1.0 - np.clip(lower_frac, 0.05, 0.95))
    # valid_projection already requires np.isfinite(points_xyz).all(axis=1)
    # (see project_points), so no need to recheck it here.
    candidates = valid_projection.copy()
    candidates &= (uv[:, 0] >= 0) & (uv[:, 0] < width)
    candidates &= (uv[:, 1] >= lower_start) & (uv[:, 1] < height)

    sample = points_xyz[candidates]
    if sample.shape[0] < 30:
        return None

    ransac_threshold_m = float(threshold_m)
    if ransac_threshold_m <= 0:
        a, b, c = fit_plane_least_squares(sample)
        if not _is_plausible_ground_tilt(a, b):
            return None
        residual = np.abs(sample[:, 1] - (a * sample[:, 0] + b * sample[:, 2] + c))
        return GroundPlane(
            a=a,
            b=b,
            c=c,
            residual_median_m=float(np.median(residual)) if residual.size else float("nan"),
            inlier_ratio=1.0,
            sample_count=int(sample.shape[0]),
        )

    rng = np.random.default_rng(114)
    best_inliers: np.ndarray | None = None
    best_count = 0
    ransac_threshold_m = max(1e-3, ransac_threshold_m)
    iterations = max(1, int(iterations))

    for _ in range(iterations):
        idx = rng.choice(sample.shape[0], size=3, replace=False)
        picked = sample[idx]
        try:
            a, b, c = fit_plane_least_squares(picked)
        except np.linalg.LinAlgError:
            continue
        residual = np.abs(sample[:, 1] - (a * sample[:, 0] + b * sample[:, 2] + c))
        inliers = residual <= ransac_threshold_m
        count = int(np.count_nonzero(inliers))
        if count > best_count:
            best_count = count
            best_inliers = inliers

    if best_inliers is None or best_count < 20:
        return None

    inlier_points = sample[best_inliers]
    a, b, c = fit_plane_least_squares(inlier_points)
    if not _is_plausible_ground_tilt(a, b):
        return None
    residual = np.abs(inlier_points[:, 1] - (a * inlier_points[:, 0] + b * inlier_points[:, 2] + c))
    return GroundPlane(
        a=a,
        b=b,
        c=c,
        residual_median_m=float(np.median(residual)) if residual.size else 0.0,
        inlier_ratio=float(best_count / sample.shape[0]),
        sample_count=int(sample.shape[0]),
    )


def yolo_detections(result, keep_classes: set[int], image_shape: tuple[int, int]) -> list[Detection]:
    detections: list[Detection] = []
    names = getattr(result, "names", {}) or {}
    if result.boxes is None:
        return detections

    boxes = result.boxes.xyxy.detach().cpu().numpy().astype(np.float32)
    scores = result.boxes.conf.detach().cpu().numpy().astype(np.float32)
    labels = result.boxes.cls.detach().cpu().numpy().astype(np.int64)

    # result.masks.xy holds one polygon (in original-image pixel coords) per
    # detection, aligned by index with result.boxes -- Ultralytics guarantees
    # this ordering since both come from the same post-NMS detection list.
    mask_polys = None
    masks_obj = getattr(result, "masks", None)
    if masks_obj is not None:
        mask_polys = masks_obj.xy

    height, width = image_shape
    for i, (box, score, label) in enumerate(zip(boxes, scores, labels)):
        if int(label) not in keep_classes:
            continue
        mask = None
        if mask_polys is not None and i < len(mask_polys):
            poly = mask_polys[i]
            if poly is not None and len(poly) >= 3:
                canvas = np.zeros((height, width), dtype=np.uint8)
                cv2.fillPoly(canvas, [np.round(poly).astype(np.int32)], 1)
                mask = canvas.astype(bool)
        detections.append(
            Detection(
                xyxy=box,
                score=float(score),
                label=int(label),
                name=str(names.get(int(label), int(label))),
                mask=mask,
            )
        )
    return detections


def padded_box(box: np.ndarray, padding_frac: float, width: int, height: int) -> np.ndarray:
    x1, y1, x2, y2 = box.astype(np.float32)
    pad_x = (x2 - x1) * float(padding_frac)
    pad_y = (y2 - y1) * float(padding_frac)
    return np.array(
        [
            np.clip(x1 - pad_x, 0, width - 1),
            np.clip(y1 - pad_y, 0, height - 1),
            np.clip(x2 + pad_x, 0, width - 1),
            np.clip(y2 + pad_y, 0, height - 1),
        ],
        dtype=np.float32,
    )


def point_mask_for_detection(
    det: Detection,
    uv: np.ndarray,
    valid_points: np.ndarray,
    image_shape: tuple[int, int],
    args: argparse.Namespace,
    height_above_ground: np.ndarray | None,
    height_range: tuple[float, float],
) -> np.ndarray:
    height, width = image_shape

    # Depth-range gating already happened in valid_points (against camera-frame
    # z, before any --align-ground rotation). Re-checking points_xyz[:, 2] here
    # would be redundant when unrotated, and wrong when rotated -- after ground
    # alignment, z is a ground-plane axis, not camera-forward depth.
    mask = valid_points.copy()

    if det.mask is not None:
        # Precise per-instance silhouette from YOLO-seg. This replaces both the
        # bbox bounds and the vertical-slice heuristic below: the heuristic
        # assumes a car-like box where the lower half is vehicle body, which
        # systematically fails on tall/thin boxes (e.g. a motorcycle box that
        # includes the rider's torso) where the true body only covers a small,
        # oddly-shaped part of the box.
        # NaN coordinates (points already excluded via valid_points) must not
        # reach the int cast below -- float->int on NaN is platform-dependent
        # and can produce an out-of-bounds index into det.mask.
        safe_u = np.where(np.isfinite(uv[:, 0]), uv[:, 0], 0.0)
        safe_v = np.where(np.isfinite(uv[:, 1]), uv[:, 1], 0.0)
        u_idx = np.clip(np.round(safe_u), 0, width - 1).astype(np.int32)
        v_idx = np.clip(np.round(safe_v), 0, height - 1).astype(np.int32)
        mask &= det.mask[v_idx, u_idx]
    else:
        box = padded_box(det.xyxy, args.bbox_padding_frac, width, height)
        x1, y1, x2, y2 = box
        mask &= (uv[:, 0] >= x1) & (uv[:, 0] <= x2)
        mask &= (uv[:, 1] >= y1) & (uv[:, 1] <= y2)

        slice_frac = float(np.clip(args.bbox_vertical_slice, 0.05, 1.0))
        if slice_frac < 1.0:
            slice_y1 = y2 - (y2 - y1) * slice_frac
            mask &= uv[:, 1] >= slice_y1

    if height_above_ground is not None:
        mask &= (height_above_ground >= height_range[0]) & (height_above_ground <= height_range[1])

    return mask


def robust_stats(values: np.ndarray) -> dict[str, float]:
    if values.size == 0:
        nan = float("nan")
        return {
            "min": nan,
            "p10": nan,
            "p25": nan,
            "median": nan,
            "p75": nan,
            "mean": nan,
            "max": nan,
        }
    return {
        "min": float(np.min(values)),
        "p10": float(np.percentile(values, 10)),
        "p25": float(np.percentile(values, 25)),
        "median": float(np.median(values)),
        "p75": float(np.percentile(values, 75)),
        "mean": float(np.mean(values)),
        "max": float(np.max(values)),
    }


def draw_overlay(
    image_bgr: np.ndarray,
    detections: list[Detection],
    rows: list[dict[str, object]],
    uv: np.ndarray,
    point_masks: list[np.ndarray],
    output_path: Path,
    max_points_per_detection: int,
) -> None:
    canvas = image_bgr.copy()
    palette = [(0, 255, 0), (0, 220, 255), (255, 120, 0), (255, 0, 255), (80, 180, 255)]

    for idx, mask in enumerate(point_masks):
        pts = uv[mask]
        if pts.size:
            pts = pts[np.isfinite(pts).all(axis=1)]
            stride = max(1, int(np.ceil(pts.shape[0] / max(1, max_points_per_detection))))
            pts = pts[::stride]
            for u, v in pts.astype(np.int32):
                cv2.circle(canvas, (int(u), int(v)), 1, palette[idx % len(palette)], -1, cv2.LINE_AA)

    for idx, (det, row) in enumerate(zip(detections, rows)):
        color = (0, 255, 0) if row["status"] == "ok" else (0, 0, 255)
        x1, y1, x2, y2 = det.xyxy.astype(np.int32)
        cv2.rectangle(canvas, (x1, y1), (x2, y2), color, 2)
        if det.mask is not None:
            # Draw the actual segmentation silhouette so it's visually obvious
            # which pixels points were selected from, vs. the crude bbox above.
            contours, _ = cv2.findContours(det.mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            cv2.drawContours(canvas, contours, -1, color, 1, cv2.LINE_AA)
        distance_p10 = float(row["distance_p10_m"])
        distance_text = "nan" if np.isnan(distance_p10) else f"{distance_p10:.1f}"
        text = f"{idx} {det.name} {det.score:.2f} z10={distance_text}m"
        cv2.putText(canvas, text, (x1, max(20, y1 - 5)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2, cv2.LINE_AA)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), canvas)


def process_pair(
    image_path: Path,
    cloud_path: Path,
    model,
    keep_classes: set[int],
    args: argparse.Namespace,
    out_dir: Path,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    image = cv2.imread(str(image_path))
    if image is None:
        raise RuntimeError(f"Unable to read image: {image_path}")
    img_h, img_w = image.shape[:2]

    points_xyz, colors_rgb, metadata = load_point_cloud_points(cloud_path)
    pointcloud_scale = float(args.pointcloud_scale)
    if not np.isfinite(pointcloud_scale) or pointcloud_scale <= 0:
        raise ValueError("--pointcloud-scale must be a positive finite number")
    points_xyz = points_xyz * pointcloud_scale

    intr = build_intrinsics(img_w, img_h, args, metadata)
    uv, valid_projection = project_points(points_xyz, intr)
    # Camera-forward depth, kept separate from points_xyz because --align-ground
    # later rotates points_xyz so its z column stops meaning "depth from camera".
    # Uniform rescaling (pointcloud-scale / anchor calibration) preserves the uv
    # projection exactly (x/z and y/z ratios are scale-invariant), so uv and
    # valid_projection are computed once here and never need recomputing.
    camera_depth_z = points_xyz[:, 2].copy()
    valid_points = valid_projection.copy()
    valid_points &= (camera_depth_z >= args.min_depth) & (camera_depth_z <= args.max_depth)
    valid_points &= (uv[:, 0] >= 0) & (uv[:, 0] < img_w) & (uv[:, 1] >= 0) & (uv[:, 1] < img_h)

    ground = None
    if args.ground_mode == "auto":
        ground = fit_ground_plane(
            points_xyz,
            uv,
            valid_projection,
            image_shape=(img_h, img_w),
            lower_frac=args.ground_lower_frac,
            threshold_m=args.ground_ransac_threshold,
            iterations=args.ground_ransac_iters,
        )
    # Optionally align point cloud to ground (BEV). This only re-expresses each
    # point's 3D coordinates in a ground-horizontal frame; it does not move the
    # camera, so the original pixel projection (uv/valid_projection/valid_points,
    # computed above from the pre-rotation points_xyz) still correctly says which
    # pixel each point (by array index) belongs to. Re-projecting the rotated
    # points through the same camera intrinsics would treat them as if they were
    # still in the camera frame and produce pixel coordinates that match nothing
    # in the actual photo, so we deliberately do NOT recompute uv here. The
    # ground plane coefficients are replaced with the rotated ones so that
    # height-above-ground is computed against the frame points_xyz is now in.
    rotation_info: dict[str, object] | None = None
    height_axis_convention = args.y_axis_convention
    if args.align_ground and ground is not None:
        points_xyz, ground, rotation_info = align_point_cloud_to_ground(points_xyz, ground)
        # The rotation aligns "up" to +Y, so larger y now means higher above
        # ground regardless of the original point cloud's y-axis convention.
        height_axis_convention = "opengl-y-up"

    # Optional anchor-based scale calibration (provide two pixel coords and real length)
    scale_info: dict[str, object] | None = None
    if args.anchor_pt1 and args.anchor_pt2 and args.anchor_length_m > 0.0:
        try:
            x1s, y1s = [float(v) for v in str(args.anchor_pt1).split(",")]
            x2s, y2s = [float(v) for v in str(args.anchor_pt2).split(",")]
            p1 = np.array([x1s, y1s], dtype=np.float32)
            p2 = np.array([x2s, y2s], dtype=np.float32)
            radius_px = max(3.0, 0.01 * max(img_w, img_h))
            d1 = np.linalg.norm(uv - p1.reshape(1, 2), axis=1)
            d2 = np.linalg.norm(uv - p2.reshape(1, 2), axis=1)
            mask1 = (d1 <= radius_px) & valid_projection & np.isfinite(points_xyz).all(axis=1)
            mask2 = (d2 <= radius_px) & valid_projection & np.isfinite(points_xyz).all(axis=1)
            if int(np.count_nonzero(mask1)) >= 3 and int(np.count_nonzero(mask2)) >= 3:
                p3d_1 = np.median(points_xyz[mask1], axis=0)
                p3d_2 = np.median(points_xyz[mask2], axis=0)
                est = float(np.linalg.norm(p3d_1 - p3d_2))
                if est > 1e-6:
                    S = float(args.anchor_length_m) / est
                    points_xyz = points_xyz * S
                    camera_depth_z = camera_depth_z * S
                    if ground is not None:
                        # a/b are dimensionless slopes (invariant to uniform
                        # scaling); c is a meters offset and must scale with
                        # points_xyz, or height-above-ground would be off by
                        # c * (S - 1) after calibration.
                        ground = GroundPlane(
                            a=ground.a,
                            b=ground.b,
                            c=ground.c * S,
                            residual_median_m=ground.residual_median_m,
                            inlier_ratio=ground.inlier_ratio,
                            sample_count=ground.sample_count,
                        )
                    scale_info = {"anchor_pixels": [p1.tolist(), p2.tolist()], "anchor_length_m": args.anchor_length_m, "estimated_m": est, "scale": S}
                    # uv/valid_projection are unaffected by uniform rescaling
                    # (see comment above camera_depth_z) so only the depth
                    # portion of valid_points needs to be rebuilt here.
                    valid_points = valid_projection.copy()
                    valid_points &= (camera_depth_z >= args.min_depth) & (camera_depth_z <= args.max_depth)
                    valid_points &= (uv[:, 0] >= 0) & (uv[:, 0] < img_w) & (uv[:, 1] >= 0) & (uv[:, 1] < img_h)
        except Exception:
            scale_info = {"anchor_error": "failed_to_compute_anchor_scale"}

    # Run YOLO at the original image size to avoid letterbox/rescale mismatch
    try:
        yolo_result = model.predict(source=str(image_path), imgsz=(img_w, img_h), conf=args.conf, iou=args.iou, verbose=False)[0]
    except TypeError:
        yolo_result = model.predict(source=str(image_path), conf=args.conf, iou=args.iou, verbose=False)[0]
    detections = yolo_detections(yolo_result, keep_classes, image_shape=(img_h, img_w))
    height_range = parse_pair(args.object_height_range, "--object-height-range")

    # Computed once for the whole point cloud rather than once per detection --
    # ground and points_xyz don't change across the loop below.
    height_above_ground = ground.height_above_ground(points_xyz, height_axis_convention) if ground is not None else None

    rows: list[dict[str, object]] = []
    point_masks: list[np.ndarray] = []
    for obj_index, det in enumerate(detections):
        mask = point_mask_for_detection(
            det,
            uv,
            valid_points,
            image_shape=(img_h, img_w),
            args=args,
            height_above_ground=height_above_ground,
            height_range=height_range,
        )
        point_masks.append(mask)

        selected = points_xyz[mask]
        has_selected_points = selected.shape[0] > 0
        if has_selected_points and args.align_ground:
            # after aligning ground, measure planar ground distance (BEV): sqrt(x^2 + z^2)
            ground_distances = np.sqrt(np.square(selected[:, 0]) + np.square(selected[:, 2]))
            z_stats = robust_stats(ground_distances)
        else:
            z_stats = robust_stats(selected[:, 2] if has_selected_points else np.empty((0,), dtype=np.float32))

        if ground is not None and height_above_ground is not None and has_selected_points:
            h_stats = robust_stats(height_above_ground[mask])
        else:
            h_stats = robust_stats(np.empty((0,), dtype=np.float32))

        distance_iqr = z_stats["p75"] - z_stats["p25"] if has_selected_points else float("nan")
        if args.ground_mode == "auto" and ground is None:
            # Ground-plane fit failed (too few candidates, no plausible-tilt
            # RANSAC winner, etc.), so the height-above-ground filter above was
            # never applied -- only bbox/depth/vertical-slice gating ran. Any
            # points here, including road/background points, were kept
            # unfiltered, so this must not be silently reported as "ok".
            status = "weak_ground_plane"
        elif selected.shape[0] < int(args.min_object_points):
            status = "few_points"
        elif np.isfinite(distance_iqr) and distance_iqr > float(args.max_distance_iqr):
            status = "unstable_depth_iqr"
        else:
            status = "ok"
        x1, y1, x2, y2 = det.xyxy.tolist()
        rows.append(
            {
                "image": image_path.name,
                "pointcloud": cloud_path.name,
                "object_index": obj_index,
                "class_id": det.label,
                "class_name": det.name,
                "confidence": det.score,
                "x1": float(x1),
                "y1": float(y1),
                "x2": float(x2),
                "y2": float(y2),
                "point_count": int(selected.shape[0]),
                "distance_min_m": z_stats["min"],
                "distance_p10_m": z_stats["p10"],
                "distance_p25_m": z_stats["p25"],
                "distance_median_m": z_stats["median"],
                "distance_p75_m": z_stats["p75"],
                "distance_mean_m": z_stats["mean"],
                "distance_max_m": z_stats["max"],
                "distance_iqr_m": distance_iqr,
                "height_median_m": h_stats["median"],
                "height_min_m": h_stats["min"],
                "height_max_m": h_stats["max"],
                "used_segmentation_mask": det.mask is not None,
                "status": status,
            }
        )

    overlay_path = out_dir / "overlays" / f"{image_path.stem}_sharp_yolo_distance.png"
    draw_overlay(image, detections, rows, uv, point_masks, overlay_path, args.overlay_max_points)

    pair_summary = {
        "image": str(image_path),
        "pointcloud": str(cloud_path),
        "pointcloud_metadata": metadata,
        "image_size": {"width": img_w, "height": img_h},
        "intrinsics": {
            "fx": intr.fx,
            "fy": intr.fy,
            "cx": intr.cx,
            "cy": intr.cy,
            "source": "explicit_or_ply_metadata" if (args.fx > 0 or "intrinsics" in metadata) else "fallback_fov",
        },
        "projected_point_count": int(np.count_nonzero(valid_points)),
        "projected_point_ratio": float(np.count_nonzero(valid_points) / max(1, points_xyz.shape[0])),
        "detection_count": len(detections),
        "overlay": str(overlay_path),
        "ground_plane": None
        if ground is None
        else {
            "model": "y = a*x + b*z + c",
            "a": ground.a,
            "b": ground.b,
            "c": ground.c,
            "residual_median_m": ground.residual_median_m,
            "inlier_ratio": ground.inlier_ratio,
            "sample_count": ground.sample_count,
        },
        "alignment": rotation_info,
        "scale_info": scale_info,
    }
    return rows, pair_summary


def main() -> None:
    args = parse_args()
    image_path = Path(args.image)
    cloud_path = Path(args.pointcloud)
    out_dir = Path(args.out_dir)
    if not image_path.is_absolute():
        image_path = PROJECT_ROOT / image_path
    if not cloud_path.is_absolute():
        cloud_path = PROJECT_ROOT / cloud_path
    if not out_dir.is_absolute():
        out_dir = PROJECT_ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    pairs = pair_inputs(image_path, cloud_path)
    keep_classes = parse_classes(args.classes)

    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise RuntimeError("ultralytics is required. Install it with: pip install ultralytics") from exc

    model = YOLO(args.yolo_model)

    all_rows: list[dict[str, object]] = []
    summaries: list[dict[str, object]] = []
    for img, cloud in pairs:
        rows, summary = process_pair(img, cloud, model, keep_classes, args, out_dir)
        all_rows.extend(rows)
        summaries.append(summary)

    csv_path = out_dir / "sharp_yolo_distances.csv"
    fieldnames = [
        "image",
        "pointcloud",
        "object_index",
        "class_id",
        "class_name",
        "confidence",
        "x1",
        "y1",
        "x2",
        "y2",
        "point_count",
        "distance_min_m",
        "distance_p10_m",
        "distance_p25_m",
        "distance_median_m",
        "distance_p75_m",
        "distance_mean_m",
        "distance_max_m",
        "distance_iqr_m",
        "height_median_m",
        "height_min_m",
        "height_max_m",
        "used_segmentation_mask",
        "status",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)

    summary_path = out_dir / "sharp_yolo_distance_summary.json"
    summary = {
        "mode": "sharp_yolo_distance",
        "pair_count": len(pairs),
        "row_count": len(all_rows),
        "config": {
            "yolo_model": args.yolo_model,
            "conf": args.conf,
            "iou": args.iou,
            "classes": sorted(list(keep_classes)),
            "fov_deg": args.fov_deg,
            "pointcloud_scale": args.pointcloud_scale,
            "min_depth": args.min_depth,
            "max_depth": args.max_depth,
            "bbox_vertical_slice": args.bbox_vertical_slice,
            "y_axis_convention": args.y_axis_convention,
            "ground_mode": args.ground_mode,
            "object_height_range": args.object_height_range,
            "max_distance_iqr": args.max_distance_iqr,
            "overlay_max_points": args.overlay_max_points,
        },
        "pairs": summaries,
        "csv": str(csv_path),
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"saved_csv={csv_path.resolve()}")
    print(f"saved_summary={summary_path.resolve()}")
    print(f"saved_overlays={(out_dir / 'overlays').resolve()}")


if __name__ == "__main__":
    main()
