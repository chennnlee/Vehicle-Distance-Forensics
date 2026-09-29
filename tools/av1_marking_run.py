#!/usr/bin/env python3
"""Run the marking calibration over Argoverse 1 with the sampling rows chosen by the
measurement itself, so no part of the run needs the constant it is recovering.

Why a driver instead of new rows in the batch tool.  Condition (2) of the screen
(docs/TERRY_RESEARCH_RECORD.md 6.5) says the 13-row sampling band must cover less road at
the farthest row than half a dash.  Turning that into a row number needs A = h*f -- which
is exactly the factory value the AV2 experiment is trying to recover.  Picking the rows
from the factory value and then reporting how close the answer came to it is circular, and
on this camera it is not a harmless circularity: rows placed 50 px too far refused both
development logs outright.

So the rows are chosen in two passes, from the measurement:

  seed    three near rows, fixed by image geometry alone (fractions of the distance from
          the middle of the frame to its bottom edge, the same fractions AV2 used).  Near
          rows satisfy condition (2) on any camera -- the band shrinks with distance -- so
          this pass needs no scale at all.  It gives a provisional A and the horizon row.
  extend  the farthest row condition (2) allows at that provisional A:
              y_far = y_h + sqrt(24*A/dash + 36)
          then the final measurement over [y_far] + the seed rows.  A wider span is what
          makes the row pairs long enough to resolve a lag, so this is not cosmetic.

Nothing here reads a cuboid, and with `av1_prepare.py --hide-factory` nothing reads h or
A_factory either: those sit in factory_reference.json, which only the scoring step opens.
Ego speed is used, in the batch tool's cycle gate only, to turn a locked period into the
cycle length it implies -- the same external reference the project notes already require of the
Taiwanese clips, and not the quantity being scored.

Usage:
  python3 tools/av1_marking_run.py --windows data/output/av1_marking/windows.csv \
      --logs-file tools/av1_val_logs.txt --out data/output/av1_marking/calib.json
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable


def run(cmd, quiet=False):
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    if not quiet:
        print(r.stdout.rstrip() or r.stderr.rstrip()[-400:], flush=True)
    return r


def calib(logs, root, rows, band, out, cycle_set, dedup_row, dedup_px, side_row, extra=()):
    lf = Path(out).parent / "_logs.txt"
    lf.parent.mkdir(parents=True, exist_ok=True)
    lf.write_text("\n".join(logs) + "\n")
    run([PY, ROOT / "tools/av2_marking_calib.py", "--logs-file", lf, "--av2-root", root,
         "--rows", rows, "--band", band, "--cycle-set", cycle_set,
         "--dedup-row", dedup_row, "--dedup-px", dedup_px, "--side-row", side_row,
         "--out", out, *extra])
    return {r["log"]: r for r in json.loads(Path(out).read_text())} if Path(out).exists() else {}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--logs-file", required=True)
    ap.add_argument("--windows", required=True, help="windows.csv from av1_select.py")
    ap.add_argument("--root", default="data/input/av1")
    ap.add_argument("--seed-rows", default="822,912,1008",
                    help="near rows from image geometry only: 600 + (0.37,0.52,0.68)*600 on a "
                         "1200-tall frame, the fractions AV2's row set corresponds to")
    ap.add_argument("--band", default="700,1100", help="ridge band for the lane fit, fixed across "
                                                       "both passes so the horizon cannot move")
    # lane_line_fit defaults to row 620 for both of its judging rows, which is where this
    # camera's horizon is (604-627 across the val logs). Leaving them at the default is the
    # very defect this round set out to fix: candidate lines converge at the horizon, so they
    # de-duplicate into one and the left/right test lands on the wrong side. Passing them is
    # not optional on AV1 -- the first overnight run forgot to, and three logs came back
    # "not a lane" while a fourth moved its A by 12%.
    ap.add_argument("--dedup-row", type=float, default=727.0,
                    help="~110 px below AV1's horizon, the same offset AV2's 620 has from its own")
    ap.add_argument("--dedup-px", type=float, default=29.0,
                    help="25 px scaled by frame height (1200/1024): the same real separation "
                         "subtends more pixels on a taller sensor")
    ap.add_argument("--side-row", type=float, default=1008.0,
                    help="lowest seed row; below the horizon by a wide margin on this camera")
    ap.add_argument("--dash-m", type=float, default=3.05, help="painted dash, MUTCD 10 ft")
    ap.add_argument("--cycle-set", default="12.19,14.63")
    ap.add_argument("--skip-prepare", action="store_true")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    win = {}
    for i, line in enumerate(Path(args.windows).read_text().splitlines()):
        if i == 0 or not line.strip():
            continue
        f = line.split(",")
        win[f[0]] = (float(f[4]), float(f[5]))
    logs = [l.strip() for l in Path(args.logs_file).read_text().splitlines() if l.strip()]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    if not args.skip_prepare:
        for lg in logs:
            t0, t1 = win.get(lg, (0.0, float("inf")))
            print(f"--- prepare {lg[:8]}  window {t0:.1f}-{t1:.1f} s", flush=True)
            run([PY, ROOT / "tools/av1_prepare.py", "--log", Path(args.root) / lg,
                 "--t0", t0, "--t1", t1, "--hide-factory"])

    print("\n=== pass 1: seed rows (no scale used anywhere) ===", flush=True)
    seed = calib(logs, args.root, args.seed_rows, args.band,
                 out.parent / "calib_seed.json", args.cycle_set,
                 args.dedup_row, args.dedup_px, args.side_row)

    print("\n=== pass 2: far row from the measured A, per log ===", flush=True)
    merged = []
    for lg in logs:
        s = seed.get(lg, {})
        if s.get("status") != "ok":
            print(f"{lg[:8]}  seed pass gave no A ({s.get('status')}) -- reported as refused")
            s.setdefault("log", lg)
            s["rows_used"] = args.seed_rows
            s["pass"] = "seed only"
            merged.append(s)
            continue
        y_far = s["y_h"] + math.sqrt(24 * s["A_marking"] / args.dash_m + 36)
        rows = f"{int(round(y_far))}," + args.seed_rows
        print(f"{lg[:8]}  seed A {s['A_marking']:.0f} -> far row {y_far:.0f} "
              f"({s['A_marking'] / (y_far - s['y_h']):.1f} m); rows {rows}", flush=True)
        r = calib([lg], args.root, rows, args.band,
                  out.parent / f"calib_{lg[:8]}.json", args.cycle_set,
                  args.dedup_row, args.dedup_px, args.side_row).get(lg, {})
        if r.get("status") != "ok":
            # The wider span refused where the near rows alone did not. Report the seed
            # answer and say which pass it came from; do not quietly keep the better one.
            print(f"{lg[:8]}  extended pass refused ({r.get('status')}); keeping the seed answer")
            s["rows_used"], s["pass"] = args.seed_rows, "seed only (extended refused)"
            s["extended_status"] = r.get("status")
            merged.append(s)
            continue
        r["rows_used"], r["pass"] = rows, "extended"
        r["A_seed"] = s["A_marking"]
        merged.append(r)

    out.write_text(json.dumps(merged, indent=2))
    ok = [r for r in merged if r.get("status") == "ok"]
    print(f"\n{len(ok)}/{len(merged)} logs produced an answer -> {out}")
    for r in ok:
        print(f"  {r['log'][:8]}  A {r['A_marking']:6.0f}  spread {r['spread']*100:4.1f}%  "
              f"pairs {r['n_pairs']:2d}  rows {r['rows_used']}  [{r['pass']}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
