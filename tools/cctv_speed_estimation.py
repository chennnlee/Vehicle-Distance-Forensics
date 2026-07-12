from __future__ import annotations

import argparse
import csv
import json
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

# YOLO flickers between car/truck/bus on the SAME vehicle (grille/roofline
# ambiguity at CCTV resolution). Association and duplicate suppression must
# therefore compare size groups, not raw classes, or every flicker cuts the
# track and the vehicle is counted twice. Two-wheelers stay a separate group:
# a scooter filtering past a queued car must never inherit its track.
CLASS_GROUP = {"car": "4w", "bus": "4w", "truck": "4w", "motorcycle": "2w"}


def _box_overlap(a: list[float], b: list[float]) -> float:
    """Intersection over the SMALLER box area — catches nested double boxes
    (car box inside a truck box on the same vehicle) that plain IoU misses."""
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    area_a = max(1e-6, (a[2] - a[0]) * (a[3] - a[1]))
    area_b = max(1e-6, (b[2] - b[0]) * (b[3] - b[1]))
    return inter / min(area_a, area_b)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Estimate vehicle speeds from a static-CCTV frame sequence. "
        "Geometry comes from ONE SHARP reference frame (ground plane + anchor-calibrated scale); "
        "every tracked pixel is then ray-cast onto that fixed plane, so SHARP never runs per frame."
    )
    parser.add_argument("--frames-dir", required=True, help="Directory of ordered frames (f001.jpg ...).")
    parser.add_argument("--reference-pointcloud", required=True, help="SHARP PLY of a reference frame from the SAME camera view.")
    parser.add_argument("--pointcloud-scale", type=float, required=True, help="Anchor-derived scale factor (e.g. from lane_dash_calibration).")
    parser.add_argument("--clock-roi", default="0,0,520,40", help="OSD clock region x1,y1,x2,y2 used to detect 1-second ticks for frame timing.")
    parser.add_argument("--fps", type=float, default=0.0, help="Known constant frame rate. When set, timestamps are i/fps and the OSD clock is not used (for re-encoded evidence videos without a reliable ticking clock).")
    parser.add_argument("--yolo-model", default="checkpoints/yolov8m-seg.pt", help="Ultralytics segmentation model.")
    parser.add_argument("--conf", type=float, default=0.3, help="Detection confidence threshold.")
    parser.add_argument("--out-dir", required=True, help="Output directory.")
    parser.add_argument("--min-track-frames", type=int, default=4, help="Minimum observations per track.")
    parser.add_argument("--min-track-seconds", type=float, default=2.0, help="Minimum track duration.")
    parser.add_argument("--min-path-m", type=float, default=5.0, help="Minimum path length in meters for a speed to be reported.")
    parser.add_argument("--min-disp-m", type=float, default=5.0,
                        help="Minimum NET start-to-end displacement in meters. Unlike path length, net displacement "
                        "cannot be accumulated by bbox jitter, so this gate removes stationary vehicles that would "
                        "otherwise 'walk' tens of meters of path while queueing at a red light.")
    parser.add_argument("--max-sens-m-per-px", type=float, default=0.30,
                        help="Far-field rejection: flag a track 'far_field' when the median ground-sensitivity of its "
                        "observations exceeds this many meters per pixel. Near the horizon one pixel of detection "
                        "noise moves the ray-plane intersection by meters, so no speed there can be trusted "
                        "(lesson from case 1110822 where the culprit sat 10-30px below the horizon).")
    parser.add_argument("--scale-cv", type=float, default=0.0,
                        help="Relative uncertainty of the calibration scale (the lane-dash length CV); folded into "
                        "each reported speed's +/- confidence interval.")
    parser.add_argument("--anchors-json", default="",
                        help="lane_dash_calibration.json path; its calibrated dashes are drawn in the rendered video "
                        "(primary chain green, secondary chains cyan) so the scale's origin is visible on screen.")
    parser.add_argument("--camera-label", default="", help="Camera/case name shown in the rendered video HUD.")
    parser.add_argument("--render-video", default="", help="Optional output mp4 path: per-frame boxes, recent trails, live speed labels, real-time playback.")
    parser.add_argument("--playback-fps", type=int, default=12, help="Playback fps of the rendered video; source frames are repeated to match real durations.")
    parser.add_argument("--time-scale", type=float, default=1.0,
                        help="Uniform fast-forward factor for realtime mode: playback = real time / k with constant "
                        "time flow (no rubber-banding), unlike native mode whose speed varies with source burstiness.")
    parser.add_argument("--also-frame-video", default="",
                        help="Optional second mp4: native-mode one-frame-per-source-frame with filename/t/dt burned "
                        "in -- the forensic frame-stepping companion to the realtime video.")
    parser.add_argument("--playback-mode", choices=("realtime", "native"), default="realtime",
                        help="realtime: wall-clock pacing (frames repeat to fill their true duration; forensically faithful). "
                        "native: one output frame per source frame like the original stream player -- smooth but time-compressed.")
    return parser.parse_args()


