"""Fit the two ego-lane lines from the accumulated contrast ridge, without eyeballing.

The project notes record a real gap (docs/METHODOLOGY_PITFALLS.md item 13): the lane-width calibration's pixel pairs were never
stored, so every scale factor derived from them (hs005 0.66% CV, wow001 1.52%,
dc006 2.0%, dc007 7.9%, dc003 11%) is unreproducible -- and on one occasion the
wrong clip's pairs were copied across, which invalidated a whole set of numbers.
Reading coordinates off a heat map by eye is what made both failures possible.

This picks them by RANSAC over per-row ridge peaks and prints the `--pairs` string
`dashcam_lane_width_calib.py` takes, plus the fitted lines and their vanishing
point. The vanishing point is worth having on its own: the horizon row of the
ground plane must pass through it, so it is an independent measurement of the
plane's pitch that uses no neural network (2026-08-19 used it to overturn a
claimed 20-30% longitudinal error, and 2026-09-01 the factory radar agreed with
it against SHARP).

The selection rule is the part that matters. "Take the nearest ridge either side
of centre" is the obvious rule and it is wrong: tyre polish inboard of the paint
wins it, and on comma2k19 seg21 that moved the vanishing point by 15 px. A
windscreen camera sits near the middle of its lane, so the pair whose MIDPOINT at
the bottom row is closest to the principal column is the one with physics behind
it.

Usage:
  python3 tools/lane_line_fit.py --frames-dir /tmp/dc006_frames \
      --rows 500,540,580,615 --band 460,625 --step 4
"""
from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np

