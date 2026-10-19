"""Copied unchanged from research/sharp_free/motion_scale.py (2026-10-18), the depth-scale calibration the main flow uses.

Original docstring follows.
Metric depth of static points from image motion and the odometer, then DA3's scale at those points (amendment D2).

For a camera translating by D along the direction whose image is the focus of expansion e, a static
point's image moves radially away from e and (u1 - e) = (u0 - e) Z0 / (Z0 - D) (the z-component of
the travel; the focal length cancels). So rho = |u1 - e| / |u0 - e| gives Z0 = D rho / (rho - 1),
and DA3's scale at that point is s = Z0 / c0. Only DA3's depth VALUE at the point is used, not its
change between frames (which DA3 under-reports, worst for far scenery).

Small rotations between the two frames (pitch from bumps, yaw on curves) add a nearly uniform image
shift; it is estimated per frame pair together with e (one e per segment: the camera is fixed to the
car and the car moves along its heading). Both steps are linear least squares with Tukey weights:
  shift | e : the flow minus the shift must be radial; the perpendicular residual is linear in the shift
  e | shifts: cross(flow - shift, u0 - e) = 0 is linear in e
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

SIGMA_FLOW = 0.2             # px (processed resolution), a priori LK precision
SIGMA_DA3 = 0.05             # relative, a priori DA3 noise floor
MIN_TRANS_FLOW = 1.0         # px; below this the depth from motion is too imprecise
MIN_RADIUS = 10.0            # px from the focus of expansion
TUKEY = 4.685


def _tukey(r: np.ndarray) -> np.ndarray:
    s = 1.4826 * np.median(np.abs(r - np.median(r)))
    if not s > 0:
        return np.ones(len(r))
    u = r / (TUKEY * s)
    return np.where(np.abs(u) < 1, (1 - u ** 2) ** 2, 0.0)


def _shift(u0, v0, fx, fy, e, w0, rounds=5):
    rx, ry = u0 - e[0], v0 - e[1]
    rn = np.hypot(rx, ry)
    nx, ny = -ry / rn, rx / rn
    proj = nx * fx + ny * fy
    w = w0.copy()
    s = np.zeros(2)
    for _ in range(rounds):
        A = np.array([[np.sum(w * nx * nx), np.sum(w * nx * ny)], [np.sum(w * nx * ny), np.sum(w * ny * ny)]])
        b = np.array([np.sum(w * nx * proj), np.sum(w * ny * proj)])
        if np.linalg.cond(A) > 1e6:
            return np.zeros(2), False
        s = np.linalg.solve(A, b)
        w = w0 * _tukey(proj - (nx * s[0] + ny * s[1]))
    return s, True


def estimate(p: pd.DataFrame, e0: tuple[float, float], rounds: int = 6) -> tuple[np.ndarray, dict]:
    """p: one segment's points with frame0, x0, y0, x1, y1. Returns e and {frame0: shift}."""
    e = np.array(e0, float)
    groups = {f: g.index.to_numpy() for f, g in p.groupby("frame0") if len(g) >= 30}
    u0, v0 = p.x0.to_numpy(float), p.y0.to_numpy(float)
    fx, fy = (p.x1 - p.x0).to_numpy(float), (p.y1 - p.y0).to_numpy(float)
    pos = {k: i for i, k in enumerate(p.index)}
    shifts = {}
    for _ in range(rounds):
        shifts = {}
        for f, idx in groups.items():
            ii = np.array([pos[k] for k in idx])
            s, ok = _shift(u0[ii], v0[ii], fx[ii], fy[ii], e, np.ones(len(ii)))
            if ok:
                shifts[f] = s
        sx = np.array([shifts.get(f, (np.nan, np.nan))[0] for f in p.frame0])
        sy = np.array([shifts.get(f, (np.nan, np.nan))[1] for f in p.frame0])
        ok = np.isfinite(sx)
        gx, gy = fx[ok] - sx[ok], fy[ok] - sy[ok]
        uu, vv = u0[ok], v0[ok]
        w = np.ones(ok.sum())
        for _ in range(5):
            rn2 = (uu - e[0]) ** 2 + (vv - e[1]) ** 2
            ww = w / np.maximum(rn2, MIN_RADIUS ** 2)
            A = np.c_[gy, -gx]
            b = gy * uu - gx * vv
            e = np.linalg.solve(A.T @ (ww[:, None] * A), A.T @ (ww * b))
            cross = gx * (vv - e[1]) - gy * (uu - e[0])
            w = _tukey(cross / np.sqrt(np.maximum((uu - e[0]) ** 2 + (vv - e[1]) ** 2, MIN_RADIUS ** 2)))
    return e, shifts


