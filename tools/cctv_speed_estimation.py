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
    parser.add_argument("--yolo-model", default="checkpoints/yolov8m-seg.pt", help="Ultralytics model for track().")
    parser.add_argument("--conf", type=float, default=0.3, help="Detection confidence threshold.")
    parser.add_argument("--out-dir", required=True, help="Output directory.")
    parser.add_argument("--min-track-frames", type=int, default=4, help="Minimum observations per track.")
    parser.add_argument("--min-track-seconds", type=float, default=2.0, help="Minimum track duration.")
    parser.add_argument("--min-path-m", type=float, default=5.0, help="Minimum path length in meters for a speed to be reported.")
    parser.add_argument("--render-video", default="", help="Optional output mp4 path: per-frame boxes, recent trails, live speed labels, real-time playback.")
    parser.add_argument("--playback-fps", type=int, default=12, help="Playback fps of the rendered video; source frames are repeated to match real durations.")
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
) -> None:
    """Real-time annotated playback: each source frame is repeated to match its
    true duration (from OSD-clock timestamps), so vehicle motion in the output
    plays at wall-clock speed even though the NVR stream is ~1-2 fps."""
    sample = cv2.imread(str(frames[0]))
    h, w = sample.shape[:2]
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(video_path), fourcc, playback_fps, (w, h))

    # Sorted per-track observation arrays for time interpolation
    track_obs: dict[int, list[dict]] = {}
    for tid, rec in tracks.items():
        if tid in reported and rec["obs"]:
            track_obs[tid] = sorted(rec["obs"], key=lambda o: o["t"])

    def lerp(a: float, b: float, w: float) -> float:
        return a + (b - a) * w

    def draw_at(img: np.ndarray, t_render: float) -> None:
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

            color = _id_color(tid)
            rec = tracks[tid]
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
                label_anchor = (bx1, max(20, by1 - 8))
            else:
                label_anchor = (int(px) + 8, int(py) - 8)
            cv2.circle(img, (int(px), int(py)), 6, color, -1)
            cv2.circle(img, (int(px), int(py)), 6, (255, 255, 255), 1)
            speed = lerp(float(a.get("speed_kmh", 0)), float(b.get("speed_kmh", 0)), w)
            label = f"id{tid} {rec['cls']} {speed:.0f}km/h"
            cv2.putText(img, label, label_anchor, cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 4)
            cv2.putText(img, label, label_anchor, cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

    med_dt = float(np.median(np.diff(times)))
    for i, f in enumerate(frames):
        base = cv2.imread(str(f))
        t0 = float(times[i])
        dt = float(times[i + 1] - times[i]) if i + 1 < len(times) else med_dt
        repeats = max(1, int(round(dt * playback_fps)))
        for k in range(repeats):
            img = base.copy()
            draw_at(img, t0 + dt * (k / repeats))
            writer.write(img)
    writer.release()


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
            for box, cls in zip(boxes, clss):
                if int(cls) not in VEHICLE_CLASSES:
                    continue
                x1, y1, x2, y2 = box
                gp = pixel_to_ground_m((x1 + x2) / 2.0, y2)
                if gp is None:
                    continue
                dets.append({"cls": VEHICLE_CLASSES[int(cls)], "px": float((x1 + x2) / 2), "py": float(y2),
                             "box": [float(x1), float(y1), float(x2), float(y2)], "pos": gp})

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
                gate = max(4.0, speed * dt * 1.6 + 2.0)
            for di, det in enumerate(dets):
                if det["cls"] != tr["cls"]:
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
            tr["last_t"] = t_now
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
                 "pos_m": det["pos"].tolist(), "speed_kmh": disp_speed}
            )

        for di, det in enumerate(dets):
            if di in used_d:
                continue
            tid = next_id
            next_id += 1
            active.append({"id": tid, "cls": det["cls"], "pos": det["pos"], "vel": np.zeros(3), "last_t": t_now, "n_obs": 1})
            tracks[tid] = {"cls": det["cls"], "obs": [
                {"frame": i, "t": t_now, "px": det["px"], "py": det["py"], "box": det["box"],
                 "pos_m": det["pos"].tolist(), "speed_kmh": 0.0}
            ]}

        active = [tr for tr in active if t_now - tr["last_t"] <= 3.0]

    rows = []
    for tid, rec in sorted(tracks.items()):
        obs = rec["obs"]
        if len(obs) < args.min_track_frames:
            continue
        t = np.array([o["t"] for o in obs])
        P = np.array([o["pos_m"] for o in obs])
        duration = float(t[-1] - t[0])
        if duration < args.min_track_seconds:
            continue
        path_len = float(np.sum(np.linalg.norm(np.diff(P, axis=0), axis=1)))
        if path_len < args.min_path_m:
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
        rows.append({
            "track_id": tid,
            "class": rec["cls"],
            "n_frames": len(obs),
            "duration_s": round(duration, 2),
            "path_m": round(path_len, 1),
            "speed_kmh": round(speed_ms * 3.6, 1),
            "fit_rmse_m": round(rmse, 2),
            "quality": "ok" if rmse < 1.5 else "nonuniform_motion",
        })

    csv_path = out_dir / "speeds.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["track_id", "class", "n_frames", "duration_s", "path_m", "speed_kmh", "fit_rmse_m", "quality"])
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
        label = f"id{tid} {r['class']} {r['speed_kmh']:.0f}km/h"
        anchor = pts[-1]
        cv2.putText(canvas, label, (anchor[0] + 8, anchor[1] - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 4)
        cv2.putText(canvas, label, (anchor[0] + 8, anchor[1] - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
    vis_path = out_dir / "speed_overlay.png"
    cv2.imwrite(str(vis_path), canvas)

    if args.render_video:
        video_path = Path(args.render_video)
        if not video_path.is_absolute():
            video_path = out_dir / video_path
        render_video(frames, times, tracks, reported, video_path, args.playback_fps)
        print(f"saved: {video_path}")

    print(f"tracks_total={len(tracks)} reported={len(rows)}")
    for r in rows:
        print(f"  id{r['track_id']:>3} {r['class']:10s} {r['speed_kmh']:6.1f} km/h  ({r['n_frames']}f {r['duration_s']}s {r['path_m']}m rmse={r['fit_rmse_m']} {r['quality']})")
    print(f"saved: {csv_path}")
    print(f"saved: {vis_path}")


if __name__ == "__main__":
    main()
