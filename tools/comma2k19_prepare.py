"""Turn comma2k19 raw chunks into the frames + ground-truth CSV this project eats.

comma2k19 (Schafer et al., 2018) is 33 hours of California I-280 commute recorded
at 20 Hz by a windshield-mounted comma EON. It matters here for one reason: it is
the only public dataset with a paper whose ego-speed truth comes off the car's own
CAN bus while the camera looks at continuous highway lane dashes -- exactly the
domain of pipeline B's dash-cycle odometer. KITTI has the speed band but only
10 Hz (see docs/PUBLIC_DATASET_BENCHMARK_PLAN.md: 5.0 frames per cycle, octave
selection collapses); comma2k19's 20 Hz puts a 12 m cycle at ~8.4 frames, right at
the boundary this project derived, which makes it a test of that criterion rather
than a safe demo.

Two speed records come out of every segment and they are NOT the same number:

  can     `processed_log/CAN/speed` -- what the car's own wheel-speed sensor says.
          This is the dataset's headline truth, and like any wheel sensor it can
          carry a percent-level scale error.
  pose    `global_pose/frame_velocities` -- ECEF velocity from comma's tightly
          coupled GNSS/INS/vision optimiser, one sample per video frame.

This project has already been bitten by treating a device's own readout as gold
(2026-08-02: two dashcams' GPS OSD disagreed with the manual frame-by-frame truth
by up to 2.9 km/h, in opposite directions). So both are exported, and the CSV the
evaluator reads is chosen explicitly with --truth. Their disagreement is printed
per segment and is itself a number worth reporting.
"""
from __future__ import annotations

import argparse
import csv
import re
import subprocess
import zipfile
from pathlib import Path

import numpy as np


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--zip", required=True, help="raw_data/Chunk_N.zip from the comma2k19 HF repo.")
    ap.add_argument("--out-root", required=True, help="Where segment dirs are written.")
    ap.add_argument("--list", action="store_true", help="Just list the segments in the zip and exit.")
    ap.add_argument("--segments", default="", help="Comma-separated 'route|number' segment keys, or '' with --take-n.")
    ap.add_argument("--take-n", type=int, default=0, help="Take the first N segments (one per route unless --same-route).")
    ap.add_argument("--same-route", action="store_true", help="Allow several segments from the same route.")
    ap.add_argument("--truth", choices=("can", "pose"), default="can", help="Which record gt.csv carries.")
    ap.add_argument("--fps", type=float, default=20.0, help="comma EON road camera rate.")
    ap.add_argument("--no-frames", action="store_true", help="Write truth CSVs only, skip hevc decode.")
    return ap.parse_args()


def segment_key(name: str) -> tuple[str, int] | None:
    """'Chunk_1/<route>/<n>/video.hevc' -> (route, n)."""
    m = re.match(r"^Chunk_\d+/([^/]+)/(\d+)/video\.hevc$", name)
    return (m.group(1), int(m.group(2))) if m else None


def load_npy(zf: zipfile.ZipFile, name: str) -> np.ndarray | None:
    try:
        with zf.open(name) as fh:
            return np.load(fh, allow_pickle=False)
    except KeyError:
        return None


def resample(t: np.ndarray, v: np.ndarray, t_out: np.ndarray) -> np.ndarray:
    order = np.argsort(t)
    return np.interp(t_out, t[order], v[order])