def point_depths(p: pd.DataFrame, e: np.ndarray, shifts: dict) -> pd.DataFrame:
    """Per point: rho, translational flow, perpendicular residual, Z0 from motion, s = Z0 / c0, weight."""
    q = p[p.frame0.isin(list(shifts))].copy()
    sx = q.frame0.map(lambda f: shifts[f][0]).to_numpy(float)
    sy = q.frame0.map(lambda f: shifts[f][1]).to_numpy(float)
    gx, gy = (q.x1 - q.x0).to_numpy(float) - sx, (q.y1 - q.y0).to_numpy(float) - sy
    rx, ry = q.x0.to_numpy(float) - e[0], q.y0.to_numpy(float) - e[1]
    rn = np.hypot(rx, ry)
    tf = (gx * rx + gy * ry) / rn                     # radial (translational) flow, px
    q["radius"] = rn
    q["trans_flow"] = tf
    q["perp"] = (gx * -ry + gy * rx) / rn
    rho = 1.0 + tf / rn
    q["rho"] = rho
    q["z_motion"] = np.where(rho > 1, q.delta.to_numpy(float) * rho / np.maximum(rho - 1, 1e-9), np.nan)
    q["s_point"] = q.z_motion / q.c0
    q["w"] = 1.0 / ((SIGMA_FLOW / (rho * np.maximum(tf, 1e-9))) ** 2 + SIGMA_DA3 ** 2)
    # perpendicular residual scale per pair (robust)
    mad = q.groupby("frame0").perp.transform(lambda r: 1.4826 * np.median(np.abs(r - np.median(r))))
    q["usable"] = ((q.trans_flow >= MIN_TRANS_FLOW) & (q.radius >= MIN_RADIUS) & (q.perp.abs() <= 3 * mad)
                   & np.isfinite(q.s_point) & (q.s_point > 0))
    return q


def wmedian(x: np.ndarray, w: np.ndarray) -> float:
    o = np.argsort(x)
    cw = np.cumsum(w[o])
    return float(x[o][min(len(x) - 1, np.searchsorted(cw, 0.5 * cw[-1]))])


# ----------------------------------------------------------------------------- per-segment scales (amendments D2, D3)
FOE_X, FOE_Y = (0.2, 0.8), (0.25, 0.6)      # plausible focus of expansion, fraction of width / height
GROUND_MARGIN = 5.0                         # px below the focus of expansion
MIN_PAIRS, MIN_ANCHOR = 50, 200
ROLL_FRAMES, ROLL_MIN = 200, 100            # +-10 s at 20 fps; points
NL_BOOT, BLOCK = 200, 100                   # bootstrap reps; 5 s blocks
BLOCK_MIN, BLOCK_TOL, BLOCK_DROP_MAX = 30, math.log(1.3), 0.25
RULE_TOL = math.log(1.5)                    # octave errors give x2; valid for this study's camera only
ANCHOR_C = (3.0, 45.0)                      # same depth range as the 4-60 m cars
ROAD_G, VERT_G = (0.5, 1.5), 0.25           # normalised row gradient of inverse depth
NL_MIN_BETA, NL_C_MAX = 0.05, 45.0
GRID_STEP = 6


def robust_line(x: np.ndarray, y: np.ndarray, w: np.ndarray, iters: int = 10) -> np.ndarray:
    """Weighted straight line y = b0 + b1 x with Tukey reweighting of sqrt(w)-standardised residuals."""
    ww = w.copy()
    b = np.zeros(2)
    for _ in range(iters):
        s0, s1, s2 = ww.sum(), (ww * x).sum(), (ww * x * x).sum()
        t0, t1 = (ww * y).sum(), (ww * x * y).sum()
        det = s0 * s2 - s1 * s1
        if not det > 0:
            return np.array([np.nan, np.nan])
        b = np.array([(s2 * t0 - s1 * t1) / det, (s0 * t1 - s1 * t0) / det])
        ww = w * _tukey((y - b[0] - b[1] * x) * np.sqrt(w))
    return b


