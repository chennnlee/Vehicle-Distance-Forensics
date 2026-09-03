"""Evidence figure for the radar validation: where the range agrees, and what
averaging buys on the speed. Reads the evaluator's JSON, so it redraws without
re-running anything."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ap = argparse.ArgumentParser()
ap.add_argument("--json", nargs="+", required=True)
ap.add_argument("--out", required=True)
a = ap.parse_args()

runs = [json.loads(Path(p).read_text(encoding="utf-8")) for p in a.json]
fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.3))
colors = ["#1f4e79", "#c0504d", "#4f8a2f"]

ax = axes[0]
for r, c in zip(runs, colors):
    b = r["range"]["bands"]
    xs = [0.5 * (q["lo"] + q["hi"]) for q in b]
    ax.plot(xs, [q["ratio"] for q in b], "o-", color=c, label=r["label"])
ax.axhline(1.0, color="#888", lw=1, ls="--")
# The pipeline's own near/far boundary: sens = fwd^2/A <= 0.8 m/px, i.e. fwd <= sqrt(0.8 A).
# With A ~ 1200-1440 on this camera that is ~31-34 m, so the band is drawn at 32 m.
ax.axvspan(0, 32, color="#4f8a2f", alpha=0.07)
lo, hi = ax.get_ylim()
ax.text(16, hi - 0.06 * (hi - lo), "near field the pipeline trusts\n(sens <= 0.8 m/px)",
        ha="center", va="top", fontsize=8, color="#3c6b23")
ax.set_xlabel("radar range (m)")
ax.set_ylabel("radar / ours")
ax.set_title("Following distance vs factory radar")
ax.legend(fontsize=8)
ax.grid(alpha=0.25)

ax = axes[1]
for r, c in zip(runs, colors):
    ws, ys = [], []
    for k, v in r["speed_avg"].items():
        if v["end_to_end"]["n"] and v["end_to_end"]["mae"] == v["end_to_end"]["mae"]:
            ws.append(float(k.rstrip("s")))
            ys.append(v["end_to_end"]["mae"])
    ax.plot(ws, ys, "o-", color=c, label=r["label"])
ax.set_xlabel("averaging window (s)")
ax.set_ylabel("target speed MAE (km/h)")
ax.set_title("Averaging absorbs the frame-to-frame noise")
ax.grid(alpha=0.25)
ax.legend(fontsize=8)

fig.tight_layout()
fig.savefig(a.out, dpi=150)
print("wrote", a.out)