ap = argparse.ArgumentParser(description=__doc__,
                             formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--frames-dir", required=True)
ap.add_argument("--rows", required=True, help="Rows to emit pairs for, e.g. '500,540,580,615'.")
ap.add_argument("--band", default="460,625", help="y0,y1 of the road band the ridge is read from.")
ap.add_argument("--step", type=int, default=4, help="Frame stride when accumulating the ridge.")
ap.add_argument("--peaks-per-row", type=int, default=8)
ap.add_argument("--inlier-px", type=float, default=4.0)
ap.add_argument("--dedup-row", type=float, default=620.0,
                help="Row at which two candidate lines closer than --dedup-px count as one. "
                     "Must sit BELOW the horizon: above it every candidate converges on the "
                     "vanishing point and all but one are discarded. Default 620 is the value "
                     "hard-coded when this tool was written (2026-09-03, commit 27a7c21, for "
                     "comma2k19's 1164x874 frames, whose horizon is near row 380); it also "
                     "happens to sit 108 px under AV2's horizon at 512. It does NOT transfer: "
                     "A2D2 (1208 tall) and AV1 (1200 tall) put the horizon at 604-684, above "
                     "it. Give a taller camera its own value.")
ap.add_argument("--dedup-px", type=float, default=25.0)
ap.add_argument("--side-row", type=float, default=620.0,
                help="Row at which a line counts as left or right of the principal column. "
                     "Same constraint and same default as --dedup-row, for the same reason: "
                     "above the horizon a line's column crosses to the other side of the "
                     "vanishing point.")
a = ap.parse_args()
frames_dir, step, out_rows = a.frames_dir, a.step, a.rows
y0, y1 = (int(v) for v in a.band.split(","))
fs = sorted(Path(frames_dir).glob("*.jpg"))[::step]
if not fs:
    raise SystemExit(f"no frames in {frames_dir}")
acc = None
for f in fs:
    g = cv2.cvtColor(cv2.imread(str(f)), cv2.COLOR_BGR2GRAY).astype(np.float32)
    d = cv2.subtract(g, cv2.GaussianBlur(g, (51, 51), 0))
    acc = d if acc is None else acc + d
acc /= len(fs)
H, W = acc.shape
print(f"{len(fs)} frames, {W}x{H}")

pts = []
for y in range(y0, y1 + 1, 5):
    prof = np.clip(acc[y], 0, None).copy()
    work = prof.copy()
    for _ in range(a.peaks_per_row):
        x = int(np.argmax(work))
        if work[x] <= 0:
            break
        # sub-pixel: parabolic on the local profile, the same refinement the
        # odometer uses on its correlation peak
        if 0 < x < W - 1:
            den = prof[x-1] - 2*prof[x] + prof[x+1]
            xs = x + (0.5 * (prof[x-1] - prof[x+1]) / den if abs(den) > 1e-9 else 0.0)
        else:
            xs = float(x)
        pts.append((y, float(xs), float(prof[x])))
        work[max(0, x-30): x+31] = 0
pts = [p for p in pts if p[2] > 0.15]
P = np.array([(p[0], p[1]) for p in pts])
print(f"{len(P)} ridge peaks over rows {y0}-{y1}")

rng = np.random.default_rng(0)
lines = []
for _ in range(6000):
    i, j = rng.integers(0, len(P), 2)
    if abs(P[i, 0] - P[j, 0]) < 60:
        continue
    m = (P[j, 1] - P[i, 1]) / (P[j, 0] - P[i, 0])
    if abs(m) < 0.3 or abs(m) > 6:          # lane lines are steep but not vertical
        continue
    k = P[i, 1] - m * P[i, 0]
    r = np.abs(m * P[:, 0] + k - P[:, 1])
    inl = r < a.inlier_px
    if inl.sum() < 6 or np.ptp(P[inl, 0]) < 100:
        continue
    mm, kk = np.polyfit(P[inl, 0], P[inl, 1], 1)
    lines.append((int(inl.sum()), float(mm), float(kk), float(np.abs(mm*P[inl,0]+kk-P[inl,1]).mean())))
lines.sort(key=lambda t: -t[0])
# Both this de-duplication and the left/right test below are judged at a row that has to sit
# below the horizon, and neither can be a constant: 620 was written for one camera and goes
# quietly wrong on taller ones (see --dedup-row). They are parameters now, defaulting to the
# historical values so that every run made before 2026-09-28 reproduces exactly, and the
# warning printed after the fit says when a row landed on the wrong side of the horizon --
# the failure that is otherwise invisible, presenting either as "could not bracket the ego
# lane" or as a shortlist holding six copies of one line.
row_d, tol_d = a.dedup_row, a.dedup_px
uniq = []
for n, m, k, res in lines:
    if any(abs(m*row_d+k - (mm*row_d+kk)) < tol_d for _, mm, kk, _ in uniq):
        continue
    uniq.append((n, m, k, res))
    if len(uniq) >= 6:
        break
_rb = max(int(v) for v in out_rows.split(","))
_rt = min(int(v) for v in out_rows.split(","))
print(f"\n{'n':>4s} {'slope':>7s} {'x@'+str(_rb):>7s} {'x@'+str(_rt):>7s} {'resid':>6s}")
for n, m, k, res in uniq:
    print(f"{n:4d} {m:7.3f} {m*_rb+k:7.1f} {m*_rt+k:7.1f} {res:6.2f}")

# Choose the pair whose midpoint at the bottom row sits closest to the principal
# column. "Nearest line either side of centre" is the obvious rule and it is wrong:
# a tyre-polish streak inboard of the paint wins it, and on seg21 that shifted the
# vanishing point by 15 px. A windscreen camera sits near the middle of its lane,
# so the midpoint is the criterion with physics behind it.
# The row this is judged at must be BELOW the horizon, or left and right swap: a line's
# column crosses to the other side of the vanishing point above it. See --side-row.
cxb = W / 2
row_b = a.side_row
left = [l for l in uniq if l[1]*row_b + l[2] < cxb and l[1] < 0]
right = [l for l in uniq if l[1]*row_b + l[2] > cxb and l[1] > 0]
if not (left and right):
    raise SystemExit(f"could not bracket the ego lane (judged at row {row_b})")
L, R = min(((a, b) for a in left for b in right),
           key=lambda ab: abs(0.5 * ((ab[0][1]*row_b + ab[0][2]) + (ab[1][1]*row_b + ab[1][2])) - cxb))
vy = (R[2] - L[2]) / (L[1] - R[1])
print(f"\nego lane: left x = {L[1]:.4f}y + {L[2]:.1f} (n={L[0]}), "
      f"right x = {R[1]:.4f}y + {R[2]:.1f} (n={R[0]})")
print(f"vanishing point: row {vy:.1f}, col {L[1]*vy + L[2]:.1f}")
for _nm, _rv in (("--dedup-row", row_d), ("--side-row", row_b)):
    if _rv <= vy:
        print(f"  WARNING {_nm} {_rv:.0f} is ABOVE the measured horizon {vy:.1f}: candidate "
              f"lines converge there, so this fit may have dropped a real line or swapped "
              f"left for right. Re-run with {_nm} below {vy:.0f}.")
pairs = ";".join(f"{L[1]*y + L[2]:.0f},{y},{R[1]*y + R[2]:.0f},{y}"
                 for y in (int(v) for v in out_rows.split(",")))
print(f"--pairs \"{pairs}\"")
for y in (int(v) for v in out_rows.split(",")):
    print(f"   row {y}: width {R[1]*y + R[2] - (L[1]*y + L[2]):.1f} px")
