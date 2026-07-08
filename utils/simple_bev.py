from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

import cv2
import numpy as np


@dataclass(frozen=True)
class SimpleBEVConfig:
    x_range_m: Tuple[float, float] = (-20.0, 20.0)
    z_range_m: Tuple[float, float] = (0.0, 60.0)
    resolution_m: float = 0.2
    fov_deg: float = 90.0
    ground_start_ratio: float = 0.45
    pitch_deg: float = 0.0


def _validate_config(config: SimpleBEVConfig) -> None:
    x_min, x_max = config.x_range_m
    z_min, z_max = config.z_range_m
    if x_max <= x_min:
        raise ValueError("BEV x_range_m 必須滿足 max > min")
    if z_max <= z_min:
        raise ValueError("BEV z_range_m 必須滿足 max > min")
    if config.resolution_m <= 0:
        raise ValueError("BEV resolution_m 必須大於 0")
    if not (0.0 <= config.ground_start_ratio < 1.0):
        raise ValueError("BEV ground_start_ratio 必須介於 0 與 1 之間")
    if config.fov_deg <= 0 or config.fov_deg >= 180:
        raise ValueError("BEV fov_deg 必須介於 0 與 180 之間")


def project_depth_to_bev(depth_map: np.ndarray, config: SimpleBEVConfig = SimpleBEVConfig()) -> tuple[np.ndarray, dict[str, float]]:
    """把 metric depth 近似投影為鳥瞰圖熱度圖。

    這不是完整的 SimpleBEV 神經網路，而是用 Metric3D v2 的 metric depth
    做一個輕量、可直接視覺化的 BEV 投影，用來先驗證整合流程。
    """
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
    if ys.size == 0:
        bev_h = int(np.ceil((config.z_range_m[1] - config.z_range_m[0]) / config.resolution_m))
        bev_w = int(np.ceil((config.x_range_m[1] - config.x_range_m[0]) / config.resolution_m))
        return np.zeros((bev_h, bev_w), dtype=np.float32), {"bev_nonzero_ratio": 0.0, "bev_peak": 0.0}

    depths = depth[ys, xs]

    fov_rad = np.deg2rad(config.fov_deg)
    fx = w / (2.0 * np.tan(fov_rad / 2.0))
    fy = fx
    cx = (w - 1) * 0.5
    cy = (h - 1) * 0.5

    x_cam = (xs.astype(np.float32) - cx) / fx * depths
    y_cam = (ys.astype(np.float32) - cy) / fy * depths

    pitch_rad = np.deg2rad(config.pitch_deg)
    x_world = x_cam
    z_world = depths * np.cos(pitch_rad) + y_cam * np.sin(pitch_rad)

    x_min, x_max = config.x_range_m
    z_min, z_max = config.z_range_m
    range_mask = (x_world >= x_min) & (x_world <= x_max) & (z_world >= z_min) & (z_world <= z_max)
    if not np.any(range_mask):
        bev_h = int(np.ceil((z_max - z_min) / config.resolution_m))
        bev_w = int(np.ceil((x_max - x_min) / config.resolution_m))
        return np.zeros((bev_h, bev_w), dtype=np.float32), {"bev_nonzero_ratio": 0.0, "bev_peak": 0.0}

    x_world = x_world[range_mask]
    z_world = z_world[range_mask]
    depths = depths[range_mask]

    bev_w = int(np.ceil((x_max - x_min) / config.resolution_m))
    bev_h = int(np.ceil((z_max - z_min) / config.resolution_m))
    bev = np.zeros((bev_h, bev_w), dtype=np.float32)

    cols = np.floor((x_world - x_min) / config.resolution_m).astype(np.int32)
    rows = np.floor((z_max - z_world) / config.resolution_m).astype(np.int32)

    valid_grid = (rows >= 0) & (rows < bev_h) & (cols >= 0) & (cols < bev_w)
    if not np.any(valid_grid):
        return bev, {"bev_nonzero_ratio": 0.0, "bev_peak": 0.0}

    rows = rows[valid_grid]
    cols = cols[valid_grid]
    depths = depths[valid_grid]

    weights = 1.0 / np.clip(depths, 1.0, None)
    np.add.at(bev, (rows, cols), weights)

    bev_peak = float(bev.max()) if bev.size else 0.0
    bev_nonzero_ratio = float(np.count_nonzero(bev) / bev.size) if bev.size else 0.0
    return bev, {"bev_nonzero_ratio": bev_nonzero_ratio, "bev_peak": bev_peak}


def save_bev_colormap(bev_map: np.ndarray, output_path: str | Path) -> None:
    """把 BEV 熱圖轉為彩色影像並存檔。"""
    bev = bev_map.astype(np.float32, copy=False)
    if bev.size == 0:
        raise ValueError("bev_map 不可為空")

    bev_norm = cv2.normalize(bev, None, 0, 255, cv2.NORM_MINMAX)
    bev_u8 = bev_norm.astype(np.uint8)
    bev_color = cv2.applyColorMap(bev_u8, cv2.COLORMAP_TURBO)
    cv2.imwrite(str(output_path), bev_color)