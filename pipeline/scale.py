"""Block 4b: the depth scale (metres per canonical depth unit at the processed size). One rule, first that works:
  1. a same-camera scale given by the user (median of the camera's other clips);
  2. this clip's own: image expansion of static ground points + odometer travel (motion_scale.segment_flow, ground anchor);
  3. the 30 mm rule focal, flagged 'scale_rule_focal' (uncalibrated).
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from . import motion_scale as M


def rule_scale(size: tuple[int, int], proc_w: int) -> float:
    """DA3METRIC: metres = focal_px x output / 300; the 30 mm rule focal at the processed width."""
    f_rule = 30.0 / 43.2666 * math.hypot(*size)
    return f_rule * (proc_w / size[0]) / 300.0


def travel(ego_kmh: np.ndarray, method: np.ndarray, fps: float, step: int) -> dict[int, float]:
    """Odometer travel (m) from frame f to f + step, only where every frame in between is a dash-odometer reading."""
    out = {}
    for f in range(len(ego_kmh) - step):
        if all(method[f + j] == "dash_odometer" for j in range(step + 1)):
            v = ego_kmh[f: f + step + 1] / 3.6
            out[f] = float(np.sum((v[1:] + v[:-1]) / 2) / fps)
    return out


def choose(depth: dict, ego_kmh: np.ndarray, method: np.ndarray, fps: float, step: int,
           camera_scale: float | None = None) -> dict:
    hp, wp = depth["proc_hw"]
    s_rule = rule_scale(depth["size"], wp)
    if camera_scale:
        return {"s": float(camera_scale), "source": "same_camera", "s_rule": s_rule}
    p = depth["pairs"].copy()
    trav = travel(ego_kmh, method, fps, step)
    p["delta"] = p["frame0"].astype(int).map(trav)
    p = p[p.delta.notna() & (p.delta > 0)]
    why = None
    if len(p):
        e0 = ((wp - 1) / 2, (hp - 1) / 2)
        fl = M.segment_flow(p, e0, wp, hp, np.arange(len(ego_kmh)), depth["grid_frames"], depth["grid"], s_rule)
        s = fl["anchors"].get("ground", {}).get("s")
        if s:
            return {"s": float(s), "source": "odometer", "s_rule": s_rule, "foe_proc": fl.get("foe_proc")}
        why = fl.get("why") or fl["anchors"].get("ground", {}).get("why")
    else:
        why = "no odometer travel"
    return {"s": s_rule, "source": "rule_focal", "s_rule": s_rule, "why": why}
