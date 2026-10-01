"""Render a clean, Chinese-labelled demo clip from a finished pipeline-B run.

This only draws; it measures nothing. Every number on screen comes straight from
the run's tracks.json (written by tools/dashcam_range_speed.py), and the drawing
follows the same rules as that tool's own annotated video:
  * tracks shorter than one second, and duplicates, are not drawn;
  * a car whose ground-contact sensitivity exceeds --max-sens (m/px) is far range:
    it gets a thin grey box and no numbers, because far-range distance is not
    trustworthy (docs/FAILURE_BOUNDARIES.md);
  * near cars show forward distance (m) and absolute speed (km/h) for that frame.
Labels refresh every --hold frames so the digits stay readable; the values are the
per-frame measurements at the refresh frame, not smoothed or edited.

  python3 tools/report/render_demo_video.py --frames-dir <frames> --tracks <run>/tracks.json \
      --fps 20 --start-s 22 --end-s 36 --out demo.mp4 --gif demo.gif
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

PALETTE = [(46, 204, 113), (52, 152, 219), (241, 196, 15), (231, 76, 60), (155, 89, 182),
           (26, 188, 156), (230, 126, 34), (236, 112, 160), (0, 184, 212), (163, 203, 56)]
FAR_GREY = (170, 170, 170)
FONT_CANDIDATES = ["/mnt/c/Windows/Fonts/msjhbd.ttc", "/mnt/c/Windows/Fonts/msjh.ttc",
                   "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"]


def load_font(size: int) -> ImageFont.FreeTypeFont:
    for p in FONT_CANDIDATES:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    raise SystemExit("No CJK font found; pass a font path in FONT_CANDIDATES.")


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--frames-dir", required=True)
    ap.add_argument("--tracks", required=True, help="tracks.json from dashcam_range_speed.py")
    ap.add_argument("--fps", type=float, required=True)
    ap.add_argument("--start-s", type=float, default=0.0)
    ap.add_argument("--end-s", type=float, default=None)
    ap.add_argument("--max-sens", type=float, default=0.8, help="Same far-range threshold as the pipeline.")
    ap.add_argument("--hold", type=int, default=4, help="Refresh label digits every N frames.")
    ap.add_argument("--source", default="影像來源:comma2k19 公開資料集(MIT 授權)")
    ap.add_argument("--out", required=True, help="Output mp4 (H.264).")
    ap.add_argument("--width", type=int, default=0, help="Output width; 0 keeps the frame width.")
    ap.add_argument("--gif", default="", help="Also write a GIF preview.")
    ap.add_argument("--gif-width", type=int, default=720)
    ap.add_argument("--gif-fps", type=int, default=10)
    return ap.parse_args()


def rounded_label(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, font, fg, bg, pad=6):
    x, y = xy
    l, t, r, b = draw.textbbox((x, y), text, font=font)
    draw.rounded_rectangle((l - pad, t - pad // 2 - 1, r + pad, b + pad // 2 + 1), radius=6, fill=bg)
    draw.text((x, y), text, font=font, fill=fg)
    return (l - pad, t - pad, r + pad, b + pad)


def main() -> None:
    a = parse_args()
    data = json.loads(Path(a.tracks).read_text())
    frames = sorted(Path(a.frames_dir).glob("*.jpg")) + sorted(Path(a.frames_dir).glob("*.png"))
    if not frames:
        raise SystemExit("no frames found")
    ego = data.get("ego_visual_kmh") or []
    i0 = int(round(a.start_s * a.fps))
    i1 = len(frames) if a.end_s is None else min(len(frames), int(round(a.end_s * a.fps)))

    per_frame: dict[int, list[tuple[int, dict]]] = {}
    for tid, rec in data["tracks"].items():
        if len(rec["obs"]) < int(a.fps) or rec.get("duplicate_of"):
            continue
        for o in rec["obs"]:
            per_frame.setdefault(o["frame"], []).append((int(tid), o))

    w0, h0 = Image.open(frames[0]).size
    scale = (a.width / w0) if a.width else 1.0
    W, H = int(round(w0 * scale / 2) * 2), int(round(h0 * scale / 2) * 2)
    f_big, f_mid, f_small = load_font(int(30 * W / 1164)), load_font(int(21 * W / 1164)), load_font(int(16 * W / 1164))

    held: dict[int, str] = {}
    ego_txt = "—"
    tmp = Path(tempfile.mkdtemp(prefix="demo_"))
    for k, i in enumerate(range(i0, i1)):
        im = Image.open(frames[i]).convert("RGB")
        if scale != 1.0:
            im = im.resize((W, H), Image.LANCZOS)
        ov = Image.new("RGBA", im.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(ov)
        refresh = (k % a.hold == 0)
        obs = sorted(per_frame.get(i, []), key=lambda r: -r[1]["py"])
        placed: list[tuple[int, int, int, int]] = []
        for tid, o in obs:
            far = o["sens"] is None or not np.isfinite(o["sens"]) or o["sens"] > a.max_sens
            x1, y1, x2, y2 = (v * scale for v in o["box"])
            if far:
                d.rectangle((x1, y1, x2, y2), outline=FAR_GREY + (150,), width=1)
                continue
            col = PALETTE[tid % len(PALETTE)]
            d.rectangle((x1, y1, x2, y2), outline=col + (255,), width=3)
            gx, gy = o["px"] * scale, o["py"] * scale
            d.ellipse((gx - 4, gy - 4, gx + 4, gy + 4), fill=col + (255,))
            if refresh or tid not in held:
                spd = "" if o.get("abs_kmh") is None else f"  {o['abs_kmh']:.0f} km/h"
                held[tid] = f"{o['fwd_m']:.1f} m{spd}"
            text = held[tid]
            tw = d.textlength(text, font=f_mid)
            tx = min(max(4, x1), W - tw - 10)
            ty = max(70, y1 - 34)
            for _ in range(8):
                box = (tx - 6, ty - 4, tx + tw + 6, ty + 30)
                if all(box[2] <= r[0] or box[0] >= r[2] or box[3] <= r[1] or box[1] >= r[3] for r in placed):
                    break
                ty -= 34
            placed.append((tx - 6, ty - 4, tx + tw + 6, ty + 30))
            rounded_label(d, (int(tx), int(ty)), text, f_mid, (255, 255, 255, 255), col + (215,))
        # top bar: ego speed
        if refresh or ego_txt == "—":
            v = ego[i] if i < len(ego) else None
            ego_txt = f"{v:.0f} km/h" if v is not None and np.isfinite(v) else "沒有讀值"
        d.rectangle((0, 0, W, 58), fill=(10, 14, 22, 175))
        d.text((16, 12), "自車速", font=f_mid, fill=(200, 210, 225, 255))
        d.text((16 + d.textlength("自車速 ", font=f_mid), 6), ego_txt, font=f_big, fill=(255, 255, 255, 255))
        cap = "由車道虛線的週期量得"
        d.text((16 + d.textlength("自車速 ", font=f_mid) + d.textlength(ego_txt + "  ", font=f_big), 16),
               cap, font=f_small, fill=(170, 182, 200, 255))
        sw = d.textlength(a.source, font=f_small)
        d.text((W - sw - 16, 19), a.source, font=f_small, fill=(170, 182, 200, 255))
        # legend
        leg = "框上數字:與這台車的距離、這台車的時速;灰框:距離太遠,不顯示數字"
        lw = d.textlength(leg, font=f_small)
        d.rounded_rectangle((12, H - 40, 28 + lw, H - 10), radius=6, fill=(10, 14, 22, 160))
        d.text((20, H - 36), leg, font=f_small, fill=(225, 230, 238, 255))
        Image.alpha_composite(im.convert("RGBA"), ov).convert("RGB").save(tmp / f"f{k:05d}.png")

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    enc = "libx264" if "libx264" in subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True).stdout else "libopenh264"
    q = ["-crf", "23", "-preset", "slow"] if enc == "libx264" else ["-b:v", "3M"]
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-framerate", str(a.fps), "-i", str(tmp / "f%05d.png"),
                    "-c:v", enc, *q, "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)], check=True)
    print(f"saved: {out} ({out.stat().st_size / 1e6:.1f} MB, {enc})")
    if a.gif:
        pal = tmp / "pal.png"
        vf = f"fps={a.gif_fps},scale={a.gif_width}:-1:flags=lanczos"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(out), "-vf", vf + ",palettegen=stats_mode=diff", str(pal)], check=True)
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(out), "-i", str(pal), "-lavfi",
                        vf + " [x]; [x][1:v] paletteuse=dither=bayer:bayer_scale=4", a.gif], check=True)
        print(f"saved: {a.gif} ({Path(a.gif).stat().st_size / 1e6:.1f} MB)")
    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
