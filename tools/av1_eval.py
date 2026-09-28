#!/usr/bin/env python3
"""Score the marking-scaled depth model against Argoverse 1's lidar cuboids.

Same experiment and the same output keys as `av2_eval.py` -- what changes is only where the
truth lives, because AV1 ships per-sweep JSON in the egovehicle frame instead of AV2's
feather table.  Keeping the keys identical is the point: the cross-camera claim is that the
SAME method, scored the SAME way, behaves the same on a different sensor.

This is the step that opens the ground truth, so it is deliberately last: the scale constant,
the target pixels and the model readings are all on disk before any cuboid is extracted.
`--verify-sealed` re-checks the prediction files against the hashes recorded at that point.

⚠ The blind is weaker here than on AV2 and the report must say so.  AV2's cuboids are a
separate S3 object that was never downloaded, so `seal_predictions.py --absent` could show
the truth was not on the machine.  AV1 ships them inside the same 61 GB tar as the images,
so the guarantee is procedural: `av1_fetch.py` excludes them on the first pass, and the
timestamped fetch log shows the `--only-truth` pass ran after the seal.

What is compared, on the same rows (as av2_eval):
  method C   d = A_marking/(py_max - y_h): markings only, no model, no learning.
  raw depth  what the model prints in metres at the body pixel.
  x k_blind  scaled by a constant taken from method C on every detected target, truth
             nowhere in it -- the number a deployed system can actually get.
  x k_marking / x k_oracle   the same constant fitted on the scored rows / on the cuboids.

Ground truth per target: the nearest cuboid corner measured forward from the camera.

Usage:
  python3 tools/av1_eval.py --log data/input/av1/<log> --calib data/output/av1_marking/calib.json \
      --pred "data/output/av1_depth/pred_<log>__*.csv" --out data/output/av1_depth/eval_<log>.json
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
from pathlib import Path

import numpy as np

VEHICLE = ("VEHICLE", "LARGE_VEHICLE", "BUS", "SCHOOL_BUS", "TRAILER", "EMERGENCY_VEHICLE",
           "MOTORCYCLE", "MOPED")


def quat_to_R(qw, qx, qy, qz):
    return np.array([
        [1 - 2 * (qy * qy + qz * qz), 2 * (qx * qy - qz * qw), 2 * (qx * qz + qy * qw)],
        [2 * (qx * qy + qz * qw), 1 - 2 * (qx * qx + qz * qz), 2 * (qy * qz - qx * qw)],
        [2 * (qx * qz - qy * qw), 2 * (qy * qz + qx * qw), 1 - 2 * (qx * qx + qy * qy)]])


def SE3(q, t):
    M = np.eye(4)
    M[:3, :3] = quat_to_R(*q)
    M[:3, 3] = t
    return M


def corners(o):
    """Eight cuboid corners in the egovehicle frame of the sweep that labelled it."""
    l, w, h = o["length"] / 2, o["width"] / 2, o["height"] / 2
    c = np.array([[sx * l, sy * w, sz * h] for sx in (1, -1) for sy in (1, -1) for sz in (1, -1)])
    r = o["rotation"]
    R = quat_to_R(r["w"], r["x"], r["y"], r["z"])
    ctr = o["center"]
    return c @ R.T + np.array([ctr["x"], ctr["y"], ctr["z"]])


def iou(a, b):
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[2], b[2]), min(a[3], b[3])
    if x1 <= x0 or y1 <= y0:
        return 0.0
    i = (x1 - x0) * (y1 - y0)
    return i / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - i)


def med(x):
    return float(np.median(x)) if len(x) else float("nan")


def rel_err(pred, gt):
    return med(np.abs(np.asarray(pred) - np.asarray(gt)) / np.asarray(gt)) * 100


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--log", required=True)
    ap.add_argument("--calib", required=True)
    ap.add_argument("--pred", default="", help="glob of prediction CSVs; omit to score method C only")
    ap.add_argument("--targets", default="", help="targets CSV (needed when --pred is omitted)")
    ap.add_argument("--frames-name", default="pinhole")
    ap.add_argument("--min-iou", type=float, default=0.5)
    ap.add_argument("--near-m", type=float, default=32.0)
    ap.add_argument("--max-dt-ms", type=float, default=60.0)
    ap.add_argument("--verify-sealed", default="")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    import pandas as pd

    log = Path(args.log)
    meta = json.loads((log / f"{args.frames_name}_meta.json").read_text())
    cal = {c["log"]: c for c in json.loads(Path(args.calib).read_text())}[log.name]
    if cal.get("status") != "ok":
        raise SystemExit(f"{log.name}: marking calibration did not pass ({cal.get('status')})")
    A, y_h = cal["A_marking"], cal["y_h"]

    preds = sorted(glob.glob(args.pred)) if args.pred else []
    if args.pred and not preds:
        raise SystemExit(f"no prediction CSV matched {args.pred}")
    if args.verify_sealed:
        seal = json.loads(Path(args.verify_sealed).read_text())
        for p in preds:
            h = hashlib.sha256(Path(p).read_bytes()).hexdigest()
            if seal.get("files", {}).get(Path(p).name) != h:
                raise SystemExit(f"{Path(p).name}: sha256 differs from the sealed record")
        print(f"sealed predictions verified ({len(preds)} files, sealed {seal.get('sealed_utc')})")

    ann_dir = log / "per_sweep_annotations_amodal"
    if not ann_dir.is_dir():
        raise SystemExit(f"{ann_dir} missing -- run av1_fetch.py --only-truth AFTER sealing")
    ann_ts = np.array(sorted(int(p.stem.split("_")[-1]) for p in ann_dir.glob("*.json")))

    pose_files = {int(p.stem.split("_")[-1]): p for p in (log / "poses").glob("*.json")}
    ptime = np.array(sorted(pose_files))

    def pose_at(ts):
        i = int(np.argmin(np.abs(ptime - ts)))
        d = json.loads(pose_files[int(ptime[i])].read_text())
        return SE3(d["rotation"], d["translation"])

    cal_j = json.loads((log / "vehicle_calibration_info.json").read_text())
    cam = next(e["value"] for e in cal_j["camera_data_"] if e["key"].endswith(meta["camera"]))
    ego_T_cam = SE3(cam["vehicle_SE3_camera_"]["rotation"]["coefficients"],
                    cam["vehicle_SE3_camera_"]["translation"])
    cam_T_ego = np.linalg.inv(ego_T_cam)
    cam_x = float(cam["vehicle_SE3_camera_"]["translation"][0])
    K = np.array([[meta["fx"], 0, meta["cx"]], [0, meta["fy"], meta["cy"]], [0, 0, 1]])

    fr = pd.read_csv(log / f"{args.frames_name}_frames.csv")
    ts_of = dict(zip(fr.frame_idx, fr.timestamp_ns))

    by_model = {}
    for p in preds:
        d = pd.read_csv(p)
        by_model[d.model.iloc[0] if "model" in d else Path(p).stem] = d
    base = next(iter(by_model.values())) if by_model else pd.read_csv(args.targets)

    gt_cache, rows_out = {}, []
    for _, t in base.iterrows():
        f = t.frame_idx
        ts = ts_of[f]
        if f not in gt_cache:
            ats = int(ann_ts[np.argmin(np.abs(ann_ts - ts))])
            if abs(ats - ts) > args.max_dt_ms * 1e6:
                gt_cache[f] = []
                continue
            T_ego = np.linalg.inv(pose_at(ts)) @ pose_at(ats)      # ego(t_lidar) -> ego(t_cam)
            T = cam_T_ego @ T_ego
            out = []
            for o in json.loads((ann_dir / f"tracked_object_labels_{ats}.json").read_text()):
                if o.get("label_class") not in VEHICLE:
                    continue
                C = corners(o)
                Ch = (T @ np.c_[C, np.ones(8)].T).T[:, :3]
                if (Ch[:, 2] <= 0.5).any():                        # partly behind the camera
                    continue
                uv = (K @ Ch.T).T
                uv = uv[:, :2] / uv[:, 2:3]
                Ce = (T_ego @ np.c_[C, np.ones(8)].T).T[:, :3]
                out.append(dict(box=[uv[:, 0].min(), uv[:, 1].min(), uv[:, 0].max(), uv[:, 1].max()],
                                gt=float(Ce[:, 0].min()) - cam_x, lat=float(np.median(Ce[:, 1])),
                                cat=o["label_class"]))
            gt_cache[f] = out
        best, bi = 0.0, None
        for g in gt_cache[f]:
            v = iou([t.x0, t.y0, t.x1, t.y1], g["box"])
            if v > best:
                best, bi = v, g
        if bi is None or best < args.min_iou or bi["gt"] <= 0:
            continue
        rows_out.append(dict(frame_idx=f, px=t.px, py=t.py, py_max=t.py_max, iou=round(best, 3),
                             gt_m=bi["gt"], lat_m=bi["lat"], cat=bi["cat"],
                             method_c=A / (t.py_max - y_h)))

    if not rows_out:
        raise SystemExit("nothing matched the cuboids")
    R = pd.DataFrame(rows_out)
    key = list(zip(R.frame_idx, R.px))
    for m, d in by_model.items():
        k = dict(zip(zip(d.frame_idx, d.px), d.pred))
        R[m] = [k.get(x, np.nan) for x in key]

    near = R.gt_m < args.near_m
    res = dict(log=log.name, dataset="av1", n=len(R), n_near=int(near.sum()),
               A_marking=A, A_factory=meta["A_factory"], A_ratio=A / meta["A_factory"],
               y_h=y_h, cy=meta["cy"], near_m=args.near_m,
               gt_range=[float(R.gt_m.min()), float(R.gt_m.max())],
               method_c_err_pct=rel_err(R.method_c[near], R.gt_m[near]),
               method_c_err_pct_blindnear=rel_err(R.method_c[R.method_c < args.near_m],
                                                  R.gt_m[R.method_c < args.near_m]),
               models={})
    print(f"\n{log.name}   {len(R)} matched targets ({int(near.sum())} nearer than {args.near_m:g} m), "
          f"gt {R.gt_m.min():.1f}-{R.gt_m.max():.1f} m")
    print(f"  A marking {A:.0f} vs factory {meta['A_factory']:.0f}  "
          f"({A / meta['A_factory'] * 100 - 100:+.1f}%)")
    print(f"  method C (markings only)            {res['method_c_err_pct']:6.2f}%   "
          f"(near field by its own distance: {res['method_c_err_pct_blindnear']:.2f}%)")
    for m, d in by_model.items():
        v = R[m].values.astype(float)
        ok = np.isfinite(v) & near.values
        k_mark = med(R.method_c.values[ok] / v[ok])
        k_orac = med(R.gt_m.values[ok] / v[ok])
        mc_all = A / (d.py_max.values.astype(float) - y_h)
        pv = d.pred.values.astype(float)
        sel = np.isfinite(pv) & (pv > 0) & (mc_all < args.near_m)
        k_blind = med(mc_all[sel] / pv[sel])
        e = dict(n=int(ok.sum()), n_blind=int(sel.sum()),
                 k_marking=k_mark, k_blind=k_blind, k_oracle=k_orac,
                 raw_pct=rel_err(v[ok], R.gt_m.values[ok]),
                 marking_pct=rel_err(v[ok] * k_mark, R.gt_m.values[ok]),
                 blind_pct=rel_err(v[ok] * k_blind, R.gt_m.values[ok]),
                 oracle_pct=rel_err(v[ok] * k_orac, R.gt_m.values[ok]))
        res["models"][m] = e
        print(f"  {m:<24} raw {e['raw_pct']:6.2f}%   x k_blind {e['blind_pct']:6.2f}%   "
              f"x k_marking {e['marking_pct']:6.2f}%   x k_oracle {e['oracle_pct']:6.2f}%   "
              f"(k {k_blind:.3f} / {k_mark:.3f} / {k_orac:.3f})")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(res, indent=2))
    R.to_csv(str(args.out).replace(".json", "_rows.csv"), index=False)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
