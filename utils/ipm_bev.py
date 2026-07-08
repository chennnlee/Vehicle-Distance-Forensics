from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

import cv2
import numpy as np


@dataclass(frozen=True)
class IPMBEVConfig:
    x_range_m: Tuple[float, float] = (0.0, 40.0)
    y_range_m: Tuple[float, float] = (-12.0, 12.0)
    output_size: Tuple[int, int] = (800, 800)
    camera_height_m: float = 1.6
    pitch_deg: float = 15.0
    fov_deg: float = 90.0
    yaw_deg: float = 0.0


@dataclass(frozen=True)
class PseudoPointCloudBEVConfig:
    x_range_m: Tuple[float, float] = (0.0, 40.0)
    y_range_m: Tuple[float, float] = (-12.0, 12.0)
    output_size: Tuple[int, int] = (800, 800)
    camera_height_m: float = 1.6
    pitch_deg: float = 15.0
    fov_deg: float = 90.0
    height_range_m: Tuple[float, float] = (-20.0, 20.0)
    sampling_stride: int = 1


@dataclass(frozen=True)
class PointCloudBEVConfig:
    x_range_m: Tuple[float, float] = (0.0, 40.0)
    y_range_m: Tuple[float, float] = (-12.0, 12.0)
    output_size: Tuple[int, int] = (800, 800)
    camera_height_m: float = 1.6
    pitch_deg: float = 15.0
    height_range_m: Tuple[float, float] = (-1.0, 3.0)
    sampling_stride: int = 1
    grid_resolution_m: float = 0.05
    blur_kernel_px: int = 1
    density_gamma: float = 0.75
    draw_grid: bool = False


@dataclass(frozen=True)
class GroundPlaneModel:
    a: float
    b: float
    c: float
    residual_median_m: float
    inlier_ratio: float
    sample_count: int

    def normal(self) -> np.ndarray:
        # Plane is y = a*x + b*z + c, i.e. a*x - y + b*z + c = 0.
        # Its gradient (a, -1, b) points toward smaller y, which is "up" in the
        # OpenCV y-down convention used throughout this project.
        return np.array([self.a, -1.0, self.b], dtype=np.float32)


def _fit_plane_least_squares(points_xyz: np.ndarray) -> tuple[float, float, float]:
    design = np.column_stack([points_xyz[:, 0], points_xyz[:, 2], np.ones(points_xyz.shape[0], dtype=np.float32)])
    target = points_xyz[:, 1]
    coeff, *_ = np.linalg.lstsq(design, target, rcond=None)
    return float(coeff[0]), float(coeff[1]), float(coeff[2])


def _rotation_matrix_from_vectors(source: np.ndarray, target: np.ndarray) -> np.ndarray:
    source = np.asarray(source, dtype=np.float32)
    target = np.asarray(target, dtype=np.float32)
    source_norm = np.linalg.norm(source)
    target_norm = np.linalg.norm(target)
    if source_norm <= 0 or target_norm <= 0:
        return np.eye(3, dtype=np.float32)

    source = source / source_norm
    target = target / target_norm
    cross = np.cross(source, target)
    dot = float(np.clip(np.dot(source, target), -1.0, 1.0))
    cross_norm = float(np.linalg.norm(cross))

    if cross_norm <= 1e-8:
        if dot > 0.0:
            return np.eye(3, dtype=np.float32)

        helper = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        if abs(float(np.dot(helper, source))) > 0.9:
            helper = np.array([0.0, 0.0, 1.0], dtype=np.float32)
        axis = np.cross(source, helper)
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

    vx = np.array(
        [
            [0.0, -cross[2], cross[1]],
            [cross[2], 0.0, -cross[0]],
            [-cross[1], cross[0], 0.0],
        ],
        dtype=np.float32,
    )
    return np.eye(3, dtype=np.float32) + vx + vx @ vx * ((1.0 - dot) / max(1e-8, cross_norm * cross_norm))


# Reject a fitted "ground" plane tilted more than 45 degrees from horizontal
# (tan(45 deg) == 1.0). A close-following vehicle body or a wall filling the
# lower-image candidate window can otherwise win RANSAC and be accepted as
# ground, corrupting height-above-ground for every point measured against it.
MAX_GROUND_TILT_SLOPE_SQ = 1.0


def _is_plausible_ground_tilt(a: float, b: float) -> bool:
    return (a * a + b * b) <= MAX_GROUND_TILT_SLOPE_SQ


