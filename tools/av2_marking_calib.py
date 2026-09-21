#!/usr/bin/env python3
"""Run the marking-only range calibration over a batch of Argoverse 2 logs and score it
against each log's factory calibration.

This is the external check the Taiwanese clips cannot give: there, A = h*f is only ever
measured by this same method, so a bias would be invisible.  Every AV2 log carries the
camera's focal length and mounting height, so the measurement has something to be wrong
against.  Nothing here reads annotations.feather -- the cuboids are for the distance
experiment, not for this one.

Per log:
  1. `lane_line_fit.py`     the two ego-lane lines and their vanishing point -> y_h.
                            Its residual also tells us the imagery really is rectified
                            (a few px; a distorted image gives tens).
  2. `vanishing_point_range_calib.py`   A = h*f from the time dashes take to travel
                            between image rows, with the legal cycle as the only scale.
  3. gates, then compare A against h*fy from the calibration files.

The cycle gate is the one this batch added.  A line's own pair-to-pair spread does not
notice a wrong period: on the Miami log the right-hand line locked onto a 6.94-frame
rhythm (kerb seams, not paint) with a tidy 4.5% spread, and pooling it pulled A from 1547
to 1562.  Ego speed from the poses converts the locked period into the cycle length it
implies (v * period / fps); paint that is not a 12.19 m cycle is thrown out.  This is the
rule CLAUDE.md already states for Taiwan ("週期勿信規範先驗 ... 有 GPS 就先反驗"), applied
where a speed reference exists.

Usage:
  python3 tools/av2_marking_calib.py --logs-file <file with one log id per line> \
      --out data/output/av2_marking/calib.json
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
CYCLE_M = 12.19            # MUTCD broken line: 10 ft stripe + 30 ft gap
PY = sys.executable


def lane_lines(frames_dir, rows, band, step):
    out = subprocess.run([PY, str(ROOT / "tools/lane_line_fit.py"), "--frames-dir", str(frames_dir),
                          "--rows", rows, "--band", band, "--step", str(step)],
                         capture_output=True, text=True).stdout
    m = re.search(r"ego lane: left x = (-?[\d.]+)y \+ (-?[\d.]+) \(n=(\d+)\), "
                  r"right x = (-?[\d.]+)y \+ (-?[\d.]+) \(n=(\d+)\)", out)
    v = re.search(r"vanishing point: row (-?[\d.]+), col (-?[\d.]+)", out)
    if not m or not v:
        return None
    resid = [float(x) for x in re.findall(r"^\s*\d+\s+-?[\d.]+\s+-?[\d.]+\s+-?[\d.]+\s+([\d.]+)$",
                                          out, re.M)[:2]]
    return dict(left=(float(m[1]), float(m[2]), int(m[3])), right=(float(m[4]), float(m[5]), int(m[6])),
                y_h=float(v[1]), x_vp=float(v[2]), resid=resid)


def measure_A(frames_dir, fps, y_h, lines, rows, out_json):
    Path(out_json).parent.mkdir(parents=True, exist_ok=True)
    cmd = [PY, str(ROOT / "tools/vanishing_point_range_calib.py"), "--frames-dir", str(frames_dir),
           "--fps", str(fps), "--y-h", str(y_h), "--cycle-m", str(CYCLE_M), "--rows", rows,
           "--out-json", str(out_json), "--max-spread", "0.10"]
    for a, b, _ in lines:
        cmd.append(f"--line={a},{b}")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if not Path(out_json).exists():
        print("   ", (r.stderr or r.stdout).strip().splitlines()[-1:])
        return None
    return json.loads(Path(out_json).read_text())


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--logs-file", required=True)
    ap.add_argument("--av2-root", default="data/input/av2")
    ap.add_argument("--rows", default="620,700,780,860")
    ap.add_argument("--band", default="580,890")
    ap.add_argument("--step", type=int, default=2)
    ap.add_argument("--max-resid-px", type=float, default=3.0)
    ap.add_argument("--min-inliers", type=int, default=15)
    ap.add_argument("--cycle-tol", type=float, default=0.20,
                    help="reject a line whose locked period implies a cycle this far from legal")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    logs = [l.strip() for l in open(args.logs_file) if l.strip()]
    results = []
    for log in logs:
        root = Path(args.av2_root) / log
        meta_p = root / "pinhole_meta.json"
        if not meta_p.exists():
            subprocess.run([PY, str(ROOT / "tools/av2_prepare.py"), "--log", str(root)],
                           capture_output=True, text=True)
        if not meta_p.exists():
            print(f"{log[:8]}  ✗ prepare failed"); continue
        meta = json.loads(meta_p.read_text())
        r = dict(log=log, A_factory=meta["A_factory"], cy=meta["cy"], fps=meta["fps"],
                 v_mps=meta["speed_mps_median"], cam_h=meta["cam_height_m"])

        lf = lane_lines(root / "pinhole", args.rows, args.band, args.step)
        if lf is None:
            r.update(status="no lane pair"); results.append(r); print(f"{log[:8]}  ✗ no lane pair"); continue
        r.update(y_h=lf["y_h"], x_vp=lf["x_vp"], lane_resid_px=lf["resid"],
                 pitch_px=lf["y_h"] - meta["cy"])
        if max(lf["resid"] or [99]) > args.max_resid_px or min(lf["left"][2], lf["right"][2]) < args.min_inliers:
            r.update(status="lane fit weak"); results.append(r)
            print(f"{log[:8]}  ✗ lane fit weak (resid {lf['resid']}, n {lf['left'][2]}/{lf['right'][2]})")
            continue

        cal = measure_A(root / "pinhole", meta["fps"], lf["y_h"], [lf["left"], lf["right"]],
                        args.rows, Path(args.out).parent / f"A_{log[:8]}.json")
        if cal is None:
            r.update(status="no line passed (tool gate)"); results.append(r)
            print(f"{log[:8]}  ✗ no line passed the tool's own spread gate"); continue

        kept, lines_out = [], []
        for line in cal["lines"]:
            p = line.get("period_frames")
            implied = meta["speed_mps_median"] * p / meta["fps"] if p else None
            ok_cycle = implied is not None and abs(implied - CYCLE_M) / CYCLE_M <= args.cycle_tol
            take = bool(line.get("accepted")) and ok_cycle and len(line.get("pairs", [])) >= 3
            lines_out.append(dict(line=line["line"], period=p, implied_cycle_m=implied,
                                  spread=line.get("spread"), n_pairs=len(line.get("pairs", [])),
                                  accepted=take))
            if take:
                kept += [e["A"] for e in line["pairs"]]
        r["lines"] = lines_out
        if not kept:
            r.update(status="no line passed"); results.append(r)
            print(f"{log[:8]}  ✗ no line passed  " +
                  "  ".join(f"[period {l['period']} -> cycle "
                            f"{l['implied_cycle_m']:.1f} m]" if l["period"] else "[no lock]" for l in lines_out))
            continue
        A = float(np.median(kept))
        r.update(status="ok", A_marking=A, n_pairs=len(kept),
                 spread=float((max(kept) - min(kept)) / A), ratio=A / meta["A_factory"])
        results.append(r)
        print(f"{log[:8]}  A {A:6.0f}  factory {meta['A_factory']:6.0f}  "
              f"ratio {r['ratio']:.3f}  ({r['ratio'] * 100 - 100:+.1f}%)  "
              f"pairs {len(kept)}  spread {r['spread'] * 100:.1f}%  "
              f"pitch {r['pitch_px']:+.1f} px")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(results, indent=2))
    ok = [r for r in results if r.get("status") == "ok"]
    print(f"\n{len(ok)}/{len(results)} logs produced an answer")
    if ok:
        rr = np.array([r["ratio"] for r in ok])
        pp = np.array([r["pitch_px"] for r in ok])
        print(f"  marking / factory : median {np.median(rr):.3f}  "
              f"range {rr.min():.3f}-{rr.max():.3f}  |error| median {np.median(np.abs(rr - 1)) * 100:.1f}%")
        print(f"  vanishing point - principal row : median {np.median(pp):+.1f} px "
              f"(range {pp.min():+.1f}..{pp.max():+.1f})")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    raise SystemExit(main())
