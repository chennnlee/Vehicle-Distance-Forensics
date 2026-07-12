from __future__ import annotations

import argparse
import csv
import json
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
                        help="Octave-guard ratio: double the picked lag when ac[2*lag] >= this * ac[lag]. "
                        "The default 0.75 catches interleaved neighboring-lane dashes (true period = double). "
                        "But on clean cruising footage the finite-window autocorrelation of the TRUE period "
                        "still decays only to ~(W-2L)/(W-L) (e.g. 0.85 at 87 km/h in a 3 s window), so 0.75 "
                        "halves the speed systematically. When the search band (+-120 px) is geometrically "
                        "too narrow to contain a second lane line, raise this to ~0.95 to disable the guard.")
    parser.add_argument("--max-sens-m-per-px", type=float, default=0.8,
                        help="far-range display threshold. Looser than the CCTV pipeline's 0.30: at 30 fps there "
                        "are ~30x more observations to average, so a given per-pixel sensitivity costs far less "
                        "speed accuracy than at 1-4 fps.")
    return parser.parse_args()


def build_geometry(ply_path: Path, scale: float, image_shape: tuple[int, int], hood_y: int):
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
        """Pixel -> (lat_m, fwd_m) on the road plane, camera-relative, scaled."""
        dx = (px - cx) / fx
        dy = (py - cy) / fy
        denom = dy - a * dx - b
        if abs(denom) < 1e-9:
            return None
        t = c / denom
        if t <= 0:
            return None
        p = np.array([dx * t, dy * t, t], dtype=np.float64) * scale
        return np.array([float(p @ e_lat), float(p @ e_fwd)])

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


def extract_odometer_signals(frames: list[Path], points: list[tuple[int, int]]) -> dict:
    """Per-frame (pulse strength, pulse x-offset) at each odometer point."""
    sig = {pt: [] for pt in points}
    for f in frames:
        g = cv2.cvtColor(cv2.imread(str(f)), cv2.COLOR_BGR2GRAY)
        # Local contrast (brighter than the surrounding road), like the dash
        # detector uses: robust to global illumination shifts.
        diff = cv2.subtract(g, cv2.GaussianBlur(g, (51, 51), 0)).astype(np.float32)
        for (x, y) in points:
            # The car drifts laterally inside (or across) its lane over the
            # clip, so a FIXED pixel slides off the paint. Instead search a
            # +-120 px band on the row: whenever a dash crosses this row, the
            # band's peak lights up no matter where the line has wandered.
            x0 = max(0, x - 120)
            band = diff[max(0, y - 6): y + 7, x0: x + 121]
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


