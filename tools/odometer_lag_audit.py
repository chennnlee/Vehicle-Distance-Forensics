from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "tools"))

from dashcam_range_speed import dash_cycle_speeds, extract_odometer_signals


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit which lag corrections (octave guard / sub-octave) actually fire on real "
        "footage. Runs ONLY the dash-cycle odometer (no YOLO), replicates the pipeline's dual-window "
        "combination, and tallies per-candidate lag decisions. Motivation: synthetic tests show the "
        "two corrections can silently cancel each other (the sub-octave check reverts an octave "
        "doubling whenever the argmax lag is an interior peak), so before touching that logic we "
        "need to know how often each path fires on the validated cases."
    )
    parser.add_argument("--frames-dir", required=True)
    parser.add_argument("--odometer-points", required=True, help="Same format as dashcam_range_speed.")
    parser.add_argument("--dash-cycle-m", type=float, default=10.0)
    parser.add_argument("--fps", type=float, required=True)
    parser.add_argument("--odometer-window-s", type=float, default=3.0)
    parser.add_argument("--octave-thresholds", default="0.75,0.95",
                        help="Comma list; each is audited independently on the same extracted signal.")
    parser.add_argument("--compare-csv", default="", help="Archived ego_speed.csv to diff against "
                        "(rows with method=dash_odometer). Rebuilt frames are re-encoded, so expect "
                        "near-equal, not bit-equal.")
    parser.add_argument("--compare-threshold", type=float, default=0.0,
                        help="Which audited threshold the archived run used (default: first in the list).")
    parser.add_argument("--label", default="")
    parser.add_argument("--out-json", default="", help="Write the aggregated stats as JSON.")
    return parser.parse_args()


def combine_windows(v1, c1, p1, v2):
    """Replicates main()'s dual-window agreement + strong-lock override."""
    agree = np.isfinite(v1) & np.isfinite(v2) & (np.abs(v1 - v2) <= 0.12 * np.maximum(v1, v2))
    strong = np.isfinite(v1) & (c1 >= 0.5) & (p1 >= 0.5)
    return np.where(agree, 0.5 * (v1 + v2), np.where(strong, v1, np.nan)), agree, strong


def rolling_median(x: np.ndarray, fps: float) -> np.ndarray:
    k = max(3, int(round(fps)) | 1)
    pad = k // 2
    with np.errstate(all="ignore"):
        return np.array([np.nanmedian(x[max(0, i - pad): i + pad + 1])
                         if np.isfinite(x[max(0, i - pad): i + pad + 1]).any() else np.nan
                         for i in range(len(x))])


def summarize_events(events: list[dict]) -> dict:
    n = len(events)
    stats = {
        "candidates": n,
        "octave_fired": 0,            # guard doubled the argmax lag
        "suboct_fired": 0,            # sub-octave halved the post-guard lag
        "cancel_chain": 0,            # doubled THEN reverted to argmax = the two cancel
        "octave_survived": 0,         # doubled and the doubling stuck
        "suboct_on_argmax": 0,        # halved without any doubling (stud-fix path)
        "prominent": 0,
    }
    for e in events:
        oct_f = e["lag_octave"] != e["lag_argmax"]
        sub_f = e["lag_suboct"] != e["lag_octave"]
        stats["octave_fired"] += oct_f
        stats["suboct_fired"] += sub_f
        stats["prominent"] += e["prominent"]
        if oct_f and e["lag_suboct"] == e["lag_argmax"]:
            stats["cancel_chain"] += 1
        elif oct_f and not sub_f:
            stats["octave_survived"] += 1
        if not oct_f and sub_f:
            stats["suboct_on_argmax"] += 1
    return stats


