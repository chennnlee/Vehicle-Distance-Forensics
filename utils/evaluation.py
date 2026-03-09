from typing import Dict

import numpy as np


def mae(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """計算 Mean Absolute Error。"""
    if y_true.shape != y_pred.shape:
        raise ValueError("y_true 與 y_pred 維度需一致")
    return float(np.mean(np.abs(y_true - y_pred)))


def residual_stats(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, float]:
    """回傳殘差分析指標。"""
    residual = y_pred - y_true
    return {
        "mean": float(np.mean(residual)),
        "std": float(np.std(residual)),
        "min": float(np.min(residual)),
        "max": float(np.max(residual)),
        "mae": mae(y_true, y_pred),
    }
