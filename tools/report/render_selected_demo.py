"""Draw a still, Chinese-labelled demo of tools/selected_vehicle_speed.py.

The measuring is done by that module, unchanged; this script only draws, in the
same style as render_demo_video.py:
  * a car the module trusts gets a coloured box, its ground-contact dot, and
    "distance m  speed km/h";
  * a car the module flags gets a WHITE box and WHITE text with the reason
    appended (too far, too few frames, too close, no detection). With
    --hide-unreliable such a car is not drawn at all, matching the module.
The top bar shows the ego speed that was typed in (INPUT-2), not a measured one.

The two front-page images come from comma2k19 seg21 (frames and parameters as in
data/output/comma2k19_radar_eval/README.md section 3; distance correction left at
1.0 like that evaluation). The ego speed typed in is the car's CAN speed at the
frame; boxes are the tracked cars' boxes from that evaluation's tracks.json.

  G="--frames-dir <seg21>/frames --fps 20 --hood-y 630 --pointcloud-scale 1.032805 \\
     --reference-pointcloud data/output/sharp_gaussians/c2k19_seg21_ref.ply"
  python3 tools/report/render_selected_demo.py $G --frame 603 --ego-kmh 114.2 \\
      --box 606,365,847,531 --box 290,373,382,424 --box 428,371,457,392 --box 543,375,564,390 \\
      --out docs/media/select_lead_car.jpg
  python3 tools/report/render_selected_demo.py $G --frame 450 --ego-kmh 115.3 \\
      --box 312,376,452,459 --box 843,373,980,441 --box 483,370,533,412 \\
      --box 768,373,821,405 --box 543,381,564,394 --out docs/media/select_multi_car.jpg

The lead car in frame 603 is the one the radar tracks: 119.0 km/h here, 120.9 km/h
by radar (CAN speed + radar range rate, seg21_pairs.csv).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from render_demo_video import PALETTE, load_font, rounded_label                    # noqa: E402
from selected_vehicle_speed import PROJECT_ROOT, finalize, measure, window_detections  # noqa: E402
from dashcam_range_speed import build_geometry                                     # noqa: E402

REASON_ZH = {"far_field": "太遠", "too_few_frames": "前後追不到", "below_hood": "太近",
             "no_detection": "找不到車", "no_ego": "本車車速無讀值"}


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--frames-dir", required=True)
    ap.add_argument("--fps", type=float, required=True)
    ap.add_argument("--reference-pointcloud", required=True)
    ap.add_argument("--pointcloud-scale", type=float, required=True)
    ap.add_argument("--hood-y", type=int, default=900)
    ap.add_argument("--distance-correction", type=float, default=1.0)
    ap.add_argument("--yolo-model", default="checkpoints/yolov8m-seg.pt")
    ap.add_argument("--conf", type=float, default=0.3)
    ap.add_argument("--max-sens-m-per-px", type=float, default=0.8)
    ap.add_argument("--window-s", type=float, default=1.0)
    ap.add_argument("--frame", type=int, required=True)
    ap.add_argument("--ego-kmh", type=float, required=True)
    ap.add_argument("--box", action="append", required=True, help="x1,y1,x2,y2; repeat for more cars.")
    ap.add_argument("--hide-unreliable", action="store_true")
    ap.add_argument("--ego-caption", default="使用者輸入,這裡用車上的車速表")
    ap.add_argument("--source", default="影像來源:comma2k19 公開資料集(MIT 授權)")
    ap.add_argument("--out", required=True, help="Output image (jpg/png).")
    ap.add_argument("--out-json", default="", help="Also write the module's results.")
    return ap.parse_args()


def draw_results(im: Image.Image, results: list[dict], ego_kmh: float, hide_unreliable: bool,
                 ego_caption: str, source: str) -> Image.Image:
    """Draw the module's results on one frame; returns a new RGB image.
    Shared with tools/selected_vehicle_gui.py so both draw the same way. An entry may be
    None (a car not tracked in this frame of a follow video); it keeps the other cars'
    colours fixed, since a car's colour comes from its position in the list."""
    W, H = im.size
    f_big, f_mid, f_small = (load_font(int(s * W / 1164)) for s in (30, 21, 16))
    ov = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    placed: list[tuple[float, float, float, float]] = []
    order = sorted((k for k in range(len(results)) if results[k] is not None),
                   key=lambda k: -results[k].get("ground_px", [0, H])[1])
    for k in order:
        r = results[k]
        if r["status"] != "ok" and hide_unreliable:
            continue
        x1, y1, x2, y2 = r.get("matched_box", r["box_input"])
        if r["status"] == "ok":
            col, width, fg, bg = PALETTE[k % len(PALETTE)], 3, (255, 255, 255, 255), None
            text = f"{r['range_m']:.1f} m  {r['speed_kmh']:.0f} km/h"
        else:
            col, width, fg, bg = (255, 255, 255), 2, (255, 255, 255, 255), (10, 14, 22, 170)
            why = "、".join(REASON_ZH.get(x, x) for x in r["reasons"])
            if r["status"] != "no_measurement":
                text = f"{r['range_m']:.0f} m  {r['speed_kmh']:.0f} km/h({why},不準)"
            elif "range_m" in r:        # 量得到距離、算不出時速(例如本車車速沒有讀值)
                text = f"{r['range_m']:.1f} m({why},無時速)"
            else:
                text = f"{why},無法量測"
        d.rectangle((x1, y1, x2, y2), outline=col + (255,), width=width)
        if "ground_px" in r:
            gx, gy = r["ground_px"]
            d.ellipse((gx - 4, gy - 4, gx + 4, gy + 4), fill=col + (255,))
        tw = d.textlength(text, font=f_mid)
        tx = min(max(4, x1), W - tw - 10)
        ty = max(70, y1 - 34)
        for _ in range(8):
            lab = (tx - 6, ty - 4, tx + tw + 6, ty + 30)
            if all(lab[2] <= p[0] or lab[0] >= p[2] or lab[3] <= p[1] or lab[1] >= p[3] for p in placed):
                break
            ty -= 34
        placed.append((tx - 6, ty - 4, tx + tw + 6, ty + 30))
        rounded_label(d, (int(tx), int(ty)), text, f_mid, fg, bg or (col + (215,)))

    d.rectangle((0, 0, W, 58), fill=(10, 14, 22, 175))
    d.text((16, 12), "自車速", font=f_mid, fill=(200, 210, 225, 255))
    ego_txt = f"{ego_kmh:.0f} km/h" if ego_kmh is not None else "無讀值"
    x = 16 + d.textlength("自車速 ", font=f_mid)
    d.text((x, 6), ego_txt, font=f_big, fill=(255, 255, 255, 255))
    d.text((x + d.textlength(ego_txt + "  ", font=f_big), 16), ego_caption, font=f_small,
           fill=(170, 182, 200, 255))
    sw = d.textlength(source, font=f_small)
    d.text((W - sw - 16, 19), source, font=f_small, fill=(170, 182, 200, 255))
    leg = ("彩色框:量得準,框上是距離與時速;量不準的車不顯示" if hide_unreliable
           else "彩色框:量得準,框上是距離與時速;白框白字:量不準,數字只供參考")
    lw = d.textlength(leg, font=f_small)
    d.rounded_rectangle((12, H - 40, 28 + lw, H - 10), radius=6, fill=(10, 14, 22, 160))
    d.text((20, H - 36), leg, font=f_small, fill=(225, 230, 238, 255))

    return Image.alpha_composite(im.convert("RGBA"), ov).convert("RGB")