def frame_times_from_clock(frames: list[Path], clock_roi: tuple[int, int, int, int]) -> np.ndarray:
    """Assign a timestamp (seconds) to every frame using the burned-in OSD clock.

    NVR streams lie about fps in the container header (nominal 25, actual ~2),
    so wall time must come from the image itself. The clock region's pixel
    hash changes exactly when the displayed second increments; frames between
    two ticks are spread uniformly inside that second.
    """
    x1, y1, x2, y2 = clock_roi
    bins = []
    for f in frames:
        img = cv2.imread(str(f), cv2.IMREAD_GRAYSCALE)
        crop = img[y1:y2, x1:x2]
        bins.append((crop > 160).astype(np.uint8))

    # A digit rollover flips tens of pixels at once; JPEG noise flips a few
    # scattered ones. Requiring a minimum changed-pixel count keeps the
    # detector from firing on every frame of a high-fps, noisy encode.
    area = max(1, (y2 - y1) * (x2 - x1))
    min_changed = max(25, int(area * 0.004))
    tick_idx = [
        i
        for i in range(1, len(bins))
        if int(np.count_nonzero(bins[i] != bins[i - 1])) >= min_changed
    ]
    if len(tick_idx) < 2:
        raise RuntimeError("OSD clock ticks not detected; check --clock-roi.")

    times = np.full(len(frames), np.nan)
    for second, idx in enumerate(tick_idx):
        times[idx] = float(second)
    # Interpolate uniformly between ticks
    for a, b in zip(tick_idx[:-1], tick_idx[1:]):
        n = b - a
        for k in range(1, n):
            times[a + k] = times[a] + k / n
    # Extrapolate head/tail with the median inter-frame interval
    valid = ~np.isnan(times)
    med_dt = float(np.median(np.diff(times[valid]))) if valid.sum() > 2 else 0.5
    first = int(np.argmax(valid))
    for i in range(first - 1, -1, -1):
        times[i] = times[i + 1] - med_dt
    last = len(times) - 1 - int(np.argmax(valid[::-1]))
    for i in range(last + 1, len(times)):
        times[i] = times[i - 1] + med_dt
    return times


def build_ray_caster(ply_path: Path, scale: float, image_shape: tuple[int, int]):
    points_xyz, _, metadata = load_point_cloud_points(ply_path)
    intr = metadata.get("intrinsics") or {}
    fx = float(intr["fx"])
    fy = float(intr.get("fy") or fx)
    cx = float(intr.get("cx", (image_shape[1] - 1) * 0.5))
    cy = float(intr.get("cy", (image_shape[0] - 1) * 0.5))

    z = points_xyz[:, 2]
    valid = np.isfinite(points_xyz).all(axis=1) & (z > 1e-6)
    u = np.where(valid, fx * (points_xyz[:, 0] / z) + cx, np.nan)
    v = np.where(valid, fy * (points_xyz[:, 1] / z) + cy, np.nan)
    h, w = image_shape
    ground = fit_ground_plane_raw(points_xyz, u, v, (0, int(h * 0.35), w, h))
    if ground is None:
        raise RuntimeError("Ground plane fit failed on the reference point cloud.")

    a, b, c = ground["a"], ground["b"], ground["c"]

    def pixel_to_ground_m(px: float, py: float) -> np.ndarray | None:
        # Ray through pixel: d = ((px-cx)/fx, (py-cy)/fy, 1); intersect y = a x + b z + c
        dx = (px - cx) / fx
        dy = (py - cy) / fy
        denom = dy - a * dx - b
        if abs(denom) < 1e-9:
            return None
        t = c / denom
        if t <= 0:  # intersection behind the camera -> pixel above the horizon
            return None
        p_raw = np.array([dx * t, dy * t, t], dtype=np.float64)
        return p_raw * scale

    return pixel_to_ground_m, ground


SPEC_NOTE_EN = {"lane_line_4m": "4m lane dash", "lane_line_4m_freeway": "4m freeway dash", "guide_line_50cm": "0.5m guide line"}


def load_calibration_anchors(path: Path) -> tuple[list[dict], str]:
    """Turn a lane_dash_calibration.json into drawable video anchors.

    Primary-chain dashes come out green with 'ref X.XXm (legal Ym)' labels;
    secondary chains (independent lane lines that passed the CV gate) come out
    cyan. Burning them into every frame makes the video self-documenting: the
    viewer sees exactly which painted marks the metric scale came from.
    """
    d = json.loads(Path(path).read_text())
    scale = d.get("scale_factor")
    spec = d.get("identified_spec")
    legal = None
    if spec:
        from lane_dash_calibration import MARKING_SPECS

        legal = MARKING_SPECS[spec]["dash_m"]
    anchors: list[dict] = []
    for row in d.get("dashes", []):
        length = row.get("length_3d_raw_m")
        if length is None or scale is None:
            continue
        label = f"ref {length * scale:.2f}m (legal {legal:g}m)" if legal else f"ref {length * scale:.2f}m"
        anchors.append({"p1": row["tip_near_px"], "p2": row["tip_far_px"], "label": label, "color": (0, 255, 0)})
    for chain in d.get("secondary_chains", []):
        # Junk chains (solid-line fragments, worn paint) show CV > 0.5;
        # only stable chains are presented as on-screen evidence.
        if chain.get("length_cv", 1.0) > 0.15 or scale is None:
            continue
        for tip_near, tip_far, length in chain.get("tips", []):
            anchors.append({"p1": tip_near, "p2": tip_far, "label": f"{length * scale:.2f}m", "color": (255, 255, 0)})
    return anchors, SPEC_NOTE_EN.get(spec, spec or "anchor")


def _id_color(tid: int) -> tuple[int, int, int]:
    rng = np.random.default_rng(tid * 9973 + 7)
    h = int(rng.integers(0, 180))
    hsv = np.uint8([[[h, 200, 255]]])
    b, g, r = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)[0, 0]
    return int(b), int(g), int(r)


