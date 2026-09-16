from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "tools"))

from utils.pointcloud_io import load_point_cloud_points
from lane_dash_calibration import fit_ground_plane_raw

VEHICLE_CLASSES = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}

# Same lesson as the CCTV v3 tracker: YOLO flickers between car/truck/bus on
# ONE vehicle, so association and duplicate suppression must compare size
# groups, not raw classes, or every flicker cuts the track and the target is
# reported twice (dc007's red car lived as id20->id105->id171 partly for this
# reason). Two-wheelers stay separate: a scooter filtering past a car must
# never inherit its track.
CLASS_GROUP = {"car": "4w", "bus": "4w", "truck": "4w", "motorcycle": "2w"}


def _box_overlap(a: list[float], b: list[float]) -> float:
    """Intersection over the SMALLER box area -- catches nested double boxes
    (car box inside a truck box on the same vehicle) that plain IoU misses."""
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    area_a = max(1e-6, (a[2] - a[0]) * (a[3] - a[1]))
    area_b = max(1e-6, (b[2] - b[0]) * (b[3] - b[1]))
    return inter / min(area_a, area_b)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Following-distance and speed estimation from a MOVING dashcam. "
        "On flat road the ground plane is fixed in the CAMERA frame (height and pitch stay "
        "constant while driving), so one SHARP reference frame plus a legal lane-dash scale "
        "makes every frame metric: vehicle ground contacts ray-cast to range ahead, road-surface "
        "optical flow ray-casts to ego speed, and target absolute speed = ego + d(range)/dt. "
        "The dashcam's own GPS speed burned into the OSD is the non-circular ground truth "
        "for the ego-speed estimate."
    )
    parser.add_argument("--frames-dir", required=True, help="Directory of ordered 30fps frames.")
    parser.add_argument("--fps", type=float, required=True, help="True video frame rate (e.g. 29.97).")
    parser.add_argument("--reference-pointcloud", required=True, help="SHARP PLY of one frame from THIS video.")
    parser.add_argument("--pointcloud-scale", type=float, required=True, help="Lane-dash calibrated scale factor.")
    parser.add_argument("--scale-cv", type=float, default=0.0, help="Calibration dash-length CV (for the HUD).")
    parser.add_argument("--hood-y", type=int, default=900, help="Image row where the hood begins; pixels below are excluded from plane fit and flow.")
    parser.add_argument("--yolo-model", default="checkpoints/yolov8m-seg.pt")
    parser.add_argument("--conf", type=float, default=0.3)
    parser.add_argument("--camera-label", default="", help="Name shown in the HUD.")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--render-video", default="", help="Output annotated mp4 (native 1:1 frames at --fps).")
    parser.add_argument("--odometer-points", default="",
                        help="Semicolon-separated x,y pixels ON the lane dash line (e.g. '586,800;546,850'). "
                        "Enables the dash-cycle odometer: the brightness at a fixed image spot oscillates once "
                        "per legal dash cycle as the paint streams past, so ego speed = cycle_m / period. "
                        "Immune to lens distortion, SHARP scale, and pitch vibration -- unlike optical flow.")
    parser.add_argument("--dash-cycle-m", type=float, default=10.0,
                        help="Legal dash cycle length: 4m dash + 6m gap = 10m on ordinary roads/expressways, "
                        "4m + 8m = 12m on freeways.")
    parser.add_argument("--odometer-window-s", type=float, default=3.0, help="Sliding autocorrelation window.")
    parser.add_argument("--octave-threshold", type=float, default=0.75,
                        help="DEPRECATED / no-op, kept so existing run commands still parse. The old "
                        "octave-guard + sub-octave chain it tuned was replaced by one-shot harmonic-comb "
                        "fundamental selection (a five-demo audit found the two corrections cancelled on "
                        "98-100%% of frames); this value is now ignored.")
    parser.add_argument("--no-join-octaves", dest="join_octaves", action="store_false",
                        help="Choose each frame's fundamental independently, as before 2026-08-17. "
                        "The default joins the choice along time, which is what stops a lock halving "
                        "for a second and coming back where a retroreflective marker puts a real peak "
                        "at half the paint period (measured on comma2k19's night freeway: MAE 13.9 -> "
                        "4.5, p90 88.3 -> 3.4). Turn it off to reproduce an archived run.")
    parser.add_argument("--max-rel-change-per-s", type=float, default=1.5,
                        help="Speed change per second the joint octave choice treats as free, as a "
                        "fraction of speed. 1.5 is far above any real vehicle and far below the 0.69 "
                        "log-jump an octave costs, which is the only thing it needs to separate.")
    parser.add_argument("--distance-correction", type=float, default=1.0,
                        help="Multiplier on forward distance, from "
                        "tools/odometer_distance_calib.py. SHARP's fixed-FOV assumption reads "
                        "range 8-32%% long depending on the camera (hs005 0.760, dc002 0.845, "
                        "dc008 0.874, dc006 0.923); lateral width is unaffected and must not be "
                        "scaled. Default 1.0 reproduces the archived runs.")
    parser.add_argument("--max-sens-m-per-px", type=float, default=0.8,
                        help="far-range display threshold. Looser than the CCTV pipeline's 0.30: at 30 fps there "
                        "are ~30x more observations to average, so a given per-pixel sensitivity costs far less "
                        "speed accuracy than at 1-4 fps.")
    return parser.parse_args()


def build_geometry(ply_path: Path, scale: float, image_shape: tuple[int, int], hood_y: int,
                   distance_correction: float = 1.0):
    points_xyz, _, metadata = load_point_cloud_points(ply_path)
    intr = metadata.get("intrinsics") or {}
    fx = float(intr["fx"])
    fy = float(intr.get("fy") or fx)
    h, w = image_shape
    cx = float(intr.get("cx", (w - 1) * 0.5))
    cy = float(intr.get("cy", (h - 1) * 0.5))

    z = points_xyz[:, 2]
    valid = np.isfinite(points_xyz).all(axis=1) & (z > 1e-6)
    u = np.where(valid, fx * (points_xyz[:, 0] / z) + cx, np.nan)
    v = np.where(valid, fy * (points_xyz[:, 1] / z) + cy, np.nan)
    # Plane fit must stop above the hood: the hood is a reflective plane of
    # its own and would hijack RANSAC.
    ground = fit_ground_plane_raw(points_xyz, u, v, (0, int(h * 0.45), w, hood_y))
    if ground is None:
        raise RuntimeError("Ground plane fit failed.")
    a, b, c = ground["a"], ground["b"], ground["c"]

    # On-plane orthonormal basis: e_fwd = viewing axis projected on the plane
    # (the direction of travel for a forward dashcam), e_lat completes it.
    n = np.array([a, -1.0, b], dtype=np.float64)
    n /= np.linalg.norm(n)
    fwd = np.array([0.0, 0.0, 1.0]) - n * float(n @ np.array([0.0, 0.0, 1.0]))
    e_fwd = fwd / np.linalg.norm(fwd)
    e_lat = np.cross(n, e_fwd)
    e_lat /= np.linalg.norm(e_lat)

    def pixel_to_plane(px: float, py: float) -> np.ndarray | None:
        """Pixel -> (lat_m, fwd_m) on the road plane, camera-relative, scaled.

        `distance_correction` scales the FORWARD component only, and that
        asymmetry is the whole point. SHARP assumes a fixed field of view
        (fx = 0.7955 x width), and forward distance goes as the focal length
        while lateral width at a given row goes as camera height alone -- the
        focal cancels there. So a wrong FOV stretches range and leaves widths
        correct, which is exactly what the lane-width anchor cannot see and what
        tools/odometer_distance_calib.py measures: 0.76 to 0.92 depending on the
        camera. Scaling both components would break the lane-width calibration
        that is already right.
        """
        dx = (px - cx) / fx
        dy = (py - cy) / fy
        denom = dy - a * dx - b
        if abs(denom) < 1e-9:
            return None
        t = c / denom
        if t <= 0:
            return None
        p = np.array([dx * t, dy * t, t], dtype=np.float64) * scale
        return np.array([float(p @ e_lat), float(p @ e_fwd) * distance_correction])

    return pixel_to_plane, ground


