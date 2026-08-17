"""Re-report the comma2k19 pipeline-B numbers with the domain split out, and show why.

The first comma2k19 run (2026-08-10) reported coverage 84.3% and MAE 10.54 km/h
against the GNSS/INS pose truth, with a p50 of only 1.20 -- an error distribution
so split that it obviously came from a distinct population, not from noise. That
run attributed the population to raised pavement markers laid between the paint
dashes at half the paint cycle, and concluded that brightness autocorrelation
could not separate two periods that are both physically on the road.

Re-examined on 2026-08-17, that attribution was wrong on both counts, and this
tool is the re-examination. Three things it establishes, in order of how much
they cost:

1. The doubling is a step function of POSITION, not of speed. Along the one
   north-south corridor the segments share, the share of frames locked at half
   the assumed cycle runs 0.0% south of latitude 37.700 and 90.4% north of
   37.715, and the implied cycle there is a clean 7.39 m. Looking at those
   frames settles it: north of the step the car is on a signalised urban
   arterial whose lane dashes really are about half as long, and it only reaches
   the I-280 freeway further south. The segment filter that built the set was
   "median speed >= 70 km/h", which admits a segment that starts on an arterial
   and ends on a freeway. The odometer read the road correctly; a single
   statutory cycle applied to two road classes is what doubled the speed.

2. What remains after excluding the arterial is governed by ILLUMINATION.
   On the freeway, daylight segments lock at half the cycle on 1.0% of frames
   and dark ones on 11.9% -- 16 of 18 daylight segments are at exactly 0.0%.
   Retroreflective markers return headlight glare straight to the camera, so
   after dark they outshine the paint and the dominant period in the brightness
   signal becomes theirs; in daylight the paint dominates and they are invisible
   to the measurement. The original run's "speed-gated" mechanism (a lag floor
   admitting the marker period only below 105 km/h) was a confound: the dark
   segments and the arterial approach are also the slow ones.

3. The pulses in the failing stretches do NOT alternate. Interleaved paint and
   markers would produce a train alternating in width, amplitude, and area
   between neighbours; measured alternation contrast is no higher in half-locked
   windows than in correctly locked ones, and adjacent-pair agreement sits at
   0.53-0.72 against 0.50 for a coin. So the geometry was never paint-plus-marker
   at half the cycle -- it is one uniform train whose period is not the one the
   evaluation assumed.

Everything here recomputes from `per_frame/*.npz` plus the segment positions in
the chunk zip, so it never re-decodes video or re-measures: the numbers are the
same measurement pass as the published run, only grouped honestly.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import zipfile
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# WGS-84, for turning the dataset's ECEF frame positions into latitude/longitude.
WGS84_A = 6378137.0
WGS84_E2 = (1 / 298.257223563) * (2 - 1 / 298.257223563)

# The arterial approach, in the corridor the commute segments share. Latitude
# cut sits south of the last traffic signal and north of the freeway on-ramp;
# the numbers are insensitive to it (37.708 gives MAE 5.23 where 37.712 gives
# 5.32), which is what you expect from a boundary in the road rather than a
# tuned threshold.
CORRIDOR_LON = -122.4715
CORRIDOR_LON_TOL = 0.004
ARTERIAL_LAT_MIN = 37.712


def ecef_to_geodetic(pos: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    x, y, z = pos[:, 0], pos[:, 1], pos[:, 2]
    lon = np.arctan2(y, x)
    r = np.hypot(x, y)
    lat = np.arctan2(z, r * (1 - WGS84_E2))
    for _ in range(6):  # Bowring iteration; converges long before this
        n = WGS84_A / np.sqrt(1 - WGS84_E2 * np.sin(lat) ** 2)
        h = r / np.cos(lat) - n
        lat = np.arctan2(z, r * (1 - WGS84_E2 * n / (n + h)))
    return np.degrees(lat), np.degrees(lon)


def road_luminance(frames_dir: Path, points: np.ndarray, stride: int = 40) -> float:
    """Median grey level of the road around the sampling points.

    The illumination split has to be stated in terms of something the method can
    actually see, not the wall-clock hour: a tunnel at noon and an unlit freeway
    at 21:00 are the same problem. This is that quantity.
    """
    import cv2

    frames = sorted(frames_dir.glob("*.jpg"))[::stride]
    if not frames:
        return float("nan")
    vals = []
    for f in frames:
        g = cv2.cvtColor(cv2.imread(str(f)), cv2.COLOR_BGR2GRAY)
        for (x, y) in points:
            patch = g[max(0, y - 8): y + 9, max(0, x - 120): x + 121]
            if patch.size:
                vals.append(float(np.median(patch)))
    return float(np.median(vals)) if vals else float("nan")


def draw(path: Path, lat_bins: list[dict], per_clip: list[dict], errs: dict,
         cycle: float, lum_threshold: float) -> None:
    """Four panels, in the order the argument actually runs.

    Left column shares a latitude axis so the step in the marking period and the
    step in the failure rate can be read against each other without a second
    y-scale. Labels are English: this box has no CJK font and the README carries
    the prose anyway.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    SURF, INK, INK2 = "#fcfcfb", "#0b0b0b", "#52514e"
    S1, S2, S3 = "#2a78d6", "#eb6834", "#1baf7a"
    GRID = "#e3e2de"

    fig, axes = plt.subplots(2, 2, figsize=(11.5, 8.0), facecolor=SURF)
    for ax in axes.ravel():
        ax.set_facecolor(SURF)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        for s in ("left", "bottom"):
            ax.spines[s].set_color(GRID)
        ax.tick_params(colors=INK2, labelsize=8.5)
        ax.grid(True, color=GRID, linewidth=0.7, alpha=0.9)
        ax.set_axisbelow(True)

    lat = np.array([b["lat_lo"] for b in lat_bins]) + 0.0025
    half = np.array([b["half_pct"] for b in lat_bins])
    imp = np.array([b["implied_median_m"] for b in lat_bins])

    axA = axes[0][0]
    axA.bar(lat, half, width=0.0042, color=S1, linewidth=0)
    axA.set_ylabel("frames locked at half the assumed cycle (%)", color=INK2, fontsize=9)
    axA.set_title("The failure is a step in POSITION", color=INK, fontsize=11, loc="left")
    axA.axvspan(ARTERIAL_LAT_MIN, lat.max() + 0.003, color=S2, alpha=0.10, linewidth=0)
    axA.annotate("signalised arterial\n(shorter statutory dash)", (37.7175, 62),
                 color=INK, fontsize=8.5, ha="center")
    axA.annotate("I-280 freeway", (37.688, 62), color=INK, fontsize=8.5, ha="center")

    axB = axes[1][0]
    axB.plot(lat, imp, color=S1, linewidth=2, marker="o", markersize=5)
    axB.axhline(cycle, color=INK2, linewidth=1, linestyle="--")
    axB.axhline(cycle / 2, color=INK2, linewidth=1, linestyle=":")
    axB.annotate(f"assumed {cycle:.2f} m  (Caltrans freeway 48 ft)", (lat.min(), cycle + 0.6),
                 color=INK2, fontsize=8)
    axB.annotate(f"half = {cycle/2:.2f} m", (lat.min(), cycle / 2 + 0.6), color=INK2, fontsize=8)
    axB.axvspan(ARTERIAL_LAT_MIN, lat.max() + 0.003, color=S2, alpha=0.10, linewidth=0)
    axB.set_xlabel("latitude along the shared corridor (deg N)", color=INK2, fontsize=9)
    axB.set_ylabel("measured cycle, median (m)", color=INK2, fontsize=9)
    axB.set_title("and the road's period really is half there", color=INK, fontsize=11, loc="left")
    axB.set_ylim(5, 17)

    axC = axes[0][1]
    lum = np.array([c["road_luminance"] for c in per_clip])
    hp = np.array([c["half_locked_pct"] for c in per_clip])
    axC.scatter(lum, hp, s=42, color=S1, linewidth=0, zorder=3)
    axC.axvspan(64.0, 69.5, color=INK2, alpha=0.09, linewidth=0)
    axC.annotate("empty gap in the measured\ndistribution -> the cut", (66.8, max(hp) * 0.80),
                 color=INK, fontsize=8.5, ha="center")
    axC.annotate("dark", (58, max(hp) * 0.97), color=INK2, fontsize=9, ha="center")
    axC.annotate("daylight", (73, max(hp) * 0.97), color=INK2, fontsize=9, ha="center")
    axC.set_xlabel("road-surface grey level at the sampling points", color=INK2, fontsize=9)
    axC.set_ylabel("half-locked frames per segment (%)", color=INK2, fontsize=9)
    axC.set_title("What is left on the freeway is ILLUMINATION", color=INK, fontsize=11, loc="left")

    axD = axes[1][1]
    # The three curves' 95% crossings are only a decade apart, which is not enough
    # room on a log axis for three multi-word labels -- direct labels collide
    # whichever side they are placed. So the identity carrier here is a keyed list
    # in the empty lower-right, with each curve's 95% crossing marked on the curve
    # so the numbers in the key can be found on the plot. The labels are visible
    # text, which is also the relief the aqua slot's sub-3:1 contrast requires.
    order = [("all_24_segments", S2, "all 24 segments"),
             ("freeway_only", S3, "arterial excluded"),
             ("freeway_daylight", S1, "arterial excluded, daylight only")]
    handles = []
    for key, colour, label in order:
        if key not in errs:   # --no-luminance leaves the daylight split unpopulated
            continue
        e = np.sort(np.abs(errs[key]))
        y = 100.0 * np.arange(1, e.size + 1) / e.size
        line, = axD.plot(e, y, color=colour, linewidth=2)
        x95 = float(e[min(e.size - 1, int(np.searchsorted(y, 95.0)))])
        axD.plot([x95], [95.0], marker="o", markersize=6, color=colour, linewidth=0, zorder=4)
        line.set_label(f"{label}\nMAE {np.abs(errs[key]).mean():.2f}  ·  95% within {x95:.1f} km/h")
        handles.append(line)
    leg = axD.legend(handles=handles, loc="lower right", frameon=False, fontsize=8.5,
                     labelspacing=0.9, handlelength=1.6, borderaxespad=0.8)
    for t in leg.get_texts():
        t.set_color(INK)
    axD.set_xscale("log")
    axD.set_xlim(0.05, 200)
    axD.axvline(3.0, color=INK2, linewidth=1, linestyle=":")
    axD.annotate("±3 km/h", (3.3, 55), color=INK2, fontsize=8)
    axD.set_xlabel("|speed error| vs GNSS/INS pose truth (km/h)", color=INK2, fontsize=9)
    axD.set_ylabel("share of locked frames below (%)", color=INK2, fontsize=9)
    axD.set_title("Stating the domain moves the whole tail", color=INK, fontsize=11, loc="left")

    fig.suptitle("comma2k19 pipeline-B: the doubled locks are road class and darkness, not markers "
                 "between dashes", color=INK, fontsize=12.5)
    fig.tight_layout(rect=(0, 0, 1, 0.965))
    fig.savefig(path, dpi=150, facecolor=SURF)
    print(f"圖 -> {path}")


