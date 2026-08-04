"""Locate lane lines by accumulating local contrast over many frames.

Picking odometer sample points by eye does not work: in any single frame the
paint exists only where a dash happens to be, so you end up guessing where the
line runs. Averaging the local-contrast response over a few hundred frames of
in-lane driving smears the intermittent dashes into a continuous ridge whose
per-row peak is well defined -- solid lines come out strong, dashed lines come
out weaker but still unambiguous, and that strength difference itself tells you
which line is which (only the dashed one carries a period the odometer can lock
onto).

It also exposes the trap CLAUDE.md warns about: continuous longitudinal bright
streaks (tyre polish, repair seams) look like ridges but have no period, and
sampling on one of them is why hs003s scored 31% coverage / MAE 25.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--frames-dir", required=True)
    ap.add_argument("--first", type=int, default=1, help="1-based first frame.")
    ap.add_argument("--last", type=int, default=0, help="1-based last frame; 0 = all.")
    ap.add_argument("--step", type=int, default=2)
    ap.add_argument("--rows", required=True, help="Comma-separated image rows to report peaks for.")
    ap.add_argument("--band-px", type=int, default=60, help="Non-max suppression half-width between peaks.")
    ap.add_argument("--min-score", type=float, default=1.0, help="Ignore peaks weaker than this.")
    ap.add_argument("--out", default="", help="Optional heat-map PNG (rows marked).")
    ap.add_argument("--crop", default="", help="Optional y0,y1 to crop the output image to the road band.")
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    d = Path(args.frames_dir)
    fs = sorted(list(d.glob("*.jpg")) + list(d.glob("*.png")))
    if not fs:
        raise SystemExit(f"no frames in {d}")
    fs = fs[args.first - 1: (args.last or len(fs)): args.step]

    acc = None
    for f in fs:
        g = cv2.cvtColor(cv2.imread(str(f)), cv2.COLOR_BGR2GRAY).astype(np.float32)
        # Same local-contrast response the odometer itself uses, so the ridge
        # you see here is the signal the odometer will actually get.
        diff = cv2.subtract(g, cv2.GaussianBlur(g, (51, 51), 0))
        acc = diff if acc is None else acc + diff
    acc /= len(fs)
    print(f"accumulated {len(fs)} frames from {d}")

    vis = cv2.applyColorMap(cv2.normalize(acc, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8),
                            cv2.COLORMAP_JET)
    for y in (int(r) for r in args.rows.split(",") if r.strip()):
        if not 0 <= y < acc.shape[0]:
            print(f"  row {y}: outside image")
            continue
        prof = np.clip(acc[y], 0, None)
        work, peaks = prof.copy(), []
        for _ in range(6):
            x = int(np.argmax(work))
            if work[x] <= 0:
                break
            peaks.append((x, float(prof[x])))
            work[max(0, x - args.band_px): x + args.band_px + 1] = 0
        peaks = [p for p in sorted(peaks) if p[1] > args.min_score]
        print(f"  row {y:4d}: " + "   ".join(f"x={x} s={s:.1f}" for x, s in peaks))
        cv2.line(vis, (0, y), (vis.shape[1], y), (255, 255, 255), 1)
        for x, _ in peaks:
            cv2.circle(vis, (x, y), 5, (255, 255, 255), 2)

    if args.out:
        if args.crop:
            y0, y1 = (int(v) for v in args.crop.split(","))
            vis = vis[y0:y1]
        cv2.imwrite(args.out, vis)
        print("wrote", args.out)


if __name__ == "__main__":
    main()
