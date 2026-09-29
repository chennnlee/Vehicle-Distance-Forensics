#!/usr/bin/env python3
"""Can the marking method work on a camera at all?  Three conditions, checkable before
downloading a dataset -- plus a fourth that no calculation can answer.

docs/TERRY_RESEARCH_RECORD.md sections 6.5 and 6.7 state the conditions; this puts the
arithmetic in version control, because the screen that picked A2D2 was a throwaway script
and its numbers cannot be reproduced.  Reproducing them turned up an error worth keeping:
that screen listed AV2's A as 6098, which is h * fy_full_res / scale -- A scales linearly
with image scale, not quadratically, so the AV2 row was 2x too large and its sampling band
looked 2x kinder than it is.

    d = A / (py - y_h),  A = h * f          the range model the whole method rests on

  (1) frames per dash cycle = fps * cycle / v >= ~8.  Below that the autocorrelation cannot
      separate a period from its octaves.  Found on KITTI at 10 Hz (project notes).
  (2) the 13-row sampling band (y-6..y+6, `extract_odometer_signals`) must cover less road
      at the FARTHEST sampled row than half a dash, or the dash is averaged away:
          cover(y) = A/(dy-6) - A/(dy+6),  dy = y - y_h
  (3) a row pair must be at least ~4 frames of travel apart, or the cross-correlation has no
      lag to resolve:  (d_far - d_near) * fps / v >= 4.  The method pools every pair, so what
      matters is that the WIDEST pair clears it; adjacent rows are under 4 frames on every
      camera here, including both that worked.

  (4) the frames must actually contain a legal periodic dash.  Not computable: A2D2 passed
      all three and was still refused, because that road's centre line is solid and its
      edge line unpainted.  The cheap check is to pick straight fast windows from the
      vehicle signals, pull one frame at each, and look before downloading the segment.

⚠ Condition (2)'s threshold is calibrated, not derived.  The camera that works, AV2, sits
exactly on it (band 1.53 m against a 1.53 m half-dash), and the one refused for sampling
geometry, KITTI, is 4x past it.  So "<= 1" is known to work and ">= 4" is known to fail;
in between, this screen does not know.  Report the ratio, not a verdict.

Usage:
  python3 tools/marking_method_screen.py                        # the known cameras
  python3 tools/marking_method_screen.py --add "AV1 ring_front_center:A=2283:y_h=604.4:\
rows=765,886,1004,1123:fps=30:v=12.1:cycle=12.19:dash=3.05"
"""
from __future__ import annotations

import argparse

# Every field is either published by the dataset or measured and recorded; the provenance
# column says which, because a screen that quietly uses a measured A cannot be run before
# downloading.
KNOWN = [
    dict(name="AV2 ring_front_center @0.5", A=1530.2, y_h=510.3, rows=[620, 700, 780, 860],
         fps=20.0, v=12.12, cycle=12.19, dash=3.05, outcome="passed (4 of 16 logs)",
         src="factory h*fy from pinhole_meta.json; y_h = cy; rows as run; v = log median"),
    dict(name="KITTI 0015", A=1196.0, y_h=173.9, rows=[215, 250, 300, 370],
         fps=10.0, v=12.2, cycle=12.0, dash=4.0, outcome="refused (locks disagree)",
         src="h 1.658 (lidar - offset) x f 721; y_h from vanishing point; rows as run"),
    dict(name="A2D2 front_center", A=3019.6, y_h=684.4, rows=[860, 900, 930, 960],
         fps=30.0, v=18.0, cycle=18.0, dash=6.0, outcome="refused (no dash painted)",
         src="factory h*fy from pinhole_meta.json; y_h = cy; rows approximate"),
    dict(name="hs005 (Taiwan, Garmin)", A=1364.0, y_h=600.5, rows=[700, 750, 800, 850],
         fps=29.89, v=26.4, cycle=10.0, dash=4.0, outcome="passed",
         src="A measured by the odometer cross-row method (no factory value exists); "
             "y_h from vanishing point"),
]


def screen(c):
    A, y_h, rows, fps, v = c["A"], c["y_h"], sorted(c["rows"]), c["fps"], c["v"]
    d = [A / (r - y_h) for r in rows]
    far = rows[0]
    dy = far - y_h
    cover = A / (dy - 6) - A / (dy + 6)
    pair_frames = [(d[i] - d[i + 1]) * fps / v for i in range(len(rows) - 1)]
    wide = (d[0] - d[-1]) * fps / v
    dy_ok = (24 * A / c["dash"] + 36) ** 0.5          # row where the band covers half a dash
    return dict(fpc=fps * c["cycle"] / v, d_far=d[0], d_near=d[-1], cover=cover,
                ratio2=cover / (c["dash"] / 2), min_pair=min(pair_frames), wide_pair=wide,
                d_usable=A / dy_ok, pairs=pair_frames)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--add", action="append", default=[],
                    help="name:A=..:y_h=..:rows=a,b,c:fps=..:v=..:cycle=..:dash=..")
    args = ap.parse_args()

    cams = list(KNOWN)
    for spec in args.add:
        parts = spec.split(":")
        c = dict(name=parts[0], outcome="(candidate)", src="from --add")
        for kv in parts[1:]:
            k, val = kv.split("=")
            c[k] = [int(x) for x in val.split(",")] if k == "rows" else float(val)
        cams.append(c)

    print(f"{'camera':30s} {'A':>6s} {'fr/cyc':>7s} {'far m':>6s} {'near m':>7s} "
          f"{'band m':>7s} {'/half-dash':>10s} {'pair fr':>14s} {'usable to m':>11s}   outcome")
    for c in cams:
        s = screen(c)
        print(f"{c['name']:30s} {c['A']:6.0f} {s['fpc']:7.1f} {s['d_far']:6.1f} {s['d_near']:7.1f} "
              f"{s['cover']:7.2f} {s['ratio2']:10.2f} "
              f"{s['min_pair']:6.1f}-{s['wide_pair']:<7.1f} {s['d_usable']:11.1f}   {c['outcome']}")
    print("\n(1) frames/cycle >= ~8   (2) band/half-dash at the far row: <=1 known to work,"
          " >=4 known to fail   (3) widest pair >= ~4 frames")
    print("'usable to m' = how far this camera can sample before the band swallows half a dash")
    print("(4) a legal periodic dash must actually be painted -- look at one frame per window;"
          " no calculation decides it")
    for c in cams:
        print(f"  {c['name']}: {c['src']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