def render_video(
    frames: list[Path],
    times: np.ndarray,
    tracks: dict[int, dict],
    reported: dict[int, dict],
    video_path: Path,
    playback_fps: int,
    trail_seconds: float = 6.0,
    mode: str = "realtime",
    anchors: list | None = None,
    time_scale: float = 1.0,
    frame_info: bool = False,
    hud: str = "",
) -> None:
    """Real-time annotated playback: each source frame is repeated to match its
    true duration (from OSD-clock timestamps), so vehicle motion in the output
    plays at wall-clock speed even though the NVR stream is ~1-2 fps."""
    sample = cv2.imread(str(frames[0]))
    h, w = sample.shape[:2]
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(video_path), fourcc, playback_fps, (w, h))
    font = cv2.FONT_HERSHEY_SIMPLEX

    def smooth_display(obs: list[dict]) -> list[dict]:
        # Display-only smoothing: raw YOLO boxes wobble with shadows/mirrors/
        # mask splits, which reads as box jitter in the report video. A
        # centered (1/4, 1/2, 1/4) average over neighboring observations
        # cancels that noise WITHOUT lagging constant-velocity motion (a
        # centered average preserves linear trends). Measured positions in
        # tracks.json stay raw. Skipped across uneven time gaps (stitch seams,
        # dropouts), where asymmetric spacing would shift the box sideways.
        if len(obs) < 3:
            return obs
        med_dt = float(np.median(np.diff([o["t"] for o in obs])))
        sm = [dict(o) for o in obs]
        for j in range(1, len(obs) - 1):
            a, b, c = obs[j - 1], obs[j], obs[j + 1]
            if (b["t"] - a["t"]) > 2.0 * med_dt or (c["t"] - b["t"]) > 2.0 * med_dt:
                continue
            if a.get("box") and b.get("box") and c.get("box"):
                sm[j]["box"] = [0.25 * a["box"][k] + 0.5 * b["box"][k] + 0.25 * c["box"][k] for k in range(4)]
            sm[j]["px"] = 0.25 * a["px"] + 0.5 * b["px"] + 0.25 * c["px"]
            sm[j]["py"] = 0.25 * a["py"] + 0.5 * b["py"] + 0.25 * c["py"]
        return sm

    # Sorted per-track observation arrays for time interpolation
    track_obs: dict[int, list[dict]] = {}
    for tid, rec in tracks.items():
        if tid in reported and rec["obs"]:
            track_obs[tid] = smooth_display(sorted(rec["obs"], key=lambda o: o["t"]))

    def lerp(a: float, b: float, w: float) -> float:
        return a + (b - a) * w

    def put_label(img: np.ndarray, text: str, x: float, y: float, color: tuple, fs: float = 0.6,
                  placed: list | None = None) -> None:
        # Labels must stay readable in a report video: clamp them inside the
        # frame (edge anchors used to run off screen) and, when a placed-rect
        # list is given, push colliding labels upward so queued vehicles do
        # not print on top of each other.
        (tw, th), _ = cv2.getTextSize(text, font, fs, 2)
        x = int(min(max(2, x), img.shape[1] - tw - 2))
        y = int(min(max(th + 4, y), img.shape[0] - 6))
        if placed is not None:
            for _ in range(8):
                box = (x, y - th - 3, x + tw, y + 3)
                if all(box[2] <= r[0] or box[0] >= r[2] or box[3] <= r[1] or box[1] >= r[3] for r in placed):
                    break
                y -= th + 10
                if y < th + 4:
                    y = th + 4
                    break
            placed.append((x, y - th - 3, x + tw, y + 3))
        cv2.putText(img, text, (x, y), font, fs, (0, 0, 0), 4)
        cv2.putText(img, text, (x, y), font, fs, color, 2)

    def draw_anchors(img: np.ndarray, placed: list) -> None:
        # The calibration dashes ARE the measurement's ruler; showing them in
        # every frame lets a report viewer see where the scale comes from.
        if not anchors:
            return
        for an in anchors:
            p1 = tuple(int(v) for v in an["p1"])
            p2 = tuple(int(v) for v in an["p2"])
            color = an.get("color", (0, 255, 0))
            cv2.line(img, p1, p2, color, 3)
            if an.get("label"):
                put_label(img, an["label"], (p1[0] + p2[0]) // 2 + 8, (p1[1] + p2[1]) // 2,
                          color, fs=0.5, placed=placed)

    def draw_hud(img: np.ndarray, t_render: float, extra: str = "") -> None:
        if not hud and not extra:
            return
        text = "  ".join(s for s in (hud, f"t=+{t_render:.1f}s", extra) if s)
        (tw, th), _ = cv2.getTextSize(text, font, 0.55, 2)
        y0 = img.shape[0] - 14
        overlay = img[y0 - th - 8: y0 + 8, 8: 24 + tw]
        overlay[:] = (overlay.astype(np.int32) * 3 // 10).astype(np.uint8)  # darken strip for contrast
        cv2.putText(img, text, (16, y0), font, 0.55, (255, 255, 255), 2)

    def draw_at(img: np.ndarray, t_render: float, placed: list) -> None:
        # Source frames arrive at ~1-4fps, but we know each track's positions
        # at consecutive observations, so annotations are interpolated to the
        # playback timestamp: boxes glide between detections instead of
        # jumping once per source frame, and a track disappears right after
        # its last observation instead of freezing in place for seconds.
        for tid, obs in track_obs.items():
            if t_render < obs[0]["t"] or t_render > obs[-1]["t"] + 0.3:
                continue
            hi = 0
            while hi < len(obs) and obs[hi]["t"] < t_render:
                hi += 1
            if hi == 0:
                a = b = obs[0]
                w = 0.0
            elif hi >= len(obs):
                a = b = obs[-1]
                w = 0.0
            else:
                a, b = obs[hi - 1], obs[hi]
                span = b["t"] - a["t"]
                w = 0.0 if span <= 1e-9 else (t_render - a["t"]) / span

            rec = tracks[tid]
            row = reported.get(tid, {})
            quality = row.get("quality", "ok")
            # A far-field track's positions are geometric noise (meters per
            # pixel); printing a km/h number there would be fabrication, so it
            # is drawn gray and explicitly labeled unreliable instead.
            far_field = quality == "far_field"
            # Same treatment when the fit CI exceeds half the speed itself:
            # that is the statistical signature of a mis-associated track
            # (e.g. two vehicles stitched across carriageways) or of motion
            # too erratic for any single number to represent.
            fit_speed = float(row.get("speed_kmh", 0.0))
            fit_ci = float(row.get("speed_ci_kmh", 0.0))
            uncertain = fit_speed > 0 and fit_ci > 0.5 * fit_speed
            color = (150, 150, 150) if (far_field or uncertain) else _id_color(tid)
            trail = [(int(p["px"]), int(p["py"])) for p in obs if t_render - trail_seconds <= p["t"] <= t_render]
            px = lerp(a["px"], b["px"], w)
            py = lerp(a["py"], b["py"], w)
            trail.append((int(px), int(py)))
            for p, q in zip(trail[:-1], trail[1:]):
                cv2.line(img, p, q, color, 2)
            box_a, box_b = a.get("box"), b.get("box")
            if box_a is not None and box_b is not None:
                bx1, by1, bx2, by2 = (int(lerp(box_a[k], box_b[k], w)) for k in range(4))
                cv2.rectangle(img, (bx1, by1), (bx2, by2), color, 2)
                label_anchor = (bx1, by1 - 8)
            else:
                label_anchor = (int(px) + 8, int(py) - 8)
            cv2.circle(img, (int(px), int(py)), 6, color, -1)
            cv2.circle(img, (int(px), int(py)), 6, (255, 255, 255), 1)
            if far_field:
                label = f"id{tid} {rec['cls']} far-range: no speed"
            elif uncertain:
                # Show the fitted speed WITH its interval instead of the live
                # windowed speed: a number this uncertain must not look alive.
                label = f"id{tid} {rec['cls']} {fit_speed:.0f}+-{fit_ci:.0f}km/h?"
            else:
                speed = lerp(float(a.get("speed_kmh", 0)), float(b.get("speed_kmh", 0)), w)
                # "~" marks tracks whose overall motion was not uniform
                # (fit rmse > 1.5 m): the number is a rougher average.
                label = f"id{tid} {rec['cls']} {speed:.0f}km/h" + ("~" if quality == "nonuniform_motion" else "")
            put_label(img, label, label_anchor[0], label_anchor[1], color, fs=0.6, placed=placed)

    med_dt = float(np.median(np.diff(times)))
    if mode == "native":
        # One output frame per source frame, like the original stream player:
        # smooth motion, but the timeline is compressed wherever the source
        # skipped time. Speed labels stay correct (computed from real
        # timestamps); a watermark declares the compression for honesty.
        span = float(times[-1] - times[0])
        speedup = span / max(1e-9, len(frames) / playback_fps)
        for i, f in enumerate(frames):
            img = cv2.imread(str(f))
            placed: list = []
            draw_anchors(img, placed)
            draw_at(img, float(times[i]), placed)
            if frame_info:
                dt_i = float(times[i] - times[i - 1]) if i > 0 else 0.0
                info = f"{f.name}  frame#{i:04d}  t={float(times[i]-times[0]):+8.3f}s  dt={dt_i:.3f}s"
                cv2.putText(img, info, (16, 72), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 0), 5)
                cv2.putText(img, info, (16, 72), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 255), 2)
            draw_hud(img, float(times[i] - times[0]), extra=f"native playback (~x{speedup:.1f} time-compressed)")
            writer.write(img)
        writer.release()
        return
    t_start = float(times[0])
    for i, f in enumerate(frames):
        base = cv2.imread(str(f))
        t0 = float(times[i])
        dt = float(times[i + 1] - times[i]) if i + 1 < len(times) else med_dt
        repeats = max(1, int(round(dt * playback_fps / max(1e-6, time_scale))))
        for k in range(repeats):
            img = base.copy()
            t_render = t0 + dt * (k / repeats)
            placed = []
            draw_anchors(img, placed)
            draw_at(img, t_render, placed)
            extra = f"x{time_scale:g} fast-forward (uniform time)" if time_scale != 1.0 else ""
            draw_hud(img, t_render - t_start, extra=extra)
            writer.write(img)
    writer.release()


