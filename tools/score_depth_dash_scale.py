#!/usr/bin/env python3
"""Score the sealed depth_dash_scale results against the answers -- run only after sealing.

Definitions are the ones pre-registered in docs/DEPTH_DASH_SCALE_PREREG.md section 5.
The script refuses to run if any result file differs from its sealed hash, or if a result
file exists that the seal does not list.

  python3 tools/score_depth_dash_scale.py
"""
from __future__ import annotations

import csv
import glob
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parents[1]
FINAL = ROOT / "data/output/dash_scale/final"
MODEL = "da3_metric"
IN = ROOT / "data/input"
BENCH = ROOT / "data/output/depth_benchmark"
NEAR_M = 32.0


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def verify_seal():
    seal = json.loads((FINAL / "seal.json").read_text())
    files = {p.name for p in FINAL.glob("*.json") if p.name not in ("seal.json", "manifest.json", "score.json")}
    unlisted = files - set(seal["files"])
    if unlisted:
        sys.exit(f"result files not in the seal: {sorted(unlisted)}")
    for name, h in seal["files"].items():
        if sha(FINAL / name) != h:
            sys.exit(f"{name} changed after sealing")
    return seal


# ------------------------------------------------------------------ Haisheng ego speed

def truth_xlsx(item) -> list[str]:
    key = item["key"]
    if key.startswith("hs1230car_"):
        case = key.split("_")[1]
        return glob.glob(str(IN / f"海盛_20251230/汽車行車紀錄器 - 人工標註/{case}_*/*_manual.xlsx"))
    folder = Path(item["video"]).parent            # 人工畫格法 folder / motorcycle case folder
    return sorted(glob.glob(str(folder / "*.xlsx")))


def seg_speed(res, a1, b1):
    """Our mean speed over original frames a1..b1 (1-based, inclusive), or None."""
    st = res.get("stride", 1)
    pairs = [s for s in res.get("speeds", []) if s["frame_i"] * st >= a1 - 1 and s["frame_j"] * st <= b1 - 1]
    got = [s["kmh"] for s in pairs if s["kmh"] is not None]
    if not pairs or len(got) < 0.5 * len(pairs):
        return None, len(pairs), len(got)
    return float(np.mean(got)), len(pairs), len(got)


def score_haisheng(manifest, rows_out):
    from haisheng_manual_truth import parse
    per_set = {}
    for it in manifest:
        if not it["set"].startswith("hs") or not (FINAL / f"{it['key']}.json").exists():
            continue
        res = json.loads((FINAL / f"{it['key']}.json").read_text())
        xl = truth_xlsx(it)
        entry = dict(key=it["key"], status=res["status"], k=res.get("k"), truth_files=len(xl))
        if len(xl) != 1:
            entry["note"] = f"{len(xl)} truth files found, not scored"
            per_set.setdefault(it["set"], []).append(entry)
            continue
        try:
            fps_x, segs, bad = parse(xl[0])
        except Exception as e:                     # a report in another layout
            entry["note"] = f"report not parsed: {type(e).__name__}"
            per_set.setdefault(it["set"], []).append(entry)
            continue
        entry.update(report_fps=fps_x, source_fps=res.get("source_fps"), n_segs=len(segs), self_check_fail=len(bad))
        for sg in segs:
            ours, npair, ngot = seg_speed(res, sg["f_start"], sg["f_end"])
            rows_out.append(dict(set=it["set"], key=it["key"], seg=sg["seg"], f_start=sg["f_start"],
                                 f_end=sg["f_end"], truth_kmh=sg["speed_kmh"],
                                 ours_kmh=None if ours is None else round(ours, 2),
                                 diff_kmh=None if ours is None else round(ours - sg["speed_kmh"], 2),
                                 pairs=npair, readings=ngot))
        per_set.setdefault(it["set"], []).append(entry)
    return per_set


def summarize(rows):
    d = np.array([r["diff_kmh"] for r in rows if r["diff_kmh"] is not None])
    out = dict(segments=len(rows), with_reading=int(len(d)))
    if len(d):
        out.update(mae=float(np.mean(np.abs(d))), bias=float(np.mean(d)),
                   within_3=float(np.mean(np.abs(d) <= 3)), p90=float(np.percentile(np.abs(d), 90)))
    return out


# ------------------------------------------------------------------ comma2k19 distance

C2K = {"c2k19_seg10": "b0c9d2329ad1606b_2018-07-30--13-44-30_10",
       "c2k19_seg21": "b0c9d2329ad1606b_2018-08-15--09-01-03_21"}


