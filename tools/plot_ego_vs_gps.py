from __future__ import annotations

"""Validation figure: visual ego speed (dash-cycle odometer) vs dashcam GPS.

The GPS values are transcribed from the video's own burned-in OSD -- an
independent sensor, so the comparison is non-circular. Chart follows the
dataviz rules: one axis, categorical slots in fixed order, direct labels,
recessive grid, text in ink colors.
"""

import argparse
import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

SERIES_1 = "#2a78d6"  # categorical slot 1: visual estimate line
SERIES_2 = "#1baf7a"  # categorical slot 2: GPS truth dots (direct-labeled)
INK = "#333333"
INK_MUTED = "#767676"
GRID = "#e3e3e0"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", required=True,
                    help="JSON list: [{'name':..., 'ego_csv':..., 'gps':[..], 'gps_dt':2.0}, ...]")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    cases = json.loads(Path(args.cases).read_text())

    fig, axes = plt.subplots(len(cases), 1, figsize=(9, 3.1 * len(cases)), sharex=False)
    if len(cases) == 1:
        axes = [axes]
    for ax, case in zip(axes, cases):
        rows = list(csv.DictReader(open(case["ego_csv"])))
        t = np.array([float(r["t_s"]) for r in rows])
        v = np.array([float(r["ego_visual_kmh"]) for r in rows])
        gps = np.array(case["gps"], dtype=float)
        tg = np.arange(len(gps)) * float(case.get("gps_dt", 2.0))

        ax.plot(t, v, color=SERIES_1, lw=2, label="visual (dash-cycle odometer)", zorder=3)
        ax.scatter(tg, gps, s=64, color=SERIES_2, zorder=4, label="GPS (dashcam OSD)")

        vi = np.interp(tg, t, v)
        mae = float(np.mean(np.abs(vi - gps)))
        bias = float(np.mean(vi - gps))
        ax.set_title(f"{case['name']}   MAE {mae:.1f} km/h, bias {bias:+.1f} km/h vs GPS",
                     color=INK, fontsize=11, loc="left")
        ax.set_ylabel("speed (km/h)", color=INK)
        ax.set_xlabel("time in clip (s)", color=INK)
        ax.grid(color=GRID, lw=0.8)
        ax.set_axisbelow(True)
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)
        for spine in ("left", "bottom"):
            ax.spines[spine].set_color(INK_MUTED)
        ax.tick_params(colors=INK_MUTED)
        # direct labels near the series ends (identity never color-alone)
        ax.annotate("visual", (t[-1], v[-1]), textcoords="offset points", xytext=(6, 2),
                    color=INK, fontsize=9)
        ax.annotate("GPS", (tg[-1], gps[-1]), textcoords="offset points", xytext=(6, -12),
                    color=INK, fontsize=9)
        ax.legend(loc="lower right", frameon=False, fontsize=9, labelcolor=INK)
        lo = min(v.min(), gps.min()) - 6
        hi = max(np.percentile(v, 98), gps.max()) + 6
        ax.set_ylim(max(0, lo), hi)

    fig.tight_layout()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=160)
    print(f"saved: {out}")


if __name__ == "__main__":
    main()