def _endpoint_velocity(obs: list[dict], tail: bool, window_s: float = 2.0) -> np.ndarray:
    """Constant-velocity fit over a fragment's first/last `window_s` seconds."""
    t = np.array([o["t"] for o in obs])
    P = np.array([o["pos_m"] for o in obs])
    m = (t >= t[-1] - window_s) if tail else (t <= t[0] + window_s)
    if m.sum() < 2 or float(t[m][-1] - t[m][0]) < 0.2:
        return np.zeros(3)
    A = np.column_stack([t[m] - t[m][0], np.ones(int(m.sum()))])
    return np.array([np.linalg.lstsq(A, P[m][:, ax], rcond=None)[0][0] for ax in range(3)])


def _recompute_display_speeds(obs: list[dict]) -> None:
    """Re-derive the per-observation display speed over the merged history so
    the seam of a stitched track does not show bootstrap zeros mid-video."""
    for j, o in enumerate(obs):
        for k in range(j - 1, -1, -1):
            if o["t"] - obs[k]["t"] >= 0.6:
                d = float(np.linalg.norm(np.array(o["pos_m"]) - np.array(obs[k]["pos_m"])))
                dt_w = o["t"] - obs[k]["t"]
                o["speed_kmh"] = 0.0 if d < 0.35 else (d / dt_w) * 3.6
                break