def score_c2k19():
    out = {}
    for key, tag in C2K.items():
        rp = FINAL / f"{key}.json"
        if not rp.exists():
            continue
        res = json.loads(rp.read_text())
        e = dict(status=res["status"], k=res.get("k"))
        if res["status"] == "ok":
            keep = {r["frame_idx"] for r in csv.DictReader(open(BENCH / f"paired_{tag}.csv"))}
            rows = [r for r in csv.DictReader(open(BENCH / f"unf_{tag}__{MODEL}.csv")) if r["frame_idx"] in keep]
            pred = np.array([float(r["pred"]) for r in rows])
            gt = np.array([float(r["radar_range_m"]) for r in rows])
            n = gt < NEAR_M
            e.update(n_near=int(n.sum()),
                     raw_pct=float(np.median(np.abs(pred[n] - gt[n]) / gt[n]) * 100),
                     scaled_pct=float(np.median(np.abs(res["k"] * pred[n] - gt[n]) / gt[n]) * 100),
                     radar_k=float(np.median(gt[n] / pred[n])))
            # ego speed vs CAN at the paired frames (NOT blind: one CAN value was seen during development)
            can = {int(r["frame_idx"].lstrip("f")) - 1: float(r["can_ego_kmh"])
                   for r in csv.DictReader(open(BENCH / f"paired_{tag}.csv"))}
            d = []
            for s in res.get("speeds", []):
                if s["kmh"] is None:
                    continue
                mid = (s["frame_i"] + s["frame_j"]) / 2
                near = [f for f in can if abs(f - mid) <= 2]
                if near:
                    d.append(s["kmh"] - can[min(near, key=lambda f: abs(f - mid))])
            if d:
                d = np.array(d)
                e.update(ego_vs_can=dict(n=len(d), mae=float(np.mean(np.abs(d))), bias=float(np.mean(d)),
                                         note="not blind: one CAN value was seen during development"))
        out[key] = e
    return out


# ------------------------------------------------------------------ Argoverse 2 distance

def score_av2():
    out = {}
    for fp in sorted((ROOT / "data/output/av2_depth").glob("eval_*_rows.csv")):
        log = fp.name.split("_")[1]
        key = f"av2_{log[:8]}"
        rp = FINAL / f"{key}.json"
        if not rp.exists():
            continue
        res = json.loads(rp.read_text())
        e = dict(status=res["status"], k=res.get("k"))
        rows = list(csv.DictReader(open(fp)))
        gt = np.array([float(r["gt_m"]) for r in rows])
        if MODEL in rows[0]:
            pred = np.array([float(r[MODEL]) if r[MODEL] not in ("", "nan") else np.nan for r in rows])
        else:                                      # model read at the same target pixels, run separately
            pp = ROOT / f"data/output/av2_depth/pred_{log}__{MODEL}.csv"
            if not pp.exists():
                out[key] = dict(status=res["status"], k=res.get("k"), note=f"no {MODEL} readings at the targets")
                continue
            got = {(r["frame_idx"], r["px"], r["py"]): float(r["pred"]) for r in csv.DictReader(open(pp))}
            pred = np.array([got.get((r["frame_idx"], r["px"], r["py"]), np.nan) for r in rows])
        n = (gt < NEAR_M) & np.isfinite(pred)
        e.update(n_near=int(n.sum()), raw_pct=float(np.median(np.abs(pred[n] - gt[n]) / gt[n]) * 100),
                 truth_k=float(np.median(gt[n] / pred[n])))
        if res["status"] == "ok":
            e["scaled_pct"] = float(np.median(np.abs(res["k"] * pred[n] - gt[n]) / gt[n]) * 100)
        out[key] = e
    return out


def main():
    global FINAL, MODEL
    import argparse
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default="da3_metric")
    ap.add_argument("--final-dir", default="", help="results dir (default: final, or final_<model>)")
    args = ap.parse_args()
    MODEL = args.model
    if args.final_dir:
        FINAL = Path(args.final_dir)
    elif MODEL != "da3_metric":
        FINAL = FINAL.parent / f"final_{MODEL}"
    seal = verify_seal()
    manifest = json.loads((FINAL / "manifest.json").read_text())
    rows = []
    hs = score_haisheng(manifest, rows)
    with open(FINAL / "haisheng_segments.csv", "w", newline="", encoding="utf-8") as f:
        if rows:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
    score = dict(sealed_utc=seal["sealed_utc"], sealed_commit=seal["git_commit"],
                 haisheng={s: dict(clips=v, **summarize([r for r in rows if r["set"] == s])) for s, v in hs.items()},
                 haisheng_all=summarize(rows), c2k19=score_c2k19(), av2=score_av2())
    (FINAL / "score.json").write_text(json.dumps(score, indent=1, ensure_ascii=False))
    print(json.dumps({k: v for k, v in score.items() if k != "haisheng"}, indent=1, ensure_ascii=False))
    for s, v in score["haisheng"].items():
        ok = sum(1 for c in v["clips"] if c["status"] == "ok")
        print(f"{s}: clips {len(v['clips'])} (k found {ok})  segments {v['segments']}  with reading "
              f"{v['with_reading']}  MAE {v.get('mae')}  bias {v.get('bias')}  within3 {v.get('within_3')}")


if __name__ == "__main__":
    main()
