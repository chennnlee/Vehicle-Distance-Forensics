"""One clip through blocks 2-4, shared by the single-video command (run.py) and the batch runner (batch.py).

run_clip() does the expensive part once (odometer, detection and tracking, depth); objects_for() turns it into
distances and speeds for any scale, so the same-camera and the clip's own scale cost nothing extra.
"""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pandas as pd

from . import depth as DP
from . import ego as EG
from . import measure as MS
from . import scale as SC
from . import vehicles as VH


def run_clip(frames: list[Path], fps: float, cycle_m: float, hood: int, picker: dict, da3_model, weights: Path) -> dict:
    import cv2
    H, W = cv2.imread(str(frames[0])).shape[:2]
    timing = {}
    t = time.time()
    ego_kmh, method, odo = EG.ego_speed(frames, fps, cycle_m, picker)
    timing["ego_s"] = round(time.time() - t, 1)
    t = time.time()
    boxes, restarts = VH.track(frames, weights, hood)
    timing["vehicles_s"] = round(time.time() - t, 1)
    t = time.time()
    dep = DP.run(da3_model, frames, boxes, hood)
    timing["depth_s"] = round(time.time() - t, 1)
    own = SC.choose(dep, ego_kmh, method, fps, DP.STEP, None)
    pairs = dep["pairs"].astype({k: "float32" for k in dep["pairs"].columns if k != "frame0"})
    return {"fps": fps, "size": (W, H), "hood": hood, "cycle_m": cycle_m, "ego_kmh": ego_kmh, "method": method,
            "odometer": odo, "boxes": boxes, "restarts": restarts, "cars": dep["cars"], "proc_hw": dep["proc_hw"],
            "own_scale": own, "timing": timing,
            # kept for later steps that need the static points (scale, image ego speed) without rerunning the models
            "pairs": pairs, "grid_frames": dep["grid_frames"], "grid": dep["grid"]}


def same_camera(s: float, clip: dict) -> dict:
    return {"s": float(s), "source": "same_camera", "s_rule": clip["own_scale"]["s_rule"]}


def objects_for(clip: dict, scale: dict, win_s: float = 1.0, corr: MS.DistanceCorrection | None = None) -> pd.DataFrame:
    return MS.objects(clip["boxes"], clip["cars"], scale, clip["ego_kmh"], clip["fps"], DP.STEP, clip["size"], clip["proc_hw"][1],
                      win_s, corr)


def ego_table(clip: dict, processed_only: bool = False) -> pd.DataFrame:
    e = pd.DataFrame({"frame_idx": np.arange(len(clip["ego_kmh"])), "ego_kmh": np.round(clip["ego_kmh"], 2),
                      "flag": np.where(np.isfinite(clip["ego_kmh"]), clip["method"], "none")})
    return e[e.frame_idx % DP.STEP == 0] if processed_only else e