def main() -> None:
    a = parse_args()
    frames = sorted(Path(a.frames_dir).glob("*.jpg")) + sorted(Path(a.frames_dir).glob("*.png"))
    im = Image.open(frames[a.frame]).convert("RGB")
    W, H = im.size
    ply = Path(a.reference_pointcloud)
    if not ply.is_absolute():
        ply = PROJECT_ROOT / ply
    p2p, _ = build_geometry(ply, a.pointcloud_scale, (H, W), a.hood_y, a.distance_correction)

    from ultralytics import YOLO

    frame_dets = window_detections(frames, a.frame, YOLO(a.yolo_model), p2p, a.fps, a.hood_y, a.conf, a.window_s)
    results = []
    for b in a.box:
        xa, ya, xb, yb = (float(v) for v in b.split(","))
        box = [min(xa, xb), min(ya, yb), max(xa, xb), max(ya, yb)]
        results.append(finalize(measure(frame_dets, a.frame, a.ego_kmh, box, a.fps, a.hood_y,
                                        a.max_sens_m_per_px), a.hide_unreliable))
    if a.out_json:
        Path(a.out_json).write_text(json.dumps(results, ensure_ascii=False, indent=1, default=float),
                                    encoding="utf-8")

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    draw_results(im, results, a.ego_kmh, a.hide_unreliable, a.ego_caption, a.source).save(out, quality=90)
    for r in results:
        spd = "—" if r.get("speed_kmh") is None else f"{r['speed_kmh']:.1f}"
        print(f"{r['status']:>14}  range {r.get('range_m', float('nan')):5.1f} m  speed {spd}  {r['reasons']}")
    print(f"saved: {out}")


if __name__ == "__main__":
    main()
