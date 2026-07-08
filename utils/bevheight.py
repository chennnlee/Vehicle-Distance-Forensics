from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

import cv2
import numpy as np


@dataclass(frozen=True)
class BEVHeightConfig:
    x_range_m: Tuple[float, float] = (-20.0, 20.0)
    z_range_m: Tuple[float, float] = (0.0, 60.0)
    height_range_m: Tuple[float, float] = (-3.0, 5.0)
    resolution_m: float = 0.2
    fov_deg: float = 90.0
    ground_start_ratio: float = 0.45
    pitch_deg: float = 0.0
    num_height_bins: int = 8


def _validate_config(config: BEVHeightConfig) -> None:
    x_min, x_max = config.x_range_m
    z_min, z_max = config.z_range_m
    h_min, h_max = config.height_range_m
    if x_max <= x_min:
        raise ValueError("BEVHeight x_range_m 必須滿足 max > min")
    if z_max <= z_min:
        raise ValueError("BEVHeight z_range_m 必須滿足 max > min")
    if h_max <= h_min:
        raise ValueError("BEVHeight height_range_m 必須滿足 max > min")
    if config.resolution_m <= 0:
        raise ValueError("BEVHeight resolution_m 必須大於 0")
    if not (0.0 <= config.ground_start_ratio < 1.0):
        raise ValueError("BEVHeight ground_start_ratio 必須介於 0 與 1 之間")
    if config.fov_deg <= 0 or config.fov_deg >= 180:
        raise ValueError("BEVHeight fov_deg 必須介於 0 與 180 之間")
    if config.num_height_bins <= 0:
        raise ValueError("BEVHeight num_height_bins 必須大於 0")


def _normalize_for_preview(image: np.ndarray) -> np.ndarray:
    normalized = cv2.normalize(image.astype(np.float32), None, 0, 255, cv2.NORM_MINMAX)
    return normalized.astype(np.uint8)


def _colorize(image: np.ndarray, colormap: int = cv2.COLORMAP_TURBO) -> np.ndarray:
    return cv2.applyColorMap(_normalize_for_preview(image), colormap)


