import numpy as np


def compute_scale_factor(predicted_distances: np.ndarray, anchor_distances: np.ndarray) -> float:
    """根據預測距離與實際 Anchor 距離估計尺度修正係數 s。"""
    if predicted_distances.shape != anchor_distances.shape:
        raise ValueError("predicted_distances 與 anchor_distances 長度需一致")

    denominator = np.sum(predicted_distances ** 2)
    if denominator == 0:
        raise ValueError("predicted_distances 全為 0，無法估計尺度")

    s = float(np.sum(predicted_distances * anchor_distances) / denominator)
    return s


def apply_scale(depth_map: np.ndarray, scale_factor: float) -> np.ndarray:
    """將尺度係數套用到深度圖。"""
    return depth_map * scale_factor
