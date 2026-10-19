"""Block 4a: Depth Anything 3 (DA3METRIC-LARGE) on every second frame.

Per tracked box: the median canonical depth of the lower band (5-35 % of its height up from the bottom, middle 60 % of
its width). Per pair of processed frames: static corners (outside boxes expanded 15 %, above the hood, 10 px from the
border) tracked with pyramidal LK, forward-backward error < 0.5 px, with the depth at both ends and a depth-edge test;
these feed the scale (motion_scale.py). The depth map of every processed frame is kept on a 6 px grid. Same rules as
research/sharp_free/depth_run.py, with the boxes taken from block 3 instead of the old pipeline's tracks.
"""
from __future__ import annotations

import contextlib
import io
import sys
from pathlib import Path

import numpy as np
import pandas as pd

TOOLS = Path(__file__).resolve().parents[1] / "tools"
STEP, GRID, BORDER = 2, 6, 10
_OFF = np.array([(dy, dx) for dy in range(-2, 3) for dx in range(-2, 3)])
_X = np.c_[np.ones(len(_OFF)), _OFF]
_RES = np.eye(len(_OFF)) - _X @ np.linalg.pinv(_X)


MODEL_ID = "depth-anything/DA3METRIC-LARGE"     # Apache 2.0; the cached snapshot is revision 4010e39f


def load_model():
    if str(TOOLS) not in sys.path:
        sys.path.insert(0, str(TOOLS))
    import logging

    import depth_backends as db
    db._shim_moviepy_editor()
    from depth_anything_3.api import DepthAnything3
    logging.disable(logging.INFO)
    return DepthAnything3.from_pretrained(MODEL_ID).to("cuda").eval()


