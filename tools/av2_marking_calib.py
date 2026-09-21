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
implies (v * period / fps).  This is the rule CLAUDE.md already states for Taiwan
("週期勿信規範先驗 ... 有 GPS 就先反驗"), applied where a speed reference exists.

⚠ The first version of that gate asked only whether the implied cycle was within +-20% of
one assumed constant, and that was too loose in both directions.  Log f668074d implied
14.50 m, passed, and came out 23% low -- because that road is not striped to the MUTCD
default of 12.19 m but to something near the Californian 48 ft (14.63 m).  The gate now
snaps the implied cycle to the nearest entry of `--cycle-set` and rejects anything further
than `--cycle-tol` from all of them; the matched entry, not the assumed one, is what A is
computed from.  Tightening it was decided after seeing that failure, so it is a post-hoc
fix: it turns f668074d's -23.2% into -7.9% and leaves the other three logs unchanged.  It
needs a speed reference, so it does not transfer to clips without GPS.

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


def measure_A(frames_dir, fps, y_h, lines, rows, out_json, reuse=False):
    Path(out_json).parent.mkdir(parents=True, exist_ok=True)
    if reuse and Path(out_json).exists():
        return json.loads(Path(out_json).read_text())
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
    ap.add_argument("--cycle-set", default="12.19,14.63",
                    help="legal dash cycles the implied cycle may snap to. "
                         "12.19 = MUTCD 10+30 ft, 14.63 = 12+36 ft (Caltrans). Taiwan would be 10.0")
    ap.add_argument("--cycle-tol", type=float, default=0.08,
                    help="reject a line whose implied cycle is this far from every entry of --cycle-set")
    ap.add_argument("--reuse-json", action="store_true",
                    help="reuse an existing A_<log>.json instead of re-reading the frames")
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
                        args.rows, Path(args.out).parent / f"A_{log[:8]}.json", args.reuse_json)
        if cal is None:
            r.update(status="no line passed (tool gate)"); results.append(r)
            print(f"{log[:8]}  ✗ no line passed the tool's own spread gate"); continue

        cycles = [float(x) for x in args.cycle_set.split(",")]
        kept, lines_out = [], []
        for line in cal["lines"]:
            p = line.get("period_frames")
            implied = meta["speed_mps_median"] * p / meta["fps"] if p else None
            matched = min(cycles, key=lambda c: abs(implied - c)) if implied else None
            ok_cycle = matched is not None and abs(implied - matched) / matched <= args.cycle_tol
            take = bool(line.get("accepted")) and ok_cycle and len(line.get("pairs", [])) >= 3
            lines_out.append(dict(line=line["line"], period=p, implied_cycle_m=implied,
                                  matched_cycle_m=matched if ok_cycle else None,
                                  spread=line.get("spread"), n_pairs=len(line.get("pairs", [])),
                                  accepted=take))
            if take:
                # A was computed with CYCLE_M; rescale to the cycle this road is actually striped to
                kept += [e["A"] * matched / CYCLE_M for e in line["pairs"]]
        r["lines"] = lines_out
        if not kept:
            r.update(status="no line passed"); results.append(r)
            print(f"{log[:8]}  ✗ no line passed  " +
                  "  ".join(f"[period {l['period']:.2f} -> implies {l['implied_cycle_m']:.1f} m]"
                            if l["period"] else "[no lock]" for l in lines_out))
            continue
        A = float(np.median(kept))
        r["cycles_used_m"] = sorted({l["matched_cycle_m"] for l in lines_out if l["accepted"]})
        r.update(status="ok", A_marking=A, n_pairs=len(kept),
                 spread=float((max(kept) - min(kept)) / A), ratio=A / meta["A_factory"])
        results.append(r)
        print(f"{log[:8]}  A {A:6.0f}  factory {meta['A_factory']:6.0f}  "
              f"ratio {r['ratio']:.3f}  ({r['ratio'] * 100 - 100:+.1f}%)  "
              f"pairs {len(kept)}  spread {r['spread'] * 100:.1f}%  "
              f"pitch {r['pitch_px']:+.1f} px  cycle {r['cycles_used_m']}")

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