def fit_ground_plane_ransac(
    points_xyz: np.ndarray,
    uv: np.ndarray,
    valid_projection: np.ndarray,
    image_shape: tuple[int, int],
    lower_frac: float = 0.45,
    threshold_m: float = 0.18,
    iterations: int = 240,
) -> GroundPlaneModel | None:
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

    threshold_m = float(threshold_m)
    if threshold_m <= 0:
        a, b, c = _fit_plane_least_squares(sample)
        if not _is_plausible_ground_tilt(a, b):
            return None
        residual = np.abs(sample[:, 1] - (a * sample[:, 0] + b * sample[:, 2] + c))
        return GroundPlaneModel(
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
    iterations = max(1, int(iterations))

    for _ in range(iterations):
        idx = rng.choice(sample.shape[0], size=3, replace=False)
        picked = sample[idx]
        try:
            a, b, c = _fit_plane_least_squares(picked)
        except np.linalg.LinAlgError:
            continue
        residual = np.abs(sample[:, 1] - (a * sample[:, 0] + b * sample[:, 2] + c))
        inliers = residual <= max(1e-3, threshold_m)
        count = int(np.count_nonzero(inliers))
        if count > best_count:
            best_count = count
            best_inliers = inliers

    if best_inliers is None or best_count < 20:
        return None

    inlier_points = sample[best_inliers]
    a, b, c = _fit_plane_least_squares(inlier_points)
    if not _is_plausible_ground_tilt(a, b):
        return None
    residual = np.abs(inlier_points[:, 1] - (a * inlier_points[:, 0] + b * inlier_points[:, 2] + c))
    return GroundPlaneModel(
        a=a,
        b=b,
        c=c,
        residual_median_m=float(np.median(residual)) if residual.size else 0.0,
        inlier_ratio=float(best_count / sample.shape[0]),
        sample_count=int(sample.shape[0]),
    )


def align_points_to_ground(
    points_xyz: np.ndarray,
    plane: GroundPlaneModel,
    anchor_point: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    points_xyz = np.asarray(points_xyz, dtype=np.float32)
    if points_xyz.ndim != 2 or points_xyz.shape[1] < 3:
        raise ValueError("points_xyz must have shape Nx3 or Nx6")

    if anchor_point is None:
        median_x = float(np.median(points_xyz[:, 0])) if points_xyz.size else 0.0
        median_z = float(np.median(points_xyz[:, 2])) if points_xyz.size else 0.0
        anchor_y = plane.a * median_x + plane.b * median_z + plane.c
        anchor_point = np.array([median_x, anchor_y, median_z], dtype=np.float32)
    else:
        anchor_point = np.asarray(anchor_point, dtype=np.float32).reshape(3)

    rotation = _rotation_matrix_from_vectors(plane.normal(), np.array([0.0, 1.0, 0.0], dtype=np.float32))
    aligned = (rotation @ (points_xyz[:, :3] - anchor_point).T).T.astype(np.float32, copy=False)
    return aligned, rotation, anchor_point


def _validate_config(config: IPMBEVConfig) -> None:
    x_min, x_max = config.x_range_m
    y_min, y_max = config.y_range_m
    out_w, out_h = config.output_size
    if x_max <= x_min:
        raise ValueError("IPM x_range_m 必須滿足 max > min")
    if y_max <= y_min:
        raise ValueError("IPM y_range_m 必須滿足 max > min")
    if out_w <= 0 or out_h <= 0:
        raise ValueError("IPM output_size 必須為正整數")
    if config.camera_height_m <= 0:
        raise ValueError("IPM camera_height_m 必須大於 0")
    if config.fov_deg <= 0 or config.fov_deg >= 180:
        raise ValueError("IPM fov_deg 必須介於 0 與 180 之間")


def _rotation_matrix_yaw_pitch(yaw_deg: float, pitch_deg: float) -> np.ndarray:
    yaw = np.deg2rad(yaw_deg)
    pitch = np.deg2rad(pitch_deg)

    cy, sy = np.cos(yaw), np.sin(yaw)
    cp, sp = np.cos(pitch), np.sin(pitch)

    rot_yaw = np.array([
        [cy, -sy, 0.0],
        [sy, cy, 0.0],
        [0.0, 0.0, 1.0],
    ], dtype=np.float32)

    rot_pitch = np.array([
        [cp, 0.0, sp],
        [0.0, 1.0, 0.0],
        [-sp, 0.0, cp],
    ], dtype=np.float32)

    return rot_pitch @ rot_yaw


def _draw_bev_grid(image_bgr: np.ndarray, x_range_m: tuple[float, float], y_range_m: tuple[float, float]) -> np.ndarray:
    grid = image_bgr.copy()
    out_h, out_w = grid.shape[:2]
    x_min, x_max = x_range_m
    y_min, y_max = y_range_m

    meters_per_px_x = max(1e-6, (y_max - y_min) / max(1, out_w))
    meters_per_px_y = max(1e-6, (x_max - x_min) / max(1, out_h))

    minor_step_m = 1.0
    major_step_m = 5.0
    minor_step_x = max(1, int(round(minor_step_m / meters_per_px_x)))
    minor_step_y = max(1, int(round(minor_step_m / meters_per_px_y)))
    major_step_x = max(minor_step_x, int(round(major_step_m / meters_per_px_x)))
    major_step_y = max(minor_step_y, int(round(major_step_m / meters_per_px_y)))

    for x in range(0, out_w, minor_step_x):
        color = (55, 55, 55) if x % major_step_x else (170, 170, 170)
        cv2.line(grid, (x, 0), (x, out_h - 1), color, 1, cv2.LINE_AA)
    for y in range(0, out_h, minor_step_y):
        color = (55, 55, 55) if y % major_step_y else (170, 170, 170)
        cv2.line(grid, (0, y), (out_w - 1, y), color, 1, cv2.LINE_AA)

    alpha = 0.22
    return cv2.addWeighted(grid, alpha, image_bgr, 1.0 - alpha, 0)


def _build_camera_matrix(width: int, height: int, fov_deg: float) -> np.ndarray:
    fov_rad = np.deg2rad(fov_deg)
    focal = width / (2.0 * np.tan(fov_rad / 2.0))
    cx = (width - 1) * 0.5
    cy = (height - 1) * 0.5
    return np.array([
        [focal, 0.0, cx],
        [0.0, focal, cy],
        [0.0, 0.0, 1.0],
    ], dtype=np.float32)


def build_ipm_homography(image_width: int, image_height: int, config: IPMBEVConfig) -> np.ndarray:
    """建立從地面平面到影像平面的單應矩陣。"""
    _validate_config(config)
    K = _build_camera_matrix(image_width, image_height, config.fov_deg)
    R = _rotation_matrix_yaw_pitch(config.yaw_deg, config.pitch_deg)
    t = np.array([[0.0], [config.camera_height_m], [0.0]], dtype=np.float32)

    # Ground plane in world coordinates: X forward, Y right, Z up = 0.
    # Homography from ground plane [X, Y, 1] to image: H = K * [r1 r2 t]
    H = K @ np.hstack([R[:, 0:1], R[:, 1:2], t])
    return H.astype(np.float32)


def warp_image_to_bev(
    image_bgr: np.ndarray,
    config: IPMBEVConfig = IPMBEVConfig(),
) -> tuple[np.ndarray, dict[str, float]]:
    """把原始影像透過地面平面 IPM 轉成鳥瞰圖。

    這是近似的地面平面鳥瞰，不依賴深度圖；沒有實際相機標定時，
    需要靠 camera height / pitch / fov 近似。
    """
    if image_bgr is None or image_bgr.ndim != 3:
        raise ValueError("image_bgr 必須是 HxWx3 的影像陣列")

    img_h, img_w = image_bgr.shape[:2]
    x_min, x_max = config.x_range_m
    y_min, y_max = config.y_range_m
    out_w, out_h = config.output_size

    fov_rad = np.deg2rad(config.fov_deg)
    fx = img_w / (2.0 * np.tan(fov_rad / 2.0))
    fy = fx
    cx = (img_w - 1) * 0.5
    cy = (img_h - 1) * 0.5

    x_vals = np.linspace(x_min, x_max, out_h, dtype=np.float32)
    y_vals = np.linspace(y_max, y_min, out_w, dtype=np.float32)
    ground_x, ground_y = np.meshgrid(x_vals, y_vals, indexing="ij")

    pitch = np.deg2rad(config.pitch_deg)
    cos_p = np.cos(pitch)
    sin_p = np.sin(pitch)

    denom = ground_x * cos_p + config.camera_height_m * sin_p
    valid = denom > 1e-6

    cam_x = ground_y
    cam_y = config.camera_height_m * cos_p - ground_x * sin_p

    map_x = fx * (cam_x / np.clip(denom, 1e-6, None)) + cx
    map_y = fy * (cam_y / np.clip(denom, 1e-6, None)) + cy

    map_x = map_x.astype(np.float32)
    map_y = map_y.astype(np.float32)

    bev = cv2.remap(
        image_bgr,
        map_x,
        map_y,
        interpolation=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0),
    )

    valid = valid & (map_x >= 0) & (map_x < img_w) & (map_y >= 0) & (map_y < img_h)
    coverage = float(np.count_nonzero(valid) / valid.size)
    return bev, {
        "ipm_coverage": coverage,
        "ipm_camera_height_m": float(config.camera_height_m),
        "ipm_pitch_deg": float(config.pitch_deg),
    }


def save_ipm_bev(image_bgr: np.ndarray, output_path: str | Path, config: IPMBEVConfig = IPMBEVConfig()) -> tuple[np.ndarray, dict[str, float]]:
    bev, stats = warp_image_to_bev(image_bgr, config)
    cv2.imwrite(str(output_path), bev)
    return bev, stats


def _project_depth_to_vehicle_frame(
    depth: np.ndarray,
    image_bgr: np.ndarray,
    config: PseudoPointCloudBEVConfig,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    if depth.ndim != 2:
        raise ValueError("depth 必須是 HxW 的單通道陣列")
    if image_bgr is None or image_bgr.ndim != 3:
        raise ValueError("image_bgr 必須是 HxWx3 的影像陣列")
    if depth.shape[:2] != image_bgr.shape[:2]:
        raise ValueError("depth 與 image_bgr 的尺寸必須一致")

    stride = max(1, int(config.sampling_stride))
    depth_sample = depth[::stride, ::stride].astype(np.float32)
    color_sample = image_bgr[::stride, ::stride].astype(np.float32)

    img_h, img_w = depth.shape[:2]
    fov_rad = np.deg2rad(config.fov_deg)
    fx = img_w / (2.0 * np.tan(fov_rad / 2.0))
    fy = fx
    cx = (img_w - 1) * 0.5
    cy = (img_h - 1) * 0.5

    grid_y, grid_x = np.mgrid[0:img_h:stride, 0:img_w:stride]
    grid_x = grid_x.astype(np.float32)
    grid_y = grid_y.astype(np.float32)

    x_cam = (grid_x - cx) / fx * depth_sample
    y_cam = (grid_y - cy) / fy * depth_sample
    z_cam = depth_sample

    pitch = np.deg2rad(config.pitch_deg)
    cos_p = np.cos(pitch)
    sin_p = np.sin(pitch)

    forward_m = z_cam * cos_p - y_cam * sin_p
    right_m = x_cam
    height_m = config.camera_height_m - (z_cam * sin_p + y_cam * cos_p)

    valid = np.isfinite(depth_sample) & (depth_sample > 0)
    valid &= np.isfinite(forward_m) & np.isfinite(right_m) & np.isfinite(height_m)
    x_min, x_max = config.x_range_m
    y_min, y_max = config.y_range_m
    h_min, h_max = config.height_range_m
    valid &= (forward_m >= x_min) & (forward_m <= x_max)
    valid &= (right_m >= y_min) & (right_m <= y_max)
    valid &= (height_m >= h_min) & (height_m <= h_max)

    if not np.any(valid):
        empty = np.zeros((0,), dtype=np.float32)
        return empty, empty, empty, empty

    return forward_m[valid], right_m[valid], height_m[valid], color_sample[valid].astype(np.float32)


def project_depth_to_pointcloud_bev(
    image_bgr: np.ndarray,
    depth: np.ndarray,
    config: PseudoPointCloudBEVConfig = PseudoPointCloudBEVConfig(),
) -> tuple[np.ndarray, dict[str, float]]:
    """把 Metric3D 深度圖反投影成偽點雲，再俯視投影成 BEV。"""
    if image_bgr is None or image_bgr.ndim != 3:
        raise ValueError("image_bgr 必須是 HxWx3 的影像陣列")
    if depth is None or depth.ndim != 2:
        raise ValueError("depth 必須是 HxW 的單通道陣列")

    out_w, out_h = config.output_size
    x_min, x_max = config.x_range_m
    y_min, y_max = config.y_range_m

    forward_m, right_m, height_m, color_bgr = _project_depth_to_vehicle_frame(depth, image_bgr, config)
    if forward_m.size == 0:
        bev = np.zeros((out_h, out_w, 3), dtype=np.uint8)
        return bev, {
            "pcd_coverage": 0.0,
            "pcd_points": 0.0,
            "pcd_peak_height_m": 0.0,
            "pcd_mean_height_m": 0.0,
        }

    row = ((x_max - forward_m) / max(1e-6, (x_max - x_min)) * (out_h - 1)).astype(np.int32)
    col = ((right_m - y_min) / max(1e-6, (y_max - y_min)) * (out_w - 1)).astype(np.int32)
    in_bounds = (row >= 0) & (row < out_h) & (col >= 0) & (col < out_w)
    if not np.any(in_bounds):
        bev = np.zeros((out_h, out_w, 3), dtype=np.uint8)
        return bev, {
            "pcd_coverage": 0.0,
            "pcd_points": float(forward_m.size),
            "pcd_peak_height_m": float(np.max(height_m)) if height_m.size else 0.0,
            "pcd_mean_height_m": float(np.mean(height_m)) if height_m.size else 0.0,
        }

    row = row[in_bounds]
    col = col[in_bounds]
    height_m = height_m[in_bounds]
    color_bgr = color_bgr[in_bounds]

    flat_index = row * out_w + col
    cell_count = np.zeros(out_h * out_w, dtype=np.float32)
    height_max = np.full(out_h * out_w, -np.inf, dtype=np.float32)
    color_sum = np.zeros((out_h * out_w, 3), dtype=np.float32)

    np.add.at(cell_count, flat_index, 1.0)
    np.add.at(color_sum, flat_index, color_bgr)
    np.maximum.at(height_max, flat_index, height_m)

    count_map = cell_count.reshape(out_h, out_w)
    height_map = height_max.reshape(out_h, out_w)
    occupied_mask = count_map > 0

    color_mean = np.zeros((out_h * out_w, 3), dtype=np.float32)
    occupied_flat = occupied_mask.reshape(-1)
    if np.any(occupied_flat):
        color_mean[occupied_flat] = color_sum[occupied_flat] / cell_count[occupied_flat, None]
    color_mean = color_mean.reshape(out_h, out_w, 3)

    density_norm = np.zeros((out_h, out_w), dtype=np.float32)
    if np.any(occupied_mask):
        density_norm[occupied_mask] = np.log1p(count_map[occupied_mask])
        density_norm /= max(1e-6, float(density_norm.max()))

    h_min, h_max = config.height_range_m
    height_norm = np.zeros((out_h, out_w), dtype=np.float32)
    finite_height = np.isfinite(height_map)
    if np.any(finite_height):
        height_norm[finite_height] = np.clip((height_map[finite_height] - h_min) / max(1e-6, (h_max - h_min)), 0.0, 1.0)

    height_u8 = (height_norm * 255.0).astype(np.uint8)
    height_col = cv2.applyColorMap(height_u8, cv2.COLORMAP_TURBO)
    density_u8 = (density_norm * 255.0).astype(np.uint8)
    density_col = cv2.cvtColor(density_u8, cv2.COLOR_GRAY2BGR)
    color_u8 = np.clip(color_mean, 0.0, 255.0).astype(np.uint8)

    bev = cv2.addWeighted(height_col, 0.72, density_col, 0.18, 0.0)
    bev = cv2.addWeighted(bev, 0.85, color_u8, 0.15, 0.0)
    bev[~occupied_mask] = 0

    coverage = float(np.count_nonzero(count_map) / count_map.size)
    return bev, {
        "pcd_coverage": coverage,
        "pcd_points": float(row.size),
        "pcd_peak_height_m": float(np.max(height_m)) if height_m.size else 0.0,
        "pcd_mean_height_m": float(np.mean(height_m)) if height_m.size else 0.0,
        "pcd_height_min_m": float(h_min),
        "pcd_height_max_m": float(h_max),
    }


def save_pointcloud_bev(
    image_bgr: np.ndarray,
    depth: np.ndarray,
    output_path: str | Path,
    config: PseudoPointCloudBEVConfig = PseudoPointCloudBEVConfig(),
) -> tuple[np.ndarray, dict[str, float]]:
    bev, stats = project_depth_to_pointcloud_bev(image_bgr, depth, config)
    cv2.imwrite(str(output_path), bev)
    return bev, stats


def project_pointcloud_to_bev(
    points_xyz: np.ndarray,
    colors_bgr: np.ndarray | None = None,
    config: PointCloudBEVConfig = PointCloudBEVConfig(),
) -> tuple[np.ndarray, dict[str, float]]:
    """Project a SHARP camera-frame point cloud to a 2D BEV density map.

    The expected coordinate convention matches SHARP's output: x right, y down,
    z forward. The raster is built on the x-z plane so the result looks like a
    top-down map rather than a point-cloud scatter plot.
    """
    if points_xyz is None:
        raise ValueError("points_xyz cannot be None")

    points_xyz = np.asarray(points_xyz)
    if points_xyz.ndim != 2 or points_xyz.shape[1] < 3:
        raise ValueError("points_xyz must have shape Nx3 or Nx6")

    if colors_bgr is not None:
        colors_bgr = np.asarray(colors_bgr)
        if colors_bgr.ndim != 2 or colors_bgr.shape[0] != points_xyz.shape[0] or colors_bgr.shape[1] < 3:
            raise ValueError("colors_bgr must have shape Nx3 and match points_xyz")

    stride = max(1, int(config.sampling_stride))
    points_xyz = points_xyz[::stride, :3].astype(np.float32, copy=False)
    if colors_bgr is not None:
        colors_bgr = colors_bgr[::stride, :3].astype(np.float32, copy=False)

    x_cam = points_xyz[:, 0]
    y_cam = points_xyz[:, 1]
    z_cam = points_xyz[:, 2]

    right_m = x_cam
    forward_m = z_cam
    # SHARP exports OpenCV-style camera coordinates: x right, y down, z forward.
    # Convert y-down camera coordinates into approximate height above the road.
    height_m = float(config.camera_height_m) - y_cam

    valid = np.isfinite(points_xyz).all(axis=1)
    valid &= np.isfinite(forward_m) & np.isfinite(right_m) & np.isfinite(height_m)
    x_min, x_max = config.x_range_m
    y_min, y_max = config.y_range_m
    h_min, h_max = config.height_range_m
    valid &= (forward_m >= x_min) & (forward_m <= x_max)
    valid &= (right_m >= y_min) & (right_m <= y_max)
    valid &= (height_m >= h_min) & (height_m <= h_max)

    if not np.any(valid):
        out_w, out_h = config.output_size
        bev = np.zeros((out_h, out_w, 3), dtype=np.uint8)
        return bev, {
            "pcd_coverage": 0.0,
            "pcd_points": 0.0,
            "pcd_peak_height_m": 0.0,
            "pcd_mean_height_m": 0.0,
            "pcd_height_min_m": float(h_min),
            "pcd_height_max_m": float(h_max),
        }

    forward_m = forward_m[valid]
    right_m = right_m[valid]
    height_m = height_m[valid]

    out_w, out_h = config.output_size

    grid_res = max(1e-3, float(config.grid_resolution_m))
    grid_h = max(1, int(np.ceil((x_max - x_min) / grid_res)))
    grid_w = max(1, int(np.ceil((y_max - y_min) / grid_res)))

    row = np.floor((x_max - forward_m) / grid_res).astype(np.int32)
    col = np.floor((right_m - y_min) / grid_res).astype(np.int32)
    in_bounds = (row >= 0) & (row < grid_h) & (col >= 0) & (col < grid_w)
    if not np.any(in_bounds):
        bev = np.zeros((out_h, out_w, 3), dtype=np.uint8)
        return bev, {
            "pcd_coverage": 0.0,
            "pcd_points": float(forward_m.size),
            "pcd_peak_height_m": float(np.max(height_m)) if height_m.size else 0.0,
            "pcd_mean_height_m": float(np.mean(height_m)) if height_m.size else 0.0,
            "pcd_height_min_m": float(h_min),
            "pcd_height_max_m": float(h_max),
        }

    row = row[in_bounds]
    col = col[in_bounds]
    height_m = height_m[in_bounds]
    if colors_bgr is not None:
        colors_bgr = colors_bgr[valid][in_bounds]

    flat_index = row * grid_w + col
    count_map = np.zeros(grid_h * grid_w, dtype=np.float32)
    height_max = np.full(grid_h * grid_w, -np.inf, dtype=np.float32)
    color_sum = None
    if colors_bgr is not None:
        color_sum = np.zeros((grid_h * grid_w, 3), dtype=np.float32)

    np.add.at(count_map, flat_index, 1.0)
    np.maximum.at(height_max, flat_index, height_m)
    if color_sum is not None:
        np.add.at(color_sum, flat_index, colors_bgr)

    count_map = count_map.reshape(grid_h, grid_w)
    height_map = height_max.reshape(grid_h, grid_w)

    density = np.log1p(count_map)
    blur_kernel = int(config.blur_kernel_px)
    if blur_kernel > 1:
        blur_kernel = max(3, blur_kernel | 1)
    if blur_kernel > 1:
        density = cv2.GaussianBlur(density, (blur_kernel, blur_kernel), 0)

    finite_density = np.isfinite(density)
    if np.any(finite_density):
        density = density / max(1e-6, float(density[finite_density].max()))
    density = np.power(np.clip(density, 0.0, 1.0), max(1e-3, float(config.density_gamma)))
    density[density < 0.03] = 0.0

    if color_sum is not None:
        color_map = color_sum.reshape(grid_h, grid_w, 3)
        occupied = count_map > 0
        if np.any(occupied):
            color_map = np.divide(
                color_map,
                count_map[..., None],
                out=np.zeros_like(color_map),
                where=occupied[..., None],
            )
        if blur_kernel > 1:
            color_map = cv2.GaussianBlur(color_map, (blur_kernel, blur_kernel), 0)
        density_scale = np.sqrt(np.clip(density, 0.0, 1.0))[..., None]
        bev_small = np.clip(color_map * (0.30 + 0.70 * density_scale), 0.0, 255.0).astype(np.uint8)
    else:
        density_u8 = (density * 255.0).astype(np.uint8)
        bev_small = cv2.applyColorMap(density_u8, cv2.COLORMAP_TURBO)
    bev = cv2.resize(bev_small, (out_w, out_h), interpolation=cv2.INTER_CUBIC)
    if config.draw_grid:
        bev = _draw_bev_grid(bev, config.x_range_m, config.y_range_m)

    occupied_mask = count_map > 0
    coverage = float(np.count_nonzero(occupied_mask) / occupied_mask.size)
    return bev, {
        "pcd_coverage": coverage,
        "pcd_points": float(row.size),
        "pcd_peak_height_m": float(np.max(height_m)) if height_m.size else 0.0,
        "pcd_mean_height_m": float(np.mean(height_m)) if height_m.size else 0.0,
        "pcd_height_min_m": float(h_min),
        "pcd_height_max_m": float(h_max),
    }


def project_aligned_pointcloud_to_bev(
    points_xyz: np.ndarray,
    colors_bgr: np.ndarray | None = None,
    config: PointCloudBEVConfig = PointCloudBEVConfig(),
) -> tuple[np.ndarray, dict[str, float]]:
    """Project a ground-aligned point cloud onto the BEV x-z plane.

    The input is expected to already be rotated so the fitted ground plane is
    horizontal. The aligned y coordinate is treated as height above the ground
    plane, while x and z form the 2D bird's-eye map.
    """
    if points_xyz is None:
        raise ValueError("points_xyz cannot be None")

    points_xyz = np.asarray(points_xyz)
    if points_xyz.ndim != 2 or points_xyz.shape[1] < 3:
        raise ValueError("points_xyz must have shape Nx3 or Nx6")

    if colors_bgr is not None:
        colors_bgr = np.asarray(colors_bgr)
        if colors_bgr.ndim != 2 or colors_bgr.shape[0] != points_xyz.shape[0] or colors_bgr.shape[1] < 3:
            raise ValueError("colors_bgr must have shape Nx3 and match points_xyz")

    stride = max(1, int(config.sampling_stride))
    points_xyz = points_xyz[::stride, :3].astype(np.float32, copy=False)
    if colors_bgr is not None:
        colors_bgr = colors_bgr[::stride, :3].astype(np.float32, copy=False)

    forward_m = points_xyz[:, 2]
    right_m = points_xyz[:, 0]
    height_m = points_xyz[:, 1]

    valid = np.isfinite(points_xyz).all(axis=1)
    valid &= np.isfinite(forward_m) & np.isfinite(right_m) & np.isfinite(height_m)
    x_min, x_max = config.x_range_m
    y_min, y_max = config.y_range_m
    h_min, h_max = config.height_range_m
    valid &= (forward_m >= x_min) & (forward_m <= x_max)
    valid &= (right_m >= y_min) & (right_m <= y_max)
    valid &= (height_m >= h_min) & (height_m <= h_max)

    if not np.any(valid):
        out_w, out_h = config.output_size
        bev = np.zeros((out_h, out_w, 3), dtype=np.uint8)
        return bev, {
            "pcd_coverage": 0.0,
            "pcd_points": 0.0,
            "pcd_peak_height_m": 0.0,
            "pcd_mean_height_m": 0.0,
            "pcd_height_min_m": float(h_min),
            "pcd_height_max_m": float(h_max),
        }

    forward_m = forward_m[valid]
    right_m = right_m[valid]
    height_m = height_m[valid]

    out_w, out_h = config.output_size

    grid_res = max(1e-3, float(config.grid_resolution_m))
    grid_h = max(1, int(np.ceil((x_max - x_min) / grid_res)))
    grid_w = max(1, int(np.ceil((y_max - y_min) / grid_res)))

    row = np.floor((x_max - forward_m) / grid_res).astype(np.int32)
    col = np.floor((right_m - y_min) / grid_res).astype(np.int32)
    in_bounds = (row >= 0) & (row < grid_h) & (col >= 0) & (col < grid_w)
    if not np.any(in_bounds):
        bev = np.zeros((out_h, out_w, 3), dtype=np.uint8)
        return bev, {
            "pcd_coverage": 0.0,
            "pcd_points": float(forward_m.size),
            "pcd_peak_height_m": float(np.max(height_m)) if height_m.size else 0.0,
            "pcd_mean_height_m": float(np.mean(height_m)) if height_m.size else 0.0,
            "pcd_height_min_m": float(h_min),
            "pcd_height_max_m": float(h_max),
        }

    row = row[in_bounds]
    col = col[in_bounds]
    height_m = height_m[in_bounds]
    if colors_bgr is not None:
        colors_bgr = colors_bgr[valid][in_bounds]

    flat_index = row * grid_w + col
    count_map = np.zeros(grid_h * grid_w, dtype=np.float32)
    height_max = np.full(grid_h * grid_w, -np.inf, dtype=np.float32)
    color_sum = None
    if colors_bgr is not None:
        color_sum = np.zeros((grid_h * grid_w, 3), dtype=np.float32)

    np.add.at(count_map, flat_index, 1.0)
    np.maximum.at(height_max, flat_index, height_m)
    if color_sum is not None:
        np.add.at(color_sum, flat_index, colors_bgr)

    count_map = count_map.reshape(grid_h, grid_w)
    height_map = height_max.reshape(grid_h, grid_w)

    density = np.log1p(count_map)
    blur_kernel = int(config.blur_kernel_px)
    if blur_kernel > 1:
        blur_kernel = max(3, blur_kernel | 1)
    if blur_kernel > 1:
        density = cv2.GaussianBlur(density, (blur_kernel, blur_kernel), 0)

    finite_density = np.isfinite(density)
    if np.any(finite_density):
        density = density / max(1e-6, float(density[finite_density].max()))
    density = np.power(np.clip(density, 0.0, 1.0), max(1e-3, float(config.density_gamma)))
    density[density < 0.03] = 0.0

    if color_sum is not None:
        color_map = color_sum.reshape(grid_h, grid_w, 3)
        occupied = count_map > 0
        if np.any(occupied):
            color_map = np.divide(
                color_map,
                count_map[..., None],
                out=np.zeros_like(color_map),
                where=occupied[..., None],
            )
        if blur_kernel > 1:
            color_map = cv2.GaussianBlur(color_map, (blur_kernel, blur_kernel), 0)
        density_scale = np.sqrt(np.clip(density, 0.0, 1.0))[..., None]
        bev_small = np.clip(color_map * (0.30 + 0.70 * density_scale), 0.0, 255.0).astype(np.uint8)
    else:
        density_u8 = (density * 255.0).astype(np.uint8)
        bev_small = cv2.applyColorMap(density_u8, cv2.COLORMAP_TURBO)
    bev = cv2.resize(bev_small, (out_w, out_h), interpolation=cv2.INTER_CUBIC)
    if config.draw_grid:
        bev = _draw_bev_grid(bev, config.x_range_m, config.y_range_m)

    occupied_mask = count_map > 0
    coverage = float(np.count_nonzero(occupied_mask) / occupied_mask.size)
    return bev, {
        "pcd_coverage": coverage,
        "pcd_points": float(row.size),
        "pcd_peak_height_m": float(np.max(height_m)) if height_m.size else 0.0,
        "pcd_mean_height_m": float(np.mean(height_m)) if height_m.size else 0.0,
        "pcd_height_min_m": float(h_min),
        "pcd_height_max_m": float(h_max),
    }


def save_ground_aligned_pointcloud_bev_from_points(
    points_xyz: np.ndarray,
    output_path: str | Path,
    colors_bgr: np.ndarray | None = None,
    config: PointCloudBEVConfig = PointCloudBEVConfig(),
) -> tuple[np.ndarray, dict[str, float]]:
    bev, stats = project_aligned_pointcloud_to_bev(points_xyz, colors_bgr, config)
    cv2.imwrite(str(output_path), bev)
    return bev, stats


def save_pointcloud_bev_from_points(
    points_xyz: np.ndarray,
    output_path: str | Path,
    colors_bgr: np.ndarray | None = None,
    config: PointCloudBEVConfig = PointCloudBEVConfig(),
) -> tuple[np.ndarray, dict[str, float]]:
    bev, stats = project_pointcloud_to_bev(points_xyz, colors_bgr, config)
    cv2.imwrite(str(output_path), bev)
    return bev, stats
