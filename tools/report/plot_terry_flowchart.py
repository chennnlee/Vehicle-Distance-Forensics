#!/usr/bin/env python3
"""Flowchart of Terry's part of the project, drawn in the same visual language as the
teammate's pipeline-B chart (red border = implemented by me, grey = existing model).

A third style marks the teammate's components that this part reuses -- the cross-row lag
measurement (odometer_distance_calib.py), the lane-line fit and the ego-speed odometer --
so the chart does not claim them.

    python3 tools/report/plot_terry_flowchart.py --out data/output/terry_flowchart
"""
import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyBboxPatch

WIN_FONTS = Path("/mnt/c/Windows/Fonts")
for name in ("arial.ttf", "arialbd.ttf", "ariali.ttf"):
    if (WIN_FONTS / name).exists():
        font_manager.fontManager.addfont(str(WIN_FONTS / name))
plt.rcParams["font.family"] = ["Arial", "DejaVu Sans"]
plt.rcParams["svg.fonttype"] = "none"   # keep text as text so the SVG stays editable

RED, RED_FILL = "#B3261E", "#FFFFFF"
GREY, GREY_FILL, GREY_TEXT = "#9A9A9A", "#EDEFF2", "#6B6B6B"
MATE, MATE_FILL = "#3F5F8F", "#E8EEF6"
ARROW, PARAM = "#222222", "#5E7F6B"

STYLES = {
    "mine": dict(ec=RED, fc=RED_FILL, lw=1.8, ls="-", tc="#111111"),
    "model": dict(ec=GREY, fc=GREY_FILL, lw=1.0, ls="-", tc=GREY_TEXT),
    "mate": dict(ec=MATE, fc=MATE_FILL, lw=1.4, ls=(0, (4, 2.5)), tc="#1F2F4A"),
}


def box(ax, x0, y0, x1, y1, text, style, size=10.5):
    s = STYLES[style]
    ax.add_patch(FancyBboxPatch((x0, y0), x1 - x0, y1 - y0,
                                boxstyle="square,pad=0", ec=s["ec"], fc=s["fc"],
                                lw=s["lw"], ls=s["ls"], zorder=2))
    ax.text((x0 + x1) / 2, (y0 + y1) / 2, text, ha="center", va="center",
            fontsize=size, color=s["tc"], linespacing=1.35, zorder=3)


def arrow(ax, p, q, param=False, label=None, label_dx=0.8):
    ax.annotate("", xy=q, xytext=p, zorder=1,
                arrowprops=dict(arrowstyle="-|>", mutation_scale=13,
                                color=PARAM if param else ARROW, lw=1.2,
                                ls=(0, (3, 2)) if param else "-",
                                shrinkA=0, shrinkB=0))
    if label:
        mx, my = (p[0] + q[0]) / 2, (p[1] + q[1]) / 2
        ax.text(mx + label_dx, my, label, fontsize=9, color=PARAM if param else ARROW,
                ha="left", va="center", style="italic")


def line(ax, p, q):
    ax.plot([p[0], q[0]], [p[1], q[1]], color=ARROW, lw=1.2, zorder=1,
            solid_capstyle="butt")


def header(ax, x, y, text):
    ax.text(x, y, text, fontsize=13, fontweight="bold", ha="left", va="center")


