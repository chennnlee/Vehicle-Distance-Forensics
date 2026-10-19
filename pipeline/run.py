"""One command: video -> ego speed, vehicles' distance and speed, a video with the numbers on the cars, a summary.
See pipeline/README.md.

  export LD_PRELOAD=~/anaconda3/envs/VisionVelocity/lib/libstdc++.so.6
  FFMPEG=$HOME/anaconda3/envs/VisionVelocity/bin/ffmpeg ~/venvs/da3/bin/python -m pipeline.run \
      --video <file> --out <folder> --road-class tw            # or --frames-dir <folder> --fps <fps>
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from . import core as CO
from . import depth as DP
from . import ego as EG
from . import frames as FR
from . import measure as MS
from . import render as RD

REPO = Path(__file__).resolve().parents[1]
ROAD_NAMES = {"tw": "台灣(虛線 10 m)", "ca_highway": "加州速限 45 mph 以上(14.63 m)", "ca_local": "加州速限 40 mph 以下(7.315 m)"}
SCALE_NAMES = {"same_camera": "同一台相機事先算好的尺度", "odometer": "這段片用碼表定的尺度", "rule_focal": "30 mm 規則焦距(未校正)"}


def summary_lines(name: str, clip: dict, sc: dict, objs) -> list[str]:
    n = len(clip["ego_kmh"])
    cov = float((clip["method"] == "dash_odometer").mean())
    near = objs[objs.dist_m.notna() & (objs.dist_m <= MS.NEAR_M)]
    why = f";這段片碼表定尺失敗:{clip['own_scale'].get('why')}" if clip["own_scale"]["source"] == "rule_focal" else ""
    return [f"# {name}", "",
            f"- 片長 {n / clip['fps']:.1f} 秒({n} 幀、{clip['fps']:.2f} fps),虛線週期 {clip['cycle_m']} m。",
            f"- 本車速度:碼表有讀值的時間 {100 * cov:.0f}%;沒讀值的時間留空,不補 0。",
            f"- 距離尺度:{SCALE_NAMES[sc['source']]},s = {sc['s']:.3f}(規則焦距為 {sc['s_rule']:.3f},比值 {sc['s'] / sc['s_rule']:.2f}){why}。",
            f"- 他車:{objs.track_id.nunique()} 台;有距離的讀值 {int(objs.dist_m.notna().sum())} 筆,其中 30 m 內 {len(near)} 筆有車速。", ""]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--video", type=Path)
    src.add_argument("--frames-dir", type=Path, help="already decoded frames (f%%05d.jpg)")
    ap.add_argument("--fps", type=float, help="needed with --frames-dir; overrides the container rate (some dashcams lie)")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--road-class", choices=list(EG.CYCLES_M), required=True, help="sets the legal dash cycle (SPEC 2.3)")
    ap.add_argument("--hood-row", type=int, help="image row of the own hood (default 72 %% of the height)")
    ap.add_argument("--picker", choices=list(EG.PICK), default="default", help="where the odometer looks for dashes")
    ap.add_argument("--camera-scale", type=float, help="same-camera depth scale (median of the camera's other clips)")
    ap.add_argument("--distance-correction", type=Path, help="json {d_m: [...], factor: [...]} learned for this camera")
    ap.add_argument("--rel-window", type=float, default=1.0, help="relative-speed fit window, s")
    ap.add_argument("--weights", type=Path, default=REPO / "checkpoints/yolov8m-seg.pt")
    ap.add_argument("--no-video", action="store_true")
    a = ap.parse_args()
    t0 = time.time()
    out = a.out
    out.mkdir(parents=True, exist_ok=True)
    if a.video:
        frames = FR.decode(a.video, out / "frames")
        fps = a.fps or FR.probe_fps(a.video)
    else:
        frames = sorted(a.frames_dir.glob("*.jpg"))
        fps = a.fps
        if not fps:
            raise SystemExit("--fps is required with --frames-dir")
    import cv2
    hood = a.hood_row or int(0.72 * cv2.imread(str(frames[0])).shape[0])
    clip = CO.run_clip(frames, fps, EG.CYCLES_M[a.road_class], hood, EG.PICK[a.picker], DP.load_model(), a.weights)
    sc = CO.same_camera(a.camera_scale, clip) if a.camera_scale else clip["own_scale"]
    corr = MS.DistanceCorrection(json.loads(a.distance_correction.read_text(encoding="utf-8"))) if a.distance_correction else None
    objs = CO.objects_for(clip, sc, a.rel_window, corr)
    CO.ego_table(clip).to_csv(out / "ego.csv", index=False)
    objs.to_csv(out / "objects.csv", index=False)
    name = a.video.name if a.video else a.frames_dir.name
    if not a.no_video:
        t = time.time()
        RD.video(frames, objs, clip["ego_kmh"], fps, DP.STEP, out / "video.mp4", out, f"深度模型 + {SCALE_NAMES[sc['source']]}  ·  {name}")
        clip["timing"]["video_s"] = round(time.time() - t, 1)
    summary = {"source": str(a.video or a.frames_dir), "frames": len(frames), "fps": round(fps, 4), "size": list(clip["size"]),
               "hood_row": hood, "road_class": a.road_class, "dash_cycle_m": clip["cycle_m"],
               "odometer_coverage": round(float((clip["method"] == "dash_odometer").mean()), 3),
               "odometer_points": clip["odometer"].get("points"), "scale": sc, "own_scale": clip["own_scale"],
               "vehicles": int(objs.track_id.nunique()), "tracker_restarts": clip["restarts"],
               "timing_s": {**clip["timing"], "total": round(time.time() - t0, 1)}}
    (out / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False, default=float), encoding="utf-8")
    lines = summary_lines(name, clip, sc, objs) + [f"- 耗時 {summary['timing_s']['total']:.0f} 秒。", ""]
    (out / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