def bilinear(img: np.ndarray, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    h, w = img.shape
    x = np.clip(x, 0, w - 1.001)
    y = np.clip(y, 0, h - 1.001)
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = x - x0, y - y0
    return (img[y0, x0] * (1 - fx) * (1 - fy) + img[y0, x0 + 1] * fx * (1 - fy)
            + img[y0 + 1, x0] * (1 - fx) * fy + img[y0 + 1, x0 + 1] * fx * fy)


def planarity(d: np.ndarray, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """RMS residual of a plane fit to 1/depth in the 5 x 5 window, relative to 1/depth at the point."""
    h, w = d.shape
    xi = np.clip(np.rint(x).astype(int), 2, w - 3)
    yi = np.clip(np.rint(y).astype(int), 2, h - 3)
    inv = 1.0 / np.maximum(d, 1e-6)
    win = inv[yi[:, None] + _OFF[None, :, 0], xi[:, None] + _OFF[None, :, 1]]
    return np.sqrt(((win @ _RES.T) ** 2).mean(1)) / inv[yi, xi]


def lower_band_median(d: np.ndarray, box, sx: float, sy: float) -> float:
    x1, y1, x2, y2 = box
    bw, bh = x2 - x1, y2 - y1
    ya, yb = (y2 - 0.35 * bh) * sy, (y2 - 0.05 * bh) * sy
    xa, xb = (x1 + 0.2 * bw) * sx, (x2 - 0.2 * bw) * sx
    hp, wp = d.shape
    reg = d[max(0, int(np.floor(ya))): min(hp, int(np.ceil(yb)) + 1), max(0, int(np.floor(xa))): min(wp, int(np.ceil(xb)) + 1)]
    reg = reg[np.isfinite(reg) & (reg > 0)]
    return float(np.median(reg)) if reg.size else float("nan")


def _grown(boxes, sx, sy):
    return [((x1 - 0.15 * (x2 - x1)) * sx, (y1 - 0.15 * (y2 - y1)) * sy, (x2 + 0.15 * (x2 - x1)) * sx, (y2 + 0.15 * (y2 - y1)) * sy)
            for x1, y1, x2, y2 in boxes]


def _inside(x, y, boxes) -> np.ndarray:
    out = np.zeros(len(x), bool)
    for x1, y1, x2, y2 in boxes:
        out |= (x >= x1) & (x <= x2) & (y >= y1) & (y <= y2)
    return out


def run(model, frames: list[Path], boxes: pd.DataFrame, hood_row: int) -> dict:
    """cars (frame_idx, track_id, c_med), pairs (static points), grid frames and maps, processed size."""
    import cv2
    import torch

    W = cv2.imread(str(frames[0])).shape[1]
    H = cv2.imread(str(frames[0])).shape[0]
    by_frame = {f: g for f, g in boxes.groupby("frame_idx")}
    cars, grids, gframes = [], [], []
    keys = ("frame0", "x0", "y0", "x1", "y1", "c0", "c1", "fb", "pl0", "pl1")
    pairs = {k: [] for k in keys}
    prev = None
    shape = None
    for fi in range(0, len(frames), STEP):
        bgr = cv2.imread(str(frames[fi]))
        with torch.no_grad(), contextlib.redirect_stdout(io.StringIO()):       # the model prints three lines per frame
            d = np.asarray(model.inference([bgr[:, :, ::-1].copy()]).depth)[0].astype(np.float32)
        hp, wp = d.shape
        shape = (hp, wp)
        sx, sy = wp / W, hp / H
        hood = int(hood_row * sy) - 2
        gray = cv2.cvtColor(cv2.resize(bgr, (wp, hp), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
        here = by_frame.get(fi)
        here_boxes = [] if here is None else list(zip(here.x0, here.y0, here.x1, here.y1))
        if here is not None:
            for tid, box in zip(here.track_id, here_boxes):
                cars.append((fi, tid, lower_band_median(d, box, sx, sy)))
        grids.append(d[::GRID, ::GRID].astype(np.float16))
        gframes.append(fi)
        bx = _grown(here_boxes, sx, sy)
        if prev is not None and prev["p0"] is not None and len(prev["p0"]):
            p1, st, _ = cv2.calcOpticalFlowPyrLK(prev["gray"], gray, prev["p0"], None, winSize=(21, 21), maxLevel=3)
            pb, st2, _ = cv2.calcOpticalFlowPyrLK(gray, prev["gray"], p1, None, winSize=(21, 21), maxLevel=3)
            fb = np.linalg.norm((prev["p0"] - pb).reshape(-1, 2), axis=1)
            ok = (st.ravel() == 1) & (st2.ravel() == 1) & (fb < 0.5)
            a, b, fbk = prev["p0"].reshape(-1, 2)[ok], p1.reshape(-1, 2)[ok], fb[ok]
            keep = (~_inside(b[:, 0], b[:, 1], bx) & (b[:, 0] >= BORDER) & (b[:, 0] < wp - BORDER)
                    & (b[:, 1] >= BORDER) & (b[:, 1] < hood))
            a, b, fbk = a[keep], b[keep], fbk[keep]
            if len(a):
                vals = {"frame0": np.full(len(a), prev["fi"]), "x0": a[:, 0], "y0": a[:, 1], "x1": b[:, 0], "y1": b[:, 1],
                        "c0": bilinear(prev["depth"], a[:, 0], a[:, 1]), "c1": bilinear(d, b[:, 0], b[:, 1]), "fb": fbk,
                        "pl0": planarity(prev["depth"], a[:, 0], a[:, 1]), "pl1": planarity(d, b[:, 0], b[:, 1])}
                for k in keys:
                    pairs[k].append(np.asarray(vals[k]))
        mask = np.full((hp, wp), 255, np.uint8)
        mask[:BORDER], mask[:, :BORDER], mask[:, wp - BORDER:], mask[hood:] = 0, 0, 0, 0
        for x1, y1, x2, y2 in bx:
            mask[max(0, int(np.floor(y1))): max(0, int(np.ceil(y2)) + 1), max(0, int(np.floor(x1))): max(0, int(np.ceil(x2)) + 1)] = 0
        p0 = cv2.goodFeaturesToTrack(gray, maxCorners=600, qualityLevel=0.01, minDistance=7, mask=mask)
        prev = {"fi": fi, "gray": gray, "depth": d, "p0": p0}
    return {"cars": pd.DataFrame(cars, columns=["frame_idx", "track_id", "c_med"]),
            "pairs": pd.DataFrame({k: (np.concatenate(v) if v else np.empty(0)) for k, v in pairs.items()}),
            "grid_frames": np.array(gframes), "grid": np.stack(grids), "proc_hw": shape, "size": (W, H)}
