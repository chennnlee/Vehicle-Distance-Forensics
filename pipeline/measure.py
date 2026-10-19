"""Distances and speeds per tracked vehicle on the processed frames (every second frame).

distance = scale x lower-band depth (<= 500 m), optionally through a distance correction g(d) learned on development
data (DistanceCorrection); relative speed = slope of a centred straight line through about win_s (default 1 s) of the
track's distances before the correction (as research/sharp_free/variants.polyfit_rel); absolute speed = ego + relative. Speeds are given
only within NEAR_M (farther, the relative speed is not better than assuming 'as fast as us' on the development data);
lateral offset from DA3's canonical camera (focal-free).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

NEAR_M, MAX_RANGE = 30.0, 500.0
ABS_MAX = 250.0     # km/h; a larger absolute speed is a slope spike (the shared format refuses |speed| > 400)


class DistanceCorrection:
    """g(d) = d * factor(d): factor linear in log distance between the table's nodes, flat outside.
    Table: {"d_m": [...], "factor": [...]} (research/blind_prep/devtune.py Corr)."""

    def __init__(self, table: dict):
        self.table = table
        self.x = np.log(np.asarray(table["d_m"], float))
        self.y = np.log(np.asarray(table["factor"], float))

    def __call__(self, d: np.ndarray) -> np.ndarray:
        d = np.asarray(d, float)
        if not len(self.x):
            return d
        with np.errstate(invalid="ignore", divide="ignore"):
            out = d * np.exp(np.interp(np.log(d), self.x, self.y))
        return np.where(np.isfinite(d) & (d > 0), out, d)


def fit_slope(t: np.ndarray, d: np.ndarray, win: int) -> np.ndarray:
    out = np.full(len(t), np.nan)
    for j in range(len(t)):
        j0, j1 = max(0, j - win // 2), min(len(t), j + win // 2 + 1)
        tt, dd = t[j0:j1], d[j0:j1]
        ok = np.isfinite(dd)
        if ok.sum() >= 5 and tt[ok][-1] - tt[ok][0] > 0.3:
            out[j] = np.polyfit(tt[ok], dd[ok], 1)[0]
    return out


def objects(boxes: pd.DataFrame, cars: pd.DataFrame, scale: dict, ego_kmh: np.ndarray, fps: float, step: int,
            size: tuple[int, int], proc_w: int, win_s: float = 1.0, corr: DistanceCorrection | None = None) -> pd.DataFrame:
    c = cars.set_index(["frame_idx", "track_id"]).c_med.to_dict()
    win = max(5, int(round(win_s * fps / step)) | 1)      # about win_s of processed frames
    cx = (size[0] - 1) / 2 * proc_w / size[0]
    flag_seg = "" if scale["source"] != "rule_focal" else "scale_rule_focal"
    rows = []
    b = boxes[boxes.frame_idx % step == 0]
    for tid, g in b.sort_values("frame_idx").groupby("track_id"):
        fr = g.frame_idx.to_numpy()
        cc = np.array([c.get((int(f), tid), np.nan) for f in fr], float)
        d = scale["s"] * cc
        d_raw = np.where(np.isfinite(d) & (d > 0) & (d <= MAX_RANGE), d, np.nan)
        d = d_raw if corr is None else np.where(np.isfinite(d_raw), corr(d_raw), np.nan)
        d = np.where(np.isfinite(d) & (d > 0) & (d <= MAX_RANGE), d, np.nan)
        rel = fit_slope(fr / fps, d_raw, win) * 3.6
        for j, r in enumerate(g.itertuples()):
            near = np.isfinite(d[j]) and d[j] <= NEAR_M
            relk = rel[j] if near and np.isfinite(rel[j]) and abs(rel[j]) <= 300 else np.nan
            e = ego_kmh[r.frame_idx] if r.frame_idx < len(ego_kmh) else np.nan
            absk = e + relk if np.isfinite(e) and np.isfinite(relk) and abs(e + relk) <= ABS_MAX else np.nan
            lat = (cx - (r.x0 + r.x1) / 2 * proc_w / size[0]) * cc[j] / 300.0 if np.isfinite(d[j]) else np.nan
            flags = [x for x in (flag_seg, "" if near or not np.isfinite(d[j]) else "far") if x]
            rows.append([r.frame_idx, tid, r.x0, r.y0, r.x1, r.y1, _r(d[j]), _r(lat), _r(relk), _r(absk), r.cls, ";".join(flags)])
    return pd.DataFrame(rows, columns=["frame_idx", "track_id", "x0", "y0", "x1", "y1", "dist_m", "lat_m", "rel_kmh",
                                       "abs_kmh", "cls", "flag"])


def _r(x, nd: int = 2):
    return round(float(x), nd) if np.isfinite(x) else np.nan
