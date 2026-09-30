#!/usr/bin/env python3
"""Lead-car relative and absolute speed from the dash-scaled depth model, scored against
the factory radar of comma2k19 -- pre-registered in docs/DEPTH_DASH_RELSPEED_PREREG.md.

Three steps, run in this order:

  detect   YOLO on every sampled frame (the frames that have a cached depth map). No radar.
  predict  front car per frame (ego-lane lines from the SEALED dash-scale result), distance
           = k * depth reading, image-only continuity, 5-sample least-squares slope. No radar.
           Seal the output with seal_predictions.py before scoring.
  score    verifies the seal, then reads the radar and CAN for the first time.

  P=~/venvs/depthbench/bin/python
  $P tools/depth_dash_relspeed.py detect
  $P tools/depth_dash_relspeed.py predict --model da3_metric
  $P tools/seal_predictions.py --files "data/output/dash_scale/relspeed/da3_metric/c2k19_*.json" \\
      --also data/output/dash_scale/relspeed/dets_c2k19_seg10.json data/output/dash_scale/relspeed/dets_c2k19_seg21.json \\
      --out data/output/dash_scale/relspeed/da3_metric/seal.json
  $P tools/depth_dash_relspeed.py score --model da3_metric

Only cv2, numpy, ultralytics and depth_dash_scale (Terry) are used for the method; nothing
from the odometer / radar-eval code.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import depth_dash_scale as D  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DS = ROOT / "data/output/dash_scale"
OUT = DS / "relspeed"
KEYS = {"c2k19_seg10": "b0c9d2329ad1606b_2018-07-30--13-44-30_10",
        "c2k19_seg21": "b0c9d2329ad1606b_2018-08-15--09-01-03_21"}

# Fixed before any prediction was made (docs/DEPTH_DASH_RELSPEED_PREREG.md section 3).
PARAMS = dict(
    yolo="checkpoints/yolov8m-seg.pt",
    conf=0.4,
    classes=[2, 5, 7],       # car, bus, truck
    lane_fallback=[0.3, 0.7],  # no ego-lane lines in the window -> this band of the width
    contact_up=0.06,         # contact pixel = box bottom - this * box height
    patch=5,                 # depth median over patch x patch (half-res map)
    min_iou=0.3,             # same car between neighbouring samples ...
    max_jump=0.15,           # ... and distance change at most this fraction
    half_win=2,              # window = centre +/- this many samples (5 samples)
    min_ego=3,               # ego readings inside the window needed for an absolute speed
    near_m=32.0,             # scoring: near field by radar range
    lane_half_m=1.8,         # scoring: in-lane radar return
    agree=0.25,              # scoring, secondary: our distance within this of the radar
)


def final_dir(model: str) -> Path:
    return DS / ("final" if model == "da3_metric" else f"final_{model}")


def sha(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def sealed_result(model: str, key: str) -> tuple[dict, dict]:
    """The dash-scale result and its manifest entry, refusing anything that is not sealed."""
    fd = final_dir(model)
    seal = json.loads((fd / "seal.json").read_text())
    fp = fd / f"{key}.json"
    if sha(fp) != seal["files"].get(fp.name):
        sys.exit(f"{fp} is not the sealed version")
    item = next(i for i in json.loads((fd / "manifest.json").read_text()) if i["key"] == key)
    return json.loads(fp.read_text()), item


# ------------------------------------------------------------------ detect

def cmd_detect(args):
    from ultralytics import YOLO
    model = YOLO(str(ROOT / PARAMS["yolo"]))
    OUT.mkdir(parents=True, exist_ok=True)
    for key in args.keys:
        res, item = sealed_result("da3_metric", key)
        frames = D.list_frames(Path(item["frames"]))
        _, osd = D.static_rows(frames)
        idx = list(range(0, len(frames), res["step"]))
        dets = {}
        for n, fi in enumerate(idx):
            img = D.black_out(cv2.imread(str(frames[fi])), osd)
            r = model.predict(img, verbose=False, conf=PARAMS["conf"], device=args.device)[0]
            boxes = []
            if r.boxes is not None:
                for b, c, s in zip(r.boxes.xyxy.cpu().numpy(), r.boxes.cls.cpu().numpy(),
                                   r.boxes.conf.cpu().numpy()):
                    if int(c) in PARAMS["classes"]:
                        boxes.append([*map(float, b), float(s), int(c)])
            dets[frames[fi].stem] = boxes
            if (n + 1) % 50 == 0:
                print(f"{key}: {n + 1}/{len(idx)}", flush=True)
        (OUT / f"dets_{key}.json").write_text(json.dumps(dict(key=key, frames_dir=item["frames"],
                                                              step=res["step"], params=PARAMS, dets=dets)))
        print("wrote", OUT / f"dets_{key}.json")


# ------------------------------------------------------------------ predict

def ego_lines(res, j):
    """Ego-lane lines of the window nearest sample j, under the demo's condition."""
    wd = D.lines_for(dict(windows=res["windows"]), j)
    return {s: wd[s] for s in ("left", "right")
            if wd.get(s) and wd.get("vp_row") and s in res.get("lines_used", [])}


