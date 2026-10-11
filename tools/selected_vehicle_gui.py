"""選一台車量時速的圖形介面 —— tools/selected_vehicle_speed.py 的網頁版。

在瀏覽器裡給同一組輸入:
  INPUT-1    拖時間軸(或按前一幀/後一幀)選畫面
  INPUT-2    填這一幀的本車車速
  INPUT-3/4  在畫面上點兩下框一台車:先點左上、再點右下;可以連續框好幾台
  參數       勾「量不準就不顯示」= --hide-unreliable
按「計算」得到這一幀的結果;按「做成跟車影片」則從這一幀往前後各追 3 秒,每一幀都標出
距離與時速。影片的本車車速預設逐幀用系統碼表的讀值(完整管線輸出的 ego_speed.csv,
碼表沒有讀值的幀只給距離),也可以改成整段用 INPUT-2;相對速度每一幀各自用前後各半秒擬合。
量測完全交給 selected_vehicle_speed.py 的函式(門檻相同,結果與命令列版逐位元一致),
結果圖用 tools/report/render_selected_demo.py 的畫法。這支只管介面。

啟動(在 repo 根目錄):
  python tools/selected_vehicle_gui.py
再用瀏覽器開 http://127.0.0.1:7860(WSL 下用 Windows 的瀏覽器開同一個網址即可)。

案例選單內建七支 demo,參數照 docs/CASE_PARAMETERS.md(含距離修正係數);
選「自訂」可以填任何影片或影格資料夾。影片第一次載入時用 ffmpeg 拆成影格
(與完整管線同一套指令,幀號才對得上),放在 --cache-dir/<名稱>/f%05d.jpg。
服務只開在本機 127.0.0.1,影像不會送出去;Gradio 的使用統計已關閉。
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")

try:
    import cv2                  # noqa: E402
    import gradio as gr         # noqa: E402
    import numpy as np          # noqa: E402
    from PIL import Image       # noqa: E402
except ModuleNotFoundError as e:
    sys.exit(f"缺少套件 {e.name}:請在裝了 requirements.txt 的 Python 環境執行"
             "(conda 環境要先 activate),或 pip install -r requirements.txt。")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "tools"))
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "report"))

from dashcam_range_speed import build_geometry                              # noqa: E402
from render_selected_demo import REASON_ZH, draw_results                    # noqa: E402
from selected_vehicle_speed import finalize, measure, track, window_detections  # noqa: E402

# 參數照 docs/CASE_PARAMETERS.md;frames 是由 original_clip_h264.mp4 拆出的幀數,載入時拿來核對。
# dc003、dc007 沒通過距離修正的品質閘,係數維持 1.0(距離未校正)。
PRESETS = {
    "hs005":  dict(fps=29.8883, scale=0.960510, hood=960,  corr=0.760, frames=536),
    "dc002":  dict(fps=30.0,    scale=1.01,     hood=900,  corr=0.811, frames=600),
    "wow001": dict(fps=30.0,    scale=0.962990, hood=755,  corr=0.815, frames=3570),
    "dc008":  dict(fps=30.0,    scale=0.884,    hood=900,  corr=0.854, frames=600),
    "dc006":  dict(fps=29.97,   scale=0.8663,   hood=930,  corr=0.903, frames=1801),
    "dc003":  dict(fps=29.97,   scale=0.854,    hood=960,  corr=1.0,   frames=1798),
    "dc007":  dict(fps=30.0,    scale=1.4421,   hood=1030, corr=1.0,   frames=330),
}
CUSTOM = "自訂"
EGO_ODOMETER, EGO_TYPED = "系統碼表(逐幀)", "我填的值(整段固定)"
EGO_CAPTION = {"dash_odometer": "系統碼表", "interpolated": "系統碼表(短缺口內插)",
               "stopped": "系統判定靜止", "none": "碼表沒有讀值"}
EGO_NOTES = {"wow001": "wow001 的自車速沒有通過驗證(對 OSD 的 MAE 11.97),碼表模式的時速只供參考。"}
STATUS_ZH = {"ok": "可信", "unreliable": "不準", "no_measurement": "量不到"}
HEADERS = ["#", "判定", "車種", "距離 (m)", "相對速度 (km/h)", "時速 (km/h)", "原因", "用到的幀"]
CLIP_S = 3.0                            # 跟車影片:選的畫面前後各幾秒
BOX_COLOR = (0, 210, 0)
PENDING_COLOR = (255, 200, 0)

_model = None
_geometry: dict[tuple, object] = {}
_detections: dict[tuple, dict] = {}     # 同一幀換框重算時不必再跑偵測


def preset_fields(name: str) -> tuple:
    p = PRESETS[name]
    return (f"data/output/dashcam_demo/{name}/original_clip_h264.mp4", p["fps"],
            f"data/output/sharp_gaussians/{name}_ref.ply", p["scale"], p["hood"], p["corr"],
            f"data/output/dashcam_demo/{name}_current/ego_speed.csv")


def resolve(path: str) -> Path:
    p = Path(path.strip()).expanduser()
    return p if p.is_absolute() else PROJECT_ROOT / p


def list_frames(folder: Path) -> list[Path]:
    return sorted(folder.glob("*.jpg")) + sorted(folder.glob("*.png"))


def ensure_frames(source: Path, cache_dir: Path) -> list[Path]:
    """影格資料夾直接用;影片拆一次放進快取,之後重用。拆法與完整管線重建影格相同:
    ffmpeg -vsync 0 -qscale:v 2 f%05d.jpg(超過 9999 幀時 %04d 會排錯序)。"""
    if source.is_dir():
        return list_frames(source)
    tag = hashlib.md5(str(source.resolve()).encode()).hexdigest()[:6]
    out = cache_dir / f"{source.parent.name}_{tag}"
    done = out / ".complete"
    if not done.exists():
        out.mkdir(parents=True, exist_ok=True)
        for f in out.glob("f*.jpg"):
            f.unlink()
        cmd = ["ffmpeg", "-v", "error", "-i", str(source), "-vsync", "0", "-qscale:v", "2",
               str(out / "f%05d.jpg")]
        run = subprocess.run(cmd, capture_output=True, text=True)
        if run.returncode != 0:
            raise gr.Error(f"ffmpeg 拆影格失敗:{run.stderr.strip()[-300:]}")
        done.write_text(str(len(list(out.glob("f*.jpg")))))
    return sorted(out.glob("f*.jpg"))


def read_ego_csv(path: Path) -> dict[int, tuple[float | None, str]]:
    """完整管線(dashcam_range_speed.py)輸出的 ego_speed.csv:{幀號: (km/h 或 None, 來源)}。
    「計算」只拿它當參考、不自動填入;跟車影片選碼表時逐幀用它。"""
    out = {}
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            v, method = row.get("ego_visual_kmh", ""), row.get("method", "")
            out[int(row["frame_idx"])] = (float(v), method) if v and method != "none" else (None, "none")
    return out


def get_geometry(st: dict, shape: tuple[int, int]):
    key = (st["ply"], st["scale"], shape, st["hood"], st["corr"])
    if key not in _geometry:
        _geometry[key] = build_geometry(Path(st["ply"]), st["scale"], shape, st["hood"], st["corr"])[0]
    return key, _geometry[key]


def get_detections(st: dict, f0: int, shape: tuple[int, int], opts, window_s: float | None = None,
                   progress=None) -> dict:
    global _model
    window_s = opts.window_s if window_s is None else window_s
    gkey, p2p = get_geometry(st, shape)
    key = (str(st["frames"][0].parent), f0, gkey, st["fps"], opts.conf, window_s)
    if key not in _detections:
        if _model is None:
            from ultralytics import YOLO
            _model = YOLO(str(resolve(opts.yolo_model)))
        _detections[key] = window_detections(st["frames"], f0, _model, p2p, st["fps"], st["hood"],
                                              opts.conf, window_s, progress)
        while len(_detections) > 8:
            _detections.pop(next(iter(_detections)))
    return _detections[key]


def read_rgb(path: Path) -> np.ndarray:
    return cv2.cvtColor(cv2.imread(str(path)), cv2.COLOR_BGR2RGB)


def preview(st: dict) -> np.ndarray:
    """目前這一幀,加上已框的車(編號對應結果表)與點了一半的角。灰線是引擎蓋線。"""
    img = read_rgb(st["frames"][st["frame"]])
    cv2.line(img, (0, st["hood"]), (img.shape[1], st["hood"]), (160, 160, 160), 1)
    for i, (x1, y1, x2, y2) in enumerate(st["boxes"], 1):
        cv2.rectangle(img, (int(x1), int(y1)), (int(x2), int(y2)), BOX_COLOR, 2)
        cv2.putText(img, str(i), (int(x1) + 4, int(y1) - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 5)
        cv2.putText(img, str(i), (int(x1) + 4, int(y1) - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.9, BOX_COLOR, 2)
    if st["pending"]:
        x, y = st["pending"]
        cv2.drawMarker(img, (x, y), PENDING_COLOR, cv2.MARKER_CROSS, 28, 2)
    return img


def boxes_text(st: dict) -> str:
    lines = [f"{i}. ({x1:.0f}, {y1:.0f}) – ({x2:.0f}, {y2:.0f})" for i, (x1, y1, x2, y2) in enumerate(st["boxes"], 1)]
    if st["pending"]:
        lines.append(f"已點左上 {tuple(st['pending'])},再點右下")
    return "**已框的車**\n\n" + "\n".join(f"- {s}" for s in lines) if lines else "還沒框車:在畫面上先點左上、再點右下。"


def frame_text(st: dict) -> str:
    i = st["frame"]
    text = f"第 **{i}** 幀(0 起算,檔名 `{st['frames'][i].name}`),t = {i / st['fps']:.2f} s"
    if st["ego_ref"]:
        v = st["ego_ref"].get(i, (None, "none"))[0]
        ref = f"{v:.1f} km/h" if v is not None else "沒有讀值(no lock)"
        text += (f"\n\n參考:本專案的碼表在這一幀讀到 {ref}。要單獨看相對速度的誤差,"
                 "INPUT-2 請填可信的來源(人工畫格、車速表)。")
    return text


def add_click(st: dict, x: int, y: int) -> None:
    if st["pending"] is None:
        st["pending"] = (int(x), int(y))
        return
    (xa, ya), (xb, yb) = st["pending"], (int(x), int(y))
    st["pending"] = None
    if abs(xa - xb) < 4 or abs(ya - yb) < 4:
        raise gr.Error("兩點太近,框不成;請重點左上、右下。")
    st["boxes"].append([float(min(xa, xb)), float(min(ya, yb)), float(max(xa, xb)), float(max(ya, yb))])


def fmt(v, spec: str) -> str:
    return "—" if v is None else format(v, spec)


def result_rows(results: list[dict]) -> list[list]:
    rows = []
    for i, r in enumerate(results, 1):
        used = f"{r['n_frames_used']} 幀 / {r['span_s']:.2f} s" if "n_frames_used" in r else "—"
        rows.append([i, STATUS_ZH[r["status"]], r.get("class", "—"), fmt(r.get("range_m"), ".1f"),
                     fmt(r.get("rel_kmh"), "+.1f"), fmt(r.get("speed_kmh"), ".1f"),
                     "、".join(REASON_ZH.get(x, x) for x in r["reasons"]) or "—", used])
    return rows


def h264_args() -> list[str]:
    """與 tools/report/render_demo_video.py 相同:有 libx264 就用,沒有就用 libopenh264。"""
    encoders = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
    return ["-c:v", "libx264", "-crf", "23", "-preset", "slow"] if "libx264" in encoders else \
        ["-c:v", "libopenh264", "-b:v", "3M"]


def follow_video(st: dict, ego: float | None, hide: bool, opts, progress) -> tuple[Path, str]:
    """選的畫面前後各 CLIP_S 秒,逐幀標出每台框選的車;回傳影片路徑與每台車的摘要。
    ego 為 None 時本車車速逐幀用 st["ego_ref"](碼表),否則整段用 ego。"""
    f0, fps, frames = st["frame"], st["fps"], st["frames"]
    series = None if ego is not None else {i: v for i, (v, _) in st["ego_ref"].items()}

    def ego_at(i):
        return ego if series is None else series.get(i)

    def caption(i):
        return "使用者輸入,整段固定" if series is None else EGO_CAPTION.get(st["ego_ref"].get(i, (0, "none"))[1], "")

    w, h = Image.open(frames[f0]).size
    dets = get_detections(st, f0, (h, w), opts, 2 * CLIP_S + opts.window_s,     # 片頭片尾也有完整的擬合窗
                          lambda n, total: progress(0.6 * n / total, desc=f"偵測車輛 {n}/{total} 幀"))
    half = max(1, int(round(opts.window_s * fps / 2)))
    near = {i: dets[i] for i in range(f0 - half, f0 + half + 1) if i in dets}   # 與「計算」同一個時間窗
    tracks = [track(dets, f0, ego, box, fps, opts.max_sens_m_per_px, opts.window_s, series) for box in st["boxes"]]
    fallback = [finalize(measure(near, f0, ego_at(f0), box, fps, st["hood"], opts.max_sens_m_per_px), hide)
                for box in st["boxes"]]

    pad = int(round(CLIP_S * fps))
    lo, hi = max(0, f0 - pad), min(len(frames) - 1, f0 + pad)
    out_dir = resolve(opts.cache_dir) / "videos"
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="follow_", dir=out_dir))
    shown: list[list[dict]] = [[] for _ in st["boxes"]]
    try:
        for n, i in enumerate(range(lo, hi + 1)):
            rows = []
            for k, tr in enumerate(tracks):
                if i in tr:
                    rows.append(finalize(dict(tr[i]), hide))
                    shown[k].append(rows[-1])
                else:
                    rows.append(fallback[k] if i == f0 else None)
            label = f"{st['label']} 第 {i} 幀" + ("(選的畫面)" if i == f0 else "")
            im = Image.open(frames[i]).convert("RGB")
            draw_results(im, rows, ego_at(i), hide, caption(i), label).save(tmp / f"f{n:05d}.jpg", quality=92)
            progress(0.6 + 0.35 * (n + 1) / (hi - lo + 1), desc=f"畫影片 {n + 1}/{hi - lo + 1} 幀")
        progress(0.97, desc="編碼影片")
        out = out_dir / f"{st['label']}_f{f0}_{time.strftime('%H%M%S')}.mp4"
        # JPEG 影格是全幅色域(yuvj420p),轉成一般的 yuv420p,瀏覽器才穩定能播
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-framerate", f"{fps:g}", "-i", str(tmp / "f%05d.jpg"),
                        "-vf", "scale=out_range=tv,format=yuv420p", *h264_args(), "-movflags", "+faststart",
                        str(out)], check=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    source = (f"使用者輸入 {ego:g} km/h,整段固定" if series is None else
              f"系統碼表逐幀(這段有 {sum(series.get(i) is None for i in range(lo, hi + 1))} 幀沒有讀值)")
    lines = [f"影片:第 {lo}–{hi} 幀({(hi - lo + 1) / fps:.1f} 秒),存在 `{out}`;本車車速:{source}。"]
    for k, rows in enumerate(shown, 1):
        if not rows:
            lines.append(f"- 車 {k}:選的畫面就對不到車,影片裡只在選的那一幀標出。")
            continue
        ok = [r["speed_kmh"] for r in rows if r["status"] == "ok"]
        no_ego = sum("no_ego" in r["reasons"] for r in rows)
        text = (f"- 車 {k}:追到 {len(rows)} 幀(第 {rows[0]['frame']}–{rows[-1]['frame']} 幀),"
                f"其中可信 {len(ok)} 幀" + (f"、本車車速沒有讀值 {no_ego} 幀(只給距離)" if no_ego else ""))
        if ok:
            text += (f";可信幀的時速中位 {np.median(ok):.1f} km/h"
                     f"(10–90% 範圍 {np.percentile(ok, 10):.1f}–{np.percentile(ok, 90):.1f})")
        lines.append(text + "。")
    return out, "\n".join(lines)


def build_ui(opts) -> gr.Blocks:
    first = next(iter(PRESETS))

    def on_preset(name):
        return preset_fields(name) if name in PRESETS else (gr.update(),) * 7

    def on_load(name, source, fps, ply, scale, hood, corr, ego_csv, progress=gr.Progress()):
        src, ply_path = resolve(source or ""), resolve(ply or "")
        if not (source or "").strip() or not src.exists():
            raise gr.Error(f"找不到影片或影格資料夾:{source}")
        if not ply_path.is_file():
            raise gr.Error(f"找不到點雲:{ply}")
        if not fps or not scale or hood is None or not corr:
            raise gr.Error("幀率、scale、hood-y、距離修正係數都要填。")
        progress(0, desc="準備影格(影片第一次載入要用 ffmpeg 拆,約幾秒到幾十秒)")
        frames = ensure_frames(src, resolve(opts.cache_dir))
        if not frames:
            raise gr.Error(f"{source} 裡沒有影格")
        st = {"frames": frames, "fps": float(fps), "ply": str(ply_path), "scale": float(scale),
              "hood": int(hood), "corr": float(corr), "frame": 0, "boxes": [], "pending": None,
              "label": name if name in PRESETS else src.stem, "ego_ref": {}}
        ego_path = resolve(ego_csv) if (ego_csv or "").strip() else None
        progress(0.5, desc="擬合路面平面")
        h, w = cv2.imread(str(frames[0])).shape[:2]
        get_geometry(st, (h, w))
        notes = [f"已載入 **{st['label']}**:{len(frames)} 幀,{w}×{h}。"]
        expect = PRESETS.get(name, {}).get("frames")
        if expect and expect != len(frames):
            notes.append(f"⚠ 幀數與紀錄的 {expect} 不同,幀號可能和其他輸出對不上。")
        if st["corr"] == 1.0:
            notes.append("注意:距離修正係數是 1.0,前向距離未校正,相對速度會帶著同比例的偏差。")
        if ego_path and ego_path.is_file():
            st["ego_ref"] = read_ego_csv(ego_path)
            if len(st["ego_ref"]) != len(frames):
                notes.append(f"⚠ 碼表輸出有 {len(st['ego_ref'])} 列,影格有 {len(frames)} 幀,幀號可能對不上。")
            if name in EGO_NOTES:
                notes.append(EGO_NOTES[name])
        else:
            notes.append("沒有碼表輸出(ego_speed.csv):跟車影片只能用「我填的值」。"
                         + (f"找不到 `{ego_csv}`。" if ego_path else ""))
        return (st, gr.Slider(minimum=0, maximum=len(frames) - 1, value=0, step=1, interactive=True),
                "\n\n".join(notes), preview(st), frame_text(st), boxes_text(st))

    def need(st):
        if st is None:
            raise gr.Error("先選案例、按「載入」。")
        return st

    def on_frame(i, st):
        if st is None:
            return st, None, "", ""
        st["frame"], st["boxes"], st["pending"] = int(i), [], None
        return st, preview(st), frame_text(st), boxes_text(st)

    def on_step(i, st, delta):
        st = need(st)
        return min(max(0, int(i) + delta), len(st["frames"]) - 1)

    def on_click(st, evt: gr.SelectData):
        st = need(st)
        add_click(st, *evt.index[:2])
        return st, preview(st), boxes_text(st)

    def on_undo(st):
        st = need(st)
        if st["pending"]:
            st["pending"] = None
        elif st["boxes"]:
            st["boxes"].pop()
        return st, preview(st), boxes_text(st)

    def on_clear(st):
        st = need(st)
        st["boxes"], st["pending"] = [], None
        return st, preview(st), boxes_text(st)

    def need_inputs(ego, st):
        st = need(st)
        if ego is None:
            raise gr.Error("INPUT-2:請填這一幀的本車車速。")
        if not st["boxes"]:
            raise gr.Error("INPUT-3/4:請先在畫面上框一台車。")
        return st

    def on_measure(ego, hide, st):
        st = need_inputs(ego, st)
        f0 = st["frame"]
        im = Image.open(st["frames"][f0]).convert("RGB")
        dets = get_detections(st, f0, (im.size[1], im.size[0]), opts)
        results = [finalize(measure(dets, f0, float(ego), box, st["fps"], st["hood"], opts.max_sens_m_per_px),
                            bool(hide)) for box in st["boxes"]]
        drawn = draw_results(im, results, float(ego), bool(hide), "使用者輸入", f"{st['label']} 第 {f0} 幀")
        return drawn, result_rows(results), json.dumps(results, ensure_ascii=False, indent=1, default=float)

    def on_video(ego, hide, mode, st, progress=gr.Progress()):
        if mode == EGO_ODOMETER:
            st = need(st)
            if not st["boxes"]:
                raise gr.Error("INPUT-3/4:請先在畫面上框一台車。")
            if not st["ego_ref"]:
                raise gr.Error("這支影片沒有碼表輸出(ego_speed.csv):先用 dashcam_range_speed.py 跑一次並在參數裡填上,"
                               "或改用「我填的值」。")
            out, summary = follow_video(st, None, bool(hide), opts, progress)
        else:
            st = need_inputs(ego, st)
            out, summary = follow_video(st, float(ego), bool(hide), opts, progress)
        return str(out), summary

    with gr.Blocks(title="選一台車量時速", analytics_enabled=False) as ui:
        state = gr.State(None)
        gr.Markdown(
            "## 選一台車量時速\n"
            "1. 選案例,按「載入」　2. 拖時間軸選一幀(INPUT-1)　3. 填這一幀的本車車速(INPUT-2)　"
            "4. 在畫面上先點車的左上角、再點右下角(INPUT-3/4),可以框好幾台　5. 按「計算」\n\n"
            "時速 = 你填的本車車速 + 程式從前後各半秒算出的相對速度。彩色框是量得準的;"
            "白框白字是量不準(太遠、太近、前後追不到、找不到車),勾「量不準就不顯示」則不畫也不給數字。"
            "畫面上的灰線是引擎蓋線,框的底邊壓到它就是太近。\n\n"
            "「做成跟車影片」:從這一幀往前後各追 3 秒,每一幀都標距離與時速。本車車速預設逐幀用系統碼表"
            "(碼表沒有讀值的幀只給距離),也可以改成整段用 INPUT-2。")
        with gr.Row():
            with gr.Column(scale=1, min_width=320):
                preset = gr.Dropdown(choices=[*PRESETS, CUSTOM], value=first, label="案例")
                f_src, f_fps, f_ply, f_scale, f_hood, f_corr, f_ego = preset_fields(first)
                with gr.Accordion("參數(選案例會自動填;自訂時自己填)", open=False):
                    source = gr.Textbox(value=f_src, label="影片或影格資料夾(相對 repo 根目錄或絕對路徑)")
                    fps = gr.Number(value=f_fps, label="幀率 fps")
                    ply = gr.Textbox(value=f_ply, label="SHARP 參考點雲")
                    scale = gr.Number(value=f_scale, label="尺度係數 scale")
                    hood = gr.Number(value=f_hood, precision=0, label="引擎蓋線 hood-y")
                    corr = gr.Number(value=f_corr, label="距離修正係數(1.0 = 未校正)")
                    ego_csv = gr.Textbox(value=f_ego, label="碼表輸出 ego_speed.csv(完整管線的輸出;跟車影片用,可留空)")
                load_btn = gr.Button("載入")
                status = gr.Markdown()
                frame = gr.Slider(0, 1, value=0, step=1, interactive=False, label="INPUT-1:畫面(幀號,0 起算)")
                with gr.Row():
                    prev_btn = gr.Button("◀ 前一幀", size="sm")
                    next_btn = gr.Button("後一幀 ▶", size="sm")
                frame_md = gr.Markdown()
                ego = gr.Number(label="INPUT-2:這一幀的本車車速 (km/h)")
                hide = gr.Checkbox(label="量不準就不顯示(不畫、不給數字)")
                boxes_md = gr.Markdown()
                with gr.Row():
                    undo_btn = gr.Button("刪掉最後一個框", size="sm")
                    clear_btn = gr.Button("全部清掉", size="sm")
                run_btn = gr.Button("計算", variant="primary")
                ego_mode = gr.Radio([EGO_ODOMETER, EGO_TYPED], value=EGO_ODOMETER, label="跟車影片的本車車速")
                video_btn = gr.Button(f"做成跟車影片(前後各 {CLIP_S:g} 秒)")
            with gr.Column(scale=3):
                view = gr.Image(type="numpy", format="jpeg", interactive=False,
                                label="INPUT-3/4:在車上先點左上、再點右下")
                result_img = gr.Image(type="pil", format="jpeg", interactive=False, label="結果")
                table = gr.Dataframe(headers=HEADERS, interactive=False, wrap=True)
                with gr.Accordion("JSON(與命令列版相同)", open=False):
                    result_json = gr.Code(language="json")
                video = gr.Video(label="跟車影片(車追丟後不再畫框)",
                                 interactive=False, autoplay=True, loop=True)
                video_md = gr.Markdown()

        preset.change(on_preset, preset, [source, fps, ply, scale, hood, corr, ego_csv])
        load_btn.click(on_load, [preset, source, fps, ply, scale, hood, corr, ego_csv],
                       [state, frame, status, view, frame_md, boxes_md])
        frame.change(on_frame, [frame, state], [state, view, frame_md, boxes_md], trigger_mode="always_last")
        prev_btn.click(lambda i, st: on_step(i, st, -1), [frame, state], frame)
        next_btn.click(lambda i, st: on_step(i, st, +1), [frame, state], frame)
        view.select(on_click, state, [state, view, boxes_md])
        undo_btn.click(on_undo, state, [state, view, boxes_md])
        clear_btn.click(on_clear, state, [state, view, boxes_md])
        run_btn.click(on_measure, [ego, hide, state], [result_img, table, result_json])
        video_btn.click(on_video, [ego, hide, ego_mode, state], [video, video_md])
    return ui


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=7860)
    ap.add_argument("--cache-dir", default="/tmp/vdf_frames", help="影片拆出的影格放這裡(重開機會消失,會自動重拆)。")
    ap.add_argument("--yolo-model", default="checkpoints/yolov8m-seg.pt")
    ap.add_argument("--conf", type=float, default=0.3)
    ap.add_argument("--max-sens-m-per-px", type=float, default=0.8, help="遠場門檻,與命令列版相同。")
    ap.add_argument("--window-s", type=float, default=1.0, help="擬合相對速度用的時間窗,與命令列版相同。")
    return ap.parse_args()


def main() -> None:
    opts = parse_args()
    build_ui(opts).queue().launch(server_name="127.0.0.1", server_port=opts.port, show_error=True,
                                  allowed_paths=[str(resolve(opts.cache_dir))])


if __name__ == "__main__":
    main()
