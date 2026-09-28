#!/usr/bin/env python3
"""A quality signal for the marking calibration that needs no factory value.

Why it exists.  The gate the method already has -- the pair-to-pair spread of A within one
lane line -- measures whether a measurement agrees with itself, not whether it is right.
Argoverse 1 showed the difference: four logs passed that gate with spreads of 3.8-6.9% and
came out at +2.4, +4.3, +13.8 and -15.9% against their factory calibration.  A gate that
lets a 16% error through cannot support the claim this method rests on, which is that it
refuses rather than answers wrongly.

What separates them is the horizon.  `d = A/(py - y_h)` has two unknowns, and the pipeline
takes y_h from the lane-line vanishing point and then solves only A.  But the row-pair
distances constrain BOTH: fitting (A, y_h) to them is over-determined once there are three
pairs.  That second estimate of y_h is independent of the lane fit, so the two can be
compared, and on AV1 the disagreement tracks the error's sign and size exactly as the
algebra says it should -- a horizon set too high in the image inflates A, too low deflates
it.

⚠ The fitted (A, y_h) is NOT a better answer.  Substituting it degrades AV2 from 1.7% to
5.8% median error, because A and y_h trade off against each other over a short row span --
the degeneracy CLAUDE.md records for `odometer_distance_calib.py`.  It is usable as a
consistency check and nothing more.

Measured on the eight logs that have both an answer and a factory value (AV2 4, AV1 4):

    |dy_h| <= 6.3 px   ->  error 0.0 - 4.3%   (n=5)
    |dy_h| >= 6.9 px   ->  error 7.8 - 15.9%  (n=3)

⚠ The 7 px threshold is calibrated on those eight, not derived, and the margin between the
last pass (6.3) and the first fail (6.9) is under a pixel.  It is a pre-registered
prediction, not an established rule: it was fixed on 2026-09-28 while the Argoverse 1
training splits were still downloading, precisely so that the logs they produce test it out
of sample.  Whatever those logs do to it goes in the record.

Usage:
  python3 tools/horizon_consistency_gate.py --calib data/output/av1_marking/calib.json \
      --root data/input/av1
"""
from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path

import numpy as np

THRESHOLD_PX = 7.0          # fixed 2026-09-28, before the out-of-sample logs existed


def fit_A_and_horizon(pairs, A0, yh0):
    """Least squares (A, y_h) on dist = A*[1/(y_far-y_h) - 1/(y_near-y_h)]."""
    from scipy.optimize import least_squares
    yf = np.array([e["y_far"] for e in pairs], dtype=float)
    yn = np.array([e["y_near"] for e in pairs], dtype=float)
    dm = np.array([e["dist_m"] for e in pairs], dtype=float)
    s = least_squares(lambda x: x[0] * (1 / (yf - x[1]) - 1 / (yn - x[1])) - dm,
                      [A0, yh0], bounds=([100, 200], [8000, 900]))
    return float(s.x[0]), float(s.x[1]), float(np.abs(s.fun).max())


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--calib", action="append", required=True,
                    help="calib json from av2_marking_calib / av1_marking_run; repeat to pool")
    ap.add_argument("--root", required=True, help="log root, for the factory reference")
    ap.add_argument("--threshold-px", type=float, default=THRESHOLD_PX)
    ap.add_argument("--exclude", default="", help="comma separated log prefixes to leave out")
    args = ap.parse_args()

    skip = tuple(x for x in args.exclude.split(",") if x)
    seen: dict[str, dict] = {}
    for pat in args.calib:
        for f in sorted(glob.glob(pat)):
            if "seed" in Path(f).name:
                continue
            for r in json.loads(Path(f).read_text()):
                seen.setdefault(r.get("log"), (r, Path(f).parent))

    print(f"{'log':10s} {'A marking':>9s} {'VP y_h':>7s} {'fit y_h':>8s} {'|dy_h|':>7s} "
          f"{'gate':>6s} {'factory':>8s} {'error':>7s}")
    rows = []
    for lg, (r, out_dir) in seen.items():
        if lg[:8] in skip or r.get("status") != "ok":
            continue
        p = out_dir / f"A_{lg[:8]}.json"
        if not p.exists():
            continue
        pairs = [e for L in json.loads(p.read_text())["lines"] if L.get("accepted")
                 for e in L["pairs"]]
        if len(pairs) < 3:
            print(f"{lg[:8]:10s} fewer than three pairs -- the fit is not over-determined")
            continue
        A_f, yh_f, resid = fit_A_and_horizon(pairs, r["A_marking"], r["y_h"])
        d = abs(yh_f - r["y_h"])
        ok = d <= args.threshold_px
        ref = Path(args.root) / lg / "factory_reference.json"
        if ref.exists():
            fa = json.loads(ref.read_text())["A_factory"]
        else:
            meta = Path(args.root) / lg / "pinhole_meta.json"
            fa = json.loads(meta.read_text()).get("A_factory")
        err = (r["A_marking"] / fa * 100 - 100) if fa else float("nan")
        rows.append((d, abs(err), ok))
        print(f"{lg[:8]:10s} {r['A_marking']:9.0f} {r['y_h']:7.1f} {yh_f:8.1f} {d:7.1f} "
              f"{'pass' if ok else 'REJECT':>6s} {fa or float('nan'):8.0f} {err:+6.1f}%")

    if rows:
        a = np.array([(d, e) for d, e, _ in rows])
        kept = np.array([e for _, e, ok in rows if ok])
        drop = np.array([e for _, e, ok in rows if not ok])
        print(f"\nthreshold {args.threshold_px:g} px: {len(kept)} pass, {len(drop)} reject")
        if kept.size:
            print(f"  passing  |error| median {np.median(kept):5.1f}%  max {kept.max():5.1f}%")
        if drop.size:
            print(f"  rejected |error| median {np.median(drop):5.1f}%  min {drop.min():5.1f}%")
        if a.shape[0] > 2:
            from scipy.stats import spearmanr
            rho, p = spearmanr(a[:, 0], a[:, 1])
            print(f"  |dy_h| vs |error|: Spearman rho {rho:+.2f} (p {p:.3f}, n {a.shape[0]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