def main() -> None:
    args = parse_args()
    zpath = Path(args.zip)
    out_root = Path(args.out_root)
    zf = zipfile.ZipFile(zpath)
    names = zf.namelist()

    segs: dict[tuple[str, int], str] = {}
    for n in names:
        k = segment_key(n)
        if k:
            segs[k] = n.rsplit("/", 1)[0]
    keys = sorted(segs)
    print(f"{zpath.name}: {len(keys)} segments across {len({k[0] for k in keys})} routes")
    if args.list:
        for r in sorted({k[0] for k in keys}):
            ns = [k[1] for k in keys if k[0] == r]
            print(f"  {r}  segments {min(ns)}-{max(ns)} (n={len(ns)})")
        return

    if args.segments:
        want = []
        for tok in args.segments.split(","):
            route, num = tok.rsplit("|", 1)
            want.append((route, int(num)))
    else:
        want, seen = [], set()
        for k in keys:
            # One segment per route by default: 60 s of the same commute tells you
            # far less than 60 s each of different lighting, traffic and lane paint.
            if not args.same_route and k[0] in seen:
                continue
            seen.add(k[0])
            want.append(k)
            if args.take_n and len(want) >= args.take_n:
                break

    out_root.mkdir(parents=True, exist_ok=True)
    index = []
    for route, num in want:
        base = segs[(route, num)]
        # '|' in the route name is legal on ext4 but poison in shell one-liners.
        tag = f"{route.replace('|', '_')}_{num}"
        d = out_root / tag
        d.mkdir(parents=True, exist_ok=True)

        ft = load_npy(zf, f"{base}/global_pose/frame_times")
        fv = load_npy(zf, f"{base}/global_pose/frame_velocities")
        can_t = load_npy(zf, f"{base}/processed_log/CAN/speed/t")
        can_v = load_npy(zf, f"{base}/processed_log/CAN/speed/value")
        if ft is None or fv is None:
            print(f"  {tag}: missing global_pose, skipped")
            continue
        t_rel = ft - ft[0]
        pose_kmh = np.linalg.norm(np.asarray(fv, dtype=np.float64), axis=1) * 3.6
        if can_t is not None and can_v is not None:
            can_kmh = resample(np.asarray(can_t, dtype=np.float64),
                               np.asarray(can_v, dtype=np.float64).reshape(len(can_t), -1)[:, 0] * 3.6, ft)
        else:
            can_kmh = np.full_like(pose_kmh, np.nan)

        with open(d / "gt_both.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["t_s", "can_kmh", "pose_kmh"])
            for i in range(len(t_rel)):
                w.writerow([f"{t_rel[i]:.4f}", f"{can_kmh[i]:.3f}", f"{pose_kmh[i]:.3f}"])
        chosen = can_kmh if args.truth == "can" else pose_kmh
        with open(d / "gt.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["t_s", "speed_kmh"])
            for i in range(len(t_rel)):
                w.writerow([f"{t_rel[i]:.4f}", f"{chosen[i]:.3f}"])

        good = np.isfinite(can_kmh) & np.isfinite(pose_kmh)
        dev = can_kmh[good] - pose_kmh[good]
        print(f"  {tag}: {len(t_rel)} frames, {t_rel[-1]:.1f} s, "
              f"pose median {np.median(pose_kmh):.1f} km/h  "
              f"CAN-pose bias {np.mean(dev):+.2f} MAE {np.mean(np.abs(dev)):.2f} km/h")

        if not args.no_frames:
            fdir = d / "frames"
            fdir.mkdir(exist_ok=True)
            if not any(fdir.glob("*.jpg")):
                vid = d / "video.hevc"
                with zf.open(f"{base}/video.hevc") as src, open(vid, "wb") as dst:
                    while chunk := src.read(1 << 20):
                        dst.write(chunk)
                subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                                "-i", str(vid), "-vsync", "0", "-qscale:v", "2",
                                str(fdir / "f%05d.jpg")], check=True)
                vid.unlink()
            n_frames = len(list(fdir.glob("*.jpg")))
            if n_frames != len(t_rel):
                # Truth is indexed by frame, so a mismatch silently shifts every
                # comparison downstream. Say it loudly rather than trimming.
                print(f"    warn: {n_frames} frames decoded but {len(t_rel)} pose samples")
        index.append({"tag": tag, "route": route, "segment": num,
                      "median_kmh": float(np.median(pose_kmh)), "seconds": float(t_rel[-1])})

    (out_root / "segments.csv").write_text(
        "tag,route,segment,median_kmh,seconds\n" +
        "".join(f"{r['tag']},{r['route']},{r['segment']},{r['median_kmh']:.2f},{r['seconds']:.1f}\n" for r in index),
        encoding="utf-8")
    print(f"\nwrote {len(index)} segments to {out_root}")


if __name__ == "__main__":
    main()
