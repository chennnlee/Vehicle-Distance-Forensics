from dataclasses import dataclass

import numpy as np


@dataclass
class CameraIntrinsics:
    fx: float
    fy: float
    cx: float
    cy: float


def depth_to_point_cloud(depth: np.ndarray, intrinsics: CameraIntrinsics) -> np.ndarray:
    """將深度圖投影為相機座標系 3D 點雲，輸出 shape: (N, 3)。"""
    h, w = depth.shape
    u, v = np.meshgrid(np.arange(w), np.arange(h))

    z = depth.reshape(-1)
    x = ((u.reshape(-1) - intrinsics.cx) * z) / intrinsics.fx
    y = ((v.reshape(-1) - intrinsics.cy) * z) / intrinsics.fy

    return np.stack([x, y, z], axis=1)


def to_bev(points_xyz: np.ndarray) -> np.ndarray:
    """將 3D 點雲映射至 BEV 平面（輸出 x-z 平面座標）。"""
    if points_xyz.ndim != 2 or points_xyz.shape[1] != 3:
        raise ValueError("points_xyz 需為 (N, 3) 陣列")
    return points_xyz[:, [0, 2]]
