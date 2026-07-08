from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "tools"))

from cctv_speed_estimation import frame_times_from_clock


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export an auditable per-frame timeline for a recording: each source frame's "
        "real timestamp (OSD-tick derived or fixed fps), whether the OSD second rolled on that "
        "frame, and where the frame lands in the rendered realtime/native videos."
    )
    parser.add_argument("--frames-dir", required=True)
    parser.add_argument("--clock-roi", default="0,0,520,40")
    parser.add_argument("--fps", type=float, default=0.0, help="Fixed fps instead of OSD ticks.")
    parser.add_argument("--native-fps", type=int, default=10, help="Playback fps used for the native-mode video.")
    parser.add_argument("--out-csv", required=True)
    parser.add_argument("--osd-strip", default="", help="Optional png: OSD clock crops at every Nth tick for human verification.")
    parser.add_argument("--osd-strip-every", type=int, default=15, help="Sample every Nth tick frame into the strip.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    frames = sorted(Path(args.frames_dir).glob("*.jpg")) + sorted(Path(args.frames_dir).glob("*.png"))
    if not frames:
        raise RuntimeError("no frames")
    roi = tuple(int(v) for v in args.clock_roi.split(","))

    if args.fps > 0:
        times = np.arange(len(frames), dtype=np.float64) / args.fps
        tick_set: set[int] = set()
    else:
        times = frame_times_from_clock(frames, roi)
        # Recompute tick frames the same way the timing did, for the CSV flag
        x1, y1, x2, y2 = roi
        bins = []
        for f in frames:
            img = cv2.imread(str(f), cv2.IMREAD_GRAYSCALE)
            bins.append((img[y1:y2, x1:x2] > 160).astype(np.uint8))
        area = max(1, (y2 - y1) * (x2 - x1))
        min_changed = max(25, int(area * 0.004))
        tick_set = {
            i for i in range(1, len(bins))
            if int(np.count_nonzero(bins[i] != bins[i - 1])) >= min_changed
        }

    out_csv = Path(args.out_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow([
            "frame_idx", "frame_file", "t_rel_s", "dt_prev_s",
            "osd_second_rollover", "realtime_video_s", "native_video_s",
        ])
        for i, f in enumerate(frames):
            dt = times[i] - times[i - 1] if i > 0 else 0.0
            w.writerow([
                i, f.name, f"{times[i]:.3f}", f"{dt:.3f}",
                int(i in tick_set), f"{times[i] - times[0]:.3f}",
                f"{i / args.native_fps:.3f}",
            ])

    if args.osd_strip and args.fps <= 0:
        x1, y1, x2, y2 = roi
        ticks = sorted(tick_set)[:: args.osd_strip_every]
        rows = []
        for i in ticks:
            img = cv2.imread(str(frames[i]))
            crop = img[y1:y2, x1:x2].copy()
            cv2.putText(crop, f"f{i} t={times[i]-times[0]:.1f}s", (crop.shape[1] - 260, crop.shape[0] - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 2)
            rows.append(crop)
        if rows:
            strip = np.vstack(rows)
            Path(args.osd_strip).parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(args.osd_strip, strip)

    dts = np.diff(times)
    print(f"frames={len(frames)} span={times[-1]-times[0]:.1f}s ticks={len(tick_set)} "
          f"fps(mean)={1/np.mean(dts):.2f} dt min/med/max={dts.min():.3f}/{np.median(dts):.3f}/{dts.max():.3f}s")
    print(f"saved: {out_csv}")


if __name__ == "__main__":
    main()