def project_depth_to_bevheight(
    depth_map: np.ndarray, config: BEVHeightConfig = BEVHeightConfig()
) -> tuple[np.ndarray, dict[str, float]]:
    """將 metric depth 轉成簡易 BEVHeight 式的高度分層 BEV 表徵。"""
    if depth_map.ndim != 2:
        raise ValueError("depth_map 必須是 HxW 的 2D 陣列")

    _validate_config(config)

    depth = depth_map.astype(np.float32, copy=False)
    valid = np.isfinite(depth) & (depth > 0)

    h, w = depth.shape
    ground_row_start = int(h * config.ground_start_ratio)
    ground_mask = np.zeros_like(valid, dtype=bool)
    ground_mask[ground_row_start:, :] = True
    valid &= ground_mask

    ys, xs = np.where(valid)
    bev_h = int(np.ceil((config.z_range_m[1] - config.z_range_m[0]) / config.resolution_m))
    bev_w = int(np.ceil((config.x_range_m[1] - config.x_range_m[0]) / config.resolution_m))
    height_bins = np.zeros((config.num_height_bins, bev_h, bev_w), dtype=np.float32)
    occupancy = np.zeros((bev_h, bev_w), dtype=np.float32)
    max_height = np.full((bev_h, bev_w), config.height_range_m[0], dtype=np.float32)
    min_height = np.full((bev_h, bev_w), config.height_range_m[1], dtype=np.float32)
    sum_height = np.zeros((bev_h, bev_w), dtype=np.float32)
    count_height = np.zeros((bev_h, bev_w), dtype=np.float32)

    if ys.size == 0:
        preview = np.zeros((bev_h * 2, bev_w * 2, 3), dtype=np.uint8)
        return preview, {
            "bevheight_nonzero_ratio": 0.0,
            "bevheight_peak": 0.0,
            "bevheight_mean_height": 0.0,
            "bevheight_height_bins": float(config.num_height_bins),
        }

    depths = depth[ys, xs]

    fov_rad = np.deg2rad(config.fov_deg)
    fx = w / (2.0 * np.tan(fov_rad / 2.0))
    fy = fx
    cx = (w - 1) * 0.5
    cy = (h - 1) * 0.5

    x_cam = (xs.astype(np.float32) - cx) / fx * depths
    y_cam = (ys.astype(np.float32) - cy) / fy * depths
    z_cam = depths

    pitch_rad = np.deg2rad(config.pitch_deg)
    x_world = x_cam
    z_world = z_cam * np.cos(pitch_rad) + y_cam * np.sin(pitch_rad)
    height_world = y_cam * np.cos(pitch_rad) - z_cam * np.sin(pitch_rad)

    x_min, x_max = config.x_range_m
    z_min, z_max = config.z_range_m
    h_min, h_max = config.height_range_m

    range_mask = (
        (x_world >= x_min)
        & (x_world <= x_max)
        & (z_world >= z_min)
        & (z_world <= z_max)
        & (height_world >= h_min)
        & (height_world <= h_max)
    )

    if not np.any(range_mask):
        preview = np.zeros((bev_h * 2, bev_w * 2, 3), dtype=np.uint8)
        return preview, {
            "bevheight_nonzero_ratio": 0.0,
            "bevheight_peak": 0.0,
            "bevheight_mean_height": 0.0,
            "bevheight_height_bins": float(config.num_height_bins),
        }

    x_world = x_world[range_mask]
    z_world = z_world[range_mask]
    height_world = height_world[range_mask]

    cols = np.floor((x_world - x_min) / config.resolution_m).astype(np.int32)
    rows = np.floor((z_max - z_world) / config.resolution_m).astype(np.int32)

    valid_grid = (rows >= 0) & (rows < bev_h) & (cols >= 0) & (cols < bev_w)
    if not np.any(valid_grid):
        preview = np.zeros((bev_h * 2, bev_w * 2, 3), dtype=np.uint8)
        return preview, {
            "bevheight_nonzero_ratio": 0.0,
            "bevheight_peak": 0.0,
            "bevheight_mean_height": 0.0,
            "bevheight_height_bins": float(config.num_height_bins),
        }

    rows = rows[valid_grid]
    cols = cols[valid_grid]
    height_world = height_world[valid_grid]
    z_world = z_world[valid_grid]

    weights = 1.0 / np.clip(z_world, 1.0, None)
    np.add.at(occupancy, (rows, cols), weights)

    height_norm = (height_world - h_min) / (h_max - h_min)
    bin_indices = np.floor(height_norm * config.num_height_bins).astype(np.int32)
    bin_indices = np.clip(bin_indices, 0, config.num_height_bins - 1)

    for bin_index in range(config.num_height_bins):
        bin_mask = bin_indices == bin_index
        if np.any(bin_mask):
            np.add.at(height_bins[bin_index], (rows[bin_mask], cols[bin_mask]), weights[bin_mask])

    np.maximum.at(max_height, (rows, cols), height_world)
    np.minimum.at(min_height, (rows, cols), height_world)
    np.add.at(sum_height, (rows, cols), height_world)
    np.add.at(count_height, (rows, cols), 1.0)

    valid_count_mask = count_height > 0
    mean_height = np.full_like(sum_height, h_min, dtype=np.float32)
    mean_height[valid_count_mask] = sum_height[valid_count_mask] / count_height[valid_count_mask]

    dominant_bin = np.argmax(height_bins, axis=0).astype(np.float32)

    occupancy_color = _colorize(occupancy)
    max_height_color = _colorize(max_height, cv2.COLORMAP_PLASMA)
    mean_height_color = _colorize(mean_height, cv2.COLORMAP_INFERNO)
    dominant_bin_color = _colorize(dominant_bin, cv2.COLORMAP_VIRIDIS)

    top_row = np.concatenate([occupancy_color, max_height_color], axis=1)
    bottom_row = np.concatenate([mean_height_color, dominant_bin_color], axis=1)
    preview = np.concatenate([top_row, bottom_row], axis=0)

    bevheight_peak = float(height_bins.max()) if height_bins.size else 0.0
    bevheight_nonzero_ratio = float(np.count_nonzero(height_bins) / height_bins.size) if height_bins.size else 0.0
    bevheight_mean_height = float(mean_height[valid_count_mask].mean()) if np.any(valid_count_mask) else 0.0

    return preview, {
        "bevheight_nonzero_ratio": bevheight_nonzero_ratio,
        "bevheight_peak": bevheight_peak,
        "bevheight_mean_height": bevheight_mean_height,
        "bevheight_height_bins": float(config.num_height_bins),
    }


def save_bevheight_preview(preview_bgr: np.ndarray, output_path: str | Path) -> None:
    if preview_bgr.size == 0:
        raise ValueError("preview_bgr 不可為空")
    cv2.imwrite(str(output_path), preview_bgr)