def road_change_fraction(prev_gray, gray, boxes, hood_y: int) -> float:
    """Fraction of road-band pixels that changed between consecutive frames.

    Feature-tracking motion cues proved unreliable across rigs (corners latch
    onto windshield reflections that are pixel-static at any speed, which
    once judged a 70 km/h night drive "stopped"), so the standstill cue is
    plain frame differencing on the road band: any real motion -- day or
    headlight-lit night -- churns the road texture, while at a stop only
    other road users change pixels, and those are masked out via the
    detector boxes. The band stays above the hood and the burned-in OSD.
    """
    h, w = gray.shape
    y0, y1 = int(h * 0.55), min(hood_y, h - 80)
    x0, x1 = int(w * 0.25), int(w * 0.75)
    if y1 <= y0:
        return 1.0
    diff = cv2.absdiff(gray[y0:y1, x0:x1], prev_gray[y0:y1, x0:x1]) > 14
    mask = np.ones_like(diff, dtype=bool)
    for bx1, by1, bx2, by2 in boxes:
        ax1 = max(0, int(bx1) - x0)
        ay1 = max(0, int(by1) - y0)
        ax2 = min(diff.shape[1], int(bx2) - x0)
        ay2 = min(diff.shape[0], int(by2) - y0)
        if ax2 > ax1 and ay2 > ay1:
            mask[ay1:ay2, ax1:ax2] = False
    if mask.sum() < 500:
        return 1.0
    return float(diff[mask].mean())


def extract_odometer_signals(frames: list[Path], points: list[tuple[int, int]],
                             band_px: int = 120) -> dict:
    """Per-frame (pulse strength, pulse x-offset) at each odometer point.

    `band_px` is the lateral search half-width. 120 px suits the 1920-wide
    Taiwanese dashcams every existing case uses and is the default so their
    numbers do not move, but it is not a constant of nature: it should stay
    inside one lane's image width at the sampling row, and on a 1164-wide
    wide-FOV camera the far rows put adjacent lane lines only ~175 px apart, so
    the default window spans more than one lane. (Measured on comma2k19, that
    straddle turned out NOT to be what made those clips read double -- halving
    the band moved their MAE by ~1 km/h. The doubling came from raised pavement
    markers at half the paint cycle, which no band width can exclude.)
    """
    sig = {pt: [] for pt in points}
    for f in frames:
        g = cv2.cvtColor(cv2.imread(str(f)), cv2.COLOR_BGR2GRAY)
        # Local contrast (brighter than the surrounding road), like the dash
        # detector uses: robust to global illumination shifts.
        diff = cv2.subtract(g, cv2.GaussianBlur(g, (51, 51), 0)).astype(np.float32)
        for (x, y) in points:
            # The car drifts laterally inside (or across) its lane over the
            # clip, so a FIXED pixel slides off the paint. Instead search a
            # band on the row: whenever a dash crosses this row, the band's
            # peak lights up no matter where the line has wandered.
            x0 = max(0, x - band_px)
            band = diff[max(0, y - 6): y + 7, x0: x + band_px + 1]
            if band.size == 0:
                sig[(x, y)].append((0.0, np.nan))
                continue
            col = band.mean(axis=0)
            # Where in the band the pulse sits: slow drift is normal lane
            # wander, but a systematic slide across the band betrays a lane
            # change (the paint being crossed is not the statutory lane dash).
            sig[(x, y)].append((float(col.max() - np.median(col)),
                                float(x0 + int(np.argmax(col)) - x)))
    return {pt: np.asarray(v, dtype=np.float64) for pt, v in sig.items()}


def _peak_snap(ac: np.ndarray, p: float, lo: int, hi: int) -> int | None:
    """Snap a candidate lag to the nearest genuine autocorrelation peak within
    +-2 frames. Returns None if it is out of range or not a local maximum (so a
    candidate that lands in an anticorrelation valley -- e.g. half the clean
    cruise lag -- is rejected rather than forced onto a shoulder)."""
    p = int(round(p))
    if p < lo or p > hi:
        return None
    best = p
    for q in range(max(lo, p - 2), min(hi, p + 2) + 1):
        if ac[q] > ac[best]:
            best = q
    if best <= 0 or best >= len(ac) - 1:
        return None
    if not (ac[best] >= ac[best - 1] and ac[best] >= ac[best + 1]):
        return None
    return best


def _comb_score(ac: np.ndarray, period: int, hi_s: int) -> float:
    """Harmonic comb minus anti-comb for a candidate fundamental period.

    A true fundamental peaks at every integer multiple (comb high) and sits in
    an anticorrelation valley at every half-integer multiple (anti low), so
    comb-anti is large. A harmonic (period = T/2) has its half-multiples land
    on the real T, 2T peaks -> anti high -> score low. A subharmonic
    (period = 2T) has its half-multiples land on the real T, 3T peaks -> anti
    high -> score low. One pass therefore separates the fundamental from both
    the octave-up and octave-down aliases without the doubling/halving chain.
    """
    ints, halfs = [], []
    k = 1
    while k * period <= hi_s:
        ints.append(ac[int(round(k * period))])
        h = int(round((k - 0.5) * period))
        if h >= 1:
            halfs.append(ac[h])
        k += 1
    if not ints:
        return -1e9
    comb = float(np.mean(ints))
    anti = float(np.mean(halfs)) if halfs else 0.0
    return comb - anti


def _dual_line(strength: np.ndarray, xoff: np.ndarray) -> float | None:
    """Detect two interleaved lane lines inside one search band.

    Two parallel lines (ego + adjacent lane) streaming past produce a brightness
    pulse train at HALF the per-line period, so the strength autocorrelation can
    latch onto that half period and double the speed (a true 54 km/h reads 108).
    Brightness alone cannot tell that from a single line at half the cycle -- but
    the pulses then alternate between two lateral positions. Detect that: pulse
    peaks must split into two x-clusters (separated well beyond their own
    scatter) that swap side on nearly every consecutive pulse. Strict on purpose
    -- a single wandering line must never trip this, or its speed would halve.

    Returns the median inter-pulse spacing (frames) when two lines are present,
    else None. The caller doubles THAT spacing to recover the per-line cycle,
    not the argmax lag: at high speed the argmax already sits on the per-line
    period (the half period is below resolution), so doubling the argmax would
    over-correct, whereas 2 x pulse-spacing is right in both regimes.
    """
    smax = float(np.nanmax(strength)) if strength.size else 0.0
    thr = max(10.0, 0.4 * smax)
    idx = [k for k in range(1, len(strength) - 1)
           if strength[k] >= thr and strength[k] >= strength[k - 1] and strength[k] > strength[k + 1]]
    if len(idx) < 4:
        return None
    idx = np.asarray(idx)
    xs = xoff[idx]
    ok = np.isfinite(xs)
    idx, xs = idx[ok], xs[ok]
    if len(xs) < 4:
        return None
    med = float(np.median(xs))
    side = (xs > med).astype(int)
    lo_grp, hi_grp = xs[side == 0], xs[side == 1]
    if len(lo_grp) < 2 or len(hi_grp) < 2:
        return None
    sep = float(hi_grp.mean() - lo_grp.mean())
    within = float(np.sqrt((lo_grp.var() + hi_grp.var()) / 2.0)) + 1e-6
    if sep < 6.0 or sep < 2.5 * within:
        return None
    switches = float(np.mean(side[1:] != side[:-1]))
    if switches <= 0.75:
        return None
    return float(np.median(np.diff(idx)))


