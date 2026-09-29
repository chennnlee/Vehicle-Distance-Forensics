#!/usr/bin/env python3
"""Demo video of the dash-scale method on a raw Haisheng clip (overlays blacked out).

Everything drawn comes from the sealed result of tools/run_depth_dash_scale.py (lines,
scale k, per-pair speeds) plus the cached depth maps; the front car is found with YOLO
(the detector all distance validations used), whose box bottom is taken as the contact point.
The manual frame-count report is drawn only if --truth is given, and only after the
results were sealed (the script checks the seal).

  python3 tools/report/demo_haisheng_dash_scale.py --key hs1230car_002 --truth
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import depth_dash_scale as D  # noqa: E402
from score_depth_dash_scale import seg_speed  # noqa: E402

FINAL = ROOT / "data/output/dash_scale/final"
OUT = ROOT / "data/output/dash_scale/demo"
C_OURS, C_TRUTH, C_LINE, C_CAR = "#1A73E8", "#111111", "#34A853", "#E8710A"


def fonts():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    for name in ("msjh.ttc", "msjhbd.ttc", "arial.ttf"):
        p = Path("/mnt/c/Windows/Fonts") / name
        if p.exists():
            font_manager.fontManager.addfont(str(p))
    plt.rcParams["font.family"] = ["Microsoft JhengHei", "Arial", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    return plt


def sealed(key):
    seal = json.loads((FINAL / "seal.json").read_text())
    fp = FINAL / f"{key}.json"
    if hashlib.sha256(fp.read_bytes()).hexdigest() != seal["files"].get(fp.name):
        sys.exit(f"{fp.name} is not the sealed version")
    return json.loads(fp.read_text()), seal


def detector():
    """YOLO, the same detector every distance validation in this project used."""
    from ultralytics import YOLO
    model = YOLO(str(ROOT / "checkpoints/yolov8m-seg.pt"))

    def run(bgr):
        r = model.predict(bgr, verbose=False, conf=0.4)[0]
        out = []
        if r.boxes is not None:
            for b, c, s in zip(r.boxes.xyxy.cpu().numpy(), r.boxes.cls.cpu().numpy(), r.boxes.conf.cpu().numpy()):
                if int(c) in (2, 5, 7):          # car, bus, truck
                    out.append((b.tolist(), float(s)))
        return out
    return run


def front_car(boxes, lines, w, h):
    """The nearest box whose bottom centre lies between the ego-lane lines."""
    best = None
    for (x0, y0, x1, y1), s in boxes:
        cx, cy = (x0 + x1) / 2, y1
        L, R = lines.get("left"), lines.get("right")
        lo = L["a"] * cy + L["b"] if L else 0.3 * w
        hi = R["a"] * cy + R["b"] if R else 0.7 * w
        if lo < cx < hi and (best is None or cy > best[3]):
            best = (x0, y0, x1, y1)
    return best


def truth_segments(key, manifest):
    from haisheng_manual_truth import parse
    it = next(i for i in manifest if i["key"] == key)
    if key.startswith("hs1230car_"):
        xl = glob.glob(str(ROOT / f"data/input/海盛_20251230/汽車行車紀錄器 - 人工標註/{key.split('_')[1]}_*/*_manual.xlsx"))
    else:
        xl = glob.glob(str(Path(it["video"]).parent / "*.xlsx"))
    return parse(xl[0])[1] if len(xl) == 1 else []


C2K = {"c2k19_seg10": "b0c9d2329ad1606b_2018-07-30--13-44-30_10",
       "c2k19_seg21": "b0c9d2329ad1606b_2018-08-15--09-01-03_21"}


def c2k19_truth(key):
    """Radar distance at the scored target pixel, and CAN speed, per frame index (0-based)."""
    import csv
    rows = csv.DictReader(open(ROOT / f"data/output/depth_benchmark/paired_{C2K[key]}.csv"))
    out = {}
    for r in rows:
        out[int(r["frame_idx"].lstrip("f")) - 1] = dict(px=float(r["px"]), py=float(r["py"]),
                                                          radar=float(r["radar_range_m"]),
                                                          can=float(r["can_ego_kmh"]))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--key", required=True)
    ap.add_argument("--frames", default="", help="frames dir (defaults to the run's)")
    ap.add_argument("--depth-cache", default="")
    ap.add_argument("--truth", action="store_true", help="draw the manual report (allowed only after sealing)")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    plt = fonts()
    res, seal = sealed(args.key)
    manifest = json.loads((FINAL / "manifest.json").read_text())
    it = next(i for i in manifest if i["key"] == args.key)
    frames = D.list_frames(Path(args.frames or res["frames_dir"]))
    cache = Path(args.depth_cache or it.get("depth_cache") or "")
    k, L = res["k"], res["cycle_m"]
    p = res["params"]
    fps, step, stride = res["fps"], res["step"], res.get("stride", 1)
    _, boxes_osd = D.static_rows(frames)
    h, w = cv2.imread(str(frames[0])).shape[:2]
    idx = list(range(0, len(frames), step))
    speeds = {s["frame_i"]: s for s in res["speeds"]}
    t_all = np.array([s["t_s"] for s in res["speeds"] if s["kmh"] is not None])
    v_all = np.array([s["kmh"] for s in res["speeds"] if s["kmh"] is not None])
    is_c2k = args.key in C2K
    segs = truth_segments(args.key, manifest) if args.truth and not is_c2k else []
    c2k = c2k19_truth(args.key) if args.truth and is_c2k else {}
    det = detector()
    half_px = max(4, int(round(p["band_half_px"] * h / 1080)))
    tdir = OUT / args.key / "frames"
    if tdir.exists():
        shutil.rmtree(tdir)
    tdir.mkdir(parents=True)
    prev = None
    backend = None
    for j in range(min(len(idx), args.limit) if args.limit else len(idx)):
        fi = idx[j]
        img = D.black_out(cv2.imread(str(frames[fi])), boxes_osd)
        wd = D.lines_for(dict(windows=res["windows"]), j)
        try:
            depth = D.load_depth(cache if str(cache) else None, frames[fi], backend)
        except FileNotFoundError:
            import depth_backends as DB
            backend = DB.get_backend("da3_metric")
            backend.load(device="cuda")
            depth = D.load_depth(cache if str(cache) else None, frames[fi], backend)
        fig = plt.figure(figsize=(19.2, 10.8), dpi=100)
        title = f"comma2k19 {args.key}(公開資料集,無 OSD)" if is_c2k else f"海盛 {args.key}(原始影片,OSD 已塗黑)"
        fig.text(0.01, 0.985, f"{title}  影格 {fi * stride + 1}  t = {fi / fps:5.2f} s",
                 fontsize=16, fontweight="bold", va="top")
        fig.text(0.99, 0.985, f"結果封存於 {seal['sealed_utc']}(commit {seal['git_commit'][:7]})"
                 + (",之後才開啟真值" if (segs or c2k) else ""), fontsize=11, ha="right", va="top", color="#555")
        a1 = fig.add_axes([0.005, 0.40, 0.49, 0.53])
        a1.imshow(img[..., ::-1])
        lines = {}
        for side in ("left", "right"):
            ln = wd.get(side)
            if ln and wd.get("vp_row") and side in res.get("lines_used", []):
                ys = np.array([wd["vp_row"] + p["vp_margin"] * h, res["det_rows"][1]])
                a1.plot(ln["a"] * ys + ln["b"], ys, color=C_LINE, lw=2.2)
                lines[side] = ln
        if wd.get("vp_row"):
            a1.axhline(wd["vp_row"], color="#FBBC04", ls=(0, (6, 4)), lw=1.4)
        car = front_car(det(img), lines, w, h)
        car_txt = "本車道前方沒有車"
        if car is not None and depth is not None:
            x0, y0, x1, y1 = car
            cx = (x0 + x1) / 2
            yb = y1 - 0.06 * (y1 - y0)
            dh, dw = depth.shape
            yy, xx = int(yb * dh / h), int(cx * dw / w)
            zm = float(np.median(depth[max(0, yy - 2): yy + 3, max(0, xx - 2): xx + 3]))
            a1.add_patch(plt.Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False, ec=C_CAR, lw=2))
            a1.plot(cx, yb, "o", color=C_CAR, ms=8, mec="white")
            a1.text(x0, y0 - 8, f"{k * zm:.1f} m", color="white", fontsize=15, fontweight="bold",
                    bbox=dict(fc=C_CAR, ec="none", pad=2))
            car_txt = f"前車距離  = k × 模型讀值 = {k:.3f} × {zm:.2f} = {k * zm:.1f} m"
            tr = c2k.get(fi)
            if tr and abs(tr["px"] - cx) < 40 and abs(tr["py"] - y1) < 40:
                err = (k * zm - tr["radar"]) / tr["radar"] * 100
                car_txt += f"  |  雷達 {tr['radar']:.1f} m({err:+.1f}%)"
        a1.set_title("① 追蹤虛線(綠)與前車(橘)", fontsize=14, fontweight="bold")
        a1.axis("off")
        a2 = fig.add_axes([0.505, 0.40, 0.49, 0.53])
        if depth is not None:
            a2.imshow(depth * k, cmap="turbo_r", vmin=3, vmax=60, extent=(0, w, h, 0))
        for ln in lines.values():
            ys = np.array([wd["vp_row"] + p["vp_margin"] * h, res["det_rows"][1]])
            a2.plot(ln["a"] * ys + ln["b"], ys, color="white", lw=1.5)
        a2.set_title("② 深度模型 da3_metric × k(公尺)", fontsize=14, fontweight="bold")
        a2.axis("off")
        # the ruler: metric profile now and one step earlier
        a3 = fig.add_axes([0.05, 0.07, 0.40, 0.26])
        cur = None
        if lines and depth is not None:
            g = cv2.imread(str(frames[fi]), cv2.IMREAD_GRAYSCALE)
            th = D.white_tophat(g, res["tophat_px"])
            rows = np.arange(res["det_rows"][1] - 1, int(wd["vp_row"] + p["vp_margin"] * h), -1)
            side = max(lines, key=lambda s: 1 if s == (speeds.get(fi, {}) or {}).get("side") else 0)
            r = D.line_profile(th, depth, lines[side], rows, half_px, p["zcap_cycles"] * L)
            if r is not None:
                grid, prof = D.resample(r[0], r[1], p["dz_model"])
                cur = (grid * k, prof)
                if prev is not None:
                    a3.plot(prev[0], prev[1], color="#BBBBBB", lw=1.5, label=f"{step} 幀前")
                sp_prev = speeds.get(fi - step)
                if prev is not None and sp_prev and sp_prev["kmh"] is not None:
                    shift = sp_prev["kmh"] / 3.6 * step / fps
                    a3.plot(prev[0] - shift, prev[1], color="#555555", lw=1.3, ls=(0, (4, 3)),
                            label=f"{step} 幀前的曲線往近處平移 {shift:.2f} m")
                a3.plot(cur[0], cur[1], color=C_LINE, lw=2, label="這一幀")
                for z in np.arange(0, 40, L):
                    a3.axvline(z, color="#EEEEEE", lw=0.8, zorder=0)
        a3.set_xlim(0, 35)
        a3.set_xlabel("沿虛線的距離(公尺,= k × 模型讀值)", fontsize=11)
        a3.set_ylabel("虛線亮度", fontsize=11)
        a3.set_title(f"③ 尺:虛線起點間距 = 法定 {L:g} m → k = {k:.3f};平移量 ÷ 時間 = 自車速",
                     fontsize=13, fontweight="bold")
        if cur is not None:
            a3.legend(loc="upper right", fontsize=9)
        prev = cur
        # speed over time
        a4 = fig.add_axes([0.53, 0.07, 0.45, 0.26])
        ymax = 1.6 * max([sg["speed_kmh"] for sg in segs] + [c["can"] for c in c2k.values()]
                         + ([float(np.median(v_all))] if len(v_all) else [100]))
        a4.plot(t_all, np.minimum(v_all, ymax * 0.98), ".", color=C_OURS, alpha=0.3, ms=4,
                label="我方每一對影格的讀值(超出範圍的標在頂端)")
        for sg in segs:
            ta, tb = (sg["f_start"] - 1) / stride / fps, (sg["f_end"] - 1) / stride / fps
            a4.plot([ta, tb], [sg["speed_kmh"]] * 2, color=C_TRUTH, lw=3.5)
            ours, _, _ = seg_speed(res, sg["f_start"], sg["f_end"])
            if ours is not None and tb <= fi / fps + 1e-9:
                a4.plot([ta, tb], [ours] * 2, color=C_OURS, lw=3.5)
                a4.text(tb, ours, f" {ours - sg['speed_kmh']:+.1f}", color=C_OURS, fontsize=9, va="center")
        if c2k:
            ts = sorted(c2k)
            a4.plot([f / fps for f in ts], [c2k[f]["can"] for f in ts], color=C_TRUTH, lw=2, label="CAN 車速(真值)")
        if segs:
            a4.plot([], [], color=C_TRUTH, lw=3.5, label="海盛人工畫格法(每段 30 m)")
            a4.plot([], [], color=C_OURS, lw=3.5, label="我方同一段平均(評分用,段落走完才顯示)")
        a4.set_ylim(0, ymax)
        a4.axvline(fi / fps, color="#D93025", lw=1.2)
        a4.set_xlim(0, len(frames) / fps)
        a4.set_xlabel("時間(秒)", fontsize=11)
        a4.set_ylabel("自車速(km/h)", fontsize=11)
        a4.set_title("④ 由距離變化推得的自車速", fontsize=13, fontweight="bold")
        a4.legend(loc="lower left", fontsize=10)
        a4.grid(alpha=0.3)
        sp = speeds.get(fi)
        sp_txt = "這一幀沒有速度讀值" if not sp or sp["kmh"] is None else \
            f"自車速 = 虛線剖面平移 ÷ 時間 = {sp['kmh']:.1f} km/h(相關 {sp['corr']:.2f})"
        fig.text(0.01, 0.355, sp_txt, fontsize=13, color=C_OURS, fontweight="bold")
        fig.text(0.51, 0.355, car_txt, fontsize=13, color=C_CAR, fontweight="bold")
        fig.savefig(tdir / f"{j:04d}.png", dpi=100)
        plt.close(fig)
        if (j + 1) % 50 == 0:
            print(f"rendered {j + 1}/{len(idx)}", flush=True)
    mp4 = OUT / f"demo_{args.key}.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", f"{fps / step:.3f}", "-i",
                    str(tdir / "%04d.png"), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", str(mp4)],
                   check=True)
    print("wrote", mp4)


if __name__ == "__main__":
    main()