def lane_edges(res, j):
    """Both tracked ego-lane lines of the window nearest sample j, whether or not they set k (the
    demo's rule, 2026-09-30); empty unless both are there and their crossing row passed its gate.
    Used by `predict --require-lanes`. ego_lines keeps only the lines that set k, so a clip whose k
    came from one line would never get a front car under that flag."""
    wd = D.lines_for(dict(windows=res["windows"]), j)
    geo = {s: wd[s] for s in ("left", "right") if wd.get(s)} if wd.get("vp_row") else {}
    return geo if len(geo) == 2 else {}


def front_car(boxes, lines, w, bonnet_row=None):
    """Nearest box whose bottom centre lies between the ego-lane lines (demo definition).

    Added 2026-09-30, after the sealed 9/29 run: a box whose bottom is on our own bonnet is
    our own bonnet (YOLO labels it "car" on comma2k19; seg10 had it as the front car in 105
    of 295 samples). bonnet_row is the top of the never-changing rows (D.static_rows), so no
    answer is involved. None keeps the sealed behaviour.
    """
    best = None
    for x0, y0, x1, y1, _, _ in boxes:
        if bonnet_row is not None and y1 >= bonnet_row - 2:
            continue
        cx, cy = (x0 + x1) / 2, y1
        L, R = lines.get("left"), lines.get("right")
        lo = L["a"] * cy + L["b"] if L else PARAMS["lane_fallback"][0] * w
        hi = R["a"] * cy + R["b"] if R else PARAMS["lane_fallback"][1] * w
        if lo < cx < hi and (best is None or cy > best[3]):
            best = (x0, y0, x1, y1)
    return best