def summarise(est: np.ndarray, truth: np.ndarray, n_domain: int, boot: int = 400) -> dict:
    e = est - truth
    ae = np.abs(e)
    rng = np.random.default_rng(0)
    means = [np.abs(rng.choice(e, e.size)).mean() for _ in range(boot)]
    return {"n": int(est.size), "coverage_pct": 100.0 * est.size / max(1, n_domain),
            "mae": float(ae.mean()), "mae_ci95": [float(np.percentile(means, 2.5)),
                                                  float(np.percentile(means, 97.5))],
            "bias": float(e.mean()), "p50": float(np.percentile(ae, 50)),
            "p90": float(np.percentile(ae, 90)), "within3_pct": float(100.0 * (ae <= 3).mean())}


def fmt(label: str, s: dict) -> str:
    return (f"{label:<30s} 覆蓋 {s['coverage_pct']:5.1f}%  n={s['n']:6d}  "
            f"MAE {s['mae']:6.2f} [{s['mae_ci95'][0]:.2f}–{s['mae_ci95'][1]:.2f}]  "
            f"bias {s['bias']:+6.2f}  p50 {s['p50']:5.2f}  p90 {s['p90']:6.2f}  "
            f"±3內 {s['within3_pct']:5.1f}%")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--eval-dir", default=str(PROJECT_ROOT / "data/output/comma2k19_eval"))
    ap.add_argument("--zip", default=str(PROJECT_ROOT / "data/input/comma2k19/Chunk_1.zip"))
    ap.add_argument("--frames-root", default="/tmp/comma_seg",
                    help="Segment dirs, only needed for the road-luminance column.")
    ap.add_argument("--dash-cycle-m", type=float, default=14.63)
    ap.add_argument("--half-tol-m", type=float, default=1.0,
                    help="A frame counts as half-locked when its implied cycle is within "
                         "this of half the assumed one.")
    ap.add_argument("--lum-threshold", type=float, default=66.0,
                    help="Road grey level separating lit from dark segments. The default sits in "
                         "an empty gap in the measured distribution (the segments run 56.0-64.0 "
                         "and then 69.5-76.0, nothing between), so it is read off the data rather "
                         "than tuned; it also agrees with the recording clock time on every "
                         "segment but one, which is genuinely street-lit.")
    ap.add_argument("--no-luminance", action="store_true", help="Skip reading frames.")
    ap.add_argument("--out-json", default="")
    ap.add_argument("--out-png", default="")
    args = ap.parse_args()

    eval_dir = Path(args.eval_dir)
    cycle = args.dash_cycle_m
    seg = {r["tag"]: (r["route"], r["segment"])
           for r in csv.DictReader(open(Path(eval_dir) / "segments.csv", encoding="utf-8"))}
    zf = zipfile.ZipFile(args.zip)

    clips = []
    for f in sorted((eval_dir / "per_frame").glob("*.npz")):
        tag = f.stem
        route, s = seg[tag]
        with zf.open(f"Chunk_1/{route}/{s}/global_pose/frame_positions") as fh:
            lat, lon = ecef_to_geodetic(np.load(io.BytesIO(fh.read())))
        d = np.load(f)
        n = min(len(lat), len(d["inv_t"]))
        rec = {"tag": tag, "lat": lat[:n], "lon": lon[:n], "usable": d["usable"][:n],
               "est": 3.6 * cycle * d["inv_t"][:n], "pose": d["v_alt"][:n],
               "can": d["v_truth"][:n], "points": d["points"]}
        rec["arterial"] = ((np.abs(rec["lon"] - CORRIDOR_LON) < CORRIDOR_LON_TOL)
                           & (rec["lat"] > ARTERIAL_LAT_MIN))
        rec["lum"] = float("nan")
        if not args.no_luminance:
            fd = Path(args.frames_root) / tag / "frames"
            if fd.is_dir():
                rec["lum"] = road_luminance(fd, d["points"])
        clips.append(rec)

    half_lo = cycle / 2 - args.half_tol_m
    half_hi = cycle / 2 + args.half_tol_m

    def pool(pick):
        est, pose, can, dom = [], [], [], 0
        for c in clips:
            m = pick(c)
            dom += int(((c["pose"] >= 25.0) & m).sum())
            u = c["usable"] & m
            est.append(c["est"][u]); pose.append(c["pose"][u]); can.append(c["can"][u])
        est, pose, can = map(np.concatenate, (est, pose, can))
        implied = cycle * pose / np.where(est == 0, np.nan, est)
        half = (implied > half_lo) & (implied < half_hi)
        return est, pose, can, dom, half

    lit = lambda c: (not np.isnan(c["lum"])) and c["lum"] >= args.lum_threshold  # noqa: E731
    views = {
        "all_24_segments": lambda c: np.ones(len(c["lat"]), bool),
        "freeway_only": lambda c: ~c["arterial"],
        "freeway_daylight": lambda c: (~c["arterial"]) & np.full(len(c["lat"]), lit(c)),
        "freeway_dark": lambda c: (~c["arterial"]) & np.full(len(c["lat"]), not lit(c)),
        "arterial_only": lambda c: c["arterial"],
    }
    if all(np.isnan(c["lum"]) for c in clips):
        # Without frames every segment reads as unlit, which would silently
        # relabel the whole freeway subset as "dark" and print it twice.
        for k in ("freeway_daylight", "freeway_dark"):
            views.pop(k)
        print("(未讀影格 → 跳過日夜分層;要它就別加 --no-luminance)")
    labels = {"all_24_segments": "① 全 24 段(原始發表)", "freeway_only": "② 排除幹道段",
              "freeway_daylight": "③ 排除幹道 + 僅日間", "freeway_dark": "  └ 對照:夜間段",
              "arterial_only": "  └ 對照:僅幹道段"}

    print(f"=== comma2k19 管線 B,對 GNSS-INS 位姿真值,cycle 固定 {cycle} m(全程不用真值)===")
    out = {"dash_cycle_m": cycle, "views": {}}
    errs: dict[str, np.ndarray] = {}
    for key, pick in views.items():
        est, pose, can, dom, half = pool(pick)
        if est.size < 20:
            continue
        errs[key] = est - pose
        s = summarise(est, pose, dom)
        s["half_locked_pct"] = float(100.0 * half.mean())
        s_can = summarise(est, can, dom)
        keep = ~half
        s_paint = summarise(est[keep], pose[keep], dom) if keep.sum() > 20 else None
        out["views"][key] = {"pose": s, "can": s_can, "paint_locked_only": s_paint}
        print(fmt(labels[key], s) + f"  半週期 {s['half_locked_pct']:5.1f}%")

    print("\n=== 逐段:照度、路類、半週期率 ===")
    print(f"{'片':>26s} {'時刻':>5s} {'路面灰階':>8s} {'含幹道':>6s} {'n':>5s} {'半週期%':>7s} {'MAE':>6s}")
    per_clip = []
    for c in sorted(clips, key=lambda c: c["lum"] if not np.isnan(c["lum"]) else -1):
        m = ~c["arterial"]
        u = c["usable"] & m
        if u.sum() < 20:
            continue
        implied = cycle * c["pose"][u] / np.where(c["est"][u] == 0, np.nan, c["est"][u])
        half = float(100.0 * ((implied > half_lo) & (implied < half_hi)).mean())
        mae = float(np.abs(c["est"][u] - c["pose"][u]).mean())
        hhmm = c["tag"].split("--")[1][:5].replace("-", ":")
        print(f"{c['tag'][-24:]:>26s} {hhmm:>5s} {c['lum']:8.1f} "
              f"{('是' if c['arterial'].any() else '否'):>6s} {int(u.sum()):5d} {half:7.1f} {mae:6.2f}")
        per_clip.append({"clip": c["tag"], "road_luminance": c["lum"],
                         "touches_arterial": bool(c["arterial"].any()),
                         "n": int(u.sum()), "half_locked_pct": half, "mae_kmh": mae})
    out["per_clip_freeway_part"] = per_clip

    print("\n=== 半週期率 vs 位置(共用走廊,依緯度分箱)===")
    corr = [(c["lat"], c["est"], c["pose"], c["usable"]) for c in clips
            if (np.abs(c["lon"] - CORRIDOR_LON) < CORRIDOR_LON_TOL).mean() > 0.5]
    lat_c = np.concatenate([a[0][a[3]] for a in corr])
    est_c = np.concatenate([a[1][a[3]] for a in corr])
    pose_c = np.concatenate([a[2][a[3]] for a in corr])
    imp_c = cycle * pose_c / np.where(est_c == 0, np.nan, est_c)
    half_c = (imp_c > half_lo) & (imp_c < half_hi)
    bins = []
    print(f"  {'緯度區間':>18s} {'n':>6s} {'半週期%':>8s} {'週期中位':>9s} {'真速中位':>9s}")
    for a in np.arange(np.floor(lat_c.min() * 200) / 200, lat_c.max(), 0.005):
        m = (lat_c >= a) & (lat_c < a + 0.005)
        if m.sum() < 60:
            continue
        row = {"lat_lo": float(a), "n": int(m.sum()), "half_pct": float(100 * half_c[m].mean()),
               "implied_median_m": float(np.nanmedian(imp_c[m])),
               "truth_median_kmh": float(np.median(pose_c[m]))}
        bins.append(row)
        print(f"  {a:8.3f}–{a+0.005:7.3f} {row['n']:6d} {row['half_pct']:8.1f} "
              f"{row['implied_median_m']:9.2f} {row['truth_median_kmh']:9.1f}")
    out["corridor_latitude_bins"] = bins

    if args.out_png:
        draw(Path(args.out_png), bins, per_clip, errs, cycle, args.lum_threshold)

    if args.out_json:
        Path(args.out_json).write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\n已寫出 {args.out_json}")


if __name__ == "__main__":
    main()
