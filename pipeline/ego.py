"""Block 2: ego speed from the dash odometer.

Points: tools/auto_odometer_points.pick_points. Speeds: tools/dashcam_range_speed.dash_cycle_speeds with the pipeline's
ego policy (two windows must agree or the short one must lock strongly; joint octave choice; gaps <= 2 s interpolated;
1 s rolling median), as copied in research/odometer_fix/odo_rerun.py, with --stopped-policy flag: no reading stays empty,
never 0. The dash cycle is the local legal value (Taiwan 10 m; California freeway 14.63 m, local roads 7.315 m).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

CYCLES_M = {"tw": 10.0, "ca_highway": 14.63, "ca_local": 7.315}     # road_class names of the shared spec (SPEC 2.3)
UNKNOWN_CYCLE = "ca_highway"        # 'unknown' road class: the method's own choice (SPEC 2.3); comma2k19 is mostly freeway
# where the picker looks for dashes, as fractions of the image height (REPRODUCE.md route 1 for comma2k19)
PICK = {"comma2k19": dict(road_top=0.48, road_bottom=0.68, window_s=3.0, sample_band_px=120),
        "default": dict(window_s=3.0, sample_band_px=120)}
WINDOW_S = 3.0


def ego_speed(frames: list[Path], fps: float, cycle_m: float, pick: dict) -> tuple[np.ndarray, np.ndarray, dict]:
    """km/h per frame (NaN where nothing is read), the source per frame, and the picker's diagnostics."""
    from auto_odometer_points import pick_points
    from dashcam_range_speed import dash_cycle_speeds

    n = len(frames)
    ego = np.full(n, np.nan)
    method = np.array(["none"] * n, dtype=object)
    pts, diag, sig = pick_points(frames, fps, with_signals=True, **pick)
    diag = {"points": [list(p) for p in pts], "picker": diag}
    if not pts:
        return ego, method, diag
    kw = {"octave_threshold": 0.75, "join_octaves": True, "max_rel_change_per_s": 1.5}
    v1, c1, p1 = dash_cycle_speeds(frames, pts, cycle_m, fps, WINDOW_S, sig=sig, **kw)
    v2, _, _ = dash_cycle_speeds(frames, pts, cycle_m, fps, WINDOW_S * 1.7, sig=sig, **kw)
    agree = np.isfinite(v1) & np.isfinite(v2) & (np.abs(v1 - v2) <= 0.12 * np.maximum(v1, v2))
    strong = np.isfinite(v1) & (c1 >= 0.5) & (p1 >= 0.5)
    v = np.where(agree, 0.5 * (v1 + v2), np.where(strong, v1, np.nan))
    use = np.isfinite(v)
    ego[use] = v[use]
    method[use] = "dash_odometer"
    good = np.isfinite(ego)
    if good.any() and (~good).any():
        idx = np.arange(n)
        filled = np.interp(idx, idx[good], ego[good])
        for run in np.split(idx[~good], np.where(np.diff(idx[~good]) > 1)[0] + 1):
            if 0 < len(run) <= int(round(2.0 * fps)) and run[0] > 0 and run[-1] < n - 1:
                ego[run] = filled[run]
                method[run] = "interpolated"
    half = max(3, int(round(fps)) | 1) // 2
    with np.errstate(all="ignore"):
        ego = np.array([np.nanmedian(ego[max(0, i - half): i + half + 1])
                        if np.isfinite(ego[max(0, i - half): i + half + 1]).any() else np.nan for i in range(n)])
    method[np.isfinite(ego) & (method == "none")] = "median_fill"
    return ego * 3.6, method, diag
