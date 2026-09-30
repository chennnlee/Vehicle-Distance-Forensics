#!/usr/bin/env python3
"""Every car in view, not just the one ahead: distance from the depth model x k, followed with ByteTrack.

Development tool (2026-09-30), not pre-registered. It continues depth_dash_scale.py: the scale k, the
tracked ego-lane lines and the ego speed come from a dash-scale result, nothing here re-measures them.

  track    YOLOv8m-seg (official Ultralytics weights; car, bus, truck) and ByteTrack (Zhang et al.,
           ECCV 2022; Ultralytics' implementation with its default bytetrack.yaml) on every frame.
           ByteTrack only gives each box an id; the boxes themselves are the detector's. Image only.
  measure  every 0.2 s, for each tracked box on a frame that has a depth map:
             lane      0 = ego lane, -1 / +1 = the lane left / right of it, from where the bottom
                       centre of the box falls against the tracked ego-lane lines at that image row
                       (lane width in pixels at that row = right line - left line); None when the
                       window has no line pair
             distance  k x depth read 6 % of the box height above its bottom, at the box centre
             far       distance beyond the ruler's reach: the 95th percentile of the far ends of the
                       dash cycles that set k. Beyond it k is an extrapolation.
             speeds    relative = slope of the distance over 5 samples of one track (0.8 s), only
                       inside the ruler's reach and while the distance moves <= 15 % per sample;
                       absolute = ego speed (median of the dash-scale readings in that window) + relative
           Boxes whose bottom reaches the bonnet rows (depth_dash_scale.static_rows) are skipped: YOLO
           calls the ego vehicle's own bonnet a car. Reads frames, cached depth maps, the dash-scale
           result and the tracks only; no answer file.
  score    comma2k19 only, on clips whose answers are already open: moving radar returns
           (|relative speed + CAN speed| > 2 m/s) are matched to our boxes frame by frame (Hungarian,
           same lane, distance within 25 % after the radar offset fixed in advance); reports distance
           error by lane and range, how many radar cars inside the ruler's reach were found, id
           switches, and relative-speed error against guessing zero.
  score-av2  Argoverse 2 development logs only (annotations already on disk; never downloads): our tracked
           boxes vs projected lidar cuboids, which keep one id per car -- counts our ids that move to another
           car and cars that get a new id; with --cars also the distance error against the lidar.

  python3 tools/depth_dash_multicar.py track   --frames DIR --out tracks.json
  python3 tools/depth_dash_multicar.py measure --frames DIR --tracks tracks.json --dash result.json \\
          --depth-cache DIR --out cars.json
  python3 tools/depth_dash_multicar.py score   --cars cars.json --truth data/output/c2k19_truth/<tag>
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import cv2
import numpy as np

import depth_dash_scale as D

ROOT = Path(__file__).resolve().parents[1]
PARAMS = dict(
    yolo="checkpoints/yolov8m-seg.pt",
    classes=[2, 5, 7],       # car, bus, truck
    det_conf=0.1,            # boxes handed to ByteTrack (its second stage uses the low-score ones)
    min_conf=0.4,            # a box is measured only at the detector threshold used elsewhere
    tracker="bytetrack.yaml",
    sample_s=0.2,            # measurement spacing
    read_up=0.06,            # depth read this fraction of the box height above its bottom
    patch=5,                 # depth median over patch x patch (half-resolution map)
    bonnet_px=2,
    reach_pct=95,            # ruler's reach: this percentile of the measured cycles' far ends
    half_win=2,              # relative speed over 2 * half_win + 1 samples
    max_jump=0.15,
    min_ego=3,
    # scoring (comma2k19)
    radar_offset_m=2.3,      # radar ranges start at the front of the car; camera ~1.52 m behind it, tyre
                             # contact ~0.8 m ahead of the rear bumper (fixed from the source code, not fitted)
    moving_ms=2.0,
    lane_half_m=1.8,
    lane_outer_m=5.5,
    match_gate=0.25,
)


# ------------------------------------------------------------------ track (image only)

def cmd_track(a):
    from ultralytics import YOLO
    from ultralytics.trackers.byte_tracker import BYTETracker
    from ultralytics.utils import YAML, IterableSimpleNamespace
    from ultralytics.utils.checks import check_yaml
    model = YOLO(str(ROOT / PARAMS["yolo"]))
    frames = D.list_frames(Path(a.frames))
    _, osd = D.static_rows(frames)
    tracker = BYTETracker(IterableSimpleNamespace(**YAML.load(check_yaml(PARAMS["tracker"]))))
    per = {}
    for n, f in enumerate(frames):
        img = D.black_out(cv2.imread(str(f)), osd)
        r = model.predict(img, verbose=False, conf=PARAMS["det_conf"], classes=PARAMS["classes"], device=a.device)[0]
        boxes = r.boxes.cpu().numpy()
        ids = [-1] * len(boxes)
        if len(boxes):
            for t in tracker.update(boxes, img):
                ids[int(t[7])] = int(t[4])
        per[f.stem] = [[*map(float, b), float(s), int(c), i] for b, s, c, i in zip(boxes.xyxy, boxes.conf, boxes.cls, ids)]
        if (n + 1) % 200 == 0:
            print(f"{n + 1}/{len(frames)}", flush=True)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(dict(params=PARAMS, frames_dir=str(a.frames), osd_boxes=osd, frames=per)))
    print("wrote", a.out)


# ------------------------------------------------------------------ measure (no answers)

def ruler_reach(res, pct=PARAMS["reach_pct"]):
    ends = [(x["z_near"] + x["period"]) * res["k"] for x in res["periods"] if x["side"] in res.get("lines_used", [])]
    return float(np.percentile(ends, pct)) if ends else None


def lane_of(box, wd):
    """0 ego, -1 left, +1 right, 2 / -2 further out; None without a line pair."""
    L, R = wd.get("left"), wd.get("right")
    if not (wd.get("vp_row") and L and R):
        return None
    x0, y0, x1, y1 = box[:4]
    cx = (x0 + x1) / 2
    xl, xr = L["a"] * y1 + L["b"], R["a"] * y1 + R["b"]
    if xr - xl <= 1:
        return None
    return int(np.clip(np.floor((cx - xl) / (xr - xl)), -2, 2))


def cmd_measure(a):
    res = json.loads(Path(a.dash).read_text())
    if res.get("status") != "ok":
        print(f"{a.dash}: the dash-scale result was refused ({res.get('reason', '')[:80]}); no distances")
        return
    tr = json.loads(Path(a.tracks).read_text())["frames"]
    frames = D.list_frames(Path(a.frames))
    h, w = cv2.imread(str(frames[0])).shape[:2]
    bonnet = D.static_rows(frames)[0]
    k, fps, step = res["k"], res["fps"], res["step"]
    reach = ruler_reach(res)
    every = max(1, int(round(PARAMS["sample_s"] * fps)))
    cache = Path(a.depth_cache)
    samples = []                                   # (fi, t, [objects])
    for fi in range(0, len(frames), every):
        stem = frames[fi].stem
        wd = D.lines_for(dict(windows=res["windows"]), fi / step)
        objs = []
        cand = [b for b in tr.get(stem, []) if b[6] >= 0 and b[4] >= PARAMS["min_conf"]
                and b[3] < bonnet - PARAMS["bonnet_px"]]
        if cand:
            try:
                depth = D.load_depth(cache, frames[fi])
            except FileNotFoundError:
                depth = None
            if depth is not None:
                dh, dw = depth.shape
                r = PARAMS["patch"] // 2
                for x0, y0, x1, y1, conf, cls, tid in cand:
                    yy = int((y1 - PARAMS["read_up"] * (y1 - y0)) * dh / h)
                    xx = int((x0 + x1) / 2 * dw / w)
                    z = float(np.median(depth[max(0, yy - r): yy + r + 1, max(0, xx - r): xx + r + 1]))
                    d = k * z
                    objs.append(dict(id=int(tid), box=[x0, y0, x1, y1], conf=conf, cls=int(cls),
                                     lane=lane_of((x0, y0, x1, y1), wd), dist=d,
                                     far=bool(reach is None or d > reach)))
        samples.append(dict(fi=fi, t=fi / fps, objects=objs))
    # relative / absolute speed per track, inside the ruler's reach only
    by_id = {}
    for j, s in enumerate(samples):
        for o in s["objects"]:
            by_id.setdefault(o["id"], {})[j] = o
    hw = PARAMS["half_win"]
    for tid, seq in by_id.items():
        for j, o in seq.items():
            grp = [seq.get(i) for i in range(j - hw, j + hw + 1)]
            if o["far"] or any(g is None or g["far"] for g in grp):
                continue
            if any(abs(b["dist"] - a_["dist"]) / a_["dist"] > PARAMS["max_jump"] for a_, b in zip(grp[:-1], grp[1:])):
                continue
            t = np.array([samples[i]["t"] for i in range(j - hw, j + hw + 1)])
            dd = np.array([g["dist"] for g in grp])
            rel = float(np.polyfit(t - t.mean(), dd, 1)[0])
            f0, f1 = samples[j - hw]["fi"], samples[j + hw]["fi"]
            ego = [sp["kmh"] for sp in res["speeds"] if sp["kmh"] is not None and sp["frame_i"] >= f0 and sp["frame_j"] <= f1]
            o["rel_kmh"] = 3.6 * rel
            o["abs_kmh"] = float(np.median(ego)) + 3.6 * rel if len(ego) >= PARAMS["min_ego"] else None
    out = dict(params=PARAMS, dash=str(a.dash), tracks=str(a.tracks), k=k, ruler_reach_m=reach, fps=fps, samples=samples)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out))
    n_obj = sum(len(s["objects"]) for s in samples)
    lanes = {}
    for s in samples:
        for o in s["objects"]:
            lanes[o["lane"]] = lanes.get(o["lane"], 0) + 1
    print(f"wrote {a.out}: k {k:.4f}, ruler reach {reach:.1f} m, {len(samples)} samples, {n_obj} car readings, "
          f"{len(by_id)} tracks, by lane {dict(sorted(lanes.items(), key=lambda x: (x[0] is None, x[0] or 0)))}")


# ------------------------------------------------------------------ score (comma2k19, answers already open)

def cmd_score(a):
    from scipy.optimize import linear_sum_assignment
    cars = json.loads(Path(a.cars).read_text())
    tdir = Path(a.truth)
    can = {int(r["frame_idx"]): float(r["can_speed_ms"]) for r in csv.DictReader(open(tdir / "ego.csv"))}
    radar = {}
    for r in csv.DictReader(open(tdir / "radar.csv")):
        f = int(r["frame_idx"])
        v = float(r["v_rel_ms"])
        if f in can and abs(v + can[f]) > PARAMS["moving_ms"] and float(r["d_rel_m"]) > 0 \
                and abs(float(r["y_rel_m"])) <= PARAMS["lane_outer_m"]:
            radar.setdefault(f, []).append((int(r["track_id"]), float(r["d_rel_m"]), float(r["y_rel_m"]), v))
    off, gate, reach = PARAMS["radar_offset_m"], PARAMS["match_gate"], cars["ruler_reach_m"]

    def rlane(y, sign):
        y = sign * y
        return 0 if abs(y) <= PARAMS["lane_half_m"] else (-1 if y > 0 else 1)

    # the radar's lateral sign: which sign puts the returns near our left-lane cars on the left
    votes = []
    for s in cars["samples"]:
        for o in s["objects"]:
            if o["lane"] in (-1, 1) and not o["far"]:
                near = [y for _, d, y, _ in radar.get(s["fi"], []) if abs(o["dist"] - (d + off)) / (d + off) < 0.10
                        and abs(y) > PARAMS["lane_half_m"]]
                if len(near) == 1:
                    votes.append(np.sign(near[0]) * (-o["lane"]))
    sign = 1.0 if np.mean(votes) >= 0 else -1.0 if votes else 1.0
    agree = float(np.mean(np.array(votes) == sign)) if votes else float("nan")
    pairs, found, total = [], 0, 0
    matched_rid = {}
    for s in cars["samples"]:
        objs = [o for o in s["objects"] if o["lane"] in (-1, 0, 1)]
        rets = [r for r in radar.get(s["fi"], []) if rlane(r[2], sign) in (-1, 0, 1)]
        in_reach = [r for r in rets if r[1] + off <= (reach or 0)]
        total += len(in_reach)
        if not objs or not rets:
            continue
        C = np.full((len(objs), len(rets)), 9.0)
        for i, o in enumerate(objs):
            for jj, (rid, d, y, v) in enumerate(rets):
                if rlane(y, sign) == o["lane"]:
                    C[i, jj] = abs(o["dist"] - (d + off)) / (d + off)
        for i, jj in zip(*linear_sum_assignment(C)):
            if C[i, jj] <= gate:
                rid, d, y, v = rets[jj]
                o = objs[i]
                pairs.append(dict(lane=o["lane"], far=o["far"], err=100 * (o["dist"] - (d + off)) / (d + off),
                                  rel=o.get("rel_kmh"), rel_truth=3.6 * v, id=o["id"], rid=rid, t=s["t"]))
                if rets[jj] in in_reach:
                    found += 1
                matched_rid.setdefault(o["id"], []).append(rid)
    print(f"radar lateral sign {sign:+.0f} (agreement {agree:.0%} over {len(votes)} votes); ruler reach {reach:.1f} m")
    print(f"radar cars in the three lanes inside the ruler's reach: {total}; matched to one of our boxes: {found} ({found / max(1, total):.0%})")
    for lab, sel in (("ego lane, inside reach", lambda p: p["lane"] == 0 and not p["far"]),
                     ("side lanes, inside reach", lambda p: p["lane"] != 0 and not p["far"]),
                     ("any lane, beyond reach", lambda p: p["far"])):
        e = np.array([p["err"] for p in pairs if sel(p)])
        if len(e):
            print(f"  distance {lab:<26} n {len(e):4d}  median |err| {np.median(np.abs(e)):4.1f}%  bias {np.median(e):+5.1f}%")
    r = [(p["rel"] - p["rel_truth"], p["rel_truth"]) for p in pairs if p["rel"] is not None]
    if r:
        r = np.array(r)
        print(f"  relative speed (inside reach) n {len(r)}  MAE {np.mean(np.abs(r[:, 0])):.2f} km/h  (guess 0: {np.mean(np.abs(r[:, 1])):.2f})")
    sw = sum(sum(1 for x, y in zip(v[:-1], v[1:]) if x != y) for v in matched_rid.values())
    frag = {}
    for tid, v in matched_rid.items():
        for rid in set(v):
            frag.setdefault(rid, set()).add(tid)
    print(f"  tracking: {len(matched_rid)} of our tracks matched; id switches (our track moving to another radar car) {sw}; "
          f"radar cars seen under more than one of our ids {sum(len(v) > 1 for v in frag.values())} of {len(frag)}")


# ------------------------------------------------------------------ score, Argoverse 2 (answers already open)

AV2_OPEN = {"c865c156", "cf5aaa11", "dc9077b9", "f668074d"}     # development logs; the four sealed ones stay closed


def av2_cuboids(log_dir: Path, stems):
    """Per frame stem: vehicle cuboids projected into the front camera (lidar annotations, track uuid) with
    the forward distance from the camera to the cuboid's nearest face. Refuses a log whose annotations are
    not on disk: this never downloads anything."""
    import pandas as pd
    import av2_eval as E
    ann_p = log_dir / "annotations.feather"
    if log_dir.name[:8] not in AV2_OPEN or not ann_p.exists():
        raise SystemExit(f"{log_dir.name}: not an open development log with annotations on disk; refusing")
    meta = json.loads((log_dir / "pinhole_meta.json").read_text())
    ann = pd.read_feather(ann_p)
    ann = ann[ann.category.isin({"REGULAR_VEHICLE", "LARGE_VEHICLE", "BUS", "BOX_TRUCK", "TRUCK", "SCHOOL_BUS",
                                 "ARTICULATED_BUS", "TRUCK_CAB", "VEHICULAR_TRAILER"})]
    poses = pd.read_feather(log_dir / "city_SE3_egovehicle.feather").drop_duplicates("timestamp_ns")
    poses = poses.sort_values("timestamp_ns").reset_index(drop=True)
    ptime = poses.timestamp_ns.values
    extr = pd.read_feather(log_dir / "calibration/egovehicle_SE3_sensor.feather")
    extr = extr[extr.sensor_name == "ring_front_center"].iloc[0]
    cam_T_ego = np.linalg.inv(E.SE3((extr.qw, extr.qx, extr.qy, extr.qz), (extr.tx_m, extr.ty_m, extr.tz_m)))
    K = np.array([[meta["fx"], 0, meta["cx"]], [0, meta["fy"], meta["cy"]], [0, 0, 1]])
    fr = pd.read_csv(log_dir / "pinhole_frames.csv")
    ts_of = dict(zip(fr.frame_idx.astype(str), fr.timestamp_ns))
    ann_ts = np.unique(ann.timestamp_ns.values)

    def pose_at(ts):
        r = poses.iloc[int(np.argmin(np.abs(ptime - ts)))]
        return E.SE3((r.qw, r.qx, r.qy, r.qz), (r.tx_m, r.ty_m, r.tz_m))
    out = {}
    for stem in stems:
        ts = ts_of.get(stem)
        cubs = []
        if ts is not None:
            ats = int(ann_ts[np.argmin(np.abs(ann_ts - ts))])
            if abs(ats - ts) <= 60e6:
                M = np.linalg.inv(pose_at(ts)) @ pose_at(ats)
                for _, a in ann[ann.timestamp_ns == ats].iterrows():
                    C = np.c_[E.corners(a), np.ones(8)].T
                    Ce = (M @ C).T[:, :3]
                    Ch = (cam_T_ego @ M @ C).T[:, :3]
                    if (Ch[:, 2] <= 0.5).any():
                        continue
                    uv = (K @ Ch.T).T
                    uv = uv[:, :2] / uv[:, 2:3]
                    cubs.append(dict(box=[float(uv[:, 0].min()), float(uv[:, 1].min()), float(uv[:, 0].max()), float(uv[:, 1].max())],
                                     gt=float(Ce[:, 0].min()) - float(extr.tx_m), uuid=str(a.track_uuid)))
        out[stem] = cubs
    return out, int(meta.get("width", 0) or 0), int(meta.get("height", 0) or 0)


def _iou(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - ix * iy
    return ix * iy / u if u > 0 else 0.0


def cmd_score_av2(a):
    """Every frame: our tracked boxes vs projected lidar cuboids (clipped to the image), Hungarian on IoU >= 0.5.
    "wrong car": one of our ids matched to cuboid A and later to cuboid B; "restart": one cuboid matched to one
    of our ids and later to another. With --cars also the distance of matched boxes (radar-free: lidar), the
    offset fixed in advance at +0.8 m (tyre contact vs the cuboid's rear face)."""
    from scipy.optimize import linear_sum_assignment
    tr = json.loads(Path(a.tracks).read_text())
    log_dir = next(Path(ROOT / "data/input/av2").glob(Path(tr["frames_dir"]).parent.name[:8] + "*"))
    frames = D.list_frames(Path(tr["frames_dir"]))
    h, w = cv2.imread(str(frames[0])).shape[:2]
    bonnet = D.static_rows(frames)[0]
    gt, _, _ = av2_cuboids(log_dir, [f.stem for f in frames])
    clip = lambda b: [max(0.0, b[0]), max(0.0, b[1]), min(float(w), b[2]), min(float(h), b[3])]
    seq_by_ours, seq_by_gt, n_match, n_gt = {}, {}, 0, 0
    match_at = {}
    for j, f in enumerate(frames):
        ours = [b for b in tr["frames"].get(f.stem, []) if b[6] >= 0 and b[4] >= PARAMS["min_conf"] and b[3] < bonnet - PARAMS["bonnet_px"]]
        cubs = [c for c in gt.get(f.stem, []) if c["gt"] <= a.max_range]
        cb = [clip(c["box"]) for c in cubs]
        keep = [i for i, b in enumerate(cb) if (b[2] - b[0]) * (b[3] - b[1]) >= 400]
        n_gt += len(keep)
        if not ours or not keep:
            continue
        C = np.array([[1 - _iou(o[:4], cb[i]) for i in keep] for o in ours])
        for oi, kj in zip(*linear_sum_assignment(C)):
            if C[oi, kj] <= 0.5:
                o, c = ours[oi], cubs[keep[kj]]
                n_match += 1
                seq_by_ours.setdefault(o[6], []).append((j, c["uuid"]))
                seq_by_gt.setdefault(c["uuid"], []).append((j, o[6]))
                match_at[(f.stem, o[6])] = c
    wrong = sum(sum(1 for (_, x), (_, y) in zip(v[:-1], v[1:]) if x != y) for v in seq_by_ours.values())
    restart = sum(sum(1 for (_, x), (_, y) in zip(v[:-1], v[1:]) if x != y) for v in seq_by_gt.values())
    tracks_wrong = sum(any(x != y for (_, x), (_, y) in zip(v[:-1], v[1:])) for v in seq_by_ours.values())
    print(f"{log_dir.name[:8]}: frames {len(frames)}, visible cuboids <= {a.max_range:.0f} m: {n_gt}, matched boxes {n_match} "
          f"({n_match / max(1, n_gt):.0%}); our tracks matched {len(seq_by_ours)}, cars matched {len(seq_by_gt)}")
    print(f"   wrong car (our id moves to another car): {wrong} times, in {tracks_wrong} of {len(seq_by_ours)} tracks "
          f"= {wrong / max(1, n_match) * 100:.2f} per 100 matched boxes")
    print(f"   restart (a car gets a new id of ours): {restart} times over {len(seq_by_gt)} cars")
    if a.cars and not Path(a.cars).exists():
        print("   distance: no measurement (dash-scale refused on this log)")
    elif a.cars:
        cars = json.loads(Path(a.cars).read_text())
        stem_of = {fi: frames[fi].stem for fi in range(len(frames))}
        e = {"ego lane, inside reach": [], "side lanes, inside reach": [], "beyond reach": []}
        for s in cars["samples"]:
            for o in s["objects"]:
                c = match_at.get((stem_of[s["fi"]], o["id"]))
                if c is None or o["lane"] not in (-1, 0, 1):
                    continue
                err = 100 * (o["dist"] - (c["gt"] + 0.8)) / (c["gt"] + 0.8)
                e["beyond reach" if o["far"] else ("ego lane, inside reach" if o["lane"] == 0 else "side lanes, inside reach")].append(err)
        for lab, v in e.items():
            if v:
                v = np.array(v)
                print(f"   distance {lab:<26} n {len(v):4d}  median |err| {np.median(np.abs(v)):4.1f}%  bias {np.median(v):+5.1f}%")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("track")
    t.add_argument("--frames", required=True)
    t.add_argument("--out", required=True)
    t.add_argument("--device", default="0")
    m = sub.add_parser("measure")
    for x in ("--frames", "--tracks", "--dash", "--depth-cache", "--out"):
        m.add_argument(x, required=True)
    s = sub.add_parser("score")
    s.add_argument("--cars", required=True)
    s.add_argument("--truth", required=True)
    v = sub.add_parser("score-av2")
    v.add_argument("--tracks", required=True)
    v.add_argument("--cars", default=None)
    v.add_argument("--max-range", type=float, default=60.0)
    a = ap.parse_args()
    dict(track=cmd_track, measure=cmd_measure, score=cmd_score)[a.cmd](a) if a.cmd != "score-av2" else cmd_score_av2(a)


if __name__ == "__main__":
    main()
