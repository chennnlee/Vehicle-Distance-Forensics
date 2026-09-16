#!/usr/bin/env python3
"""Method C: solve the range calibration from road markings alone -- no neural network.

Pipeline B gets its ground plane from SHARP and its scale from a lane-width anchor.
This solves the same two numbers from classical geometry only, so the three methods
in the report differ in exactly one thing: where the geometry comes from.

    d = A / (py - y_h)          A = h * f

  y_h   the horizon row.  Two parallel lane lines meet at the vanishing point, and
        the ground plane's horizon must pass through it.  Supplied via --y-h, from
        `tools/lane_line_fit.py`.

  A     solved here, from the *longitudinal* dash cycle.  Two consecutive dash
        starts on the same lane line are `--cycle-m` apart on the road, so

            cycle = A * [ 1/(py_far - y_h) - 1/(py_near - y_h) ]
            A     = cycle / [ 1/(py_far - y_h) - 1/(py_near - y_h) ]

        Every frame that shows two dash starts yields one estimate of A; the output
        is the median over all of them.

Why the anchor has to be longitudinal
-------------------------------------
Lane width cannot do this job.  At row py a lane of width W_m subtends
`W_px = W_m * (py - y_h) / h` -- the focal length cancels.  Lane width therefore
pins the camera height and nothing else, and A = h*f still has f unknown.  Only a
length measured *along the direction of travel* (dash cycle, wheelbase, painted
line length) constrains A.  This repeats an error already recorded in CLAUDE.md,
where a number plate was proposed as a forward-scale anchor and is algebraically
incapable of being one.

Single-frame dash spacing is noisy -- CLAUDE.md measured 8.7-11.1 m where the truth
was 10 m, because only 2-3 cycles fit in frame.  That is why this aggregates one
estimate per frame over hundreds of frames rather than trusting any single one, and
why it reports the spread rather than only the median.

Usage:
  python3 tools/vanishing_point_range_calib.py \
      --frames-dir /tmp/c2k19/<seg>/frames \
      --line " -1.6158,1211.4"  --y-h 383.2 --cycle-m 14.63 --step 4
"""

from __future__ import annotations

import argparse
import glob
from pathlib import Path

import numpy as np


def dash_starts(gray, a, b, y_h, y0, y1, half_w=6, smooth=5):
    """Rows at which a dash begins, reading brightness along the lane line.

    The profile is sampled in a narrow band centred on the fitted line, so the
    lane line is followed as it converges rather than a fixed image column.
    """
    h, w = gray.shape
    rows, vals = [], []
    for y in range(int(y0), int(y1)):
        x = int(round(a * y + b))
        if x - half_w < 0 or x + half_w >= w:
            continue
        rows.append(y)
        vals.append(float(np.mean(gray[y, x - half_w:x + half_w + 1])))
    if len(rows) < 40:
        return []
    rows = np.asarray(rows)
    v = np.asarray(vals)
    if smooth > 1:
        k = np.ones(smooth) / smooth
        v = np.convolve(v, k, mode="same")
    # local contrast: paint against the asphalt right around it
    base = np.convolve(v, np.ones(41) / 41, mode="same")
    sig = v - base
    thr = 0.5 * np.percentile(sig, 98)
    if thr <= 0:
        return []
    on = sig > thr
    starts = []
    for i in range(1, len(on)):
        if on[i] and not on[i - 1]:
            starts.append(rows[i])
    return starts


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--frames-dir", required=True)
    ap.add_argument("--line", required=True, help="'a,b' of x = a*y + b from lane_line_fit.py")
    ap.add_argument("--y-h", type=float, required=True, help="horizon row from the vanishing point")
    ap.add_argument("--cycle-m", type=float, required=True,
                    help="legal dash cycle (mark + gap). TW lane line 10, Caltrans motorway 14.63")
    ap.add_argument("--band", default="", help="y0,y1 rows to read; default y_h+60 .. y_h+280")
    ap.add_argument("--step", type=int, default=4)
    ap.add_argument("--max-frames", type=int, default=400)
    ap.add_argument("--min-gap-px", type=float, default=12.0,
                    help="reject dash pairs closer than this; they are one dash split by noise")
    args = ap.parse_args()

    a, b = (float(x) for x in args.line.split(","))
    if args.band:
        y0, y1 = (float(x) for x in args.band.split(","))
    else:
        y0, y1 = args.y_h + 60, args.y_h + 280

    import cv2
    files = sorted(glob.glob(str(Path(args.frames_dir) / "*.jpg")))[::args.step][:args.max_frames]
    print(f"frames : {len(files)}  rows {y0:.0f}..{y1:.0f}  line x = {a:.4f}y + {b:.1f}")
    print(f"y_h    : {args.y_h}    cycle = {args.cycle_m} m")

    A_est, n_pairs, n_frames_used = [], 0, 0
    for fp in files:
        g = cv2.imread(fp, cv2.IMREAD_GRAYSCALE)
        if g is None:
            continue
        st = dash_starts(g, a, b, args.y_h, y0, y1)
        if len(st) < 2:
            continue
        used = False
        for far, near in zip(st[:-1], st[1:]):
            if near - far < args.min_gap_px:
                continue
            inv = 1.0 / (far - args.y_h) - 1.0 / (near - args.y_h)
            if inv <= 0:
                continue
            A_est.append(args.cycle_m / inv)
            n_pairs += 1
            used = True
        n_frames_used += used

    if not A_est:
        print("no dash pairs found -- widen --band or lower the contrast threshold")
        return 1

    A = np.asarray(A_est)
    med = float(np.median(A))
    p25, p75 = np.percentile(A, [25, 75])
    print(f"\npairs  : {n_pairs} from {n_frames_used} frames")
    print(f"A      : median {med:.0f}   IQR {p25:.0f} .. {p75:.0f}   "
          f"spread {(p75 - p25) / med * 100:.1f}%")
    print(f"\n  d(py) = {med:.0f} / (py - {args.y_h})")
    for py in (450, 500, 550, 600, 650):
        print(f"    py={py}  ->  {med / (py - args.y_h):6.2f} m")
    print("\n  ⚠ spread is the honest uncertainty here: single-frame dash spacing is")
    print("    noisy (CLAUDE.md measured 8.7-11.1 m where truth was 10). Quote the IQR.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