def _join_octaves(cands: list[dict | None], fps: float, cycle_m: float,
                  max_rel_change_per_s: float = 1.5, break_penalty: float = 20.0) -> list[int | None]:
    """Choose each frame's fundamental jointly along time, not frame by frame.

    Inside a single window the fundamental can be genuinely undecidable: measured
    on comma2k19's night freeway, a retroreflective marker midway between the
    dashes puts a real autocorrelation peak at half the paint period, and five
    shape features (pulse width, peakedness, area, amplitude, vertical extent)
    all fail to tell the two pulse types apart -- the last differs by one image
    row, which a long night exposure smears away. So no per-window rule can fix
    it, and the previous code chose per frame per point with nothing tying one
    frame's choice to its neighbours'; a lock could halve for a second and come
    back.

    Across time it is decidable, because a vehicle cannot double its speed
    between two frames. This is a Viterbi over each frame's own candidate lags:
    the emission term keeps the harmonic-comb preference that already works, and
    the transition term charges for implied acceleration. Nothing is invented --
    every candidate is a peak this frame's autocorrelation actually has, so a
    genuine change of speed is still free to be followed; what becomes expensive
    is jumping an octave and back.

    The transition term must be SCALE-FREE, and getting that wrong is worse than
    not doing it at all. A first attempt charged absolute |dv|, which regressed
    the Taiwanese archive badly (dc003 coverage 57.8% -> 27.1%, wow001 median
    89.4 -> 77.9 km/h, 229 frames moved on hs006s): a path running an octave low
    also runs its speed CHANGES an octave low, so it always looks smoother, and
    the penalty quietly rewarded halving. Charging |d log v| costs the true and
    the halved trajectory exactly the same, which leaves the octave to be decided
    by the evidence -- the comb score summed along the run -- and leaves the
    transition term doing only what it should: making a jump between octaves
    (|log 2| = 0.69) expensive while any real acceleration stays free.

    `break_penalty` is the cost of an impossible transition rather than a ban:
    footage really does contain discontinuities (a lane change, a dropout), and a
    hard constraint would propagate one bad neighbourhood through a whole clip.
    """
    n = len(cands)
    # Per-frame allowance, from a per-second one, so a 10 fps clip is not held to
    # a 30 fps clip's step. 1.5/s is far above any real vehicle (150% of speed per
    # second) and far below an octave, which is the only thing this must catch.
    rel_tol = max_rel_change_per_s / fps
    dp: list[dict[int, float]] = [{} for _ in range(n)]
    back: list[dict[int, int]] = [{} for _ in range(n)]

    for i, rec in enumerate(cands):
        if not rec or not rec["scores"]:
            continue
        # Emission: comb score relative to this frame's best, so a frame whose
        # autocorrelation is uniformly strong or weak weighs the same as any
        # other -- only the preference between ITS candidates should matter.
        best = max(rec["scores"].values())
        prev = dp[i - 1] if i > 0 else {}
        for lag, sc in rec["scores"].items():
            emit = float(sc - best)
            if not prev:
                dp[i][lag] = emit
                back[i][lag] = -1
                continue
            bestval, bestsrc = -1e18, -1
            for plag, pval in prev.items():
                # log-ratio of speeds == log-ratio of lags, inverted; use the lags
                # directly so cycle_m and fps cannot affect the decision at all.
                step = abs(np.log(plag / lag))
                val = pval - break_penalty * max(0.0, step - rel_tol)
                if val > bestval:
                    bestval, bestsrc = val, plag
            dp[i][lag] = bestval + emit
            back[i][lag] = bestsrc

    # Backtrack each maximal run of frames that have candidates: a gap resets the
    # chain, so one unreadable stretch cannot drag its neighbours' choices.
    out: list[int | None] = [None] * n
    i = n - 1
    while i >= 0:
        if not dp[i]:
            i -= 1
            continue
        end = i
        while i >= 0 and dp[i]:
            i -= 1
        start = i + 1
        lag = max(dp[end], key=lambda lg: dp[end][lg])
        for k in range(end, start - 1, -1):
            out[k] = lag
            nxt = back[k].get(lag, -1)
            if nxt == -1:
                break
            lag = nxt
    return out