def dash_cycle_speeds(frames: list[Path], points: list[tuple[int, int]], cycle_m: float,
                      fps: float, window_s: float, sig: dict | None = None,
                      octave_threshold: float = 0.75) -> tuple[np.ndarray, np.ndarray]:
    """Ego speed from the legal dash cycle streaming past fixed image spots.

    The lane paint is a legal-length periodic pattern (dash+gap), so the
    local-contrast brightness at a fixed pixel oscillates at exactly
    v / cycle_m Hz. A sliding autocorrelation finds the period; the speed
    needs no scale factor, no ground plane, and no undistortion -- the only
    inputs are the statutory cycle length and the frame rate. Returns
    (speed_ms, confidence=autocorr peak) per frame, NaN where no clear peak.
    """
    if sig is None:
        sig = extract_odometer_signals(frames, points)
    n = len(frames)
    win = int(round(window_s * fps))
    half = win // 2
    lag_min, lag_max = int(0.25 * fps), int(3.0 * fps)  # 3..40 m/s for a 10 m cycle
    v = np.full(n, np.nan)
    conf = np.zeros(n)
    prom = np.zeros(n)
    for i in range(n):
        j0, j1 = max(0, i - half), min(n, i + half)
        if j1 - j0 < lag_max + 10:
            j0, j1 = max(0, min(j0, n - lag_max - 10)), min(n, max(j1, lag_max + 10))
        cand: list[tuple[float, float, int, np.ndarray, float]] = []
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
                if q75 - q25 > 50.0:
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
            # Octave guard: neighboring-lane dashes or sub-structure in the
            # pattern can raise a HARMONIC above the true period, doubling the
            # speed. If the double lag correlates almost as well, it is the
            # fundamental -- take it.
            for _ in range(2):
                dbl = 2 * lag
                if dbl <= hi and ac[dbl] >= octave_threshold * ac[lag]:
                    lag = dbl
                else:
                    break
            # Sub-octave correction: freeway lane dashes carry a retro-
            # reflective road stud on every OTHER dash (20 m spacing), and on
            # the near rows the stud outshines the paint, so the argmax lands
            # on TWICE the statutory cycle (half the true speed). The paint's
            # own peak still shows at half that lag; when it is a genuine
            # local peak of comparable height, it IS the statutory cycle. A
            # clean cruise lock is immune: half its lag falls inside the
            # anticorrelated valley, never on a peak.
            for h in (lag // 2, (lag + 1) // 2):
                if h >= max(lag_min, first_min) and h < len(ac) - 1 \
                        and ac[h] > ac[h - 1] and ac[h] > ac[h + 1] \
                        and ac[h] >= 0.6 * ac[lag]:
                    lag = h
                    break
            # Peak-prominence gate: a genuine dash lock rises from a real
            # valley (measured prominence 0.7-1.1); the broad shoulder of a
            # non-periodic bursty signal barely rises above it (0.00-0.03).
            if float(ac[lag] - ac[first_min]) < 0.3:
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
    pixel_to_plane, ground = build_geometry(ply_path, args.pointcloud_scale, (img_h, img_w), args.hood_y)

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
                dets.append({"cls": VEHICLE_CLASSES[int(cls)], "px": float(gx), "py": float(gy),
                             "box": [float(x1), float(y1), float(x2), float(y2)],
                             "bh": float(y2 - y1), "pos": pos, "sens": sens})
        per_frame_dets.append(dets)
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
        v1, c1, p1 = dash_cycle_speeds(frames, pts, args.dash_cycle_m, args.fps, args.odometer_window_s, sig=sig,
                                       octave_threshold=args.octave_threshold)
        v2, c2, _ = dash_cycle_speeds(frames, pts, args.dash_cycle_m, args.fps, args.odometer_window_s * 1.7, sig=sig,
                                      octave_threshold=args.octave_threshold)
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
                if det["cls"] != tr["cls"]:
                    continue
                if det["bh"] / max(1e-6, tr["bh"]) > 1.6 or det["bh"] / max(1e-6, tr["bh"]) < 0.6:
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
                tr.update(pos=det["pos"], bh=det["bh"], last_t=t_now)
                tr["n_obs"] += 1
                tracks[tr["id"]]["obs"].append({"frame": i, "t": t_now, "px": det["px"], "py": det["py"],
                                                "box": det["box"], "lat_m": float(det["pos"][0]),
                                                "fwd_m": float(det["pos"][1]), "sens": det["sens"]})
        for di, det in enumerate(dets):
            if di in used_d:
                continue
            tid = next_id
            next_id += 1
            active.append({"id": tid, "cls": det["cls"], "pos": det["pos"], "vel": np.zeros(2),
                           "bh": det["bh"], "last_t": t_now, "n_obs": 1})
            tracks[tid] = {"cls": det["cls"], "obs": [{"frame": i, "t": t_now, "px": det["px"], "py": det["py"],
                                                       "box": det["box"], "lat_m": float(det["pos"][0]),
                                                       "fwd_m": float(det["pos"][1]), "sens": det["sens"]}]}
        active = [tr for tr in active if t_now - tr["last_t"] <= 0.8]

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
        w.writerow(["track_id", "class", "frame_idx", "t_s", "range_m", "lat_m", "rel_ms", "abs_kmh", "sens_m_per_px"])
        for tid, rec in sorted(tracks.items()):
            if len(rec["obs"]) < int(args.fps):  # keep tracks >= 1 s
                continue
            for o in rec["obs"]:
                abs_s = f"{o['abs_kmh']:.1f}" if o["abs_kmh"] is not None else ""
                w.writerow([tid, rec["cls"], o["frame"], f"{o['t']:.3f}", f"{o['fwd_m']:.2f}",
                            f"{o['lat_m']:.2f}", f"{o['rel_ms']:.2f}", abs_s, f"{o['sens']:.3f}"])

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
    writer = cv2.VideoWriter(str(video_path), cv2.VideoWriter_fourcc(*"mp4v"), args.fps, (img_w, img_h))
    frame_obs: dict[int, list[tuple[int, dict, str]]] = {}
    for tid, rec in tracks.items():
        if len(rec["obs"]) < int(args.fps):
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