def iou(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def cmd_predict(args):
    od = OUT / args.model
    od.mkdir(parents=True, exist_ok=True)
    for key in args.keys:
        res, item = sealed_result(args.model, key)
        base = dict(key=key, model=args.model, params=PARAMS, k=res.get("k"), status=res["status"],
                    fps=res["fps"], step=res["step"])
        if res["status"] != "ok":
            (od / f"{key}.json").write_text(json.dumps(dict(base, samples=[], windows=[]), indent=1))
            print(f"{key}: dash-scale refused -> no readings")
            continue
        dets = json.loads((OUT / f"dets_{key}.json").read_text())
        frames = D.list_frames(Path(item["frames"]))
        h, w = cv2.imread(str(frames[0])).shape[:2]
        bonnet = D.static_rows(frames)[0] if args.bonnet else None
        k, fps, step = res["k"], res["fps"], res["step"]
        idx = list(range(0, len(frames), step))
        cache = Path(item["depth_cache"])
        samples = []
        for j, fi in enumerate(idx):
            if args.require_lanes:
                lanes = lane_edges(res, j)
                car = front_car(dets["dets"].get(frames[fi].stem, []), lanes, w, bonnet) if lanes else None
            else:
                car = front_car(dets["dets"].get(frames[fi].stem, []), ego_lines(res, j), w, bonnet)
            s = dict(j=j, frame_i=fi, t=fi / fps, box=None, dist=None)
            if car is not None:
                try:
                    depth = D.load_depth(cache, frames[fi])
                except FileNotFoundError:
                    depth = None
                if depth is not None:
                    x0, y0, x1, y1 = car
                    cx, yb = (x0 + x1) / 2, y1 - PARAMS["contact_up"] * (y1 - y0)
                    dh, dw = depth.shape
                    yy, xx, r = int(yb * dh / h), int(cx * dw / w), PARAMS["patch"] // 2
                    z = float(np.median(depth[max(0, yy - r): yy + r + 1, max(0, xx - r): xx + r + 1]))
                    s.update(box=[x0, y0, x1, y1], px=cx, py=yb, z_model=z, dist=k * z)
            samples.append(s)
        # image-only continuity
        run = -1
        for a, b in zip([None] + samples[:-1], samples):
            if b["dist"] is None:
                b["run"] = None
                continue
            same = (a is not None and a["dist"] is not None and iou(a["box"], b["box"]) >= PARAMS["min_iou"]
                    and abs(b["dist"] - a["dist"]) / a["dist"] <= PARAMS["max_jump"])
            run = run if same else run + 1
            b["run"] = run
        hw = PARAMS["half_win"]
        wins = []
        for j in range(hw, len(samples) - hw):
            grp = samples[j - hw: j + hw + 1]
            if any(g["run"] is None or g["run"] != samples[j]["run"] for g in grp):
                continue
            t = np.array([g["t"] for g in grp])
            d = np.array([g["dist"] for g in grp])
            rel = float(np.polyfit(t - t.mean(), d, 1)[0])
            f0, f1 = grp[0]["frame_i"], grp[-1]["frame_i"]
            ego = [sp["kmh"] for sp in res["speeds"]
                   if sp["kmh"] is not None and sp["frame_i"] >= f0 and sp["frame_j"] <= f1]
            ego_kmh = float(np.median(ego)) if len(ego) >= PARAMS["min_ego"] else None
            wins.append(dict(frame_i=samples[j]["frame_i"], frames=[g["frame_i"] for g in grp],
                             t=samples[j]["t"], run=samples[j]["run"], dist=float(d.mean()),
                             rel_ms=rel, n_ego=len(ego), ego_kmh=ego_kmh,
                             abs_kmh=None if ego_kmh is None else ego_kmh + 3.6 * rel))
        (od / f"{key}.json").write_text(json.dumps(dict(base, samples=samples, windows=wins), indent=1))
        n_car = sum(s["dist"] is not None for s in samples)
        print(f"{key}: k {k:.3f}  samples {len(samples)}  with front car {n_car}  "
              f"runs {run + 1}  windows {len(wins)}  with abs {sum(x['abs_kmh'] is not None for x in wins)}")


# ------------------------------------------------------------------ score

def verify_seal(od: Path):
    seal = json.loads((od / "seal.json").read_text())
    preds = {p.name for p in od.glob("c2k19_*.json")}
    if preds - set(seal["files"]):
        sys.exit(f"prediction files not in the seal: {sorted(preds - set(seal['files']))}")
    for name, hsh in seal["files"].items():
        if sha(od / name) != hsh:
            sys.exit(f"{name} changed after sealing")
    for name, hsh in seal.get("inputs", {}).items():       # the detection caches
        if (OUT / name).exists() and sha(OUT / name) != hsh:
            sys.exit(f"{name} changed after sealing")
    return seal


def stats(e):
    e = np.asarray(e, float)
    if not len(e):
        return dict(n=0)
    a = np.abs(e)
    return dict(n=int(len(e)), mae=round(float(a.mean()), 2), bias=round(float(e.mean()), 2),
                med_abs=round(float(np.median(a)), 2), p90=round(float(np.percentile(a, 90)), 2),
                within_3=round(float((a <= 3).mean()), 3))


# 2026-09-30, independent route: the truth is read by tools/c2k19_extract.py instead of the radar files an earlier
# export produced; lanes from the 12 ft (3.66 m) US freeway lane; the radar offset is fixed in advance, never fitted:
# ranges start at the front of the car (openpilot v0.5.7 radar_interface), the camera 1.52 m behind the radar, the
# depth read where the car meets the road, 0.85 m ahead of its rear face (measured on the open AV2 logs, see
# depth_dash_multicar.PARAMS["av2_offset_m"]). The 2026-09-29 scoring files are kept.
TRUTH = ROOT / "data/output/c2k19_truth"
SCORE_2 = dict(lane_half_m=3.66 / 2, radar_offset_m=2.37)


def radar_in_lane(tag):
    """Per 0-based frame: the nearest radar return within half a legal lane, with the CAN speed (km/h)."""
    can = {int(r["frame_idx"]): 3.6 * float(r["can_speed_ms"]) for r in csv.DictReader(open(TRUTH / tag / "ego.csv"))}
    best = {}
    for r in csv.DictReader(open(TRUTH / tag / "radar.csv")):
        f, rng = int(r["frame_idx"]), float(r["d_rel_m"])
        if abs(float(r["y_rel_m"])) > SCORE_2["lane_half_m"] or rng <= 0 or f not in can:
            continue
        if f not in best or rng < best[f]["range"]:
            best[f] = dict(range=rng, slot=r["track_id"], rel=float(r["v_rel_ms"]), can=can[f])
    return best


def cmd_score(args):
    od = OUT / args.model
    seal = verify_seal(od)
    out = dict(model=args.model, sealed_utc=seal["sealed_utc"], sealed_commit=seal["git_commit"], clips={})
    rows = []
    for key, tag in KEYS.items():
        fp = od / f"{key}.json"
        if not fp.exists():
            continue
        pred = json.loads(fp.read_text())
        radar = radar_in_lane(tag)
        dash, _ = sealed_result(args.model, key)
        ends = [(x["z_near"] + x["period"]) * dash["k"] for x in dash.get("periods", []) if x["side"] in dash.get("lines_used", [])]
        reach = float(np.percentile(ends, 95)) if ends else float("nan")
        step, hw = pred["step"], PARAMS["half_win"]
        ours = {w["frame_i"]: w for w in pred["windows"]}
        n_frames = max(radar) + 1 if radar else 0
        truth_windows = 0
        for c in range(hw * step, n_frames - hw * step, step):
            fr = [c + o * step for o in range(-hw, hw + 1)]
            if any(f not in radar for f in fr) or len({radar[f]["slot"] for f in fr}) != 1:
                continue
            truth_windows += 1
            rel_t = float(np.mean([radar[f]["rel"] for f in fr]))
            can = float(np.mean([radar[f]["can"] for f in fr]))
            rng = float(np.mean([radar[f]["range"] for f in fr]))
            w = ours.get(c)
            truth_d = rng + SCORE_2["radar_offset_m"]
            row = dict(key=key, frame_i=c, radar_range=rng, radar_rel_ms=rel_t, can_kmh=can,
                       near=rng < PARAMS["near_m"], has=w is not None, ruler_reach_m=reach)
            if w is not None:
                row.update(dist=w["dist"], rel_ms=w["rel_ms"], ego_kmh=w["ego_kmh"], abs_kmh=w["abs_kmh"],
                           agree=abs(w["dist"] - truth_d) / truth_d <= PARAMS["agree"],
                           e_dist_pct=100 * (w["dist"] - truth_d) / truth_d, inside_reach=w["dist"] <= reach,
                           e_rel=3.6 * (w["rel_ms"] - rel_t), e_zero=3.6 * (0.0 - rel_t),
                           e_ego=None if w["ego_kmh"] is None else w["ego_kmh"] - can,
                           e_abs=None if w["abs_kmh"] is None else w["abs_kmh"] - (can + 3.6 * rel_t))
            rows.append(row)
        out["clips"][key] = dict(status=pred["status"], k=pred["k"], truth_windows=truth_windows,
                                 ours_windows=len(pred["windows"]),
                                 covered=sum(1 for r in rows if r["key"] == key and r["has"]))

    def block(sel):
        h = [r for r in sel if r["has"]]
        ab = [r for r in h if r["e_abs"] is not None]
        b = dict(truth_windows=len(sel), with_reading=len(h),
                 coverage=round(len(h) / len(sel), 3) if sel else None,
                 dist_pct=stats([r["e_dist_pct"] for r in h]),
                 rel=stats([r["e_rel"] for r in h]), rel_zero_baseline=stats([r["e_zero"] for r in h]),
                 abs=stats([r["e_abs"] for r in ab]), ego_term=stats([r["e_ego"] for r in ab]))
        if len(h) >= 3:
            b["rel_corr"] = round(float(np.corrcoef([r["rel_ms"] for r in h], [r["radar_rel_ms"] for r in h])[0, 1]), 3)
            b["truth_rel_abs_median_kmh"] = round(float(np.median([abs(3.6 * r["radar_rel_ms"]) for r in h])), 2)
        return b

    out["scoring"] = dict(truth="tools/c2k19_extract.py", **SCORE_2,
                          note="2026-09-30 re-score of the 2026-09-29 sealed predictions; near/far as registered (radar "
                               "range < 32 m); inside/beyond the ruler's reach added (95th percentile of the cycle ends)")
    for name, f in (("all", lambda r: True), ("near", lambda r: r["near"]), ("far", lambda r: not r["near"]),
                    ("inside_reach", lambda r: r["has"] and r["inside_reach"]),
                    ("beyond_reach", lambda r: r["has"] and not r["inside_reach"])):
        sel = [r for r in rows if f(r)]
        out[name] = block(sel)
        ag = [r for r in sel if r["has"] and r["agree"]]
        out[name]["agree_subset"] = dict(kept=len(ag), of=sum(r["has"] for r in sel),
                                         rel=stats([r["e_rel"] for r in ag]),
                                         abs=stats([r["e_abs"] for r in ag if r["e_abs"] is not None]))
    for key in out["clips"]:
        out["clips"][key]["near"] = block([r for r in rows if r["key"] == key and r["near"]])
    (od / "score_own_truth_20260930.json").write_text(json.dumps(out, indent=1))
    with open(od / "windows_scored_own_truth_20260930.csv", "w", newline="") as f:
        cols = sorted({c for r in rows for c in r})
        wr = csv.DictWriter(f, fieldnames=cols)
        wr.writeheader()
        wr.writerows(rows)
    print(json.dumps(out, indent=1))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("detect")
    d.add_argument("--device", default="cpu", help="cpu keeps the GPU free for a running batch")
    for p in (d, sub.add_parser("predict"), sub.add_parser("score")):
        p.add_argument("--keys", nargs="+", default=list(KEYS))
        if p is not d:
            p.add_argument("--model", default="da3_metric")
        if p.prog.endswith("predict"):
            p.add_argument("--bonnet", action="store_true",
                           help="skip boxes whose bottom lies on our own bonnet (added after the 9/29 seal)")
            p.add_argument("--require-lanes", action="store_true",
                           help="no front car unless both ego-lane lines are found; without it the 30-70 %% width "
                                "fallback can pick a car in the next lane (added after the 9/29 seal)")
    args = ap.parse_args()
    dict(detect=cmd_detect, predict=cmd_predict, score=cmd_score)[args.cmd](args)


if __name__ == "__main__":
    main()
