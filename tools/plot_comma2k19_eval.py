"""Two figures for the comma2k19 ego-speed evaluation.

Left: the distribution of the *inverted* cycle (cycle = v_truth x T) over every
locked frame. It has two clusters, and both are real road furniture -- the 48 ft
painted dash cycle and the raised markers at half of it -- which is the whole
finding, so the figure shows the distribution rather than a summary statistic.

Right: how often the odometer latches onto the marker spacing instead of the
paint, as a function of true speed. The rate collapses above ~105 km/h because
the odometer's own lag floor (0.25 s) puts the marker period outside the search
range there -- a boundary that is calculable, not empirical, so it is drawn.

Reads the per-frame .npz dumps written by public_dataset_ego_eval.py --dump-dir.
Labels are English: this box has no CJK font, and the surrounding README carries
the Chinese narration.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

SERIES_1 = "#2a78d6"
SERIES_3 = "#eda100"
INK = "#333333"
INK_MUTED = "#767676"
GRID = "#e3e3e0"

PAINT_M = 14.63   # Caltrans freeway lane line: 12 ft stripe + 36 ft gap
MARKER_M = 7.32   # raised markers land midway in the gap -> half the paint cycle
# The odometer refuses lags below 0.25 s, so a period of MARKER_M metres is only
# inside its search range while the car is slower than this.
LAG_FLOOR_KMH = MARKER_M / 0.25 * 3.6


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump-dir", required=True)
    ap.add_argument("--truth", choices=("can", "pose"), default="pose")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    implied, truth = [], []
    for f in sorted(Path(args.dump_dir).glob("*.npz")):
        d = np.load(f)
        u = d["usable"]
        v = (d["v_alt"] if args.truth == "pose" and d["v_alt"].size else d["v_truth"])[u]
        implied.append((v / 3.6) / d["inv_t"][u])
        truth.append(v)
    implied = np.concatenate(implied)
    truth = np.concatenate(truth)
    half = (implied / PAINT_M >= 0.4) & (implied / PAINT_M < 0.6)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12.5, 4.6))

    ax1.hist(implied, bins=np.arange(4.0, 18.01, 0.2), color=SERIES_1, edgecolor="white", linewidth=0.4)
    for x, lab in ((MARKER_M, "raised markers\n24 ft = 7.32 m"), (PAINT_M, "painted cycle\n48 ft = 14.63 m")):
        ax1.axvline(x, color=INK, linewidth=1.0, linestyle=(0, (4, 3)))
        ax1.annotate(lab, (x, ax1.get_ylim()[1]), xytext=(4, -4), textcoords="offset points",
                     va="top", ha="left", fontsize=9, color=INK)
    ax1.set_xlabel("inverted cycle  $v_{truth}\\cdot T$  (m)", color=INK)
    ax1.set_ylabel("locked frames", color=INK)
    ax1.set_title(f"Both road periods are real  (n={implied.size} frames, "
                  f"{100*(~half).mean():.1f}% off the marker period)", color=INK, fontsize=11)

    edges = [60, 70, 80, 90, 100, 105, 110, 120, 140]
    share, labels, cut = [], [], None
    for i, (lo, hi) in enumerate(zip(edges[:-1], edges[1:])):
        m = (truth >= lo) & (truth < hi)
        if m.sum() < 50:
            continue
        # The lag floor turns the marker period unreachable at LAG_FLOOR_KMH.
        # Draw it at its true position, which is generally inside a bar, not on
        # a band edge -- rounding it to an edge would overstate how sharp it is.
        if lo <= LAG_FLOOR_KMH < hi:
            cut = len(share) - 0.5 + (LAG_FLOOR_KMH - lo) / (hi - lo)
        share.append(half[m].mean() * 100)
        labels.append(f"{lo}-{hi}\nn={m.sum()}")
    xs = np.arange(len(share))
    ax2.bar(xs, share, width=0.72, color=SERIES_1, edgecolor="white", linewidth=1.0)
    for x, s in zip(xs, share):
        ax2.annotate(f"{s:.1f}%", (x, s), xytext=(0, 3), textcoords="offset points",
                     ha="center", fontsize=9, color=INK)
    if cut is not None:
        ax2.axvline(cut, color=SERIES_3, linewidth=2.0)
        ax2.annotate(f"above {LAG_FLOOR_KMH:.0f} km/h the 24 ft marker period\n"
                     "falls outside the 0.25 s lag floor",
                     (cut + 0.15, max(share) * 0.72), fontsize=9, color=INK)
    ax2.set_xticks(xs, labels, color=INK)
    ax2.set_xlabel("true speed (km/h)", color=INK)
    ax2.set_ylabel("frames locked on the marker period (%)", color=INK)
    ax2.set_title("The half-cycle lock is speed-gated, not random", color=INK, fontsize=11)

    for ax in (ax1, ax2):
        ax.grid(axis="y", color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        for s in ("left", "bottom"):
            ax.spines[s].set_color(GRID)
        ax.tick_params(colors=INK_MUTED, labelsize=9)

    fig.suptitle(f"comma2k19 I-280, 24 segments / 24 min of highway  —  truth = {args.truth}",
                 color=INK, fontsize=12)
    fig.tight_layout()
    fig.savefig(args.out, dpi=150, facecolor="white")
    print("wrote", args.out)


if __name__ == "__main__":
    main()
