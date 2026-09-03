"""距離修正係數圖(報告用)——直接讀 `_calib/*.json`,不重跑量測。

左圖是證據:每一組取樣列對的「碼表實測間距」對「SHARP 平面預測間距」。全部落在
對角線下方 = SHARP 距離系統性偏高。右圖是效果:目標車跟車距離中位數的前後對照。

⚠ 只畫通過品質閘(逐對散布 ≤ 0.10)的案。wow001 / dc003 / dc007 未通過,列在圖說裡
說明為什麼被拒發 —— 報告不能把拒發的案混進效果圖裡當成果。

用法:python tools/report/plot_distance_calib.py
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DEMO = ROOT / "data/output/dashcam_demo"
CALIB = DEMO / "_calib"
ORDER = ["hs005", "dc006", "dc008", "dc002", "dc003", "dc007", "wow001"]
MARKERS = {"hs005": "o", "dc006": "s", "dc002": "D", "dc008": "v", "wow001": "^", "dc003": "P"}

cases = {}
for name in ORDER:
    f = CALIB / f"{name}.json"
    if f.exists():
        cases[name] = json.loads(f.read_text(encoding="utf-8"))

fig, (axL, axR) = plt.subplots(1, 2, figsize=(13.6, 5.1))

# ---- 左:逐列對的實測 vs 預測 -------------------------------------------------
hi = 0.0
for name, r in cases.items():
    if not r.get("usable"):
        continue
    pred = np.array(r["pred_m"])
    meas = np.array(r["meas_m"])
    hi = max(hi, pred.max(), meas.max())
    axL.scatter(pred, meas, s=64, marker=MARKERS.get(name, "o"), color="#2A78D6",
                edgecolor="white", linewidth=0.6, zorder=3,
                label=f"{name}  ×{r['distance_correction']:.2f}")
# 被拒發的案也畫出來(灰色空心):品質閘擋掉的長相要看得見,不能只秀漂亮的
for name, r in cases.items():
    if r.get("usable") or not r.get("pred_m"):
        continue
    pred, meas = np.array(r["pred_m"]), np.array(r["meas_m"])
    hi = max(hi, pred.max(), meas.max())
    axL.scatter(pred, meas, s=70, marker="x", color="#999", linewidth=1.8, zorder=2,
                label=f"{name}  rejected (spread {r['ratio_spread']:.2f})")
lim = hi * 1.12
axL.plot([0, lim], [0, lim], "--", color="#555", lw=1.2, zorder=1)
axL.text(lim * 0.72, lim * 0.79, "agreement", rotation=38, color="#555", fontsize=11)
axL.set_xlim(0, lim); axL.set_ylim(0, lim)
axL.set_xlabel("row spacing predicted by the SHARP plane (m)")
axL.set_ylabel("row spacing measured by the odometer (m)")
axL.set_title("Evidence: every row pair falls below agreement", loc="left", fontsize=13)
axL.legend(frameon=False, fontsize=11, loc="upper left")
axL.grid(alpha=0.25)

# ---- 右:跟車距離中位數的前後對照 ---------------------------------------------
rows = []
for name, r in cases.items():
    if not r.get("usable"):
        continue
    src = DEMO / (f"{name}_trackv3" if (DEMO / f"{name}_trackv3/ranges.csv").exists() else name)
    df = pd.read_csv(src / "ranges.csv")
    med = float(df["range_m"].median())
    rows.append((name, med, med * r["distance_correction"]))
rows.sort(key=lambda t: t[1])

y = np.arange(len(rows))
axR.barh(y - 0.19, [t[1] for t in rows], height=0.36, color="#EB6834", label="as published")
axR.barh(y + 0.19, [t[2] for t in rows], height=0.36, color="#2A78D6", label="odometer-calibrated")
for i, (_, a, b) in enumerate(rows):
    axR.text(a + 0.6, i - 0.19, f"{a:.1f}", va="center", fontsize=11, color="#52514E")
    axR.text(b + 0.6, i + 0.19, f"{b:.1f}", va="center", fontsize=11, color="#0B0B0B", fontweight="bold")
axR.set_yticks(y, [t[0] for t in rows])
axR.set_xlim(0, max(t[1] for t in rows) * 1.22)
axR.set_xlabel("median target following distance (m)")
axR.set_title("Effect: reported distances shrink 10-24%", loc="left", fontsize=13)
axR.legend(frameon=False, fontsize=11, loc="lower right")
axR.grid(alpha=0.25, axis="x")

fig.suptitle("Dashcam range scale measured from the odometer signal alone "
             "(no plane, no point cloud, no lane width)", fontsize=14, y=0.98)
fig.tight_layout(rect=(0, 0, 1, 0.94))
out = CALIB / "effect.png"
fig.savefig(out, dpi=150)
print(f"已寫出 {out}")
for name, r in cases.items():
    tag = "可用" if r.get("usable") else f"拒發(散布 {r.get('ratio_spread', float('nan')):.3f})"
    print(f"  {name:7s} ×{r['distance_correction']:.3f}  {len(r.get('pred_m', []))} 組列對  {tag}")
