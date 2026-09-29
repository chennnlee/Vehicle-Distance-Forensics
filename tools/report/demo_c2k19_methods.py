#!/usr/bin/env python3
"""Demo images and video: Method C and the depth model on real comma2k19 footage.

Everything drawn is computed by the project's own code, not re-implemented here:

  A and the horizon   `line_estimates` from vanishing_point_range_calib.py, re-run on all
                      1200 frames (it calls the teammate's dash-signal and cross-row lag code)
  front car           YOLO matched to the archived target exactly as
                      contact_point_definitions.py does (within 1 px of the stored pixel)
  model depth         depth_backends `infer_full` + depth_model_benchmark `sample_depth`
  marking constant k  median(Method C distance / model depth) over every detected target
                      that Method C itself places nearer than 32 m -- no radar anywhere

and each value is checked against the archived benchmark CSVs; `prep` stops if they disagree.
The radar is only used to score, never to compute a distance.

  export LD_PRELOAD=$HOME/miniconda3/lib/libstdc++.so.6        # as verify_depth_rerun.sh
  ~/venvs/depthbench/bin/python tools/report/demo_c2k19_methods.py --stage all

Stages are cached under data/output/c2k19_demo/, so an interrupted run resumes.
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

FRAMES = ROOT / "data/input/_frames_cache/c2k19"
BENCH = ROOT / "data/output/depth_benchmark"
OUT = ROOT / "data/output/c2k19_demo"
YOLO_W = ROOT / "checkpoints/yolov8m-seg.pt"
FPS, CYCLE_M, NEAR_M, MAX_SPREAD = 20.0, 14.63, 32.0, 0.10
ROWS = [500, 540, 580, 615]
MODEL = "da3_metric"
DEPTH_MODELS = ["metric3d_v2", "da3_metric", "unidepth_v2", "depth_pro", "depth_anything_v2_vits"]

# A and y_h as published (docs/DEPTH_MODEL_BENCHMARK.md section 15.2); prep re-derives A.
SEGS = {
    "seg10": dict(tag="b0c9d2329ad1606b_2018-07-30--13-44-30_10", date="2018-07-30",
                  A=1238.0, y_h=383.2, lines=[(-1.6158, 1211.4), (1.5445, 0.4)]),
    "seg21": dict(tag="b0c9d2329ad1606b_2018-08-15--09-01-03_21", date="2018-08-15",
                  A=1242.0, y_h=378.7, lines=[(-1.4047, 1129.1), (1.3492, 86.2)]),
}

C_RADAR, C_METHOD_C, C_RAW, C_SCALED = "#111111", "#E8710A", "#9AA0A6", "#1A73E8"
C_LANE, C_LANE_OFF, C_HORIZON, C_MASK = "#34A853", "#BDBDBD", "#FBBC04", "#00BCD4"


def _rows(fp: Path) -> list[dict]:
    with open(fp, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _frames(tag: str) -> list[Path]:
    return sorted((FRAMES / tag / "frames").glob("f*.jpg"))


# ------------------------------------------------------------------------------ prep

def prep_scale(seg: str) -> dict:
    """Re-derive A from the dash timing, with the published tool's own acceptance rule."""
    from vanishing_point_range_calib import line_estimates
    from dashcam_range_speed import extract_odometer_signals

    s, cache = SEGS[seg], OUT / "cache" / seg / "scale.json"
    if cache.exists():
        out = json.loads(cache.read_text())
        out["A_live"] = out.get("A_live", out["A"])
        out["A"] = s["A"]
        return out
    frames = _frames(s["tag"])
    lines, pooled = [], []
    for a, b in s["lines"]:
        pts, period, est = line_estimates(frames, a, b, ROWS, s["y_h"], FPS, CYCLE_M)
        As = np.array([e["A"] for e in est])
        med = float(np.median(As)) if len(As) else float("nan")
        spread = float((As.max() - As.min()) / med) if len(As) >= 2 else float("inf")
        ok = period is not None and len(est) >= 2 and spread <= MAX_SPREAD
        if ok:
            pooled += As.tolist()
        sig = extract_odometer_signals(frames, pts, 120)
        lines.append(dict(a=a, b=b, points=pts, period=period, pairs=est, A_median=med,
                          spread=spread, accepted=ok,
                          signals={f"{x},{y}": sig[(x, y)][:, 0].tolist() for x, y in pts}))
    A = float(np.median(pooled))
    print(f"[{seg}] A re-derived {A:.1f} from {len(pooled)} row pairs (published {s['A']:.0f})")
    if abs(A - s["A"]) > 0.5:
        sys.exit(f"[{seg}] re-derived A {A:.1f} does not match the published {s['A']:.0f}")
    out = dict(A=s["A"], A_live=A, lines=lines)   # distances use the published A, as the report does
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(out))
    return out