def draw(out_dir: Path):
    fig, ax = plt.subplots(figsize=(14, 8.4))
    ax.set_xlim(0, 100)
    ax.set_ylim(-1.5, 66)
    ax.axis("off")

    # --- input -------------------------------------------------------------------
    box(ax, 1, 33, 10, 40, "Video\nframes", "mine" if False else "model", size=12)
    ax.patches[-1].set_edgecolor("#333333"); ax.patches[-1].set_facecolor("#FFFFFF")
    ax.texts[-1].set_color("#111111")
    ax.text(5.5, 30.8, "comma2k19\nArgoverse 2 / 1\nA2D2 · KITTI\nHaisheng (Taiwan)",
            fontsize=9, color=GREY_TEXT, ha="center", va="top", style="italic",
            linespacing=1.4)

    # --- lane 1: scale from markings -------------------------------------------------
    header(ax, 14, 63.3, "Scale from road markings only: once per video")
    box(ax, 14, 53, 30, 60, "Lane-line fit\n(ridges → RANSAC)", "mate")
    box(ax, 34, 53, 52, 60, "Vanishing point used as\nhorizon row y_h\n(replaces SHARP plane)", "mine")
    box(ax, 14, 44, 30, 51, "Dash timing at fixed rows\nlag ÷ period × legal cycle", "mate", size=10)
    box(ax, 57, 44, 78, 60,
        "Fix y_h, solve A = h·f\n\nQuality checks\npair spread ≤ 10%\n"
        "cycle snapped to legal set\nlane width vs camera height", "mine")
    arrow(ax, (30, 56.5), (34, 56.5))
    arrow(ax, (52, 56.5), (57, 56.5))
    arrow(ax, (30, 47.5), (57, 47.5))

    # --- lane 2: target distance -----------------------------------------------------
    header(ax, 14, 40.8, "Target distance: every frame")
    box(ax, 14, 30, 30, 37, "YOLO masks\n(existing model)", "model")
    box(ax, 34, 30, 52, 37, "Contact point: mask\nlowest pixel (tested\nagainst 12% band)", "mine")
    box(ax, 57, 30, 78, 37, "Method C\nd = A / (py − y_h)\nno learned component", "mine")
    box(ax, 14, 20, 30, 27, "5 depth models\n(existing, used as-is)", "model")
    box(ax, 34, 20, 52, 27, "Model depth at\nthe target pixel", "mine")
    box(ax, 57, 20, 78, 27, "Method B\nd = k × model depth\nk = median(C ÷ model)", "mine")
    arrow(ax, (30, 33.5), (34, 33.5))
    arrow(ax, (52, 33.5), (57, 33.5))
    arrow(ax, (30, 23.5), (34, 23.5))
    arrow(ax, (52, 23.5), (57, 23.5))
    arrow(ax, (43, 30), (43, 27), label="target pixel")
    arrow(ax, (67.5, 30), (67.5, 27), label="sets k")
    arrow(ax, (67.5, 44), (67.5, 37), param=True, label="A, y_h")

    # --- lane 3: external validation -------------------------------------------------
    header(ax, 82, 40.8, "External validation")
    box(ax, 82, 26, 99, 35, "Seal predictions\n(sha256, truth files\nnot on disk)", "mine")
    box(ax, 82, 7, 99, 21.5,
        "Compare with instruments\nradar · lidar 3D boxes\n· factory calibration\n\n"
        "→ errors, refusals,\napplicability conditions", "mine", size=10)
    line(ax, (78, 33.5), (80, 33.5))
    line(ax, (78, 23.5), (80, 23.5))
    line(ax, (80, 23.5), (80, 33.5))
    arrow(ax, (80, 30.5), (82, 30.5))
    arrow(ax, (90.5, 26), (90.5, 21.5))

    # --- lane 4: ego-speed validation ------------------------------------------------
    header(ax, 14, 16.3, "Ego-speed validation: Haisheng batch 2")
    box(ax, 14, 6, 30, 13, "Ego speed\n(teammate's odometer)", "mate")
    box(ax, 34, 6, 52, 13, "Same-frame comparison\nper 30 m segment", "mine")
    box(ax, 57, 6, 78, 13, "Manual frame-count reports\nparse + self-check", "mine")
    arrow(ax, (30, 9.5), (34, 9.5))
    arrow(ax, (57, 9.5), (52, 9.5))

    # --- fan-out from the frames -----------------------------------------------------
    line(ax, (10, 36.5), (12, 36.5))
    line(ax, (12, 9.5), (12, 56.5))
    for y in (56.5, 47.5, 33.5, 23.5, 9.5):
        arrow(ax, (12, y), (14, y))

    # --- legend ------------------------------------------------------------------------
    ax.plot([1, 99], [2.6, 2.6], color="#CCCCCC", lw=0.8)
    ly = 0.3
    for x, style, label in ((1.5, "mine", "Implemented by me"),
                            (23.5, "model", "Existing model, used as-is"),
                            (49, "mate", "Teammate's component, reused")):
        s = STYLES[style]
        ax.add_patch(FancyBboxPatch((x, ly - 0.9), 3.2, 1.8, boxstyle="square,pad=0",
                                    ec=s["ec"], fc=s["fc"], lw=s["lw"], ls=s["ls"]))
        ax.text(x + 4, ly, label, fontsize=10.5, va="center",
                color=RED if style == "mine" else "#333333",
                fontweight="bold" if style == "mine" else "normal")
    arrow(ax, (77, ly), (81, ly))
    ax.text(82, ly, "Data", fontsize=10.5, va="center")
    arrow(ax, (87.5, ly), (91.5, ly), param=True)
    ax.text(92.5, ly, "Parameters", fontsize=10.5, va="center")

    out_dir.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "svg"):
        fig.savefig(out_dir / f"terry_flowchart.{ext}", dpi=200, bbox_inches="tight",
                    facecolor="white")
    print("wrote", out_dir / "terry_flowchart.png", "and .svg")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="data/output/terry_flowchart")
    draw(Path(ap.parse_args().out))
