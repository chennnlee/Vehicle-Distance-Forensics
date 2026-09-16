#!/usr/bin/env python3
"""Compare each demo's archived output against a rerun with the current code.

The archived demo videos under data/output/dashcam_demo/ were produced by older
code and WITHOUT the per-device distance correction, so they do not show what the
system does now. Reruns land in <name>_current/. This script puts the two side by
side so the accumulated change is visible and quantified rather than asserted.

Two things move, and they move for different reasons:

  ego speed   -- only the odometer logic changed (one-shot harmonic-comb
                 fundamental selection, then the joint-over-time octave choice).
                 Most frames should be identical; the interesting frames are the
                 ones where the old code locked onto half the true period.
  distance    -- scaled by the per-device correction factor measured from the
                 odometer itself (0.76-0.90 where the quality gate passed, 1.0
                 where it did not). This is a multiplier on forward range only.

Target ids are not comparable across runs (the tracker re-segments), so the
distance panel plots the median over all measured targets per frame, which needs
no id matching.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

DEMO = Path("data/output/dashcam_demo")
# name -> (archived dir, distance-correction applied in the rerun)
CASES = [
    ("dc007", "dc007_trackv3", 1.0),
    ("hs005", "hs005", 0.760),
    ("dc002", "dc002_trackv3", 0.811),
    ("dc008", "dc008_trackv3", 0.854),
    ("dc003", "dc003_trackv3", 1.0),
    ("dc006", "dc006_trackv3", 0.903),
    ("wow001", "wow001", 0.815),
]
OLD, NEW = "#9a9a9a", "#1f6fb4"


def load(dirpath: Path) -> tuple[pd.DataFrame | None, pd.DataFrame | None]:
    ego = dirpath / "ego_speed.csv"
    rng = dirpath / "ranges.csv"
    e = pd.read_csv(ego) if ego.exists() else None
    r = pd.read_csv(rng) if rng.exists() else None
    return e, r


def ego_series(e: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    v = pd.to_numeric(e["ego_visual_kmh"], errors="coerce").to_numpy(dtype=float)
    return e["t_s"].to_numpy(dtype=float), v


def range_median_series(r: pd.DataFrame, near_only: bool) -> tuple[np.ndarray, np.ndarray]:
    """Median measured range per frame over all targets -- no id matching needed."""
    d = r
    if near_only:
        # the archived files predate the far_field column; the rule is identical
        d = d[d["sens_m_per_px"] <= 0.8]
    if d.empty:
        return np.array([]), np.array([])
    g = d.groupby("t_s")["range_m"].median()
    return g.index.to_numpy(dtype=float), g.to_numpy(dtype=float)


def summarize(name: str, old_dir: Path, new_dir: Path, corr: float) -> dict:
    eo, ro = load(old_dir)
    en, rn = load(new_dir)
    row: dict = {"case": name, "corr": corr}

    to, vo = ego_series(eo)
    tn, vn = ego_series(en)
    n = min(len(vo), len(vn))
    both = np.isfinite(vo[:n]) & np.isfinite(vn[:n])
    row["ego_cov_old"] = float(np.isfinite(vo).mean() * 100)
    row["ego_cov_new"] = float(np.isfinite(vn).mean() * 100)
    row["ego_med_old"] = float(np.nanmedian(vo))
    row["ego_med_new"] = float(np.nanmedian(vn))
    d = np.abs(vo[:n][both] - vn[:n][both])
    row["ego_common"] = int(both.sum())
    row["ego_med_abs_diff"] = float(np.median(d)) if both.any() else float("nan")
    row["ego_frames_changed"] = float((d > 0.05).mean() * 100) if both.any() else float("nan")
    row["ego_max_diff"] = float(d.max()) if both.any() else float("nan")

    # Self-check that the rerun used the same geometry as the archive. The
    # correction scales forward range, and sensitivity is its derivative, so
    # A = fwd^2 / sens scales by exactly the correction factor and nothing else.
    # A ratio that misses the factor means a different plane went in (a wrong
    # hood-y or scale), and then the two runs are not comparable at all.
    Ao = (ro["range_m"] ** 2 / ro["sens_m_per_px"]).median()
    An = (rn["range_m"] ** 2 / rn["sens_m_per_px"]).median()
    row["A_ratio"] = float(An / Ao)
    row["A_ratio_expected"] = corr
    row["geometry_ok"] = bool(abs(An / Ao - corr) <= 0.02 * corr)

    for tag, r in (("old", ro), ("new", rn)):
        near = r[r["sens_m_per_px"] <= 0.8]
        row[f"targets_{tag}"] = int(r["track_id"].nunique())
        row[f"obs_{tag}"] = int(len(r))
        row[f"rng_med_{tag}"] = float(r["range_m"].median())
        row[f"rng_med_near_{tag}"] = float(near["range_m"].median()) if len(near) else float("nan")
        spd = pd.to_numeric(near["abs_kmh"], errors="coerce").dropna()
        row[f"spd_med_near_{tag}"] = float(spd.median()) if len(spd) else float("nan")
    return row


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-prefix", default=str(DEMO / "_rerun" / "rerun"))
    ap.add_argument("--near-only", action="store_true",
                    help="Distance panel uses only near-range observations (sens <= 0.8).")
    a = ap.parse_args()
    out = Path(a.out_prefix)
    out.parent.mkdir(parents=True, exist_ok=True)

    cases = [(n, o, c) for n, o, c in CASES if (DEMO / f"{n}_current" / "ego_speed.csv").exists()]
    if not cases:
        raise SystemExit("no <name>_current/ outputs found yet")

    rows = [summarize(n, DEMO / o, DEMO / f"{n}_current", c) for n, o, c in cases]
    df = pd.DataFrame(rows)
    df.to_csv(out.with_name(out.name + "_summary.csv"), index=False)

    print(f"{'case':8s} {'corr':>5s} | {'ego med old->new':>18s} {'cov%':>12s} {'|d| med':>8s} {'chg%':>6s} "
          f"| {'range med old->new':>20s} {'targets':>12s} | {'geom':>14s}")
    for r in rows:
        geom = f"A {r['A_ratio']:.3f}" + ("  ok" if r["geometry_ok"] else "  MISMATCH")
        print(f"{r['case']:8s} {r['corr']:5.3f} | {r['ego_med_old']:8.1f} ->{r['ego_med_new']:7.1f} "
              f"{r['ego_cov_old']:5.1f}->{r['ego_cov_new']:5.1f} {r['ego_med_abs_diff']:8.2f} "
              f"{r['ego_frames_changed']:6.1f} | {r['rng_med_old']:9.1f} ->{r['rng_med_new']:8.1f} "
              f"{r['targets_old']:5d} ->{r['targets_new']:5d} | {geom:>14s}")
    bad = [r["case"] for r in rows if not r["geometry_ok"]]
    if bad:
        print(f"\n  geometry MISMATCH on {', '.join(bad)}: the rerun's plane differs from the archive "
              f"(A should scale by exactly the correction factor). Check hood-y and pointcloud-scale "
              f"before reading anything else in that row.")

    for kind in ("ego", "range"):
        ncol = 2
        nrow = int(np.ceil(len(cases) / ncol))
        fig, axes = plt.subplots(nrow, ncol, figsize=(13, 2.5 * nrow), squeeze=False)
        for ax, (name, old, corr) in zip(axes.ravel(), cases):
            eo, ro = load(DEMO / old)
            en, rn = load(DEMO / f"{name}_current")
            if kind == "ego":
                t, v = ego_series(eo)
                ax.plot(t, v, color=OLD, lw=2.4, label="archived")
                t, v = ego_series(en)
                ax.plot(t, v, color=NEW, lw=1.2, label="current code")
                ax.set_ylabel("ego km/h")
                r = next(x for x in rows if x["case"] == name)
                ax.set_title(f"{name}  median |Δ| {r['ego_med_abs_diff']:.2f} km/h, "
                             f"{r['ego_frames_changed']:.1f}% of frames changed", fontsize=9)
            else:
                t, v = range_median_series(ro, a.near_only)
                ax.plot(t, v, color=OLD, lw=1.6, label="archived")
                t, v = range_median_series(rn, a.near_only)
                ax.plot(t, v, color=NEW, lw=1.2, label="current code")
                ax.set_ylabel("range median (m)")
                r = next(x for x in rows if x["case"] == name)
                tag = "no correction (gate not passed)" if corr == 1.0 else f"×{corr:.3f}"
                ax.set_title(f"{name}  {r['rng_med_old']:.1f} → {r['rng_med_new']:.1f} m   {tag}", fontsize=9)
            ax.grid(alpha=0.25)
            ax.set_xlabel("t (s)")
            ax.legend(fontsize=7, loc="best")
        for ax in axes.ravel()[len(cases):]:
            ax.axis("off")
        fig.suptitle("Ego speed: archived output vs current code" if kind == "ego"
                     else "Target range (per-frame median): archived vs current code, with per-device distance correction",
                     fontsize=11)
        fig.tight_layout(rect=(0, 0, 1, 0.97))
        p = out.with_name(out.name + f"_{kind}.png")
        fig.savefig(p, dpi=140)
        plt.close(fig)
        print("wrote", p)
    print("wrote", out.with_name(out.name + "_summary.csv"))


if __name__ == "__main__":
    main()