def stitch_fragments(tracks: dict[int, dict], max_gap_s: float = 4.0,
                     max_sens: float = 0.30) -> list[tuple[int, int]]:
    """Rejoin track fragments that are the same physical vehicle.

    A detection dropout longer than the tracker's 3 s active window kills the
    track; the vehicle then re-enters as a fresh id and its speed is reported
    twice. Post-hoc, fragment B continues fragment A when A's constant-velocity
    prediction lands on B's first observation under the same physical gates the
    online tracker uses (size group, bbox-height ratio, forward direction).
    Pairs are accepted greedily by prediction error; each surviving track
    records the absorbed ids in `merged_from` so a report reader can audit
    every join. Returns the accepted (survivor, absorbed) pairs.
    """
    info: dict[int, dict] = {}
    for tid, rec in tracks.items():
        obs = sorted(rec["obs"], key=lambda o: o["t"])
        rec["obs"] = obs
        info[tid] = {
            "grp": CLASS_GROUP.get(rec["cls"]),
            "t0": obs[0]["t"], "t1": obs[-1]["t"],
            "p0": np.array(obs[0]["pos_m"]), "p1": np.array(obs[-1]["pos_m"]),
            "bh0": obs[0]["box"][3] - obs[0]["box"][1],
            "bh1": obs[-1]["box"][3] - obs[-1]["box"][1],
            "sens0": obs[0].get("sens", 0.0), "sens1": obs[-1].get("sens", 0.0),
            "v0": _endpoint_velocity(obs, tail=False),
            "v1": _endpoint_velocity(obs, tail=True),
        }

    candidates = []
    for a, ia in info.items():
        for b, ib in info.items():
            if a == b or ia["grp"] != ib["grp"] or ia["grp"] is None:
                continue
            # Never stitch across a far-field seam: near the horizon one pixel
            # of noise is meters of position, so a "landed on the prediction"
            # match there routinely welds two different vehicles together.
            if ia["sens1"] > max_sens or ib["sens0"] > max_sens or not (np.isfinite(ia["sens1"]) and np.isfinite(ib["sens0"])):
                continue
            gap = ib["t0"] - ia["t1"]
            if not (0.0 < gap <= max_gap_s):
                continue
            ratio = ib["bh0"] / max(1e-6, ia["bh1"])
            if not (0.4 <= ratio <= 2.5):
                continue
            va = ia["v1"]
            sa = float(np.linalg.norm(va))
            pred = ia["p1"] + va * gap
            err = float(np.linalg.norm(pred - ib["p0"]))
            # Gate grows with speed and gap but is capped: a 4 s gap on a fast
            # track must not open a gate wide enough to swallow the next car.
            gate = min(10.0, max(3.0, 0.6 * sa * gap + 2.5))
            if err > gate:
                continue
            disp = ib["p0"] - ia["p1"]
            disp_n = float(np.linalg.norm(disp))
            if sa > 3.0 and disp_n > 2.0:
                if float(np.dot(va, disp)) / max(1e-9, sa * disp_n) < 0.2:
                    continue
            sb = float(np.linalg.norm(ib["v0"]))
            if sa > 3.0 and sb > 3.0:
                if float(np.dot(va, ib["v0"])) / max(1e-9, sa * sb) < 0.3:
                    continue
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

    # Resolve chains (A->B->C) by walking each chain head forward and folding
    # every continuation into the earliest fragment's id.
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
        _recompute_display_speeds(tracks[a]["obs"])
    return merges


def suppress_simultaneous_duplicates(tracks: dict[int, dict]) -> list[tuple[int, int]]:
    """Drop parallel ghost tracks riding on the same vehicle.

    Per-frame overlap dedup catches most double boxes, but an offset ghost box
    (mask split, reflection) can still run alongside the real track. Two real
    four-wheelers physically cannot hold < 1.2 m center distance for seconds,
    so a 4w track whose positions sit that close to a longer concurrent 4w
    track for >= 70% of its observations is marked `duplicate_of` and excluded
    from reporting. Two-wheelers are exempt: scooters do ride that close.
    """
    tids = sorted(tracks, key=lambda t: len(tracks[t]["obs"]), reverse=True)
    dropped: list[tuple[int, int]] = []
    for i, big in enumerate(tids):
        rb = tracks[big]
        if rb.get("duplicate_of") or CLASS_GROUP.get(rb["cls"]) != "4w":
            continue
        tb = np.array([o["t"] for o in rb["obs"]])
        Pb = np.array([o["pos_m"] for o in rb["obs"]])
        for small in tids[i + 1:]:
            rs = tracks[small]
            if rs.get("duplicate_of") or CLASS_GROUP.get(rs["cls"]) != "4w":
                continue
            ts = np.array([o["t"] for o in rs["obs"]])
            m = (ts >= tb[0]) & (ts <= tb[-1])
            if m.sum() < 4 or float(ts[m][-1] - ts[m][0]) < 2.0:
                continue
            Ps = np.array([o["pos_m"] for o in rs["obs"]])[m]
            interp = np.column_stack([np.interp(ts[m], tb, Pb[:, ax]) for ax in range(3)])
            close = np.linalg.norm(Ps - interp, axis=1) < 1.2
            if close.mean() >= 0.7 and m.sum() >= 0.7 * len(ts):
                rs["duplicate_of"] = big
                dropped.append((small, big))
    return dropped


