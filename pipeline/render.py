"""Output video: every processed frame with each car's distance (and speed when near) written above its box, the way
tools/dashcam_range_speed.py draws its own video. Chinese text uses Microsoft JhengHei when it is installed; otherwise
the captions fall back to English."""
from __future__ import annotations

import shutil
import subprocess
import zlib
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

FONTS = [Path("/mnt/c/Windows/Fonts/msjhbd.ttc"), Path("C:/Windows/Fonts/msjhbd.ttc")]
GREY = (150, 150, 150)


def _colour(tid: str) -> tuple[int, int, int]:
    rng = np.random.default_rng(zlib.crc32(tid.encode()))      # same colour for the same id on every run
    b, g, r = cv2.cvtColor(np.uint8([[[int(rng.integers(0, 180)), 200, 255]]]), cv2.COLOR_HSV2BGR)[0, 0]
    return int(b), int(g), int(r)


def video(frames: list[Path], objs: pd.DataFrame, ego_kmh: np.ndarray, fps: float, step: int, out: Path, work: Path,
          title: str) -> Path:
    from PIL import Image, ImageDraw, ImageFont

    font_file = next((f for f in FONTS if f.exists()), None)
    zh = font_file is not None
    tmp = work / "render"
    tmp.mkdir(parents=True, exist_ok=True)
    by_frame = {f: g for f, g in objs.groupby("frame_idx")}
    W = cv2.imread(str(frames[0])).shape[1]
    fs = max(18, round(W / 50))
    fonts = {s: (ImageFont.truetype(str(font_file), s) if zh else ImageFont.load_default()) for s in (fs, fs - 3, 26, 20)}
    for k, fi in enumerate(range(0, len(frames), step)):
        img = cv2.imread(str(frames[fi]))
        labels = []
        g = by_frame.get(fi)
        if g is not None:
            for r in g.sort_values("y1", ascending=False).itertuples():
                has = np.isfinite(r.dist_m) and r.dist_m <= 100
                near = has and "far" not in str(r.flag)
                col = _colour(str(r.track_id)) if near else GREY
                cv2.rectangle(img, (int(r.x0), int(r.y0)), (int(r.x1), int(r.y1)), col, 2)
                if has:
                    s = (f"{r.dist_m:.1f} m   {r.abs_kmh:.0f} km/h" if np.isfinite(r.abs_kmh) else f"{r.dist_m:.1f} m") if near \
                        else f"{r.dist_m:.0f} m"
                    labels.append((s, int(r.x0), int(r.y0), col, fs if near else fs - 3))
        img[:76] = (img[:76].astype(np.float32) * 0.35).astype(np.uint8)
        pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        dr = ImageDraw.Draw(pil)
        placed = [(0, 0, W, 76)]
        for s, x, y, col, size in labels:
            tw, th = dr.textbbox((0, 0), s, font=fonts[size], stroke_width=3)[2:]
            tx, ty = min(max(2, x), W - tw - 2), max(78, y - th - 6)
            for _ in range(8):
                b = (tx, ty, tx + tw + 6, ty + th + 4)
                if all(b[2] <= q[0] or b[0] >= q[2] or b[3] <= q[1] or b[1] >= q[3] for q in placed):
                    break
                ty = max(78, ty - th - 6)
            placed.append((tx, ty, tx + tw + 6, ty + th + 4))
            dr.text((tx, ty), s, font=fonts[size], fill=col[::-1], stroke_width=3, stroke_fill=(0, 0, 0))
        e = ego_kmh[fi] if fi < len(ego_kmh) else np.nan
        ego_txt = (f"本車速度 {e:.1f} km/h" if zh else f"ego {e:.1f} km/h") if np.isfinite(e) else ("本車速度:讀不到" if zh else "ego: no reading")
        dr.text((14, 8), title, font=fonts[26], fill=(255, 255, 255), stroke_width=2, stroke_fill=(0, 0, 0))
        dr.text((14, 44), f"{ego_txt}    t = {fi / fps:.1f} s", font=fonts[20], fill=(255, 255, 255), stroke_width=2, stroke_fill=(0, 0, 0))
        cv2.imwrite(str(tmp / f"f{k:05d}.jpg"), cv2.cvtColor(np.asarray(pil), cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 90])
    encoder = shutil.which("ffmpeg") or "ffmpeg"
    subprocess.run([encoder, "-hide_banner", "-loglevel", "error", "-y", "-framerate", f"{fps / step:.4f}", "-i", str(tmp / "f%05d.jpg"),
                    "-vf", "scale=min(1280\\,iw):-2", "-c:v", "libx264", "-crf", "21", "-pix_fmt", "yuv420p", str(out)], check=True)
    shutil.rmtree(tmp, ignore_errors=True)
    return out
