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
