#!/usr/bin/env python3
"""Recover the hood-y an archived dashcam run used, by matching its ground plane.

Two demos (dc002, dc008) were archived before the run parameters were being
recorded, and CLAUDE.md carried a guess read off the image ("850 / 950"). A guess
is not reproducible, and it is not harmless: hood-y is the bottom of the ROI the
ground plane is fitted in, so a wrong value fits a different plane, and then a
rerun cannot be compared against the archive at all. On dc008 the guess moved the
implied horizon by 9.5 px and the distances by ~6%.

It does not have to be guessed. tracks.json stores the plane coefficients the run
used, the plane fit is deterministic given (point cloud, hood-y), and hood-y is an
integer over a small range -- so scanning it recovers the exact value. Both demos
come back as EXACT at hood-y = 900.

Usage:  python3 tools/solve_archived_hood.py dc002 dc008
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lane_dash_calibration import fit_ground_plane_raw, load_point_cloud_points  # noqa: E402

DEMO = Path("data/output/dashcam_demo")
PLY = Path("data/output/sharp_gaussians")
_CACHE: dict[str, tuple] = {}


def plane_for(ply: Path, hood: int, shape: tuple[int, int]):
    key = str(ply)
    if key not in _CACHE:
        _CACHE[key] = load_point_cloud_points(ply)
    pts, _, meta = _CACHE[key]
    intr = meta.get("intrinsics") or {}
    fx = float(intr["fx"])
    fy = float(intr.get("fy") or fx)
    h, w = shape
    cx = float(intr.get("cx", (w - 1) * 0.5))
    cy = float(intr.get("cy", (h - 1) * 0.5))
    z = pts[:, 2]
    u = cx + fx * pts[:, 0] / z
    v = cy + fy * pts[:, 1] / z
    return fit_ground_plane_raw(pts, u, v, (0, int(h * 0.45), w, hood))


def archived_plane(name: str) -> dict:
    for cand in (DEMO / f"{name}_trackv3/tracks.json", DEMO / f"{name}/tracks.json"):
        if cand.exists():
            return json.loads(cand.read_text(encoding="utf-8"))["ground_plane"]
    raise SystemExit(f"no archived tracks.json for {name}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cases", nargs="+")
    ap.add_argument("--range", default="700,1080,10", help="lo,hi,step for the hood-y scan")
    ap.add_argument("--shape", default="1080,1920", help="frame height,width")
    a = ap.parse_args()
    lo, hi, step = (int(x) for x in a.range.split(","))
    shape = tuple(int(x) for x in a.shape.split(","))

    for name in a.cases:
        target = archived_plane(name)
        ply = PLY / f"{name}_ref.ply"
        best = None
        for hood in range(lo, hi + 1, step):
            try:
                g = plane_for(ply, hood, shape)
            except Exception:
                continue
            if not g:
                continue
            err = sum(abs(g[k] - target[k]) for k in ("a", "b", "c"))
            if best is None or err < best[0]:
                best = (err, hood, g)
            if err < 1e-12:
                break
        if best is None:
            print(f"{name}: no plane could be fitted in the scanned range")
            continue
        err, hood, g = best
        verdict = "EXACT" if err < 1e-9 else f"closest only (residual {err:.2e}) -- step may be too coarse"
        print(f"{name}: hood-y = {hood}  [{verdict}]")
        print(f"   archived: a={target['a']:.6f} b={target['b']:.6f} c={target['c']:.6f}")
        print(f"   solved  : a={g['a']:.6f} b={g['b']:.6f} c={g['c']:.6f}")


if __name__ == "__main__":
    main()