def main() -> None:
    args = parse_args()
    frames_dir = Path(args.frames_dir)
    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = PROJECT_ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    frames = sorted(frames_dir.glob("*.jpg")) + sorted(frames_dir.glob("*.png"))
    if len(frames) < 4:
        raise RuntimeError(f"Too few frames in {frames_dir}")
    sample = cv2.imread(str(frames[0]))
    img_h, img_w = sample.shape[:2]

    if args.fps > 0:
        times = np.arange(len(frames), dtype=np.float64) / args.fps
    else:
        clock_roi = tuple(int(v) for v in args.clock_roi.split(","))
        times = frame_times_from_clock(frames, clock_roi)
    print(f"frames={len(frames)} span={times[-1]-times[0]:.1f}s median_dt={np.median(np.diff(times)):.3f}s")

    ply_path = Path(args.reference_pointcloud)
    if not ply_path.is_absolute():
        ply_path = PROJECT_ROOT / ply_path
    pixel_to_ground_m, ground = build_ray_caster(ply_path, args.pointcloud_scale, (img_h, img_w))

    from ultralytics import YOLO

    model = YOLO(args.yolo_model)

    # Ground-space tracker. IoU-based trackers (ByteTrack/BoT-SORT) cannot
    # associate across ~2fps NVR frames: a 50 km/h vehicle moves ~7 m between
    # frames, so consecutive boxes never overlap. But we already know every
    # detection's METRIC ground position, so constant-velocity prediction in
    # meters makes the association trivial at any frame rate.
    next_id = 1
    active: list[dict] = []
    tracks: dict[int, dict] = {}

    for i, f in enumerate(frames):
        result = model.predict(source=str(f), conf=args.conf, verbose=False)[0]
        t_now = float(times[i])
        dets = []
        if result.boxes is not None:
            boxes = result.boxes.xyxy.cpu().numpy()
            clss = result.boxes.cls.cpu().numpy().astype(int)
            confs = result.boxes.conf.cpu().numpy()
            mask_polys = result.masks.xy if getattr(result, "masks", None) is not None else None
            for di_raw, (box, cls) in enumerate(zip(boxes, clss)):
                if int(cls) not in VEHICLE_CLASSES:
                    continue
                x1, y1, x2, y2 = box
                # Ground-contact estimate: median x over the lowest 12% of the
                # segmentation silhouette (where tires meet road). The bbox
                # bottom-center is only a fallback -- boxes wobble with
                # mirrors/shadows while the mask bottom tracks the wheels.
                gx, gy = (x1 + x2) / 2.0, y2
                if mask_polys is not None and di_raw < len(mask_polys):
                    poly = mask_polys[di_raw]
                    if poly is not None and len(poly) >= 3:
                        ys = poly[:, 1]
                        band = ys >= ys.max() - max(3.0, 0.12 * (y2 - y1))
                        if band.sum() >= 2:
                            gx = float(np.median(poly[band, 0]))
                            gy = float(ys.max())
                gp = pixel_to_ground_m(gx, gy)
                if gp is None:
                    continue
                # Geometric sensitivity: how far the ground point moves per
                # pixel of vertical detection noise. Near the horizon this
                # explodes (meters per pixel) and any speed becomes fiction;
                # the per-track median is reported and gates the far_field flag.
                gp_up = pixel_to_ground_m(gx, gy - 1.0)
                sens = float(np.linalg.norm(gp_up - gp)) if gp_up is not None else float("inf")
                dets.append({"cls": VEHICLE_CLASSES[int(cls)], "conf": float(confs[di_raw]),
                             "px": float(gx), "py": float(gy),
                             "box": [float(x1), float(y1), float(x2), float(y2)],
                             "bh": float(y2 - y1), "sens": sens, "pos": gp})

        # One vehicle, one detection: YOLO regularly fires a car box AND a
        # truck box on the same pixels; each spawned its own track and the
        # vehicle was counted (and speed-reported) twice. Keep only the
        # highest-confidence box among same-group detections that overlap
        # heavily. Overlap is intersection-over-smaller-box, so a nested
        # double box is caught even when plain IoU is modest.
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
        dets = deduped

        # Predict each active track forward and build a gated cost matrix,
        # then solve globally with Hungarian assignment. Greedy NN caused ID
        # jumps in dense queues: a closer *wrong* detection could steal a
        # track before the right pairing was considered.
        BIG = 1e6
        cost = np.full((len(active), len(dets)), BIG)
        for ti, tr in enumerate(active):
            dt = t_now - tr["last_t"]
            pred = tr["pos"] + tr["vel"] * dt
            speed = float(np.linalg.norm(tr["vel"]))
            if tr["n_obs"] == 1:
                # Bootstrap: velocity is still unknown, so the gate must cover
                # the fastest plausible urban vehicle (~90 km/h = 25 m/s), or a
                # fast mover can never be matched to its own second detection.
                gate = max(6.0, 26.0 * dt)
            else:
                # The prediction already contains the velocity, so the gate
                # only needs to cover velocity-estimate error (~25% of speed
                # per second) plus physically possible acceleration (~4 m/s^2
                # -> 2*dt^2 meters). The old speed*dt*1.6 gate ballooned to
                # tens of meters across a multi-second dropout and stitched a
                # fast track onto a DIFFERENT vehicle near the horizon,
                # fabricating ~100 km/h fits.
                gate = max(4.0, 0.25 * speed * dt + 2.0 * dt * dt + 2.0)
            # Horizon-walk guard: once the track's last observation is
            # far-field (meters per pixel of noise), its metric position is
            # fiction, and the acceleration allowance above lets the track
            # "walk" from a receding car onto an oncoming one in a few steps.
            # Freeze the gate so a far-field track can only coast to its
            # natural end instead of hopping vehicles near the horizon.
            if tr.get("last_sens", 0.0) > args.max_sens_m_per_px:
                gate = min(gate, 4.0)
            for di, det in enumerate(dets):
                # Compare size groups, not raw classes: a car/truck flicker on
                # the same vehicle must not sever the track (see CLASS_GROUP).
                if CLASS_GROUP.get(det["cls"]) != CLASS_GROUP.get(tr["cls"]):
                    continue
                # Apparent-size consistency: a vehicle cannot halve or double
                # its bbox height between consecutive frames. This blocks the
                # cross-carriageway stitches (near car matched to a far car)
                # that the wide 26 m bootstrap gate otherwise allows.
                if det["bh"] / max(1e-6, tr["bh"]) > 2.2 or det["bh"] / max(1e-6, tr["bh"]) < 0.45:
                    continue
                disp = det["pos"] - tr["pos"]
                disp_n = float(np.linalg.norm(disp))
                # Physical sanity: no urban vehicle does >135 km/h between frames
                if dt > 1e-6 and disp_n / dt > 38.0:
                    continue
                # Direction consistency: an established moving track must not
                # match a detection behind it -- that is what stitched
                # opposite-carriageway vehicles together in v1.
                if tr["n_obs"] >= 3 and speed > 3.0 and disp_n > 3.0:
                    cos_a = float(np.dot(tr["vel"], disp)) / max(1e-9, speed * disp_n)
                    if cos_a < 0.0:
                        continue
                dist = float(np.linalg.norm(det["pos"] - pred))
                if dist < gate:
                    cost[ti, di] = dist

        used_t, used_d = set(), set()
        if len(active) and len(dets):
            from scipy.optimize import linear_sum_assignment

            rr, cc = linear_sum_assignment(cost)
            matched = [(ti, di) for ti, di in zip(rr, cc) if cost[ti, di] < BIG]
        else:
            matched = []
        for ti, di in matched:
            used_t.add(ti)
            used_d.add(di)
            tr = active[ti]
            det = dets[di]
            dt = t_now - tr["last_t"]
            if dt > 1e-6:
                inst_vel = (det["pos"] - tr["pos"]) / dt
                if tr["n_obs"] == 1:
                    # First velocity estimate: adopt directly; halving it via
                    # EMA would shrink the next gate below the true motion.
                    tr["vel"] = inst_vel
                else:
                    # EMA keeps velocity stable against bottom-pixel jitter
                    tr["vel"] = 0.5 * tr["vel"] + 0.5 * inst_vel
            tr["pos"] = det["pos"]
            tr["bh"] = det["bh"]
            tr["last_t"] = t_now
            tr["last_sens"] = det["sens"]
            tr["n_obs"] += 1
            # Display speed over a >=0.6s baseline, not adjacent frames: at
            # 20fps the inter-frame dt is 0.05s, so a few-dozen-cm bbox jitter
            # divided by 0.05s fabricates tens of km/h on stationary vehicles.
            hist = tracks[tr["id"]]["obs"]
            disp_speed = 0.0
            for old in reversed(hist):
                if t_now - old["t"] >= 0.6:
                    d = float(np.linalg.norm(det["pos"] - np.array(old["pos_m"])))
                    dt_w = t_now - old["t"]
                    disp_speed = 0.0 if d < 0.35 else (d / dt_w) * 3.6
                    break
            else:
                disp_speed = float(np.linalg.norm(tr["vel"])) * 3.6 if tr["n_obs"] > 3 else 0.0
            hist.append(
                {"frame": i, "t": t_now, "px": det["px"], "py": det["py"], "box": det["box"],
                 "pos_m": det["pos"].tolist(), "speed_kmh": disp_speed, "sens": det["sens"],
                 "cls": det["cls"], "conf": det["conf"]}
            )

        for di, det in enumerate(dets):
            if di in used_d:
                continue
            tid = next_id
            next_id += 1
            active.append({"id": tid, "cls": det["cls"], "pos": det["pos"], "vel": np.zeros(3),
                           "bh": det["bh"], "last_t": t_now, "last_sens": det["sens"], "n_obs": 1})
            tracks[tid] = {"cls": det["cls"], "obs": [
                {"frame": i, "t": t_now, "px": det["px"], "py": det["py"], "box": det["box"],
                 "pos_m": det["pos"].tolist(), "speed_kmh": 0.0, "sens": det["sens"],
                 "cls": det["cls"], "conf": det["conf"]}
            ]}

        active = [tr for tr in active if t_now - tr["last_t"] <= 3.0]

    merges = stitch_fragments(tracks, max_sens=args.max_sens_m_per_px)
    if merges:
        print("stitched fragments (same vehicle, detection dropout): "
              + ", ".join(f"id{b}->id{a}" for a, b in merges))
    dups = suppress_simultaneous_duplicates(tracks)
    if dups:
        print("suppressed parallel duplicates: "
              + ", ".join(f"id{s} (ghost of id{b})" for s, b in dups))

    rows = []
    for tid, rec in sorted(tracks.items()):
        obs = rec["obs"]
        if rec.get("duplicate_of"):
            continue
        # Report the majority class over the track's observations: the online
        # class is just the first frame's guess, and car/truck flicker means
        # that guess is wrong for a visible fraction of vehicles.
        votes: dict[str, int] = {}
        for o in obs:
            votes[o.get("cls", rec["cls"])] = votes.get(o.get("cls", rec["cls"]), 0) + 1
        rec["cls"] = max(votes, key=votes.get)
        # Fit the speed over near-field observations only. A receding vehicle
        # legitimately coasts into the far field, but positions there are
        # meter-scale noise: leaving them in the constant-velocity fit dilutes
        # (or, after a horizon mis-association, corrupts) the trustworthy
        # near-field measurement. When too little near-field remains, fall
        # back to the full track, whose high median sensitivity then triggers
        # the far_field flag: reported, but with no speed number.
        near = [o for o in obs
                if np.isfinite(o.get("sens", 0.0)) and o.get("sens", 0.0) <= args.max_sens_m_per_px]
        use_near = (len(near) >= args.min_track_frames
                    and (near[-1]["t"] - near[0]["t"]) >= args.min_track_seconds)
        fit_obs = near if use_near else obs
        if len(fit_obs) < args.min_track_frames:
            continue
        t = np.array([o["t"] for o in fit_obs])
        P = np.array([o["pos_m"] for o in fit_obs])
        duration = float(t[-1] - t[0])
        if duration < args.min_track_seconds:
            continue
        path_len = float(np.sum(np.linalg.norm(np.diff(P, axis=0), axis=1)))
        if path_len < args.min_path_m:
            continue
        # NET displacement gate: a queueing vehicle's bbox jitter integrates
        # tens of meters of "path" while it goes nowhere; start-to-end
        # displacement cannot be gamed that way.
        disp_m = float(np.linalg.norm(P[-1] - P[0]))
        if disp_m < args.min_disp_m:
            continue
        # Constant-velocity linear fit per axis: robust to per-frame pixel jitter,
        # and its residual tells us whether the motion was actually uniform.
        A = np.column_stack([t - t[0], np.ones(len(t))])
        vel = []
        residuals = []
        for axis in range(3):
            coeff, *_ = np.linalg.lstsq(A, P[:, axis], rcond=None)
            vel.append(coeff[0])
            residuals.append(P[:, axis] - A @ coeff)
        speed_ms = float(np.linalg.norm(vel))
        rmse = float(np.sqrt(np.mean(np.concatenate(residuals) ** 2)))

        # 95% CI on the speed: slope standard error from the fit residuals,
        # projected onto the velocity direction, combined in quadrature with
        # the calibration-scale uncertainty (which multiplies the whole speed).
        t_c = t - t.mean()
        s_tt = float(np.sum(t_c ** 2))
        var_v = 0.0
        if s_tt > 1e-9 and len(t) > 2:
            v_hat = np.array(vel)
            v_norm = max(1e-9, float(np.linalg.norm(v_hat)))
            for axis in range(3):
                se2 = float(np.sum(residuals[axis] ** 2)) / max(1, len(t) - 2) / s_tt
                var_v += (v_hat[axis] / v_norm) ** 2 * se2
        ci_ms = float(np.hypot(1.96 * np.sqrt(var_v), 1.96 * speed_ms * args.scale_cv))

        sens_arr = np.array([o.get("sens", 0.0) for o in fit_obs], dtype=np.float64)
        sens_med = float(np.median(sens_arr[np.isfinite(sens_arr)])) if np.isfinite(sens_arr).any() else 99.0
        if not np.isfinite(sens_med):
            sens_med = 99.0
        if sens_med > args.max_sens_m_per_px or not np.isfinite(sens_arr).all():
            quality = "far_field"
        elif rmse < 1.5:
            quality = "ok"
        else:
            quality = "nonuniform_motion"
        rows.append({
            "track_id": tid,
            "class": rec["cls"],
            "n_frames": len(fit_obs),
            "duration_s": round(duration, 2),
            "path_m": round(path_len, 1),
            "disp_m": round(disp_m, 1),
            "speed_kmh": round(speed_ms * 3.6, 1),
            "speed_ci_kmh": round(ci_ms * 3.6, 1),
            "fit_rmse_m": round(rmse, 2),
            "sens_m_per_px": round(min(sens_med, 99.0), 3),
            "quality": quality,
        })

    csv_path = out_dir / "speeds.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["track_id", "class", "n_frames", "duration_s", "path_m", "disp_m",
                                                "speed_kmh", "speed_ci_kmh", "fit_rmse_m", "sens_m_per_px", "quality"])
        writer.writeheader()
        writer.writerows(rows)

    (out_dir / "tracks.json").write_text(
        json.dumps({"ground_plane": ground, "scale": args.pointcloud_scale, "tracks": tracks, "speeds": rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Visualization: last frame with every reported track's trail + speed label
    canvas = cv2.imread(str(frames[-1]))
    palette = [(0, 255, 0), (0, 200, 255), (255, 120, 0), (255, 0, 255), (0, 255, 255), (255, 255, 0)]
    reported = {r["track_id"]: r for r in rows}
    for k, (tid, rec) in enumerate(sorted(tracks.items())):
        if tid not in reported:
            continue
        color = palette[k % len(palette)]
        pts = np.array([[int(o["px"]), int(o["py"])] for o in rec["obs"]])
        for p, q in zip(pts[:-1], pts[1:]):
            cv2.line(canvas, tuple(p), tuple(q), color, 2)
        for p in pts:
            cv2.circle(canvas, tuple(p), 3, color, -1)
        r = reported[tid]
        if r["quality"] == "far_field":
            label = f"id{tid} {r['class']} far-range: no speed"
        elif r["speed_ci_kmh"] > 0.5 * max(1e-9, r["speed_kmh"]):
            label = f"id{tid} {r['class']} {r['speed_kmh']:.0f}±{r['speed_ci_kmh']:.0f}km/h?"
        else:
            label = f"id{tid} {r['class']} {r['speed_kmh']:.0f}±{r['speed_ci_kmh']:.0f}km/h"
        anchor = pts[-1]
        cv2.putText(canvas, label, (anchor[0] + 8, anchor[1] - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 4)
        cv2.putText(canvas, label, (anchor[0] + 8, anchor[1] - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
    vis_path = out_dir / "speed_overlay.png"
    cv2.imwrite(str(vis_path), canvas)

    if args.render_video:
        video_path = Path(args.render_video)
        if not video_path.is_absolute():
            video_path = out_dir / video_path
        anchors: list[dict] = []
        hud = args.camera_label
        if args.anchors_json:
            anchors, spec_note = load_calibration_anchors(Path(args.anchors_json))
            hud_scale = f"scale {args.pointcloud_scale:.3f} ({spec_note}"
            hud_scale += f", CV {args.scale_cv * 100:.0f}%)" if args.scale_cv > 0 else ")"
            hud = f"{hud}  {hud_scale}" if hud else hud_scale
        render_video(frames, times, tracks, reported, video_path, args.playback_fps,
                     mode=args.playback_mode, anchors=anchors, time_scale=args.time_scale, hud=hud)
        print(f"saved: {video_path}")
        rendered = [video_path]
        if args.also_frame_video:
            frame_video_path = Path(args.also_frame_video)
            if not frame_video_path.is_absolute():
                frame_video_path = out_dir / frame_video_path
            render_video(frames, times, tracks, reported, frame_video_path, args.playback_fps,
                         mode="native", anchors=anchors, frame_info=True, hud=hud)
            print(f"saved: {frame_video_path}")
            rendered.append(frame_video_path)
        # mp4v is what OpenCV can write, but browsers/players want H.264;
        # convert on the spot when ffmpeg is available.
        import shutil
        import subprocess

        if shutil.which("ffmpeg"):
            for vp in rendered:
                h264_path = vp.with_name(vp.stem + "_h264.mp4")
                proc = subprocess.run(
                    ["ffmpeg", "-y", "-v", "error", "-i", str(vp),
                     "-c:v", "libopenh264", "-b:v", "6M", "-pix_fmt", "yuv420p", str(h264_path)],
                    capture_output=True, text=True)
                if proc.returncode == 0:
                    print(f"saved: {h264_path}")

    print(f"tracks_total={len(tracks)} reported={len(rows)}")
    for r in rows:
        print(f"  id{r['track_id']:>3} {r['class']:10s} {r['speed_kmh']:6.1f}±{r['speed_ci_kmh']:4.1f} km/h  "
              f"({r['n_frames']}f {r['duration_s']}s disp={r['disp_m']}m rmse={r['fit_rmse_m']} "
              f"sens={r['sens_m_per_px']} {r['quality']})")
    print(f"saved: {csv_path}")
    print(f"saved: {vis_path}")


if __name__ == "__main__":
    main()