def main() -> None:
    args = parse_args()
    frames_dir = Path(args.frames_dir)
    frames = sorted(frames_dir.glob("*.jpg")) + sorted(frames_dir.glob("*.png"))
    if len(frames) < 10:
        raise RuntimeError(f"too few frames in {frames_dir}")
    pts = [tuple(int(s) for s in p.split(",")) for p in args.odometer_points.split(";") if p.strip()]
    label = args.label or frames_dir.name
    print(f"[{label}] frames={len(frames)} points={len(pts)}  extracting signals...")
    sig = extract_odometer_signals(frames, pts)

    thresholds = [float(t) for t in args.octave_thresholds.split(",")]
    report: dict[str, object] = {"label": label, "frames": len(frames), "fps": args.fps,
                                 "points": pts, "thresholds": {}}
    v_by_thr: dict[float, np.ndarray] = {}
    for thr in thresholds:
        ev1: list[dict] = []
        v1, c1, p1 = dash_cycle_speeds(frames, pts, args.dash_cycle_m, args.fps,
                                       args.odometer_window_s, sig=sig,
                                       octave_threshold=thr, lag_events=ev1)
        v2, c2, _ = dash_cycle_speeds(frames, pts, args.dash_cycle_m, args.fps,
                                      args.odometer_window_s * 1.7, sig=sig,
                                      octave_threshold=thr)
        v_odo, agree, strong = combine_windows(v1, c1, p1, v2)
        v_by_thr[thr] = v_odo
        st = summarize_events(ev1)
        st["coverage_pct"] = round(float(np.isfinite(v_odo).mean() * 100), 1)
        st["strong_only_pct"] = round(float((strong & ~agree & np.isfinite(v_odo)).mean() * 100), 1)
        with np.errstate(all="ignore"):
            st["median_kmh"] = round(float(np.nanmedian(v_odo) * 3.6), 1)
        report["thresholds"][str(thr)] = st
        c = st["candidates"]
        print(f"  thr={thr:.2f}  candidates={c}  "
              f"octave_fired={st['octave_fired']} ({st['octave_fired']/max(1,c)*100:.1f}%)  "
              f"cancel_chain={st['cancel_chain']}  octave_survived={st['octave_survived']}  "
              f"suboct_on_argmax={st['suboct_on_argmax']}")
        print(f"           coverage={st['coverage_pct']}%  median={st['median_kmh']} km/h  "
              f"strong-lock-only={st['strong_only_pct']}%")

    if len(thresholds) >= 2:
        a, b = v_by_thr[thresholds[0]], v_by_thr[thresholds[1]]
        both = np.isfinite(a) & np.isfinite(b)
        if both.any():
            d = np.abs(a[both] - b[both]) * 3.6
            print(f"  thr {thresholds[0]:.2f} vs {thresholds[1]:.2f}: both-locked {int(both.sum())}f  "
                  f"median|diff| {np.median(d):.2f} km/h  max {d.max():.2f}")
            report["threshold_diff_kmh"] = {"median": round(float(np.median(d)), 2),
                                            "max": round(float(d.max()), 2),
                                            "frames": int(both.sum())}

    if args.compare_csv:
        thr_cmp = args.compare_threshold or thresholds[0]
        mine = rolling_median(v_by_thr[thr_cmp], args.fps) * 3.6
        ref = np.full(len(frames), np.nan)
        with open(args.compare_csv, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                i = int(row["frame_idx"])
                if i < len(ref) and row["method"] == "dash_odometer" and row["ego_visual_kmh"]:
                    ref[i] = float(row["ego_visual_kmh"])
        both = np.isfinite(mine) & np.isfinite(ref)
        if both.any():
            d = np.abs(mine[both] - ref[both])
            print(f"  vs archived ({Path(args.compare_csv).name}, thr={thr_cmp}): "
                  f"overlap {int(both.sum())}f  median|diff| {np.median(d):.2f} km/h  "
                  f"p95 {np.percentile(d, 95):.2f}  max {d.max():.2f}")
            report["archive_diff_kmh"] = {"median": round(float(np.median(d)), 2),
                                          "p95": round(float(np.percentile(d, 95)), 2),
                                          "max": round(float(d.max()), 2),
                                          "frames": int(both.sum())}
        else:
            print("  vs archived: no overlapping dash_odometer frames")

    if args.out_json:
        out = Path(args.out_json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"saved: {out}")


if __name__ == "__main__":
    main()
