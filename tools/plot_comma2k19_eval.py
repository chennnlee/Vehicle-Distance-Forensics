"""Two figures for the comma2k19 ego-speed evaluation: the raw error structure.

Left: the distribution of the *inverted* cycle (cycle = v_truth x T) over every
locked frame. It has two clusters, so the figure shows the distribution rather
than a summary statistic -- a mean over a bimodal population describes neither
mode.

Right: how often the measured period comes out at half the assumed one, binned by
true speed. The odometer refuses lags below 0.25 s, which does put a hard upper
bound on the speed at which a 7.32 m period is reachable at all, and that bound
is calculable rather than fitted, so it is drawn.

WHAT THESE TWO PANELS DO NOT SHOW is why the second cluster exists. When this
figure was first made (2026-08-10) the shape was read as raised pavement markers
laid at half the paint cycle, with the speed dependence as the mechanism. Both
readings were wrong: the second cluster is mostly a genuinely shorter statutory
dash cycle on the signalised arterial that the segment filter let in, plus, on
the freeway proper, a period that only surfaces after dark. The apparent speed
dependence is a confound -- the arterial stretch and the night recordings are
also the slow ones. See `comma2k19_domain_eval.py` and domain_split.png, which
carry the actual explanation; keep these panels for the distribution shape only.

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
SHORT_M = 7.32    # half the freeway cycle: what the arterial approach actually measures
# The odometer refuses lags below 0.25 s, so a period of SHORT_M metres is only
# inside its search range while the car is slower than this. A reachability bound,
# not the reason the short period gets picked when it is reachable.
LAG_FLOOR_KMH = SHORT_M / 0.25 * 3.6


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
    for x, lab in ((SHORT_M, "half cycle\n24 ft = 7.32 m"), (PAINT_M, "assumed cycle\n48 ft = 14.63 m")):
        ax1.axvline(x, color=INK, linewidth=1.0, linestyle=(0, (4, 3)))
        ax1.annotate(lab, (x, ax1.get_ylim()[1]), xytext=(4, -4), textcoords="offset points",
                     va="top", ha="left", fontsize=9, color=INK)
    ax1.set_xlabel("inverted cycle  $v_{truth}\\cdot T$  (m)", color=INK)
    ax1.set_ylabel("locked frames", color=INK)
    ax1.set_title(f"The error population is bimodal, so no mean describes it  "
                  f"(n={implied.size} frames, {100*(~half).mean():.1f}% on the assumed cycle)",
                  color=INK, fontsize=11)

    edges = [60, 70, 80, 90, 100, 105, 110, 120, 140]
    share, labels, cut = [], [], None
    for i, (lo, hi) in enumerate(zip(edges[:-1], edges[1:])):
        m = (truth >= lo) & (truth < hi)
        if m.sum() < 50:
            continue
        # The lag floor turns the short period unreachable at LAG_FLOOR_KMH.
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
        ax2.annotate(f"above {LAG_FLOOR_KMH:.0f} km/h a 24 ft period is\n"
                     "unreachable (0.25 s lag floor) -- but below it,\n"
                     "road class and darkness decide, not speed",
                     (cut + 0.15, max(share) * 0.72), fontsize=9, color=INK)
    ax2.set_xticks(xs, labels, color=INK)
    ax2.set_xlabel("true speed (km/h)", color=INK)
    ax2.set_ylabel("frames measuring half the assumed cycle (%)", color=INK)
    ax2.set_title("Speed only bounds it; see domain_split.png for the cause", color=INK, fontsize=11)

    for ax in (ax1, ax2):
        ax.grid(axis="y", color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        for s in ("left", "bottom"):
            ax.spines[s].set_color(GRID)
        ax.tick_params(colors=INK_MUTED, labelsize=9)

    fig.suptitle(f"comma2k19, 24 segments / 24 min  (I-280 plus an arterial approach)  "
                 f"—  truth = {args.truth}", color=INK, fontsize=12)
    fig.tight_layout()
    fig.savefig(args.out, dpi=150, facecolor="white")
    print("wrote", args.out)


if __name__ == "__main__":
    main()
