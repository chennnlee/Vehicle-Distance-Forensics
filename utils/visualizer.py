from pathlib import Path

import cv2
import numpy as np


def save_depth_colormap(depth_map: np.ndarray, output_path: str | Path) -> None:
    """將深度圖轉為彩色圖並儲存。"""
    depth_norm = cv2.normalize(depth_map, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    depth_color = cv2.applyColorMap(depth_norm, cv2.COLORMAP_JET)
    cv2.imwrite(str(output_path), depth_color)