def marking_constant(seg: str, model: str) -> float:
    """k with no radar: every target Method C itself calls near (depth_blind_analysis marking)."""
    s = SEGS[seg]
    low = {r["frame_idx"]: float(r["py_max"]) for r in _rows(BENCH / "contact_defs.csv")
           if r["tag"] == s["tag"]}
    rr = [r for r in _rows(BENCH / f"unf_{s['tag']}__{model}.csv") if r["frame_idx"] in low]
    pred = np.array([float(r["pred"]) for r in rr])
    mc = s["A"] / (np.array([low[r["frame_idx"]] for r in rr]) - s["y_h"])
    keep = np.isfinite(pred) & (pred > 0) & (mc < NEAR_M)
    return float(np.median(mc[keep] / pred[keep]))


def prep_frames(seg: str) -> list[dict]:
    """YOLO + depth model on every 4th frame, cross-checked against the archive."""
    import cv2
    from ultralytics import YOLO
    import depth_backends as DB
    from depth_model_benchmark import sample_depth
    from contact_point_definitions import VEHICLE

    s, cdir = SEGS[seg], OUT / "cache" / seg
    cache = cdir / "frames.json"
    if cache.exists():
        return json.loads(cache.read_text())
    tag = s["tag"]
    targets = {r["frame_idx"]: r for r in _rows(BENCH / f"targets_{tag}.csv")}
    paired = {r["frame_idx"] for r in _rows(BENCH / f"paired_{tag}.csv")}
    defs = {r["frame_idx"]: r for r in _rows(BENCH / "contact_defs.csv") if r["tag"] == tag}
    stored = {r["frame_idx"]: float(r["pred"]) for r in _rows(BENCH / f"unf_{tag}__{MODEL}.csv")}

    yolo = YOLO(str(YOLO_W))
    be = DB.get_backend(MODEL)
    be.load(device="cuda")
    (cdir / "depth").mkdir(parents=True, exist_ok=True)
    recs, bad = [], []
    for i in range(1, 1201, 4):
        fid = f"f{i:05d}"
        fp = FRAMES / tag / "frames" / f"{fid}.jpg"
        bgr = cv2.imread(str(fp))
        rec = dict(frame_idx=fid, t=(i - 1) / FPS, has_target=fid in targets, paired=fid in paired)
        d = be.infer_full(bgr)["depth_m"]
        h, w = d.shape
        np.save(cdir / "depth" / f"{fid}.npy",
                cv2.resize(d, (w // 2, h // 2), interpolation=cv2.INTER_AREA).astype(np.float16))
        if fid in targets:
            r = targets[fid]
            res = yolo.predict(str(fp), verbose=False, conf=0.4)[0]
            best = None
            if res.masks is not None:
                H, W = res.orig_shape
                for mk, poly, cls in zip(res.masks.data.cpu().numpy(), res.masks.xy,
                                         res.boxes.cls.cpu().numpy()):
                    if int(cls) not in VEHICLE or poly is None or len(poly) < 3:
                        continue
                    ys, xs = np.nonzero(mk)
                    if ys.size < 50:
                        continue
                    ys, xs = ys * (H / mk.shape[0]), xs * (W / mk.shape[1])
                    sel = ys >= np.percentile(ys, 88.0)
                    px, py = float(np.median(xs[sel])), float(np.median(ys[sel]))
                    gap = abs(px - float(r["px"])) + abs(py - float(r["py"]))
                    if gap < 1.0 and (best is None or gap < best[0]):
                        best = (gap, poly, float(poly[:, 1].max()))
            px, py_band = float(r["px"]), float(r["py"])
            live = sample_depth(d, px, py_band, 5)
            rec.update(px=px, py_band=py_band, radar=float(r["radar_range_m"]),
                       pred_live=live, pred_stored=stored.get(fid, float("nan")))
            if abs(live - rec["pred_stored"]) > 1e-4:
                bad.append(f"{fid} depth live {live:.5f} vs archived {rec['pred_stored']:.5f}")
            if fid in defs:
                rec["py_max"] = float(defs[fid]["py_max"])
                if best is not None and abs(round(best[2], 2) - rec["py_max"]) > 0.011:
                    bad.append(f"{fid} contact row live {best[2]:.2f} vs archived {rec['py_max']:.2f}")
            if best is not None:
                rec["poly"] = best[1][::2].round(1).tolist()
        recs.append(rec)
        if len(recs) % 50 == 0:
            print(f"[{seg}] {len(recs)}/300 frames")
    n = sum(1 for r in recs if r["has_target"])
    print(f"[{seg}] cross-check: {n} targets, {len(bad)} disagreements with the archive")
    for m in bad[:10]:
        print("   ", m)
    if bad:
        sys.exit(f"[{seg}] live values disagree with the archived benchmark -- stopping")
    cache.write_text(json.dumps(recs))
    return recs


def prep_models(seg: str, fid: str) -> dict:
    """All five depth models on one frame, for the side-by-side still."""
    import cv2
    import depth_backends as DB
    from depth_model_benchmark import sample_depth

    s, cache = SEGS[seg], OUT / "cache" / seg / f"models_{fid}.npz"
    if cache.exists():
        z = np.load(cache, allow_pickle=True)
        return z["info"].item() | {"maps": {m: z[m] for m in DEPTH_MODELS}}
    bgr = cv2.imread(str(FRAMES / s["tag"] / "frames" / f"{fid}.jpg"))
    r = {x["frame_idx"]: x for x in _rows(BENCH / f"targets_{s['tag']}.csv")}[fid]
    maps, info = {}, {}
    for m in DEPTH_MODELS:
        be = DB.get_backend(m)
        be.load(device="cuda")
        out = be.infer_full(bgr)
        d = out["depth_m"] if out["depth_m"] is not None else out["relative"]
        v = sample_depth(d, float(r["px"]), float(r["py"]), 5)
        arch = {x["frame_idx"]: float(x["pred"]) for x in _rows(BENCH / f"unf_{s['tag']}__{m}.csv")}[fid]
        if abs(v - arch) > 1e-4:
            sys.exit(f"{m} {fid}: live {v:.5f} vs archived {arch:.5f}")
        h, w = d.shape
        maps[m] = cv2.resize(d, (w // 2, h // 2), interpolation=cv2.INTER_AREA).astype(np.float32)
        info[m] = dict(kind=be.kind, value=v, k=marking_constant(seg, m) if be.kind == "metric" else None)
        be.unload()
        print(f"[{seg} {fid}] {m}: {v:.3f} (matches archive)")
    np.savez(cache, info=np.array(info, dtype=object), **maps)
    return info | {"maps": maps}


# ---------------------------------------------------------------------------- render

def _setup_fonts():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    for name in ("arial.ttf", "arialbd.ttf", "ariali.ttf"):
        p = Path("/mnt/c/Windows/Fonts") / name
        if p.exists():
            font_manager.fontManager.addfont(str(p))
    plt.rcParams["font.family"] = ["Arial", "DejaVu Sans"]
    return plt


def _series(recs, A, y_h, k):
    ev = [r for r in recs if r["paired"] and "py_max" in r]
    t = np.array([r["t"] for r in ev])
    radar = np.array([r["radar"] for r in ev])
    mc = A / (np.array([r["py_max"] for r in ev]) - y_h)
    raw = np.array([r["pred_live"] for r in ev])
    return dict(t=t, radar=radar, mc=mc, raw=raw, scaled=raw * k)


def _near_err(pred, radar):
    n = radar < NEAR_M
    return float(np.median(np.abs(pred[n] - radar[n]) / radar[n]) * 100), int(n.sum())


def draw_scene(ax, img, seg, scale, rec, rows=True, fs=11, inset=True):
    from matplotlib.patches import Rectangle as plt_rect
    s = SEGS[seg]
    H, W = img.shape[:2]
    ax.imshow(img[..., ::-1])
    y_h = s["y_h"]
    xv = []
    for L in scale["lines"]:
        ys = np.array([y_h, H])
        ax.plot(L["a"] * ys + L["b"], ys, color=C_LANE if L["accepted"] else C_LANE_OFF,
                lw=2.2, ls="-" if L["accepted"] else (0, (5, 3)))
        xv.append(L["a"] * y_h + L["b"])
        if rows and L["accepted"]:
            for y in ROWS:
                ax.plot(L["a"] * y + L["b"], y, "o", mfc="none", mec="white", mew=2, ms=9)
    ax.axhline(y_h, color=C_HORIZON, ls=(0, (6, 4)), lw=1.6)
    ax.plot(np.mean(xv), y_h, "o", color=C_HORIZON, ms=8, mec="black", mew=0.8)
    ax.text(8, y_h - 8, f"horizon  y_h = {y_h:.1f}", color=C_HORIZON, fontsize=fs,
            fontweight="bold", va="bottom")
    if rec is not None and rec.get("has_target"):
        if rec.get("poly"):
            p = np.array(rec["poly"])
            ax.fill(p[:, 0], p[:, 1], fc=C_MASK, alpha=0.18, ec=C_MASK, lw=1.4)
        if "py_max" in rec:
            px, py = rec["px"], rec["py_max"]
            ax.plot(px, py, "o", color=C_METHOD_C, ms=9, mec="white", mew=1.5, zorder=5)
            xb = min(px + 70, W - 40)
            ax.annotate("", xy=(xb, y_h), xytext=(xb, py),
                        arrowprops=dict(arrowstyle="<->", color="white", lw=1.6))
            ax.text(xb + 6, (y_h + py) / 2, f"py − y_h\n= {py - y_h:.1f} px", color="white",
                    fontsize=fs, va="center", fontweight="bold")
            if inset:
                x0, x1 = int(max(0, px - 90)), int(min(W, px + 90))
                y0, y1 = int(max(0, min(py - 100, y_h - 12))), int(min(H, py + 22))
                ax.add_patch(plt_rect((x0, y0), x1 - x0, y1 - y0, fill=False, ec="white", lw=1.2))
                ins = ax.inset_axes([0.63, 0.63, 0.36, 0.36])
                ins.imshow(img[y0:y1, x0:x1, ::-1], extent=(x0, x1, y1, y0))
                if rec.get("poly"):
                    ins.plot(np.r_[p[:, 0], p[0, 0]], np.r_[p[:, 1], p[0, 1]], color=C_MASK, lw=1.5)
                ins.axhline(y_h, color=C_HORIZON, ls=(0, (6, 4)), lw=1.4)
                ins.axhline(py, color=C_METHOD_C, lw=1.0, alpha=0.8)
                ins.plot(px, py, "o", color=C_METHOD_C, ms=9, mec="white", mew=1.5)
                ins.set_xlim(x0, x1)
                ins.set_ylim(y1, y0)
                ins.set_xticks([])
                ins.set_yticks([])
                for sp in ins.spines.values():
                    sp.set_edgecolor("white")
                    sp.set_linewidth(1.5)
                ins.set_title("zoom: YOLO mask, lowest pixel = contact", fontsize=fs - 1,
                              color="white", pad=3, backgroundcolor="#00000080")
    ax.set_xlim(0, W)
    ax.set_ylim(H, 0)
    ax.axis("off")


def draw_depth(ax, depth, W, H, rec, fs=11):
    im = ax.imshow(depth.astype(np.float32), cmap="turbo_r", vmin=5, vmax=80,
                   extent=(0, W, H, 0), interpolation="bilinear")
    if rec is not None and rec.get("has_target"):
        ax.plot(rec["px"], rec["py_band"], "x", color="white", ms=12, mew=2.5)
        ax.text(rec["px"] + 14, rec["py_band"] - 14, f"{rec['pred_live']:.2f} m",
                color="white", fontsize=fs + 1, fontweight="bold")
    ax.set_xlim(0, W)
    ax.set_ylim(H, 0)
    ax.axis("off")
    return im


def draw_series(ax, ser, now=None, fs=10, errs=None):
    t = ser["t"]
    past = np.ones_like(t, bool) if now is None else t <= now + 1e-9
    for key, color, label, kw in (("raw", C_RAW, "depth model, raw", dict(ms=4)),
                                  ("scaled", C_SCALED, "depth model × marking k", dict(ms=4)),
                                  ("mc", C_METHOD_C, "Method C (markings only)", dict(ms=4))):
        ax.plot(t[~past], ser[key][~past], "o", color=color, alpha=0.15, **kw)
        lab = label + (f"  (near-field median error {errs[key]:.1f}%)" if errs else "")
        ax.plot(t[past], ser[key][past], "o", color=color, label=lab, **kw)
    gap = np.r_[False, np.diff(t) > 0.5]          # no scored frame for >0.5 s: break the line
    rt = np.insert(t, np.flatnonzero(gap), np.nan)
    rr = np.insert(ser["radar"], np.flatnonzero(gap), np.nan)
    rp = np.insert(past, np.flatnonzero(gap), False)
    ax.plot(rt, rr, "-", color=C_RADAR, lw=1.0, alpha=0.25)
    ax.plot(np.where(rp, rt, np.nan), rr, "-", color=C_RADAR, lw=1.8, label="radar (ground truth)")
    ax.axhline(NEAR_M, color="#777777", ls=":", lw=1)
    ax.text(0.5, NEAR_M + 0.5, "32 m near-field limit", fontsize=fs - 1, color="#555555")
    if now is not None:
        ax.axvline(now, color="#D93025", lw=1.2)
    ax.set_xlim(0, 60)
    ax.set_xlabel("time (s)", fontsize=fs)
    ax.set_ylabel("distance to the front car (m)", fontsize=fs)
    ax.tick_params(labelsize=fs - 1)
    ax.grid(alpha=0.25)
    ax.legend(loc="upper left", fontsize=fs - 1, ncol=2, framealpha=0.9)


def _value_lines(seg, rec, A, k):
    s = SEGS[seg]
    if not rec.get("has_target") or "py_max" not in rec:
        return [("No front car in the ego lane in this frame.", "#333333", False)]
    mc = A / (rec["py_max"] - s["y_h"])
    raw, sc = rec["pred_live"], rec["pred_live"] * k
    out = []
    if rec["paired"]:
        g = rec["radar"]
        out.append((f"Radar (truth, never used to compute)   {g:6.2f} m", C_RADAR, True))
    else:
        g = None
        out.append(("Radar: this frame's radar return did not match the car,", "#777777", False))
        out.append(("        so it is outside the scored set", "#777777", False))

    def e(x):
        return "" if g is None else f"   {(x - g) / g * 100:+5.1f}%"
    out.append((f"Method C   {A:.0f} / ({rec['py_max']:.1f} − {s['y_h']:.1f}) = {mc:6.2f} m{e(mc)}",
                C_METHOD_C, True))
    out.append((f"Depth model raw ({MODEL})              {raw:6.2f} m{e(raw)}", "#6B6B6B", True))
    out.append((f"Depth model × k  (k = {k:.3f})           {sc:6.2f} m{e(sc)}", C_SCALED, True))
    out.append((f"k = median(Method C ÷ model) over this clip; no radar", "#555555", False))
    return out


def render_video(seg, recs, scale, k, plt, limit=0):
    import cv2
    s = SEGS[seg]
    A = scale["A"]
    ser = _series(recs, A, s["y_h"], k)
    fdir = OUT / "cache" / seg / "video_frames"
    if fdir.exists():
        shutil.rmtree(fdir)
    fdir.mkdir(parents=True)
    for j, rec in enumerate(recs[:limit] if limit else recs):
        img = cv2.imread(str(FRAMES / s["tag"] / "frames" / f"{rec['frame_idx']}.jpg"))
        H, W = img.shape[:2]
        depth = np.load(OUT / "cache" / seg / "depth" / f"{rec['frame_idx']}.npy")
        fig = plt.figure(figsize=(19.2, 10.8), dpi=100)
        fig.text(0.01, 0.99, f"comma2k19  {seg} ({s['date']})   frame {rec['frame_idx']}   "
                 f"t = {rec['t']:5.1f} s", fontsize=15, fontweight="bold", va="top")
        fig.text(0.99, 0.99, "Real footage, every 4th frame (5 per second = real time).  "
                 "Every number is computed by the project's own code.", fontsize=11,
                 va="top", ha="right", color="#444444")
        a1 = fig.add_axes([0.005, 0.37, 0.49, 0.54])
        a2 = fig.add_axes([0.505, 0.37, 0.49, 0.54])
        draw_scene(a1, img, seg, scale, rec)
        a1.set_title("Method C: road markings only, no learned model", fontsize=14,
                     fontweight="bold", color=C_METHOD_C)
        im = draw_depth(a2, depth, W, H, rec)
        a2.set_title(f"Depth model ({MODEL}) output, scaled by the marking constant k",
                     fontsize=14, fontweight="bold", color=C_SCALED)
        cax = fig.add_axes([0.86, 0.39, 0.12, 0.012])
        cb = fig.colorbar(im, cax=cax, orientation="horizontal")
        cb.set_label("model depth (m)", fontsize=10, color="white", fontweight="bold")
        cb.ax.xaxis.set_label_position("top")
        cb.ax.tick_params(labelsize=8, colors="white")
        at = fig.add_axes([0.01, 0.03, 0.36, 0.30])
        at.axis("off")
        y = 0.95
        for text, color, bold in _value_lines(seg, rec, A, k):
            at.text(0.0, y, text, fontsize=12.5, color=color, family="DejaVu Sans Mono",
                    fontweight="bold" if bold else "normal", va="top", transform=at.transAxes)
            y -= 0.16
        a3 = fig.add_axes([0.42, 0.07, 0.565, 0.26])
        draw_series(a3, ser, now=rec["t"])
        fig.savefig(fdir / f"{j:04d}.png", dpi=100)
        plt.close(fig)
        if (j + 1) % 50 == 0:
            print(f"[{seg}] rendered {j + 1}/{len(recs)}")
    if limit:
        return
    mp4 = OUT / f"demo_{seg}.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", "5", "-i",
                    str(fdir / "%04d.png"), "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-crf", "20", str(mp4)], check=True)
    print(f"[{seg}] wrote {mp4}")


def pick_frame(recs, A, y_h, k):
    """A near-field evaluated frame whose Method C error is the median one -- not the best."""
    ev = [r for r in recs if r["paired"] and "py_max" in r and r["radar"] < NEAR_M and r.get("poly")]
    err = np.array([abs(A / (r["py_max"] - y_h) - r["radar"]) / r["radar"] for r in ev])
    return ev[int(np.argsort(err)[len(err) // 2])]


def still_method_c(seg, recs, scale, plt):
    import cv2
    s, A = SEGS[seg], scale["A"]
    rec = pick_frame(recs, A, s["y_h"], 1.0)
    img = cv2.imread(str(FRAMES / s["tag"] / "frames" / f"{rec['frame_idx']}.jpg"))
    mc = A / (rec["py_max"] - s["y_h"])
    fig = plt.figure(figsize=(16, 7.6), dpi=150)
    ax = fig.add_axes([0.0, 0.0, 0.62, 1.0])
    draw_scene(ax, img, seg, scale, rec, fs=12)
    at = fig.add_axes([0.64, 0.02, 0.35, 0.96])
    at.axis("off")
    steps = [
        ("Method C, one frame of real footage", "#111111", 17, "bold"),
        (f"comma2k19 {seg} ({s['date']}), frame {rec['frame_idx']}", "#555555", 11, "normal"),
        ("", None, 6, "normal"),
        ("① Horizon row y_h", C_HORIZON, 14, "bold"),
        ("Two lane lines (green) are parallel on the road,\nso in the image they meet at one point"
         f"\n(the vanishing point). That row is the horizon:\ny_h = {s['y_h']:.1f}", "#222222", 12, "normal"),
        ("② Camera constant A = height × focal length", "#333333", 14, "bold"),
        ("Measured from how long the painted dashes take\nto pass the white-circled rows (next figure):"
         f"\nA = {A:.0f}  (re-derived from the frames: {scale['A_live']:.1f})", "#222222", 12, "normal"),
        ("③ Front car's contact with the road", C_METHOD_C, 14, "bold"),
        (f"Lowest pixel of the YOLO mask (orange): py = {rec['py_max']:.1f}", "#222222", 12, "normal"),
        ("Distance", "#111111", 14, "bold"),
        (f"d = A / (py − y_h) = {A:.0f} / {rec['py_max'] - s['y_h']:.1f} = {mc:.2f} m", C_METHOD_C, 14, "bold"),
        (f"Car's own radar: {rec['radar']:.2f} m    error {(mc - rec['radar']) / rec['radar'] * 100:+.1f}%",
         "#111111", 13, "normal"),
        ("", None, 6, "normal"),
        ("This frame is the median-error frame of the clip,\nnot the best one.", "#777777", 10, "normal"),
    ]
    y = 0.98
    for text, color, size, weight in steps:
        if text:
            at.text(0, y, text, fontsize=size, color=color, fontweight=weight, va="top",
                    transform=at.transAxes, linespacing=1.3)
        y -= 0.032 * (text.count("\n") + 1) * size / 11 + 0.018
    fig.savefig(OUT / f"01_method_c_explained_{seg}.png", dpi=150, facecolor="white")
    plt.close(fig)


def still_scale(seg, scale, plt):
    """How A comes out of dash timing: the dash reaches the near row `lag` frames later."""
    import cv2
    s = SEGS[seg]
    L = next(l for l in scale["lines"] if l["accepted"])
    # the row pair whose A is closest to the adopted median, among pairs at least 70 rows
    # apart -- a representative pair, not the widest (the widest reads low on both lines)
    pair = min((e for e in L["pairs"] if e["y_near"] - e["y_far"] >= 70),
               key=lambda e: abs(e["A"] - scale["A"]))
    (xf, yf), (xn, yn) = [p for p in L["points"] if p[1] == pair["y_far"]][0], \
                         [p for p in L["points"] if p[1] == pair["y_near"]][0]
    far = np.array(L["signals"][f"{xf},{yf}"])
    near = np.array(L["signals"][f"{xn},{yn}"])
    period = L["period"]
    lag = pair["dist_m"] / CYCLE_M * period
    # a stretch where both rows are clean: highest far-row correlation over 3 s windows
    win = int(3 * FPS)
    best, i0 = -1, 0
    for i in range(0, len(far) - win - int(lag) - 1, 5):
        c = np.corrcoef(far[i:i + win], near[i + int(round(lag)):i + int(round(lag)) + win])[0, 1]
        if c > best:
            best, i0 = c, i
    seg_far = far[i0:i0 + win]
    pk = i0 + int(np.argmax(seg_far[: int(period) + 2]))
    frames = _frames(s["tag"])
    fig = plt.figure(figsize=(16, 8), dpi=150)
    n_strip = 4
    for j in range(n_strip):
        fi = pk + j                      # consecutive frames: the dash moves frame by frame
        img = cv2.imread(str(frames[fi]))
        x0 = int(min(xf, xn)) - 110
        x1 = int(max(xf, xn)) + 110
        crop = img[yf - 60: yn + 40, max(0, x0): x1]
        ax = fig.add_axes([0.02 + j * 0.245, 0.60, 0.225, 0.32])
        ax.imshow(crop[..., ::-1], extent=(max(0, x0), x1, yn + 40, yf - 60))
        for yy, col in ((yf, "#4285F4"), (yn, C_METHOD_C)):
            ax.axhline(yy, color=col, lw=2)
        ax.set_title(f"frame {fi + 1}  (+{fi - pk} frames)", fontsize=12)
        if j == 0:
            ax.text(max(0, x0) + 6, yf - 6, f"far row {yf}", color="#4285F4", fontsize=11,
                    fontweight="bold", va="bottom", backgroundcolor="#FFFFFFB0")
            ax.text(max(0, x0) + 6, yn - 6, f"near row {yn}", color=C_METHOD_C, fontsize=11,
                    fontweight="bold", va="bottom", backgroundcolor="#FFFFFFB0")
        ax.axis("off")
    fig.text(0.02, 0.975, "How the camera constant A is measured: the same painted dash passes a far row, "
             "then a near row", fontsize=15, fontweight="bold", va="top")
    ax = fig.add_axes([0.06, 0.08, 0.60, 0.50])
    t = np.arange(len(far)) / FPS
    sl = slice(i0, i0 + win)
    ax.plot(t[sl], far[sl], color="#4285F4", lw=2, label=f"brightness at far row {yf}")
    ax.plot(t[sl], near[sl], color=C_METHOD_C, lw=2, label=f"brightness at near row {yn}")
    ax.annotate("", xy=((pk + lag) / FPS, far[pk] * 1.05), xytext=(pk / FPS, far[pk] * 1.05),
                arrowprops=dict(arrowstyle="->", lw=1.8))
    ax.text((pk + lag / 2) / FPS, far[pk] * 1.12, f"lag = {lag:.2f} frames", ha="center", fontsize=12,
            bbox=dict(fc="white", ec="none", alpha=0.85))
    ax.annotate("", xy=((pk + period) / FPS, far[pk] * 0.55), xytext=(pk / FPS, far[pk] * 0.55),
                arrowprops=dict(arrowstyle="<->", lw=1.4, color="#4285F4"))
    ax.text((pk + period / 2) / FPS, far[pk] * 0.6, f"one dash cycle = {period:.2f} frames",
            ha="center", fontsize=11, color="#4285F4", bbox=dict(fc="white", ec="none", alpha=0.85))
    ax.set_ylim(top=max(far[sl].max(), near[sl].max()) * 1.3)
    ax.set_xlabel("time (s)")
    ax.set_ylabel("dash brightness at the row")
    ax.legend(loc="upper right", fontsize=10)
    ax.grid(alpha=0.25)
    inv = 1 / (yf - s["y_h"]) - 1 / (yn - s["y_h"])
    lines = [
        ("Road gap between the two rows", 13, "bold", "#111111"),
        (f"= legal cycle × lag ÷ cycle frames\n= {CYCLE_M} m × {lag:.2f} ÷ {period:.2f} = {pair['dist_m']:.2f} m",
         12, "normal", "#222222"),
        ("(vehicle speed cancels out)", 11, "normal", "#777777"),
        ("Plug into d = A / (py − y_h) for both rows", 13, "bold", "#111111"),
        (f"A = {pair['dist_m']:.2f} / [1/({yf}−{s['y_h']}) − 1/({yn}−{s['y_h']})]\n  = {pair['A']:.0f}  (this row pair)",
         12, "normal", "#222222"),
        (f"All accepted row pairs → median A = {scale['A']:.0f}", 13, "bold", C_METHOD_C),
        ("Lag and cycle come from the teammate's odometer code;\n"
         "this step only feeds it the vanishing-point horizon.", 10, "normal", "#777777"),
    ]
    y = 0.56
    for text, size, weight, color in lines:
        fig.text(0.70, y, text, fontsize=size, fontweight=weight, color=color, va="top", linespacing=1.35)
        y -= 0.028 * (text.count("\n") + 1) * size / 11 + 0.012
    fig.savefig(OUT / f"02_how_A_is_measured_{seg}.png", dpi=150, facecolor="white")
    plt.close(fig)


def still_depth(seg, recs, scale, k, plt):
    import cv2
    s, A = SEGS[seg], scale["A"]
    rec = pick_frame(recs, A, s["y_h"], k)
    img = cv2.imread(str(FRAMES / s["tag"] / "frames" / f"{rec['frame_idx']}.jpg"))
    H, W = img.shape[:2]
    depth = np.load(OUT / "cache" / seg / "depth" / f"{rec['frame_idx']}.npy")
    ser = _series(recs, A, s["y_h"], k)
    fig = plt.figure(figsize=(18, 6.4), dpi=150)
    a1 = fig.add_axes([0.005, 0.15, 0.32, 0.76])
    a1.imshow(img[..., ::-1])
    a1.plot(rec["px"], rec["py_band"], "x", color="white", ms=12, mew=2.5)
    a1.axis("off")
    a1.set_title(f"① Input frame ({seg}, {rec['frame_idx']})", fontsize=13, fontweight="bold")
    a2 = fig.add_axes([0.335, 0.15, 0.32, 0.76])
    im = draw_depth(a2, depth, W, H, rec, fs=12)
    a2.set_title(f"② {MODEL} depth map (metres, raw)", fontsize=13, fontweight="bold")
    cb = fig.colorbar(im, ax=a2, orientation="horizontal", fraction=0.05, pad=0.02)
    cb.set_label("model depth (m)")
    a3 = fig.add_axes([0.71, 0.17, 0.27, 0.72])
    n = ser["radar"] < NEAR_M
    lim = (5, NEAR_M + 3)
    a3.plot(lim, lim, color="#333333", lw=1)
    a3.fill_between(lim, [x * 0.9 for x in lim], [x * 1.1 for x in lim], color="#EEEEEE")
    e_raw = _near_err(ser["raw"], ser["radar"])[0]
    e_sc = _near_err(ser["scaled"], ser["radar"])[0]
    a3.plot(ser["radar"][n], ser["raw"][n], "o", color=C_RAW, ms=4, label=f"raw: median error {e_raw:.1f}%")
    a3.plot(ser["radar"][n], ser["scaled"][n], "o", color=C_SCALED, ms=4,
            label=f"× marking k = {k:.3f}: {e_sc:.1f}%")
    a3.set_xlim(lim)
    a3.set_ylim(lim)
    a3.set_xlabel("radar distance (m)")
    a3.set_ylabel("depth model distance (m)")
    a3.set_title(f"③ Every scored near-field frame (n = {int(n.sum())})", fontsize=13, fontweight="bold")
    a3.legend(loc="upper left", fontsize=10)
    a3.grid(alpha=0.25)
    a3.text(lim[1] - 0.5, lim[0] + 0.8, "shaded: ±10%", ha="right", fontsize=9, color="#777777")
    fig.text(0.005, 0.015, f"k = median(Method C distance ÷ model depth) over every front car in the clip "
             f"that Method C places nearer than {NEAR_M:.0f} m. The radar is not used to set k.",
             fontsize=11, color="#444444")
    fig.savefig(OUT / f"03_depth_model_explained_{seg}.png", dpi=150, facecolor="white")
    plt.close(fig)


def still_series(seg, recs, scale, k, plt):
    s, A = SEGS[seg], scale["A"]
    ser = _series(recs, A, s["y_h"], k)
    errs = {key: _near_err(ser[key], ser["radar"])[0] for key in ("mc", "raw", "scaled")}
    fig, ax = plt.subplots(figsize=(16, 6), dpi=150)
    draw_series(ax, ser, errs=errs, fs=12)
    n = int((ser["radar"] < NEAR_M).sum())
    ax.set_title(f"comma2k19 {seg} ({s['date']}): distance to the front car, 60 s, every scored frame "
                 f"(n = {len(ser['t'])}, near field {n})", fontsize=14, fontweight="bold", loc="left")
    fig.tight_layout()
    fig.savefig(OUT / f"05_distance_over_time_{seg}.png", dpi=150, facecolor="white")
    plt.close(fig)
    return errs


def still_models(seg, fid, recs, scale, plt):
    import cv2
    s = SEGS[seg]
    rec = next(r for r in recs if r["frame_idx"] == fid)
    info = prep_models(seg, fid)
    img = cv2.imread(str(FRAMES / s["tag"] / "frames" / f"{fid}.jpg"))
    H, W = img.shape[:2]
    fig = plt.figure(figsize=(18, 9.4), dpi=150)
    ax = fig.add_axes([0.005, 0.47, 0.325, 0.40])
    ax.imshow(img[..., ::-1])
    ax.plot(rec["px"], rec["py_band"], "x", color="white", ms=12, mew=2.5)
    ax.axis("off")
    g = rec["radar"]
    ax.set_title(f"Input ({seg} {fid});  radar {g:.2f} m", fontsize=13, fontweight="bold")
    slots = [(0.337, 0.47), (0.669, 0.47), (0.005, 0.02), (0.337, 0.02), (0.669, 0.02)]
    for (x, y), m in zip(slots, DEPTH_MODELS):
        a = fig.add_axes([x, y, 0.325, 0.40])
        d, inf = info["maps"][m], info[m]
        if inf["kind"] == "metric":
            a.imshow(d, cmap="turbo_r", vmin=5, vmax=80, extent=(0, W, H, 0))
            raw, sc = inf["value"], inf["value"] * inf["k"]
            title = (f"{m}\nraw {raw:.1f} m ({(raw - g) / g * 100:+.0f}%)  →  × k {sc:.1f} m "
                     f"({(sc - g) / g * 100:+.1f}%)")
        else:
            a.imshow(d, cmap="turbo", extent=(0, W, H, 0))
            title = f"{m}\nrelative depth only (no metres); needs an anchor"
        a.plot(rec["px"], rec["py_band"], "x", color="white", ms=12, mew=2.5)
        a.set_title(title, fontsize=11.5)
        a.axis("off")
    fig.text(0.005, 0.975, "Five depth models on the same frame: their raw metres disagree, "
             "one marking constant per model brings them together", fontsize=14, fontweight="bold", va="top")
    fig.savefig(OUT / f"04_five_models_{seg}.png", dpi=150, facecolor="white")
    plt.close(fig)


# ------------------------------------------------------------------------------ main

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stage", choices=["prep", "render", "all"], default="all")
    ap.add_argument("--segments", nargs="+", default=list(SEGS))
    ap.add_argument("--no-video", action="store_true", help="stills only")
    ap.add_argument("--video-limit", type=int, default=0, help="render only the first N video frames")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    summary = {}
    for seg in args.segments:
        scale = prep_scale(seg)
        recs = prep_frames(seg)
        k = marking_constant(seg, MODEL)
        if args.stage == "prep":
            continue
        plt = _setup_fonts()
        still_method_c(seg, recs, scale, plt)
        still_scale(seg, scale, plt)
        still_depth(seg, recs, scale, k, plt)
        errs = still_series(seg, recs, scale, k, plt)
        rec = pick_frame(recs, scale["A"], SEGS[seg]["y_h"], k)
        still_models(seg, rec["frame_idx"], recs, scale, plt)
        summary[seg] = dict(A=scale["A"], k=k, near_median_error_pct=errs)
        print(f"[{seg}] A {scale['A']:.0f}  k {k:.3f}  near-field median error: "
              + "  ".join(f"{key} {v:.2f}%" for key, v in errs.items()))
        if not args.no_video:
            render_video(seg, recs, scale, k, plt, args.video_limit)
    if summary:
        (OUT / "summary.json").write_text(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
