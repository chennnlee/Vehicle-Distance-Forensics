#!/usr/bin/env python3
"""Method C: solve the range calibration from road markings alone -- no neural network.

Pipeline B gets its ground plane from SHARP and its scale from a lane-width anchor.
This solves the same two numbers from classical geometry only, so the three methods
in the report differ in exactly one thing: where the geometry comes from.

    d = A / (py - y_h)          A = h * f

  y_h   the horizon row.  Two parallel lane lines meet at the vanishing point, and
        the ground plane's horizon must pass through it.  Supplied via --y-h, from
        `tools/lane_line_fit.py`.

  A     solved here, from the *time* the same dashes take to travel between image
        rows.  The dash signal at a far row reappears at a nearer row `lag` frames
        later; one dash cycle takes `period` frames to pass any row.  So the road
        distance between the two rows is `cycle_m * lag / period`, and

            cycle_m * lag / period = A * [ 1/(y_far - y_h) - 1/(y_near - y_h) ]

        gives one estimate of A per row pair.  Vehicle speed cancels in lag/period.
        The lag and period come from `odometer_distance_calib.py`, whose correction
        factors were checked against comma2k19's factory radar (CLAUDE.md, 2026-09-01).

Why not measure the dash spacing in a single frame (withdrawn 2026-09-17)
-------------------------------------------------------------------------
The first version of this tool looked for two consecutive dash starts in one frame
and set their spacing to one cycle.  It reported A = 1153 / 1139 for two segments,
"agreeing to 1.2%".  That agreement was manufactured by the tool:

  * The local-contrast baseline was a zero-padded moving mean, so it sagged at both
    ends of the read band and every profile crossed the threshold there.  The two
    "dash starts" were almost always the band's first row (y_h + 61) and a row near
    its end (y_h + 268), which fixes A = cycle / [1/61 - 1/268] ~ 1140 on ANY clip.
  * With the edge artefact removed, real pairs are rare: on this camera a 14.63 m
    cycle spans roughly the whole band, so a frame seldom holds two dash starts.
    The pairs it did find were fragments of one dash and gave A ~ 10000.

CLAUDE.md had already recorded that single-frame spacing is unusable (8.7-11.1 m
for a 10 m cycle, "only 2-3 cycles fit in frame"); this is the same limit, hidden
behind an artefact that happened to land near the right answer.

The time-lag measurement has no such failure: each row pair gives a separate
estimate, and they scatter rather than repeat one value.

Quality gate
------------
Per lane line, the relative spread (max - min) / median of its pair estimates must
be <= --max-spread (0.10, the same gate `odometer_distance_calib.py` applies).  A
line that fails is reported and left out; the answer is the median over all pairs
from the lines that pass.

Why the anchor has to be longitudinal
-------------------------------------
Lane width cannot do this job.  At row py a lane of width W_m subtends
`W_px = W_m * (py - y_h) / h` -- the focal length cancels.  Lane width therefore
pins the camera height and nothing else, and A = h*f still has f unknown.  Only a
length measured *along the direction of travel* (dash cycle, wheelbase, painted
line length) constrains A.

Usage:
  python3 tools/vanishing_point_range_calib.py \
      --frames-dir /tmp/c2k19/<seg>/frames --fps 20 --y-h 383.2 --cycle-m 14.63 \
      --line " -1.6158,1211.4" --line "1.5445,0.4" --rows 500,540,580,615
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "tools"))

from dashcam_range_speed import extract_odometer_signals                 # noqa: E402
from odometer_distance_calib import odometer_period, row_pair_distances  # noqa: E402


def line_estimates(frames, a, b, rows, y_h, fps, cycle_m):
    """A from every row pair on the lane line x = a*y + b."""
    pts = [(int(round(a * y + b)), int(y)) for y in rows]
    sig = extract_odometer_signals(frames, pts, 120)
    periods = [p for p in (odometer_period(sig[q][:, 0].astype(float), fps) for q in pts) if p]
    if not periods:
        return pts, None, []
    period = float(np.median(periods))
    out = []
    for y_far, y_near, dist_m, peak in row_pair_distances(sig, pts, period, cycle_m):
        inv = 1.0 / (y_far - y_h) - 1.0 / (y_near - y_h)
        if inv > 0:
            out.append(dict(y_far=y_far, y_near=y_near, dist_m=dist_m, xcorr=peak, A=dist_m / inv))
    return pts, period, out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--frames-dir", required=True)
    ap.add_argument("--fps", type=float, required=True)
    ap.add_argument("--line", action="append", required=True,
                    help="'a,b' of x = a*y + b from lane_line_fit.py; repeat for the other line")
    ap.add_argument("--y-h", type=float, required=True, help="horizon row from the vanishing point")
    ap.add_argument("--cycle-m", type=float, required=True,
                    help="legal dash cycle (mark + gap). TW lane line 10, Caltrans motorway 14.63")
    ap.add_argument("--rows", default="500,540,580,615", help="image rows sampled on each line")
    ap.add_argument("--max-spread", type=float, default=0.10)
    ap.add_argument("--out-json", default="")
    args = ap.parse_args()

    frames = sorted(Path(args.frames_dir).glob("*.jpg")) or sorted(Path(args.frames_dir).glob("*.png"))
    if not frames:
        sys.exit(f"{args.frames_dir}: no frames")
    rows = [int(r) for r in args.rows.split(",")]
    print(f"frames : {len(frames)}   rows {rows}   y_h {args.y_h}   cycle {args.cycle_m} m")

    report, pooled = [], []
    for spec in args.line:
        a, b = (float(x) for x in spec.split(","))
        pts, period, est = line_estimates(frames, a, b, rows, args.y_h, args.fps, args.cycle_m)
        entry = dict(line=[a, b], points=pts, period_frames=period, pairs=est)
        print(f"\nline x = {a:.4f}y + {b:.1f}   points {pts}")
        if period is None or len(est) < 2:
            entry.update(accepted=False, reason="no odometer lock" if period is None else "fewer than 2 pairs")
            print(f"  ✗ {entry['reason']}")
            report.append(entry)
            continue
        As = np.array([e["A"] for e in est])
        med = float(np.median(As))
        spread = float((As.max() - As.min()) / med)
        ok = spread <= args.max_spread
        entry.update(A_median=med, spread=spread, accepted=ok)
        print(f"  period {period:.2f} frames")
        for e in est:
            print(f"    {e['y_far']:>4.0f} -> {e['y_near']:<4.0f} {e['dist_m']:6.2f} m   xcorr {e['xcorr']:.2f}   A {e['A']:6.0f}")
        print(f"  A median {med:.0f}   spread {spread * 100:.1f}%   "
              f"{'accepted' if ok else f'✗ spread above {args.max_spread * 100:.0f}%, left out'}")
        if ok:
            pooled += As.tolist()
        report.append(entry)

    if not pooled:
        print("\nno lane line passed the quality gate -- no calibration")
        return 1
    A = float(np.median(pooled))
    print(f"\nA = {A:.0f}   from {len(pooled)} row pairs\n\n  d(py) = {A:.0f} / (py - {args.y_h})")
    for py in (450, 500, 550, 600, 650):
        if py > args.y_h:
            print(f"    py={py}  ->  {A / (py - args.y_h):6.2f} m")
    if args.out_json:
        Path(args.out_json).write_text(json.dumps(dict(A=A, y_h=args.y_h, cycle_m=args.cycle_m,
                                                       n_pairs=len(pooled), lines=report),
                                                  indent=2), encoding="utf-8")
        print(f"\nwrote {args.out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