def row_gradient(q: pd.DataFrame, grid_frames: np.ndarray, grid: np.ndarray, e_y: float) -> np.ndarray:
    """Normalised row gradient of DA3's inverse depth at each point's start (amendment D3-1).

    g = (d(1/c)/dv) / ((1/c) / (v - e_y)): 1 on a level road plane (1/c is linear in the row and
    vanishes at the horizon), 0 on a vertical face. From the 6 px grid, central differences, bilinear.
    """
    if len(q) == 0:
        return np.empty(0)
    pos = {int(f): i for i, f in enumerate(grid_frames)}
    inv = 1.0 / np.maximum(grid.astype(np.float32), 1e-3)
    dv = np.full_like(inv, np.nan)
    dv[:, 1:-1, :] = (inv[:, 2:, :] - inv[:, :-2, :]) / (2.0 * GRID_STEP)
    gh, gw = inv.shape[1:]
    k = np.array([pos.get(int(f), -1) for f in q.frame0.to_numpy()], dtype=int)
    v = q.y0.to_numpy(float)
    x, y = q.x0.to_numpy(float) / GRID_STEP, v / GRID_STEP
    ok = (k >= 0) & (x >= 0) & (x <= gw - 1.001) & (y >= 1) & (y <= gh - 2.001) & (v > e_y)
    out = np.full(len(q), np.nan)
    kk, xx, yy = k[ok], x[ok], y[ok]
    x0, y0 = np.floor(xx).astype(int), np.floor(yy).astype(int)
    fx, fy = xx - x0, yy - y0

    def samp(a):
        return (a[kk, y0, x0] * (1 - fx) * (1 - fy) + a[kk, y0, x0 + 1] * fx * (1 - fy)
                + a[kk, y0 + 1, x0] * (1 - fx) * fy + a[kk, y0 + 1, x0 + 1] * fx * fy)

    out[ok] = samp(dv) * (v[ok] - e_y) / samp(inv)
    return out


def odometer_blocks(probe: pd.DataFrame) -> tuple[set, dict]:
    """Amendment D4-1, once per segment: 5 s blocks of the probe anchor whose s is > 30 % from the probe's level."""
    ls, w = np.log(probe.s_point.to_numpy()), probe.w.to_numpy()
    l0 = wmedian(ls, w)
    blk = probe.frame0.to_numpy() // BLOCK
    bad, blocks = set(), {}
    for b in np.unique(blk):
        m = blk == b
        if m.sum() >= BLOCK_MIN:
            sb = wmedian(ls[m], w[m])
            blocks[int(b)] = round(float(math.exp(sb)), 4)
            if abs(sb - l0) > BLOCK_TOL:
                bad.add(int(b))
    frac = float(np.isin(blk, list(bad)).mean()) if bad else 0.0
    return bad, {"blocks": blocks, "bad_blocks": sorted(bad), "dropped_frac": round(frac, 4),
                 "inconsistent": frac > BLOCK_DROP_MAX}


def level(a: pd.DataFrame, s_rule: float, n_all: int) -> tuple[float | None, dict]:
    """One s for the segment from a class's anchor points left after the odometer step (amendment D4-1).

    Blocks > 30 % from the class level are dropped; more than 25 % of the class's anchor points
    (counted before the odometer step) dropped -> anchor_inconsistent; then the 1.5x check against D-rule.
    """
    info = {"n": int(len(a)), "n_all": int(n_all)}
    if len(a) < MIN_ANCHOR:
        return None, {**info, "why": f"{len(a)} anchor points"}
    ls, w = np.log(a.s_point.to_numpy()), a.w.to_numpy()
    l0 = wmedian(ls, w)
    blk = a.frame0.to_numpy() // BLOCK
    keep = np.ones(len(a), bool)
    blocks = {}
    for b in np.unique(blk):
        m = blk == b
        if m.sum() >= BLOCK_MIN:
            sb = wmedian(ls[m], w[m])
            blocks[int(b)] = round(float(math.exp(sb)), 4)
            if abs(sb - l0) > BLOCK_TOL:
                keep[m] = False
    dropped = float((~keep).sum() / max(n_all, 1))
    info.update({"blocks": blocks, "dropped_frac": round(dropped, 4)})
    if dropped > BLOCK_DROP_MAX:
        return None, {**info, "why": "anchor_inconsistent"}
    if keep.sum() < MIN_ANCHOR:
        return None, {**info, "why": f"{int(keep.sum())} anchor points after the block check"}
    lv = wmedian(ls[keep], w[keep])
    info["s"] = float(math.exp(lv))
    if abs(lv - math.log(s_rule)) > RULE_TOL:
        return None, {**info, "why": "scale_implausible"}
    info["keep"] = keep
    return float(math.exp(lv)), info


def power_law(a: pd.DataFrame, keep: np.ndarray) -> dict:
    """log s = a + beta log c on the anchor's kept points; used when |beta| >= 0.05 and the 5 s block CI excludes 0."""
    a = a[keep]
    x, y, w = np.log(a.c0.to_numpy()), np.log(a.s_point.to_numpy()), a.w.to_numpy()
    b = robust_line(x, y, w)
    blk = a.frame0.to_numpy() // BLOCK
    keys = np.unique(blk)
    idx = {k: np.flatnonzero(blk == k) for k in keys}
    rng = np.random.default_rng(20261017)
    betas = []
    for _ in range(NL_BOOT):
        ii = np.concatenate([idx[k] for k in rng.choice(keys, len(keys))])
        bb = robust_line(x[ii], y[ii], w[ii])
        if np.isfinite(bb[1]):
            betas.append(bb[1])
    lo, hi = np.percentile(betas, [2.5, 97.5]) if betas else (np.nan, np.nan)
    used = bool(np.isfinite(b[1]) and abs(b[1]) >= NL_MIN_BETA and np.isfinite(lo) and not (lo <= 0 <= hi))
    return {"a": float(b[0]), "beta": float(b[1]), "beta_ci": [float(lo), float(hi)], "used": used}


