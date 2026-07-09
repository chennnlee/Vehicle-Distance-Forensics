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
SERIES_3 = "#eda100"  # categorical slot 3: manual frame-count GT segments (direct-labeled per relief rule)
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
        # Empty cells are honest "no lock" readings; the line simply breaks there.
        v = np.array([float(r["ego_visual_kmh"]) if r["ego_visual_kmh"] else np.nan for r in rows])
        gps = np.array(case["gps"], dtype=float)
        tg = np.arange(len(gps)) * float(case.get("gps_dt", 2.0))

        ax.plot(t, v, color=SERIES_1, lw=2, label="visual (dash-cycle odometer)", zorder=3)
        ax.scatter(tg, gps, s=64, color=SERIES_2, zorder=4, label="GPS (dashcam OSD)")

        # Optional manual frame-count ground-truth segments (e.g. the
        # forensic lab's per-segment speeds), drawn over their time spans.
        for k, seg in enumerate(case.get("segments", [])):
            t0, t1, kph = seg["t0"], seg["t1"], seg["kph"]
            ax.plot([t0, t1], [kph, kph], color=SERIES_3, lw=4, solid_capstyle="butt", zorder=5,
                    label="manual frame-count GT" if k == 0 else None)
            ax.annotate(f"{kph:g}", ((t0 + t1) / 2, kph), textcoords="offset points",
                        xytext=(0, 8), ha="center", color=INK, fontsize=9)

        good = np.isfinite(v)
        vi = np.interp(tg, t[good], v[good]) if good.any() else np.full_like(gps, np.nan)
        has_reading = np.array([np.isfinite(v[np.abs(t - tt) < 1.0]).any() for tt in tg])
        mae = float(np.mean(np.abs(vi[has_reading] - gps[has_reading]))) if has_reading.any() else float("nan")
        bias = float(np.mean(vi[has_reading] - gps[has_reading])) if has_reading.any() else float("nan")
        ax.set_title(f"{case['name']}   MAE {mae:.1f} km/h, bias {bias:+.1f} km/h vs GPS (where locked)",
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
        t_last = t[good][-1] if good.any() else t[-1]
        v_last = v[good][-1] if good.any() else 0.0
        ax.annotate("visual", (t_last, v_last), textcoords="offset points", xytext=(6, 2),
                    color=INK, fontsize=9)
        ax.annotate("GPS", (tg[-1], gps[-1]), textcoords="offset points", xytext=(6, -12),
                    color=INK, fontsize=9)
        ax.legend(loc="lower right", frameon=False, fontsize=9, labelcolor=INK)
        lo = min(np.nanmin(v) if good.any() else 0.0, gps.min()) - 6
        hi = max(np.nanpercentile(v, 98) if good.any() else 0.0, gps.max()) + 6
        ax.set_ylim(max(0, lo), hi)

    fig.tight_layout()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=160)
    print(f"saved: {out}")


if __name__ == "__main__":
    main()
