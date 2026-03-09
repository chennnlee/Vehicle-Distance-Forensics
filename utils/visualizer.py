from pathlib import Path

import cv2
import matplotlib.pyplot as plt
import numpy as np


def save_depth_colormap(depth_map: np.ndarray, output_path: str | Path) -> None:
    """將深度圖轉為彩色圖並儲存。"""
    depth_norm = cv2.normalize(depth_map, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    depth_color = cv2.applyColorMap(depth_norm, cv2.COLORMAP_JET)
    cv2.imwrite(str(output_path), depth_color)


def plot_bev(points_bev: np.ndarray) -> None:
    """顯示 BEV 散點圖。"""
    plt.figure(figsize=(6, 6))
    plt.scatter(points_bev[:, 0], points_bev[:, 1], s=1)
    plt.xlabel("X")
    plt.ylabel("Z")
    plt.title("BEV Projection")
    plt.axis("equal")
    plt.grid(True)
    plt.show()


def save_bev_scatter(points_bev: np.ndarray, output_path: str | Path, max_points: int = 50000) -> None:
    """將 BEV 散點圖儲存為 PNG。"""
    if points_bev.ndim != 2 or points_bev.shape[1] != 2:
        raise ValueError("points_bev 需為 (N, 2) 陣列")

    if len(points_bev) == 0:
        raise ValueError("points_bev 不可為空")

    pts = points_bev
    if len(pts) > max_points:
        step = max(1, len(pts) // max_points)
        pts = pts[::step]

    # 過濾掉非有限值與極端離群點，避免圖面被少數點拉爆
    finite_mask = np.isfinite(pts).all(axis=1)
    pts = pts[finite_mask]
    if len(pts) == 0:
        raise ValueError("points_bev 過濾後為空")

    x = pts[:, 0]
    z = pts[:, 1]

    x_low, x_high = np.percentile(x, [1, 99])
    z_low, z_high = np.percentile(z, [1, 99])
    clip_mask = (x >= x_low) & (x <= x_high) & (z >= z_low) & (z <= z_high)
    pts = pts[clip_mask]
    if len(pts) == 0:
        pts = np.column_stack([x, z])

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    plt.figure(figsize=(6, 6), dpi=140)
    plt.scatter(pts[:, 0], pts[:, 1], s=0.8, alpha=0.7)
    plt.xlabel("X")
    plt.ylabel("Z")
    plt.title("BEV Projection")
    plt.axis("equal")
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(str(output))
    plt.close()