def nl_distance(c: np.ndarray, pl: dict) -> np.ndarray:
    """Z = e^a c^(1+beta) up to c = 45, then s held at its c = 45 value (no extrapolated power)."""
    cc = np.minimum(c, NL_C_MAX)
    return np.exp(pl["a"]) * cc ** pl["beta"] * c


def segment_flow(p: pd.DataFrame, e0: tuple[float, float], wp: int, hp: int, frames: np.ndarray,
                 grid_frames: np.ndarray, grid: np.ndarray, s_rule: float) -> dict:
    """p: points with frame0, x0..y1, c0, pl0, delta (travel known). Scales of the D_flow family (amendments D2-D4)."""
    out = {"n_pairs": 0, "anchors": {}}
    p = p[(p.pl0 <= 0.03) & (p.c0 > 1) & (p.c0 < 100)].reset_index(drop=True)
    n_pairs = int((p.groupby("frame0").size() >= 30).sum()) if len(p) else 0
    out["n_pairs"] = n_pairs
    if n_pairs < MIN_PAIRS:
        out["why"] = f"{n_pairs} frame pairs with >= 30 points"
        return out
    e, shifts = estimate(p, e0)
    out["foe_proc"] = [float(e[0]), float(e[1])]
    if not (FOE_X[0] * wp <= e[0] <= FOE_X[1] * wp and FOE_Y[0] * hp <= e[1] <= FOE_Y[1] * hp):
        out["why"] = "focus of expansion implausible"
        return out
    q = point_depths(p, e, shifts)
    u = q[q.usable].copy()
    u["g"] = row_gradient(u, grid_frames, grid, e[1])
    below = u.y0 > e[1] + GROUND_MARGIN
    in_c = u.c0.between(*ANCHOR_C)
    sel = {"ground": below,
           "road": below & in_c & u.g.between(*ROAD_G),
           "vert": below & in_c & (u.g.abs() <= VERT_G)}
    above = u[u.y0 < e[1] - GROUND_MARGIN]
    out["s_scenery"] = (float(np.exp(wmedian(np.log(above.s_point.to_numpy()), above.w.to_numpy())))
                        if len(above) >= 50 else None)
    out["n_usable"] = int(len(u))
    gd = u[below.to_numpy()]
    if len(gd):
        w = gd.w.to_numpy()
        roadlike, vertlike = gd.g.between(*ROAD_G).to_numpy(), (gd.g.abs() <= VERT_G).to_numpy()
        out["ground_diag"] = {"c_wmedian": float(wmedian(gd.c0.to_numpy(), w)),
                              "share_road": float(w[roadlike].sum() / w.sum()), "share_vert": float(w[vertlike].sum() / w.sum()),
                              "share_other": float(w[~roadlike & ~vertlike].sum() / w.sum())}
    classes = {name: u[m.to_numpy()].reset_index(drop=True) for name, m in sel.items()}
    probe = "road" if len(classes["road"]) >= MIN_ANCHOR else "ground"
    if len(classes[probe]) < MIN_ANCHOR:
        bad, oinfo = set(), {"inconsistent": False, "why": "no probe with >= 200 points"}
    else:
        bad, oinfo = odometer_blocks(classes[probe])
    out["odometer"] = {"probe": probe, **oinfo}
    for name, a_all in classes.items():
        if oinfo["inconsistent"]:
            out["anchors"][name] = {"s": None, "n_all": int(len(a_all)), "why": "odometer_inconsistent"}
            continue
        a = a_all[~np.isin(a_all.frame0.to_numpy() // BLOCK, list(bad))].reset_index(drop=True)
        s, info = level(a, s_rule, len(a_all))
        rec = {k: v for k, v in info.items() if k != "keep"}
        rec["s"] = s
        if s is not None and name == "road":
            keep = info["keep"]
            rec["nl"] = power_law(a, keep)
            ak = a[keep]
            ls, w = np.log(ak.s_point.to_numpy()), ak.w.to_numpy()
            centre = ak.frame0.to_numpy() + 1
            roll = np.empty(len(frames))
            for i, f in enumerate(frames):
                k = np.abs(centre - f) <= ROLL_FRAMES
                roll[i] = math.exp(wmedian(ls[k], w[k])) if k.sum() >= ROLL_MIN else s
            out["roll"] = roll
        out["anchors"][name] = rec
    return out