def dash_cycle_speeds(frames: list[Path], points: list[tuple[int, int]], cycle_m: float,
                      fps: float, window_s: float, sig: dict | None = None,
                      octave_threshold: float = 0.75,  # retained for CLI/API compat; no longer used
                      lag_events: list | None = None,
                      band_px: int = 120,
                      join_octaves: bool = True,
                      max_rel_change_per_s: float = 1.5) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Ego speed from the legal dash cycle streaming past fixed image spots.

    The lane paint is a legal-length periodic pattern (dash+gap), so the
    local-contrast brightness at a fixed pixel oscillates at exactly
    v / cycle_m Hz. A sliding autocorrelation finds the period; the speed
    needs no scale factor, no ground plane, and no undistortion -- the only
    inputs are the statutory cycle length and the frame rate. Returns
    (speed_ms, confidence=autocorr peak, peak_prominence) per frame, NaN/0
    where no clear peak.

    `lag_events`, when given, collects one dict per surviving per-point
    candidate recording lag_argmax, the selected lag, and whether the
    dual-line override fired. Observation only -- it never changes a value --
    but it is the audit trail for how the one-shot fundamental selection
    behaves on real footage.

    `octave_threshold` is retained only so existing CLI/API callers keep
    working; the doubling-then-halving chain it tuned has been replaced by
    harmonic-comb selection and the value is ignored.
    """
    if sig is None:
        sig = extract_odometer_signals(frames, points, band_px)
    n = len(frames)
    win = int(round(window_s * fps))
    half = win // 2
    lag_min, lag_max = int(0.25 * fps), int(3.0 * fps)  # 3..40 m/s for a 10 m cycle
    v = np.full(n, np.nan)
    conf = np.zeros(n)
    prom = np.zeros(n)
    # Pass 1 collects each frame's candidate fundamentals per point; pass 2 picks
    # among them jointly along time; pass 3 applies the gates and the cross-point
    # consensus. The split exists only so the octave choice can see its
    # neighbours -- every per-window computation below is unchanged.
    collected: dict[tuple[int, int], list[dict | None]] = {pt: [None] * n for pt in points}
    for i in range(n):
        j0, j1 = max(0, i - half), min(n, i + half)
        if j1 - j0 < lag_max + 10:
            j0, j1 = max(0, min(j0, n - lag_max - 10)), min(n, max(j1, lag_max + 10))
        for pt in points:
            arr = np.asarray(sig[pt])[j0:j1]
            s = arr[:, 0].copy()
            s = s - s.mean()
            # Signal-strength gate: when the vehicle is stopped a dash can sit
            # inside the search band as a near-constant HIGH signal whose
            # residual noise autocorrelates into absurd speed locks. No
            # streaming paint, no measurement.
            if s.std() < 2.0:
                continue
            # Lane-keeping gate: pulses from the statutory lane dash stay put
            # inside the search band (drift < ~15 px per window); during a
            # LANE CHANGE the band sweeps across ramp/exit micro-dashes and
            # the pulse x slides system-wide, producing rock-solid locks at
            # fantasy speeds (146 km/h at a true 82). Wide pulse-x spread ->
            # this point is not looking at legal paint right now.
            pulsed = arr[:, 0] > 10.0
            if pulsed.sum() >= 4:
                q75, q25 = np.percentile(arr[pulsed, 1], [75, 25])
                # Expressed as a share of the search band, so narrowing the band
                # for a wide-FOV camera does not silently also make this gate
                # stricter in relative terms.
                if q75 - q25 > 50.0 * band_px / 120.0:
                    continue
            ac = np.correlate(s, s, "full")[len(s) - 1:]
            if ac[0] <= 0:
                continue
            ac = ac / ac[0]
            # A lock must contain >= 2 full cycles inside the window, or slow
            # crawls produce single-cycle pseudo-peaks; below the implied
            # minimum speed the method honestly reports nothing.
            hi = min(lag_max, (j1 - j0) // 2, len(ac) - 2)
            # The central lobe is as wide as one dash PASSAGE (several frames),
            # so searching from lag_min alone latches onto its shoulder and
            # fabricates absurd speeds. Standard pitch-detector fix: advance
            # to the first local minimum of the autocorrelation, then peak-pick.
            d = np.diff(ac[: hi + 1])
            first_min = next((k for k in range(1, len(d)) if d[k - 1] < 0 and d[k] >= 0), None)
            if first_min is None:
                continue
            lo = max(lag_min, first_min)
            if hi <= lo:
                continue
            lag = lo + int(np.argmax(ac[lo:hi]))
            lag_argmax = lag
            # One-shot fundamental selection over {argmax/2, argmax, 2*argmax}.
            # The old code doubled the lag (octave guard) then halved it back
            # (sub-octave stud fix); a five-demo audit found the two cancel on
            # 98-100% of frames, so the doubling was dead and the neighbor-lane
            # double-speed it was meant to stop leaked through anyway. Instead
            # score each candidate period with a harmonic comb (peaks at integer
            # multiples, valleys at half-multiples) and take the best -- this
            # picks the statutory cycle whether the argmax landed on a harmonic
            # (adjacent-lane sub-structure) or a subharmonic (cat's-eye studs at
            # 20 m). Autocorrelation of brightness alone still cannot tell one
            # line at half the cycle from two interleaved lines at the full
            # cycle, so when the pulses resolve into two alternating lateral
            # positions the true period is 2x the measured pulse spacing (not
            # 2*argmax -- at speed the argmax already sits on the per-line
            # period); that dual-line override runs first.
            hi_s = min(len(ac) - 2, 4 * lag, 2 * hi)  # comb sampling reach
            lo_c = max(lag_min, first_min)
            pulse_gap = _dual_line(arr[:, 0], arr[:, 1])
            if pulse_gap is not None and (snap := _peak_snap(ac, 2 * pulse_gap, lo_c, hi)) is not None:
                # The dual-line reading is a direct observation of the geometry,
                # not a preference among peaks, so it stands alone as the frame's
                # only candidate and the joint pass has nothing to overrule.
                scores = {snap: 0.0}
            else:
                scores = {}
                for cand_p in (lag / 2.0, float(lag), 2.0 * lag):
                    snap = _peak_snap(ac, cand_p, lo_c, hi)
                    if snap is None:
                        continue
                    sc = _comb_score(ac, snap, hi_s)
                    if sc > scores.get(snap, -1e18):
                        scores[snap] = sc
                if not scores:
                    continue
            collected[pt][i] = {"scores": scores, "ac": ac, "first_min": first_min,
                                "s": s, "lag_argmax": lag_argmax,
                                "dual_line": pulse_gap is not None}

    # Pass 2: the octave choice, jointly along time.
    chosen = {pt: (_join_octaves(collected[pt], fps, cycle_m, max_rel_change_per_s)
                   if join_octaves else
                   [(max(r["scores"], key=r["scores"].get) if r else None) for r in collected[pt]])
              for pt in points}

    # Pass 3: gates and cross-point consensus, per frame.
    for i in range(n):
        cand: list[tuple[float, float, int, np.ndarray, float]] = []
        for pt in points:
            rec = collected[pt][i]
            lag = chosen[pt][i]
            if rec is None or lag is None:
                continue
            ac, first_min, s = rec["ac"], rec["first_min"], rec["s"]
            # Peak-prominence gate: a genuine dash lock rises from a real
            # valley (measured prominence 0.7-1.1); the broad shoulder of a
            # non-periodic bursty signal barely rises above it (0.00-0.03).
            prominent = float(ac[lag] - ac[first_min]) >= 0.3
            if lag_events is not None:
                lag_events.append({
                    "frame": i, "point_y": pt[1],
                    "lag_argmax": int(rec["lag_argmax"]), "lag_selected": int(lag),
                    "dual_line": bool(rec["dual_line"]),
                    "ac_final": float(ac[lag]), "prominent": prominent,
                })
            if not prominent:
                continue
            c = float(ac[lag])
            lag_f = float(lag)
            if 1 <= lag < len(ac) - 1:
                denom = ac[lag - 1] - 2 * ac[lag] + ac[lag + 1]
                if abs(denom) > 1e-9:  # parabolic sub-frame refinement
                    lag_f = lag + 0.5 * float(ac[lag - 1] - ac[lag + 1]) / float(denom)
            if c >= 0.25 and lag_f > 0:
                cand.append((cycle_m * fps / lag_f, c, pt[1], s, float(ac[lag] - ac[first_min])))
        # Anti-vibration phase gate: engine/handlebar shake is periodic too,
        # and it fools every other check because it is stationary and global.
        # But real paint streams PAST the rows in sequence (far row pulses
        # frames before the near row), while shake hits all rows in phase.
        # If every distinct-row pair peaks at ~zero cross-correlation offset,
        # the "signal" is the camera shaking, not the road moving.
        if len(cand) >= 2:
            pairs = [(a, b) for ai, a in enumerate(cand) for b in cand[ai + 1:] if a[2] != b[2]]
            if pairs:
                zero_phase = 0
                for a, b in pairs[:3]:
                    xc = np.correlate(a[3], b[3], "full")
                    off = int(np.argmax(xc)) - (len(a[3]) - 1)
                    if abs(off) < 2:
                        zero_phase += 1
                if zero_phase == min(len(pairs), 3):
                    cand = []
        # Split-lock gate: when the surviving points disagree by >1.5x (one
        # latched onto an adjacent-lane pattern or a seam), the median of two
        # irreconcilable readings is their AVERAGE -- a fantasy value (34 and
        # 98 km/h "agreeing" on 69). Keep the majority cluster around the
        # median; if no such cluster exists, report nothing.
        if len(cand) >= 2:
            vs = np.array([x[0] for x in cand])
            if vs.max() / max(vs.min(), 1e-9) > 1.5:
                med = float(np.median(vs))
                keep = [x for x in cand if abs(x[0] - med) <= 0.25 * med]
                cand = keep if len(keep) >= 2 else []
        if cand:
            # Consensus across sampling points: the median shrugs off a single
            # point whose patch drifted onto a crack or a neighboring line.
            v[i] = float(np.median([x[0] for x in cand]))
            conf[i] = float(np.median([x[1] for x in cand]))
            prom[i] = float(np.median([x[4] for x in cand]))
    return v, conf, prom


def _endpoint_velocity_2d(obs: list[dict], tail: bool, window_s: float = 1.0) -> np.ndarray:
    """Constant-velocity fit over a fragment's first/last `window_s` seconds
    of RELATIVE (lat, fwd) positions."""
    t = np.array([o["t"] for o in obs])
    P = np.array([[o["lat_m"], o["fwd_m"]] for o in obs])
    m = (t >= t[-1] - window_s) if tail else (t <= t[0] + window_s)
    if m.sum() < 3 or float(t[m][-1] - t[m][0]) < 0.2:
        return np.zeros(2)
    A = np.column_stack([t[m] - t[m][0], np.ones(int(m.sum()))])
    return np.array([np.linalg.lstsq(A, P[m][:, ax], rcond=None)[0][0] for ax in range(2)])


def _endpoint_velocity_px(obs: list[dict], tail: bool, window_s: float = 1.0) -> np.ndarray:
    """Same endpoint fit as `_endpoint_velocity_2d`, but on IMAGE coordinates.

    The relative plane goes unreliable exactly when it matters (ego braking
    pitches the camera, so fwd_m jumps metres while the target has barely
    moved on screen); image position keeps working there, so the stitcher
    needs a velocity estimate in both spaces."""
    t = np.array([o["t"] for o in obs])
    P = np.array([[o["px"], o["py"]] for o in obs])
    m = (t >= t[-1] - window_s) if tail else (t <= t[0] + window_s)
    if m.sum() < 3 or float(t[m][-1] - t[m][0]) < 0.2:
        return np.zeros(2)
    A = np.column_stack([t[m] - t[m][0], np.ones(int(m.sum()))])
    return np.array([np.linalg.lstsq(A, P[m][:, ax], rcond=None)[0][0] for ax in range(2)])


def stitch_fragments(tracks: dict[int, dict], max_gap_s: float = 2.0,
                     max_sens: float = 0.8, stitch_log: list | None = None) -> list[tuple[int, int]]:
    """Rejoin track fragments that are the same physical vehicle (CCTV v3
    port, adapted to the ego-relative plane).

    A detection dropout longer than the tracker's 0.8 s active window kills
    the track; the target then re-enters as a fresh id and appears twice in
    the report. Fragment B continues fragment A when A's constant-velocity
    prediction lands on B's first observation under physical gates (size
    group, bbox-height ratio, endpoint-velocity agreement). The gap is capped
    tighter than on CCTV: relative velocity changes with EGO braking too, so
    a long constant-velocity extrapolation in this plane is less trustworthy.
    Accepted joins are recorded in `merged_from` for audit.
    """
    info: dict[int, dict] = {}
    for tid, rec in tracks.items():
        obs = sorted(rec["obs"], key=lambda o: o["t"])
        rec["obs"] = obs
        info[tid] = {
            "grp": CLASS_GROUP.get(rec["cls"]),
            "t0": obs[0]["t"], "t1": obs[-1]["t"],
            "p0": np.array([obs[0]["lat_m"], obs[0]["fwd_m"]]),
            "p1": np.array([obs[-1]["lat_m"], obs[-1]["fwd_m"]]),
            "bh0": obs[0].get("bh", obs[0]["box"][3] - obs[0]["box"][1]),
            "bh1": obs[-1].get("bh", obs[-1]["box"][3] - obs[-1]["box"][1]),
            "sens0": obs[0].get("sens", 0.0), "sens1": obs[-1].get("sens", 0.0),
            "v0": _endpoint_velocity_2d(obs, tail=False),
            "v1": _endpoint_velocity_2d(obs, tail=True),
            "q0": np.array([obs[0]["px"], obs[0]["py"]], dtype=float),
            "q1": np.array([obs[-1]["px"], obs[-1]["py"]], dtype=float),
            "bw0": obs[0]["box"][2] - obs[0]["box"][0],
            "bw1": obs[-1]["box"][2] - obs[-1]["box"][0],
            "u0": _endpoint_velocity_px(obs, tail=False),
            "u1": _endpoint_velocity_px(obs, tail=True),
        }

    candidates = []
    for a, ia in info.items():
        for b, ib in info.items():
            if a == b or ia["grp"] != ib["grp"] or ia["grp"] is None:
                continue
            # Far-range seams are geometric noise; never stitch across them.
            if not (np.isfinite(ia["sens1"]) and np.isfinite(ib["sens0"])):
                continue
            if ia["sens1"] > max_sens or ib["sens0"] > max_sens:
                continue
            gap = ib["t0"] - ia["t1"]
            if not (0.0 < gap <= max_gap_s):
                continue
            ratio = ib["bh0"] / max(1e-6, ia["bh1"])
            if not (0.4 <= ratio <= 2.5):
                continue
            # Lateral-budget gate. The plane error gate below compares B's start
            # against A's CONSTANT-VELOCITY prediction, so a fragment whose
            # endpoint velocity is garbage can predict its way onto a different
            # vehicle and still score a small error: wow001's frame-edge car had
            # lat readings oscillating 8.75/8.36/8.35/8.46/7.70 m, which fitted
            # to 3.6 m/s of "lateral velocity", and 1.4 s of that landed the
            # prediction on the bus 4.8 m away -- error 1.50 m, gate 6.00 m,
            # accepted. Displacement, unlike prediction error, cannot be talked
            # up by a bad velocity fit: road vehicles change lanes at ~0.7-1.2
            # m/s (3.5 m over 3-5 s), so even ego and target swapping lanes in
            # opposite directions stays near 2.4 m/s and cannot hold it across
            # the gap. The 1.5 m floor is ground-point noise -- genuine rejoins
            # across 2-frame dropouts already differ by up to 1.4 m laterally,
            # so a tighter constant would sever correct joins.
            if abs(disp_lat := float(ib["p0"][0] - ia["p1"][0])) > 1.5 * gap + 1.5:
                continue
            va = ia["v1"]
            sa = float(np.linalg.norm(va))
            pred = ia["p1"] + va * gap
            err = float(np.linalg.norm(pred - ib["p0"]))
            # Relative-plane gate: covers velocity-estimate error plus the
            # relative acceleration ego/target braking can add over the gap,
            # capped so a gap never opens wide enough to swallow another car.
            gate = min(6.0, max(1.5, 0.5 * sa * gap + 1.5 * gap * gap + 1.0))
            if err > gate:
                continue
            disp = ib["p0"] - ia["p1"]
            disp_n = float(np.linalg.norm(disp))
            if sa > 2.0 and disp_n > 1.5:
                if float(np.dot(va, disp)) / max(1e-9, sa * disp_n) < 0.2:
                    continue
            sb = float(np.linalg.norm(ib["v0"]))
            if sa > 2.0 and sb > 2.0:
                if float(np.dot(va, ib["v0"])) / max(1e-9, sa * sb) < 0.3:
                    continue
            # Image-space audit of the same join (observation only here; the
            # gate that uses it is applied after the distribution was looked at).
            q_pred = ia["q1"] + ia["u1"] * gap
            err_px = float(np.linalg.norm(q_pred - ib["q0"]))
            disp_px = float(np.linalg.norm(ib["q0"] - ia["q1"]))
            scale_px = max(ia["bw1"], ib["bw0"], 1.0)
            if stitch_log is not None:
                stitch_log.append({
                    "a": a, "b": b, "gap": gap, "err_m": err, "gate_m": gate,
                    "bh_ratio": ratio, "err_px": err_px, "disp_px": disp_px,
                    "bw_tail": float(ia["bw1"]), "bw_head": float(ib["bw0"]),
                    "err_px_rel": err_px / scale_px, "disp_px_rel": disp_px / scale_px,
                    "u1": float(np.linalg.norm(ia["u1"])),
                    "disp_lat": abs(disp_lat), "disp_fwd": float(abs(disp[1])),
                    "sa": sa, "va_lat": float(abs(va[0])),
                })
            candidates.append((err + 0.5 * gap, a, b))

    candidates.sort()
    tail_used: set[int] = set()
    head_used: set[int] = set()
    accepted: list[tuple[int, int]] = []
    for _, a, b in candidates:
        if a in tail_used or b in head_used:
            continue
        tail_used.add(a)
        head_used.add(b)
        accepted.append((a, b))

    follow = dict(accepted)
    merges: list[tuple[int, int]] = []
    for a in list(follow):
        if a in head_used:
            continue  # not a chain head; handled when its own head is walked
        cur = a
        while cur in follow:
            nxt = follow[cur]
            tracks[a]["obs"].extend(tracks[nxt]["obs"])
            tracks[a].setdefault("merged_from", []).append(nxt)
            merges.append((a, nxt))
            del tracks[nxt]
            cur = nxt
        tracks[a]["obs"].sort(key=lambda o: o["t"])
    return merges


def suppress_simultaneous_duplicates(tracks: dict[int, dict]) -> list[tuple[int, int]]:
    """Drop parallel ghost tracks riding on the same vehicle (CCTV v3 port).

    Two real four-wheelers cannot hold < 1.2 m center distance for a second;
    a 4w track that shadows a longer concurrent 4w track that closely for
    >= 70% of its observations is a mask-split/reflection ghost. Two-wheelers
    are exempt: scooters do filter that close."""
    tids = sorted(tracks, key=lambda t: len(tracks[t]["obs"]), reverse=True)
    dropped: list[tuple[int, int]] = []
    for i, big in enumerate(tids):
        rb = tracks[big]
        if rb.get("duplicate_of") or CLASS_GROUP.get(rb["cls"]) != "4w":
            continue
        tb = np.array([o["t"] for o in rb["obs"]])
        Pb = np.array([[o["lat_m"], o["fwd_m"]] for o in rb["obs"]])
        for small in tids[i + 1:]:
            rs = tracks[small]
            if rs.get("duplicate_of") or CLASS_GROUP.get(rs["cls"]) != "4w":
                continue
            ts = np.array([o["t"] for o in rs["obs"]])
            m = (ts >= tb[0]) & (ts <= tb[-1])
            if m.sum() < 8 or float(ts[m][-1] - ts[m][0]) < 1.0:
                continue
            Ps = np.array([[o["lat_m"], o["fwd_m"]] for o in rs["obs"]])[m]
            interp = np.column_stack([np.interp(ts[m], tb, Pb[:, ax]) for ax in range(2)])
            close = np.linalg.norm(Ps - interp, axis=1) < 1.2
            if close.mean() >= 0.7 and m.sum() >= 0.7 * len(ts):
                rs["duplicate_of"] = big
                dropped.append((small, big))
    return dropped


def main() -> None:
    args = parse_args()
    frames = sorted(Path(args.frames_dir).glob("*.jpg")) + sorted(Path(args.frames_dir).glob("*.png"))
    if len(frames) < 10:
        raise RuntimeError("too few frames")
    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = PROJECT_ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    sample = cv2.imread(str(frames[0]))
    img_h, img_w = sample.shape[:2]
    ply_path = Path(args.reference_pointcloud)
    if not ply_path.is_absolute():
        ply_path = PROJECT_ROOT / ply_path
    pixel_to_plane, ground = build_geometry(ply_path, args.pointcloud_scale, (img_h, img_w),
                                           args.hood_y, args.distance_correction)

    from ultralytics import YOLO

    model = YOLO(args.yolo_model)
    dt = 1.0 / args.fps

    # --- pass 1: detections + ego speed per frame ---------------------------
    per_frame_dets: list[list[dict]] = []
    motion_raw: list[float] = [np.nan]
    prev_gray = None
    for i, f in enumerate(frames):
        img = cv2.imread(str(f))
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        result = model.predict(source=img, conf=args.conf, verbose=False)[0]
        dets = []
        boxes_px = []
        if result.boxes is not None:
            boxes = result.boxes.xyxy.cpu().numpy()
            clss = result.boxes.cls.cpu().numpy().astype(int)
            confs = result.boxes.conf.cpu().numpy()
            mask_polys = result.masks.xy if getattr(result, "masks", None) is not None else None
            for di, (box, cls) in enumerate(zip(boxes, clss)):
                if int(cls) not in VEHICLE_CLASSES:
                    continue
                x1, y1, x2, y2 = box
                boxes_px.append((float(x1), float(y1), float(x2), float(y2)))
                gx, gy = (x1 + x2) / 2.0, y2
                if mask_polys is not None and di < len(mask_polys):
                    poly = mask_polys[di]
                    if poly is not None and len(poly) >= 3:
                        ys = poly[:, 1]
                        band = ys >= ys.max() - max(3.0, 0.12 * (y2 - y1))
                        if band.sum() >= 2:
                            gx = float(np.median(poly[band, 0]))
                            gy = float(ys.max())
                if gy >= args.hood_y - 2:  # own hood reflection
                    continue
                pos = pixel_to_plane(gx, gy)
                if pos is None:
                    continue
                up = pixel_to_plane(gx, gy - 1.0)
                sens = float(np.linalg.norm(up - pos)) if up is not None else float("inf")
                dets.append({"cls": VEHICLE_CLASSES[int(cls)], "conf": float(confs[di]),
                             "px": float(gx), "py": float(gy),
                             "box": [float(x1), float(y1), float(x2), float(y2)],
                             "bh": float(y2 - y1), "pos": pos, "sens": sens})
        # One vehicle, one detection (ported from CCTV v3): a car box and a
        # truck box regularly fire on the same pixels; keep only the highest-
        # confidence box among heavily overlapping same-group detections.
        dets.sort(key=lambda d: -d["conf"])
        deduped: list[dict] = []
        for det in dets:
            dup = any(
                CLASS_GROUP.get(det["cls"]) == CLASS_GROUP.get(k["cls"])
                and _box_overlap(det["box"], k["box"]) > 0.65
                for k in deduped
            )
            if not dup:
                deduped.append(det)
        per_frame_dets.append(deduped)
        if prev_gray is not None:
            motion_raw.append(road_change_fraction(prev_gray, gray, boxes_px, args.hood_y))
        prev_gray = gray
        if i % 100 == 0:
            print(f"  pass1 {i}/{len(frames)}")

    n = len(frames)
    # 0.5 s median turns per-pair change fractions into stable spans.
    change = np.array(motion_raw, dtype=np.float64)
    k = max(3, int(round(args.fps * 0.5)) | 1)
    pad = k // 2
    with np.errstate(all="ignore"):
        change = np.array([np.nanmedian(change[max(0, i - pad): i + pad + 1])
                           if np.isfinite(change[max(0, i - pad): i + pad + 1]).any() else np.nan
                           for i in range(n)])
    stopped = np.isfinite(change) & (change < 0.02)

    # Ego speed policy: the dash-cycle odometer is the only trusted moving-
    # speed source (statutory anchor); a confident standstill pins 0; short
    # gaps are interpolated; everything else is an honest NaN ("no lock").
    # Optical flow gets no say in any speed value: on vibrating or night
    # footage it fabricates near-zero readings at 60+ km/h.
    ego_s = np.full(n, np.nan)
    ego_method = np.array(["none"] * n, dtype=object)
    if args.odometer_points:
        pts = [tuple(int(s) for s in p.split(",")) for p in args.odometer_points.split(";") if p.strip()]
        sig = extract_odometer_signals(frames, pts)
        # Dual-window agreement gate: octave errors and acceleration smear are
        # window-length sensitive while true locks are not, so demand two
        # window sizes to agree within 12% before trusting a value.
        odo_kw = {"octave_threshold": args.octave_threshold,
                  "join_octaves": args.join_octaves,
                  "max_rel_change_per_s": args.max_rel_change_per_s}
        v1, c1, p1 = dash_cycle_speeds(frames, pts, args.dash_cycle_m, args.fps, args.odometer_window_s,
                                       sig=sig, **odo_kw)
        v2, c2, _ = dash_cycle_speeds(frames, pts, args.dash_cycle_m, args.fps, args.odometer_window_s * 1.7,
                                      sig=sig, **odo_kw)
        agree = np.isfinite(v1) & np.isfinite(v2) & (np.abs(v1 - v2) <= 0.12 * np.maximum(v1, v2))
        # A STRONG short-window lock (sharp, prominent peak) stands on its
        # own: on short decelerating clips the long window's average drifts
        # away and the agreement gate would wrongly discard a clean lock.
        strong = np.isfinite(v1) & (c1 >= 0.5) & (p1 >= 0.5)
        v_odo = np.where(agree, 0.5 * (v1 + v2), np.where(strong, v1, np.nan))
        # A prominence-gated lock outranks the standstill vote (paint cannot
        # stream past the band while parked), and streaming paint (high band
        # signal variance) vetoes the standstill vote in turn.
        use = np.isfinite(v_odo)
        stopped &= ~use
        act_win = max(5, int(round(args.fps * 0.5)))
        arr = np.array([sig[pt][:, 0] for pt in pts], dtype=np.float64)
        activity = np.array([float(arr[:, max(0, i - act_win): i + act_win + 1].std(axis=1).max())
                             for i in range(n)])
        stopped &= activity < 3.0
        ego_s[use] = v_odo[use]
        ego_method[use] = "dash_odometer"
        print(f"dash odometer: coverage {use.mean()*100:.0f}%  "
              f"median {np.nanmedian(v_odo[use])*3.6 if use.any() else float('nan'):.1f} km/h  "
              f"median conf {np.median(np.minimum(c1, c2)[use]) if use.any() else 0:.2f}")
    ego_s[stopped] = 0.0
    ego_method[stopped] = "stopped"
    good = np.isfinite(ego_s)
    if good.any() and (~good).any():
        idx = np.arange(n)
        filled = np.interp(idx, idx[good], ego_s[good])
        max_gap = int(round(2.0 * args.fps))
        for run in np.split(idx[~good], np.where(np.diff(idx[~good]) > 1)[0] + 1):
            if 0 < len(run) <= max_gap and run[0] > 0 and run[-1] < n - 1:
                ego_s[run] = filled[run]
                ego_method[run] = "interpolated"
    print(f"ego readings: stopped {int(stopped.sum())}f  no-reading {int(np.isnan(ego_s).sum())}f")

    # Final 1 s rolling median: isolated bad windows (lane change, worn paint)
    # cannot drag the curve, while genuine acceleration still passes through.
    k2 = max(3, int(round(args.fps)) | 1)
    pad2 = k2 // 2
    with np.errstate(all="ignore"):
        ego_s = np.array([np.nanmedian(ego_s[max(0, i - pad2): i + pad2 + 1])
                          if np.isfinite(ego_s[max(0, i - pad2): i + pad2 + 1]).any() else np.nan
                          for i in range(len(ego_s))])

    # --- pass 2: relative tracking on the plane -----------------------------
    next_id = 1
    active: list[dict] = []
    tracks: dict[int, dict] = {}
    for i, dets in enumerate(per_frame_dets):
        t_now = i * dt
        BIG = 1e6
        cost = np.full((len(active), len(dets)), BIG)
        for ti, tr in enumerate(active):
            step_dt = t_now - tr["last_t"]
            pred = tr["pos"] + tr["vel"] * step_dt
            gate = 2.0 + 8.0 * step_dt  # relative speeds are small at 30fps
            for di, det in enumerate(dets):
                # Group comparison, not raw class: car/truck flicker on the
                # same vehicle must not sever the track (see CLASS_GROUP).
                if CLASS_GROUP.get(det["cls"]) != CLASS_GROUP.get(tr["cls"]):
                    continue
                if det["bh"] / max(1e-6, tr["bh"]) > 1.6 or det["bh"] / max(1e-6, tr["bh"]) < 0.6:
                    continue
                # Image-space consistency. The relative plane fails exactly
                # where it is needed most: ego braking pitches the camera, so
                # fwd_m swings metres while the vehicle has barely moved on
                # screen, and the plane gate then happily hands the track to
                # the car alongside (dc007 7.5-11 s: id152/157 swapped back and
                # forth between the blue and red cars). Image position survives
                # pitch, and a real vehicle cannot jump across the frame: over
                # the demos, consecutive-frame centre motion stays under ~0.18
                # box widths (p99 0.11-0.18), while the swap steps sat at 0.90.
                # The box-width term is what lets NEAR vehicles move fast in
                # pixels (apparent speed scales with apparent size) without
                # loosening the gate for distant ones.
                dc = float(np.hypot((det["box"][0] + det["box"][2]) * 0.5 - tr["cx"],
                                    (det["box"][1] + det["box"][3]) * 0.5 - tr["cy"]))
                bw = max(det["box"][2] - det["box"][0], tr["bw"], 1.0)
                if dc > 0.35 * bw + 250.0 * step_dt:
                    continue
                d = float(np.linalg.norm(det["pos"] - pred))
                if d < gate:
                    cost[ti, di] = d
        used_d = set()
        if len(active) and len(dets):
            from scipy.optimize import linear_sum_assignment

            rr, cc = linear_sum_assignment(cost)
            for ti, di in zip(rr, cc):
                if cost[ti, di] >= BIG:
                    continue
                used_d.add(di)
                tr = active[ti]
                det = dets[di]
                step_dt = t_now - tr["last_t"]
                if step_dt > 1e-6:
                    inst = (det["pos"] - tr["pos"]) / step_dt
                    tr["vel"] = inst if tr["n_obs"] == 1 else 0.7 * tr["vel"] + 0.3 * inst
                tr.update(pos=det["pos"], bh=det["bh"], last_t=t_now,
                          cx=(det["box"][0] + det["box"][2]) * 0.5,
                          cy=(det["box"][1] + det["box"][3]) * 0.5,
                          bw=det["box"][2] - det["box"][0])
                tr["n_obs"] += 1
                tracks[tr["id"]]["obs"].append({"frame": i, "t": t_now, "px": det["px"], "py": det["py"],
                                                "box": det["box"], "lat_m": float(det["pos"][0]),
                                                "fwd_m": float(det["pos"][1]), "sens": det["sens"],
                                                "cls": det["cls"], "bh": det["bh"]})
        for di, det in enumerate(dets):
            if di in used_d:
                continue
            tid = next_id
            next_id += 1
            active.append({"id": tid, "cls": det["cls"], "pos": det["pos"], "vel": np.zeros(2),
                           "bh": det["bh"], "last_t": t_now, "n_obs": 1,
                           "cx": (det["box"][0] + det["box"][2]) * 0.5,
                           "cy": (det["box"][1] + det["box"][3]) * 0.5,
                           "bw": det["box"][2] - det["box"][0]})
            tracks[tid] = {"cls": det["cls"], "obs": [{"frame": i, "t": t_now, "px": det["px"], "py": det["py"],
                                                       "box": det["box"], "lat_m": float(det["pos"][0]),
                                                       "fwd_m": float(det["pos"][1]), "sens": det["sens"],
                                                       "cls": det["cls"], "bh": det["bh"]}]}
        active = [tr for tr in active if t_now - tr["last_t"] <= 0.8]

    stitch_log: list[dict] = []
    merges = stitch_fragments(tracks, max_sens=args.max_sens_m_per_px, stitch_log=stitch_log)
    if os.environ.get("DASHCAM_STITCH_LOG"):
        Path(os.environ["DASHCAM_STITCH_LOG"]).write_text(
            json.dumps({"accepted": [list(m) for m in merges], "candidates": stitch_log},
                       indent=1), encoding="utf-8")
    if merges:
        print("stitched fragments (same vehicle, detection dropout): "
              + ", ".join(f"id{b}->id{a}" for a, b in merges))
    dups = suppress_simultaneous_duplicates(tracks)
    if dups:
        print("suppressed parallel duplicates: "
              + ", ".join(f"id{s} (ghost of id{b})" for s, b in dups))
    # Majority class over the track's observations: the stored class is just
    # the first frame's guess, wrong for a visible share of vehicles.
    for rec in tracks.values():
        votes: dict[str, int] = {}
        for o in rec["obs"]:
            c = o.get("cls", rec["cls"])
            votes[c] = votes.get(c, 0) + 1
        rec["cls"] = max(votes, key=votes.get)

    # --- per-track series: range, relative rate, absolute speed -------------
    win = max(5, int(round(args.fps * 1.0)) | 1)  # 1 s sliding fit window
    for tid, rec in tracks.items():
        obs = rec["obs"]
        for j, o in enumerate(obs):
            j0, j1 = max(0, j - win // 2), min(len(obs), j + win // 2 + 1)
            seg = obs[j0:j1]
            tt = np.array([s["t"] for s in seg])
            ff = np.array([s["fwd_m"] for s in seg])
            if len(seg) >= 5 and tt[-1] - tt[0] > 0.3:
                slope = float(np.polyfit(tt, ff, 1)[0])  # +: pulling away
            else:
                slope = 0.0
            o["rel_ms"] = slope
            ego_here = float(ego_s[min(o["frame"], len(ego_s) - 1)])
            # No trusted ego speed -> no absolute speed claim for the target.
            o["abs_kmh"] = (ego_here + slope) * 3.6 if np.isfinite(ego_here) else None

    # --- outputs -------------------------------------------------------------
    ego_csv = out_dir / "ego_speed.csv"
    with ego_csv.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["frame_idx", "t_s", "ego_visual_kmh", "method"])
        for i in range(len(frames)):
            val = f"{ego_s[i] * 3.6:.1f}" if np.isfinite(ego_s[i]) else ""
            w.writerow([i, f"{i * dt:.3f}", val, ego_method[i] if val else "none"])

    range_csv = out_dir / "ranges.csv"
    with range_csv.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        # far_field marks rows whose per-pixel sensitivity puts them past the
        # threshold the HUD and targets_summary.csv already honour: there the
        # speed is withheld entirely. The distance is still written here (it is
        # the only per-frame record), but it carries a median ~20% and worst
        # ~72% bias out there, measured against a factory radar, so anything
        # reading this file downstream must be able to see the flag.
        w.writerow(["track_id", "class", "frame_idx", "t_s", "range_m", "lat_m", "rel_ms", "abs_kmh",
                    "sens_m_per_px", "far_field"])
        for tid, rec in sorted(tracks.items()):
            if len(rec["obs"]) < int(args.fps) or rec.get("duplicate_of"):  # keep real tracks >= 1 s
                continue
            for o in rec["obs"]:
                abs_s = f"{o['abs_kmh']:.1f}" if o["abs_kmh"] is not None else ""
                far = not np.isfinite(o["sens"]) or o["sens"] > args.max_sens_m_per_px
                w.writerow([tid, rec["cls"], o["frame"], f"{o['t']:.3f}", f"{o['fwd_m']:.2f}",
                            f"{o['lat_m']:.2f}", f"{o['rel_ms']:.2f}", abs_s, f"{o['sens']:.3f}",
                            1 if far else 0])

    # Per-target one-line summaries (report table): when/where each target was
    # measurable and its median absolute speed over trusted (near-range) obs.
    sum_csv = out_dir / "targets_summary.csv"
    with sum_csv.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        # abs_speed_median_kmh uses NEAR-range obs only, matching the video's
        # far-range policy (no printed speed past the sensitivity threshold).
        # The far-range median goes in its own clearly-named column instead of
        # being silently mixed in: those positions carry meters of per-pixel
        # noise, so the number is a rough estimate, not a measurement.
        w.writerow(["track_id", "class", "t_start_s", "t_end_s", "range_min_m", "range_max_m",
                    "abs_speed_median_kmh", "abs_speed_median_far_kmh", "n_obs", "merged_from"])
        for tid, rec in sorted(tracks.items()):
            obs = rec["obs"]
            if len(obs) < int(args.fps) or rec.get("duplicate_of"):
                continue
            fwd = [o["fwd_m"] for o in obs]
            near = [o["abs_kmh"] for o in obs
                    if o["abs_kmh"] is not None and np.isfinite(o["sens"]) and o["sens"] <= args.max_sens_m_per_px]
            far = [o["abs_kmh"] for o in obs
                   if o["abs_kmh"] is not None and not (np.isfinite(o["sens"]) and o["sens"] <= args.max_sens_m_per_px)]
            med_near = f"{np.median(near):.1f}" if near else ""
            med_far = f"{np.median(far):.1f}" if far else ""
            merged = "+".join(str(m) for m in rec.get("merged_from", []))
            w.writerow([tid, rec["cls"], f"{obs[0]['t']:.1f}", f"{obs[-1]['t']:.1f}",
                        f"{min(fwd):.1f}", f"{max(fwd):.1f}", med_near, med_far, len(obs), merged])

    (out_dir / "tracks.json").write_text(json.dumps(
        {"ground_plane": ground, "scale": args.pointcloud_scale,
         "ego_visual_kmh": [round(float(v) * 3.6, 2) if np.isfinite(v) else None for v in ego_s],
         "tracks": {k: v for k, v in tracks.items() if len(v["obs"]) >= int(args.fps)}},
        ensure_ascii=False, default=float), encoding="utf-8")
    print(f"saved: {ego_csv}\nsaved: {range_csv}")
    with np.errstate(all="ignore"):
        print(f"ego speed (visual): med={np.nanmedian(ego_s)*3.6:.1f} km/h  "
              f"p10={np.nanpercentile(ego_s,10)*3.6:.1f}  p90={np.nanpercentile(ego_s,90)*3.6:.1f}")

    if not args.render_video:
        return

    # --- render: 1:1 frames, per-frame truth, no interpolation needed -------
    font = cv2.FONT_HERSHEY_SIMPLEX
    video_path = Path(args.render_video)
    if not video_path.is_absolute():
        video_path = out_dir / video_path
    video_path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(video_path), cv2.VideoWriter_fourcc(*"mp4v"), args.fps, (img_w, img_h))
    # VideoWriter reports failure only through isOpened(); without this check a
    # bad path renders nothing and the run still prints "saved".
    if not writer.isOpened():
        raise RuntimeError(f"Could not open video writer at {video_path}")
    frame_obs: dict[int, list[tuple[int, dict, str]]] = {}
    for tid, rec in tracks.items():
        if len(rec["obs"]) < int(args.fps) or rec.get("duplicate_of"):
            continue
        for o in rec["obs"]:
            frame_obs.setdefault(o["frame"], []).append((tid, o, rec["cls"]))

    def id_color(tid: int) -> tuple[int, int, int]:
        rng = np.random.default_rng(tid * 9973 + 7)
        hsv = np.uint8([[[int(rng.integers(0, 180)), 200, 255]]])
        b, g, r = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)[0, 0]
        return int(b), int(g), int(r)

    for i, f in enumerate(frames):
        img = cv2.imread(str(f))
        placed: list[tuple[int, int, int, int]] = []
        for tid, o, cls in sorted(frame_obs.get(i, []), key=lambda r: -r[1]["py"]):
            far = not np.isfinite(o["sens"]) or o["sens"] > args.max_sens_m_per_px
            color = (150, 150, 150) if far else id_color(tid)
            x1, y1, x2, y2 = (int(v) for v in o["box"])
            cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
            gxy = (int(o["px"]), int(o["py"]))
            cv2.circle(img, gxy, 5, color, -1)
            if far:
                text = f"id{tid} {cls} far-range"
            elif o["abs_kmh"] is None:
                text = f"id{tid} {cls} {o['fwd_m']:.1f}m"
            else:
                text = f"id{tid} {cls} {o['fwd_m']:.1f}m  ~{o['abs_kmh']:.0f}km/h"
            (tw, th), _ = cv2.getTextSize(text, font, 0.7, 2)
            tx = int(min(max(2, x1), img_w - tw - 2))
            ty = int(max(th + 4, y1 - 8))
            # push colliding labels upward so queued/parked rows stay readable
            for _ in range(8):
                box = (tx, ty - th - 3, tx + tw, ty + 3)
                if all(box[2] <= r[0] or box[0] >= r[2] or box[3] <= r[1] or box[1] >= r[3] for r in placed):
                    break
                ty -= th + 10
                if ty < th + 4:
                    ty = th + 4
                    break
            placed.append((tx, ty - th - 3, tx + tw, ty + 3))
            cv2.putText(img, text, (tx, ty), font, 0.7, (0, 0, 0), 4)
            cv2.putText(img, text, (tx, ty), font, 0.7, color, 2)
        ego_txt = f"{ego_s[i]*3.6:5.1f} km/h" if np.isfinite(ego_s[i]) else "no lock"
        hud = (f"{args.camera_label}  ego(visual) {ego_txt}  <-> compare GPS in OSD below  "
               f"scale {args.pointcloud_scale:.3f} (CV {args.scale_cv*100:.0f}%)")
        (tw, th), _ = cv2.getTextSize(hud, font, 0.62, 2)
        y0 = 46
        strip = img[y0 - th - 8: y0 + 8, 8: 24 + tw]
        strip[:] = (strip.astype(np.int32) * 3 // 10).astype(np.uint8)
        cv2.putText(img, hud, (16, y0), font, 0.62, (255, 255, 255), 2)
        writer.write(img)
    writer.release()
    print(f"saved: {video_path}")
    if shutil.which("ffmpeg"):
        h264 = video_path.with_name(video_path.stem + "_h264.mp4")
        proc = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(video_path),
                               "-c:v", "libopenh264", "-b:v", "8M", "-pix_fmt", "yuv420p", str(h264)],
                              capture_output=True, text=True)
        if proc.returncode == 0:
            print(f"saved: {h264}")


if __name__ == "__main__":
    main()
