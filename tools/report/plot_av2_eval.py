#!/usr/bin/env python3
"""Draw the Argoverse 2 external check: what the markings recover, and what the depth
model does once the markings have scaled it.

Three panels, because the experiment answers three separate questions:

  left    Does the marking measurement recover the factory scale constant A = h*f?
          One point per log, with the pair-to-pair spread as the error bar.  The logs the
          quality gate rejected are not here -- that is the point of the gate -- and the
          one log that passed the gate and is still 23% out is drawn in red, because a
          figure that hides its failure is worth nothing.
  middle  Predicted distance against the lidar cuboid, per target.
  right   Relative error against distance, which is where a scale error (flat line) and a
          horizon error (rising line) look different.

Usage:
  python3 tools/report/plot_av2_eval.py --calib data/output/av2_marking/calib.json \
      --eval "data/output/av2_depth/eval_*.json" --out data/output/av2_depth/av2_results.png
"""
from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

INK, ACCENT, WARN, MUTED = "#1f2933", "#1f4e79", "#c0392b", "#7b8794"


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--calib", required=True)
    ap.add_argument("--eval", required=True, help="glob of eval_*.json from av2_eval.py")
    ap.add_argument("--model", default="metric3d_v2", help="model drawn in the scatter panels")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    cal = [c for c in json.loads(Path(args.calib).read_text())]
    ok = [c for c in cal if c.get("status") == "ok"]
    evals = [json.loads(Path(p).read_text()) for p in sorted(glob.glob(args.eval))]

    fig, ax = plt.subplots(1, 3, figsize=(15.5, 4.8))

    # ---- panel 1: marking A vs factory A
    a = ax[0]
    for c in ok:
        bad = abs(c["ratio"] - 1) > 0.10
        a.errorbar(c["A_factory"], c["A_marking"], yerr=c["A_marking"] * c["spread"] / 2,
                   fmt="o", ms=7, color=WARN if bad else ACCENT, capsize=3, zorder=3)
        a.annotate(f"{c['log'][:8]}\n{c['ratio'] * 100 - 100:+.1f}%",
                   (c["A_factory"], c["A_marking"]), textcoords="offset points",
                   xytext=(9, -4), fontsize=8, color=WARN if bad else MUTED)
    lo = min([c["A_factory"] for c in ok] + [c["A_marking"] for c in ok]) * 0.92
    hi = max([c["A_factory"] for c in ok] + [c["A_marking"] for c in ok]) * 1.06
    a.plot([lo, hi], [lo, hi], "-", color=MUTED, lw=1, zorder=1)
    a.fill_between([lo, hi], [lo * 0.95, hi * 0.95], [lo * 1.05, hi * 1.05],
                   color=ACCENT, alpha=0.07, zorder=0, label="±5%")
    a.set_xlim(lo, hi); a.set_ylim(lo, hi)
    a.set_xlabel("factory  A = h·f  [px·m]"); a.set_ylabel("markings only  A  [px·m]")
    a.set_title(f"scale constant from road markings\n{len(ok)} of {len(cal)} logs passed the gates",
                fontsize=10, color=INK)
    a.legend(fontsize=8, loc="upper left")

    # ---- panels 2,3: distance
    rows = []
    for e in evals:
        p = Path(args.eval).parent / f"eval_{e['log']}_rows.csv"
        if p.exists():
            d = pd.read_csv(p)
            d["log"] = e["log"][:8]
            k = e["models"].get(args.model, {}).get("k_marking", np.nan)
            d["scaled"] = d[args.model] * k
            rows.append(d)
    if rows:
        R = pd.concat(rows)
        b, c = ax[1], ax[2]
        for i, (lg, d) in enumerate(R.groupby("log")):
            col = plt.cm.viridis(i / max(len(R.log.unique()) - 1, 1) * 0.8)
            b.scatter(d.gt_m, d.scaled, s=12, alpha=0.55, color=col, label=lg)
            c.scatter(d.gt_m, (d.scaled - d.gt_m) / d.gt_m * 100, s=12, alpha=0.55, color=col)
        m = [R.gt_m.min() * 0.9, R.gt_m.max() * 1.05]
        b.plot(m, m, color=MUTED, lw=1)
        b.fill_between(m, [x * 0.9 for x in m], [x * 1.1 for x in m], color=ACCENT, alpha=0.07)
        b.set_xlabel("lidar cuboid distance [m]"); b.set_ylabel(f"{args.model} × marking k  [m]")
        b.set_title(f"{len(R)} targets, {R.log.nunique()} logs\nshaded ±10%", fontsize=10, color=INK)
        b.legend(fontsize=8, loc="upper left")
        c.axhline(0, color=MUTED, lw=1)
        c.axhline(10, color=MUTED, lw=0.6, ls=":"); c.axhline(-10, color=MUTED, lw=0.6, ls=":")
        c.set_xlabel("lidar cuboid distance [m]"); c.set_ylabel("relative error [%]")
        c.set_title("error against distance\n(flat = scale error, sloped = horizon error)",
                    fontsize=10, color=INK)
        c.set_ylim(-45, 45)

    for x in ax:
        x.grid(alpha=0.25, lw=0.6)
        for s in ("top", "right"):
            x.spines[s].set_visible(False)
    fig.tight_layout()
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out, dpi=150)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    raise SystemExit(main())
