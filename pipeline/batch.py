"""Batch runner in the shared format (monocular-driving-distance docs/SPEC.md): a segments root and a list of ids in,
predictions/<method>/<version>/<segment_id>/{ego.csv, objects.csv, meta.json} out.

Per segment: frames and fps from segment.json; the dash cycle from its road_class (SPEC 2.3; 'unknown' -> ego.UNKNOWN_CYCLE);
blocks 2-4 once (core.run_clip); two versions from the same run:
  --version-own   the clip's own scale (odometer, or the rule focal flagged when that fails)
  --version-main  the same-camera scale given by --camera-scale (written only when it is given); --camera-scale-night
                  replaces it on segments whose segment.json light is 'night'; --distance-correction (a table learned
                  on development data for the same-camera scale) applies to this version only
--rel-window sets the relative-speed fit window for both versions; --cycle-select lets the image pick between the two
Californian dash cycles per second (pipeline/cycle.py) for both versions (the cache keeps the odometer's own reading).
ego.csv lists the processed frames (every second frame), the scorer's scope. A per-segment cache (cars, boxes, ego, scale)
goes to --cache so other scales can be applied later without rerunning the models.
A segment that fails is written as refused (meta.json status "refused" + reason, SPEC 3.1) and the run goes on.
meta.json records the code (git commit and a sha256 over pipeline/ and the tools files it imports) and the weights.

  export LD_PRELOAD=~/anaconda3/envs/VisionVelocity/lib/libstdc++.so.6
  FFMPEG=<agreed ffmpeg> ~/venvs/da3/bin/python -m pipeline.batch --segments-root <root> --ids <file> \
      --out-root <predictions/A_.../> --cache <folder> [--camera-scale S] [--hood-row 630] [--picker comma2k19]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pickle
import subprocess
import time
import traceback
from pathlib import Path

from . import core as CO
from . import cycle as CY
from . import depth as DP
from . import ego as EG
from . import measure as MS

REPO = Path(__file__).resolve().parents[1]
METHOD = "A_depth_odometer"
# everything the outputs depend on besides the weights: this folder and the tools modules it imports
CODE_FILES = ["tools/dashcam_range_speed.py", "tools/auto_odometer_points.py", "tools/depth_backends.py",
              "tools/lane_dash_calibration.py", "utils/pointcloud_io.py"]


def commit() -> str:
    head = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "-C", str(REPO), "status", "--porcelain", "pipeline", *CODE_FILES],
                           capture_output=True, text=True).stdout.strip()
    return f"Vehicle-Distance-Forensics {head}" + (" + uncommitted changes" if dirty else "")


def code_sha256() -> str:
    h = hashlib.sha256()
    for p in sorted((REPO / "pipeline").glob("*.py")) + [REPO / f for f in CODE_FILES]:
        h.update(p.relative_to(REPO).as_posix().encode() + b"\0" + p.read_bytes() + b"\0")
    return h.hexdigest()


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while block := fh.read(1 << 20):
            h.update(block)
    return h.hexdigest()


def read_ids(path: Path) -> list[str]:
    """One id per line; blank lines and '#' comments skipped, a byte-order mark tolerated (as mddbench's lists)."""
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    return [x.strip() for x in lines if x.strip() and not x.strip().startswith("#")]


def write(out: Path, clip: dict, sc: dict, seg: dict, version: str, extra: dict, run: dict, win_s: float = 1.0,
          corr: MS.DistanceCorrection | None = None) -> None:
    out.mkdir(parents=True, exist_ok=True)
    CO.ego_table(clip, processed_only=True).to_csv(out / "ego.csv", index=False)
    CO.objects_for(clip, sc, win_s, corr).to_csv(out / "objects.csv", index=False)
    meta = {"spec": "0.1", "method": METHOD, "version": version, "segment_id": seg["segment_id"], "status": "ok",
            **run, "params": {"scale": sc, "own_scale": clip["own_scale"], "dash_cycle_m": clip["cycle_m"],
                              "hood_row": clip["hood"], "tracker_restarts": clip["restarts"],
                              "odometer_coverage": round(float((clip["method"] == "dash_odometer").mean()), 3),
                              "rel_window_s": win_s, "distance_correction": None if corr is None else corr.table, **extra}}
    (out / "meta.json").write_text(json.dumps(meta, indent=1, default=float), encoding="utf-8")


def refuse(out: Path, sid: str, version: str, reason: str, run: dict) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for f in ("ego.csv", "objects.csv"):
        (out / f).unlink(missing_ok=True)
    meta = {"spec": "0.1", "method": METHOD, "version": version, "segment_id": sid, "status": "refused", "reason": reason, **run}
    (out / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--segments-root", type=Path, required=True)
    ap.add_argument("--ids", type=Path, required=True)
    ap.add_argument("--out-root", type=Path, required=True, help="predictions/<method>; versions go below it")
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--camera-scale", type=float)
    ap.add_argument("--camera-scale-night", type=float, help="same-camera scale for segments labelled night")
    ap.add_argument("--distance-correction", type=Path, help="json {d_m: [...], factor: [...]} for the main version")
    ap.add_argument("--rel-window", type=float, default=1.0, help="relative-speed fit window, s")
    ap.add_argument("--cycle-select", action="store_true", help="image picks between the two legal Californian cycles")
    ap.add_argument("--version-main", default="v2")
    ap.add_argument("--version-own", default="v2own")
    ap.add_argument("--hood-row", type=int, default=630)
    ap.add_argument("--picker", choices=list(EG.PICK), default="comma2k19")
    ap.add_argument("--weights", type=Path, default=REPO / "checkpoints/yolov8m-seg.pt")
    a = ap.parse_args()
    ids = read_ids(a.ids)
    corr = MS.DistanceCorrection(json.loads(a.distance_correction.read_text(encoding="utf-8"))) if a.distance_correction else None
    os.environ.setdefault("HF_HUB_OFFLINE", "1")        # the cached DA3 snapshot, never a newer download
    run = {"code_commit": commit(), "code_sha256": code_sha256(),
           "weights": {"yolo": f"{a.weights.name} sha256 {file_sha256(a.weights)}", "depth": DP.MODEL_ID,
                       "ffmpeg_env": os.environ.get("FFMPEG", "")}}
    model = DP.load_model()
    versions = [a.version_own] + ([a.version_main] if a.camera_scale else [])
    for k, sid in enumerate(ids):
        if all((a.out_root / v / sid / "meta.json").exists() for v in versions):
            continue
        t0 = time.time()
        try:
            seg = json.loads((a.segments_root / sid / "segment.json").read_text(encoding="utf-8"))
            road = seg.get("road_class") or "unknown"
            cycle = EG.CYCLES_M.get(road, EG.CYCLES_M[EG.UNKNOWN_CYCLE])
            frames = sorted((a.segments_root / sid / "frames").glob("*.jpg"))
            if len(frames) != seg["n_frames"]:
                raise RuntimeError(f"{len(frames)} frames on disk, segment.json says {seg['n_frames']}")
            clip = CO.run_clip(frames, float(seg["fps"]), cycle, a.hood_row, EG.PICK[a.picker], model, a.weights)
        except Exception as e:      # one bad segment must not stop the batch; it is written as refused (SPEC 3.1)
            reason = f"{type(e).__name__}: {e}"
            print(f"{k + 1}/{len(ids)} {sid} REFUSED {reason}\n{traceback.format_exc()}", flush=True)
            for v in versions:
                refuse(a.out_root / v / sid, sid, v, reason, run)
            continue
        a.cache.mkdir(parents=True, exist_ok=True)
        with open(a.cache / f"{sid}.pkl", "wb") as fh:
            pickle.dump(clip, fh)
        extra = {"road_class": road, "cycle_from": road if road in EG.CYCLES_M else f"unknown -> {EG.UNKNOWN_CYCLE}"}
        night = seg.get("light") == "night" and a.camera_scale_night
        s_main = (a.camera_scale_night if night else a.camera_scale) if a.camera_scale else None
        if a.cycle_select:      # after the cache is written: the cache keeps the odometer's own reading
            ego2, _, cinfo = CY.select(clip, CY.image_speed(clip, s_main or clip["own_scale"]["s"]))
            clip = {**clip, "ego_kmh": ego2}
            extra["cycle_select"] = {k: cinfo[k] for k in ("switched_seconds", "seconds_with_ratio")}
        write(a.out_root / a.version_own / sid, clip, clip["own_scale"], seg, a.version_own, extra, run, a.rel_window)
        if a.camera_scale:
            write(a.out_root / a.version_main / sid, clip, CO.same_camera(s_main, clip), seg, a.version_main,
                  {**extra, "light": seg.get("light", "unknown"), "camera_scale_from": "night" if night else "all"}, run,
                  a.rel_window, corr)
        print(f"{k + 1}/{len(ids)} {sid} {road} own scale {clip['own_scale']['source']} "
              f"{clip['own_scale']['s'] / clip['own_scale']['s_rule']:.3f} x rule, {time.time() - t0:.0f} s", flush=True)


if __name__ == "__main__":
    main()
