"""Block 2b (optional, batch --cycle-select): pick between the two legal Californian dash cycles per second with the image.

A segment gets one road-class label, so where it changes road class part-way (a freeway exit into town) one part reads
exactly half or double. The image only chooses between the two legal cycles; it never gives a speed value.
  image speed  static road points (below the focus of expansion, planarity <= 0.03) between frames f and f+2:
               travel D = s * c0 * (rho - 1) / rho (motion_scale; rho = radial distance ratio from the FOE after the
               per-pair rotation shift), weighted median per frame pair (>= 20 points), median per second
  selector     r = odometer speed (the label's cycle) / image speed per second; centred 11 s window, >= 5 seconds:
               median log r. That second switches to the other cycle when |log r| > log 1.5 and |log r'| < log 1.25.
Copied from research/blind_prep/cycle_select.py (registered as amendment 4 there; passed on development data), with one
guard added: nothing happens unless the label's cycle is one of the two Californian cycles.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from . import depth as DP
from . import ego as EG
from . import motion_scale as M

LEGAL = (EG.CYCLES_M["ca_local"], EG.CYCLES_M["ca_highway"])
WIN_S, MIN_SEC, SWITCH, ACCEPT = 11, 5, math.log(1.5), math.log(1.25)
MIN_POINTS = 20


def image_speed(clip: dict, s: float) -> pd.Series:
    """Per second (int), the image ego speed in km/h; empty when the static points do not allow it."""
    p = clip["pairs"]
    p = p[(p.pl0 <= 0.03) & (p.c0 > 1) & (p.c0 < 100)].reset_index(drop=True)
    if (p.groupby("frame0").size() >= 30).sum() < M.MIN_PAIRS:
        return pd.Series(dtype=float)
    hp, wp = clip["proc_hw"]
    e, shifts = M.estimate(p, ((wp - 1) / 2, (hp - 1) / 2))
    if not (M.FOE_X[0] * wp <= e[0] <= M.FOE_X[1] * wp and M.FOE_Y[0] * hp <= e[1] <= M.FOE_Y[1] * hp):
        return pd.Series(dtype=float)
    q = M.point_depths(p.assign(delta=1.0), e, shifts)
    u = q[q.usable & (q.y0 > e[1] + M.GROUND_MARGIN)].copy()
    u["D"] = s * u.c0 * (u.rho - 1) / u.rho
    dt = DP.STEP / clip["fps"]
    per = {}
    for f, g in u.groupby("frame0"):
        if len(g) >= MIN_POINTS:
            per[int(f)] = M.wmedian(g.D.to_numpy(float), g.w.to_numpy(float)) / dt * 3.6
    if not per:
        return pd.Series(dtype=float)
    t = pd.Series(per)
    return t.groupby((t.index + DP.STEP / 2) // clip["fps"]).median()


def odo_seconds(ego: np.ndarray, method: np.ndarray, fps: float) -> pd.Series:
    f = np.arange(len(ego))
    m = (np.asarray(method) == "dash_odometer") & np.isfinite(ego)
    s = pd.Series(ego[m], index=f[m] // fps)
    return s.groupby(level=0).mean()


def select(clip: dict, img: pd.Series) -> tuple[np.ndarray, np.ndarray, dict]:
    """Per frame: the ego speed after the selector and whether that frame was switched."""
    fps, c = clip["fps"], clip["cycle_m"]
    ego = np.asarray(clip["ego_kmh"], float).copy()
    switched = np.zeros(len(ego), bool)
    if not any(abs(c - x) < 1e-6 for x in LEGAL):
        return ego, switched, {"seconds_with_ratio": 0, "alt_cycle": None, "switched_seconds": 0}
    alt = LEGAL[0] if abs(c - LEGAL[1]) < 1e-6 else LEGAL[1]
    odo = odo_seconds(ego, clip["method"], fps)
    lr = np.log(odo / img).dropna()
    info = {"seconds_with_ratio": int(len(lr)), "alt_cycle": alt, "switched_seconds": 0}
    if not len(lr):
        return ego, switched, info
    n_sec = int(math.ceil(len(ego) / fps))
    for sec in range(n_sec):
        w = lr[(lr.index >= sec - WIN_S // 2) & (lr.index <= sec + WIN_S // 2)]
        if len(w) < MIN_SEC:
            continue
        m = float(np.median(w))
        m_alt = m + math.log(alt / c)
        if abs(m) > SWITCH and abs(m_alt) < ACCEPT:
            fr = slice(int(sec * fps), int(min(len(ego), (sec + 1) * fps)))
            ego[fr] = ego[fr] * alt / c
            switched[fr] = True
            info["switched_seconds"] += 1
    return ego, switched, info
