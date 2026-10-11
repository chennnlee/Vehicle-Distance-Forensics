"""選一台車、算它的速度 —— 把「相對速度」這一項的誤差單獨拿出來量。

他車速度 = 本車車速 + 相對速度,兩項各有誤差。完整管線(dashcam_range_speed.py)
的本車車速來自碼表;這支工具改由使用者直接給,例如填人工畫格法的真值,
算出來的誤差就只剩相對速度這一項。

輸入
  INPUT-1    --frame             影格編號,0 起算,與 ranges.csv / ego_speed.csv 的 frame_idx 相同
                                 (ffmpeg 抽出的 f00001.jpg 是第 0 幀)
  INPUT-2    --ego-kmh           該幀的本車車速
  INPUT-3/4  --box x1,y1,x2,y2   目標車的左上角與右下角;不給就開視窗,在車上點左上、右下兩下。
                                 可重複給 --box 一次量好幾台,結果依序列在 JSON 陣列裡
  參數       --hide-unreliable   量不準時不畫、速度回傳 null(status=unreliable);
                                 不加時照樣算,改用白框白字畫出來,表示這個數字不可信

一張畫面只算得出距離,算不出相對速度(速度要看距離怎麼變)。所以工具會在所選畫面
前後各半秒自己找同一台車,用這段時間「距離對時間」的斜率當相對速度。
接地點、路面平面、追蹤門檻都沿用完整管線,差別在時間窗:完整管線取前後各 15 個觀測,
偵測斷掉時窗會被拉長(hs005 實測拉到 2–6 秒,把幾秒外、差 3–5 m 的觀測也算進斜率);
這裡嚴格只用前後各半秒。hs005 隨機 25 個近場樣本中 17 個兩邊差 ≤ 1 km/h,
差較大的 8 個都是完整管線的窗被拉長。
另一個兩邊共有的雜訊:YOLO 在 640 寬的縮圖上產生遮罩,1920 寬的畫面上接地點只落在
每 3 px 一格的列上,hs005 在 26 m 處一格約 1.5 m。

不準確的判準(reasons,可同時出現多個):
  no_detection    偵測器在框內找不到車(與框的 IoU < 0.3),沒有任何數字
  below_hood      框的底緣壓到引擎蓋線:車太近,接地點看不到
  far_field       接地點每像素對應超過 --max-sens-m-per-px 公尺(預設 0.8,即完整管線的遠場旗標;
                  對雷達量到遠場距離中位偏 20%)
  too_few_frames  前後找到的同一台車不到 5 幀或跨不到 0.3 秒,斜率不可信
未涵蓋:擦身而過的側向目標(docs/FAILURE_BOUNDARIES.md)目前沒有量化門檻,工具不會自動判斷。

圖形介面版:tools/selected_vehicle_gui.py(同一組函式,在瀏覽器裡選畫面、填車速、點兩下框車)。

用法範例(hs005,參數見 docs/CASE_PARAMETERS.md):
  python tools/selected_vehicle_speed.py --frames-dir /tmp/hs005_frames --fps 29.8883 \\
      --reference-pointcloud data/output/sharp_gaussians/hs005_ref.ply \\
      --pointcloud-scale 0.960510 --hood-y 960 --distance-correction 0.760 \\
      --frame 300 --ego-kmh 95 --box 880,560,1010,660 --out-image hs005_f300.jpg
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "tools"))

from dashcam_range_speed import CLASS_GROUP, build_geometry, frame_vehicle_detections  # noqa: E402

MIN_IOU = 0.3           # 使用者的框與偵測框至少要重疊這麼多,才算同一台車
MIN_OBS = 5             # 與完整管線相同:少於 5 幀不擬合斜率
MIN_SPAN_S = 0.3
MAX_GAP_S = 0.8         # 與完整管線相同:斷掉超過 0.8 秒就不再接
OK_COLOR = (0, 210, 0)
WHITE = (255, 255, 255)


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="選一台車,用使用者給的本車車速 + 本方法的相對速度算出它的速度。")
    ap.add_argument("--frames-dir", required=True, help="整段影片抽出的影格資料夾(要有前後幀才算得出相對速度)。")
    ap.add_argument("--fps", type=float, required=True, help="真實幀率。")
    ap.add_argument("--reference-pointcloud", required=True)
    ap.add_argument("--pointcloud-scale", type=float, required=True)
    ap.add_argument("--hood-y", type=int, default=900)
    ap.add_argument("--distance-correction", type=float, default=1.0,
                    help="前向距離係數,見 docs/CASE_PARAMETERS.md;預設 1.0 = 距離未校正。")
    ap.add_argument("--yolo-model", default="checkpoints/yolov8m-seg.pt")
    ap.add_argument("--conf", type=float, default=0.3)
    ap.add_argument("--max-sens-m-per-px", type=float, default=0.8, help="遠場門檻,與完整管線相同。")
    ap.add_argument("--window-s", type=float, default=1.0, help="擬合相對速度用的時間窗(以所選畫面為中心)。")
    ap.add_argument("--frame", type=int, required=True, help="INPUT-1:影格編號(0 起算)。")
    ap.add_argument("--ego-kmh", type=float, required=True, help="INPUT-2:該幀的本車車速。")
    ap.add_argument("--box", action="append", default=[],
                    help="INPUT-3/4:x1,y1,x2,y2(左上、右下),可重複;不給就開視窗點選一台。")
    ap.add_argument("--hide-unreliable", action="store_true",
                    help="量不準時不畫、速度回傳 null;不加時用白框白字標示。")
    ap.add_argument("--out-image", default="", help="畫好框與數字的輸出圖。")
    ap.add_argument("--out-json", default="", help="結果另存 JSON(結果一律也會印在 stdout)。")
    return ap.parse_args()


def iou(a, b) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def pick_box(img) -> list[float]:
    """開視窗讓使用者點兩下:先左上、再右下。Esc 取消。"""
    clicks: list[tuple[int, int]] = []
    win = "click top-left, then bottom-right (Esc = cancel)"

    def on_mouse(event, x, y, *_):
        if event == cv2.EVENT_LBUTTONDOWN and len(clicks) < 2:
            clicks.append((x, y))

    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    cv2.setMouseCallback(win, on_mouse)
    while len(clicks) < 2:
        view = img.copy()
        for c in clicks:
            cv2.circle(view, c, 6, OK_COLOR, -1)
        cv2.imshow(win, view)
        if cv2.waitKey(20) == 27:
            cv2.destroyWindow(win)
            sys.exit("已取消")
    cv2.destroyWindow(win)
    (xa, ya), (xb, yb) = clicks
    return [float(min(xa, xb)), float(min(ya, yb)), float(max(xa, xb)), float(max(ya, yb))]


def follow(start: dict, frame_dets: dict[int, list[dict]], order: list[int], f0: int, fps: float) -> list[dict]:
    """從所選畫面往前或往後,一幀一幀接同一台車。門檻與完整管線的關聯層相同:
    同尺寸群組、框高比 0.6–1.6、畫面位置一致性、路面距離 < 2 m + 8 m/s × 間隔。

    唯一不同:不用速度預測,以上一個位置為中心。完整管線的軌跡在這之前已平滑過
    幾十幀;這裡是新起的軌跡,第一個單幀速度幾乎全是遮罩底緣的量化跳動
    (hs005 第 412→413 幀同一台車 27.46 → 21.34 m),拿它外推會把鏈帶到跳動上。
    1 秒窗內真實的相對位移遠小於門檻,不需要預測。"""
    out = []
    tr = {"pos": start["pos"], "bh": start["bh"], "t": 0.0,
          "cx": (start["box"][0] + start["box"][2]) * 0.5, "cy": (start["box"][1] + start["box"][3]) * 0.5,
          "bw": start["box"][2] - start["box"][0], "grp": CLASS_GROUP.get(start["cls"])}
    for i in order:
        t = abs(i - f0) / fps
        step_dt = t - tr["t"]
        if step_dt > MAX_GAP_S:
            break
        best, best_d = None, 2.0 + 8.0 * step_dt
        for det in frame_dets[i]:
            if CLASS_GROUP.get(det["cls"]) != tr["grp"]:
                continue
            if not 0.6 <= det["bh"] / max(1e-6, tr["bh"]) <= 1.6:
                continue
            dc = float(np.hypot((det["box"][0] + det["box"][2]) * 0.5 - tr["cx"],
                                (det["box"][1] + det["box"][3]) * 0.5 - tr["cy"]))
            if dc > 0.35 * max(det["box"][2] - det["box"][0], tr["bw"], 1.0) + 250.0 * step_dt:
                continue
            d = float(np.linalg.norm(det["pos"] - tr["pos"]))
            if d < best_d:
                best, best_d = det, d
        if best is None:
            continue
        tr.update(pos=best["pos"], bh=best["bh"], t=t,
                  cx=(best["box"][0] + best["box"][2]) * 0.5, cy=(best["box"][1] + best["box"][3]) * 0.5,
                  bw=best["box"][2] - best["box"][0])
        out.append({"frame": i, "t": (i - f0) / fps, "fwd_m": float(best["pos"][1]), "det": best})
    return out


def window_detections(frames: list[Path], f0: int, model, pixel_to_plane, fps: float, hood_y: int,
                      conf: float, window_s: float, progress=None) -> dict[int, list[dict]]:
    """所選畫面前後各半個時間窗內,每一幀的車輛偵測。同一幀量好幾台車時共用這一份。
    progress(已完成幀數, 總幀數) 給圖形介面顯示進度用。"""
    half = max(1, int(round(window_s * fps / 2)))
    span = range(max(0, f0 - half), min(len(frames) - 1, f0 + half) + 1)
    out = {}
    for n, i in enumerate(span, 1):
        result = model.predict(source=cv2.imread(str(frames[i])), conf=conf, verbose=False)[0]
        out[i] = frame_vehicle_detections(result, hood_y, pixel_to_plane)[0]
        if progress:
            progress(n, len(span))
    return out


def match_target(frame_dets: dict[int, list[dict]], f0: int, box: list[float]) -> tuple[float, dict | None]:
    """使用者的框對到第 f0 幀的哪一個偵測(IoU 最大者);對不到回傳 None。"""
    scored = [(iou(box, d["box"]), d) for d in frame_dets[f0]]
    score, target = max(scored, key=lambda s: s[0], default=(0.0, None))
    return (score, target) if target is not None and score >= MIN_IOU else (score, None)


def chain_of(frame_dets: dict[int, list[dict]], f0: int, target: dict, fps: float) -> list[dict]:
    """從 f0 往前、往後接同一台車,涵蓋 frame_dets 的全部幀;依幀號排好。"""
    lo, hi = min(frame_dets), max(frame_dets)
    return (follow(target, frame_dets, list(range(f0 - 1, lo - 1, -1)), f0, fps)[::-1]
            + [{"frame": f0, "t": 0.0, "fwd_m": float(target["pos"][1]), "det": target}]
            + follow(target, frame_dets, list(range(f0 + 1, hi + 1)), f0, fps))


def place(res: dict, det: dict, max_sens: float, match_iou: float | None = None) -> None:
    """把偵測到的位置寫進結果;接地點每像素超過 max_sens 公尺時記 far_field。"""
    res.update({"class": det["cls"], "matched_box": det["box"]})
    if match_iou is not None:
        res["match_iou"] = round(match_iou, 3)
    res.update({"ground_px": [det["px"], det["py"]], "range_m": float(det["pos"][1]),
                "lat_m": float(det["pos"][0]), "sens_m_per_px": det["sens"]})
    if not np.isfinite(det["sens"]) or det["sens"] > max_sens:
        res["reasons"].append("far_field")


def fit_relative(res: dict, obs: list[dict], ego_kmh: float | None) -> dict:
    """obs 的 t 以結果那一幀為 0;用「距離對時間」的斜率當相對速度。
    ego_kmh 為 None(本車車速沒有讀值)時只給距離與相對速度,記 no_ego。"""
    tt = np.array([o["t"] for o in obs])
    res["n_frames_used"] = len(obs)
    res["span_s"] = float(tt[-1] - tt[0])
    if len(obs) < MIN_OBS or res["span_s"] <= MIN_SPAN_S:
        res["reasons"].append("too_few_frames")
    if len(obs) >= 2 and res["span_s"] > 0:
        rel_ms = float(np.polyfit(tt, [o["fwd_m"] for o in obs], 1)[0])  # +: 拉開距離
        res["rel_kmh"] = rel_ms * 3.6
        if ego_kmh is not None:
            res["speed_kmh"] = ego_kmh + rel_ms * 3.6
    if ego_kmh is None:
        res["reasons"].append("no_ego")
    return res


def measure(frame_dets: dict[int, list[dict]], f0: int, ego_kmh: float, box: list[float], fps: float,
            hood_y: int, max_sens: float) -> dict:
    """回傳一台車在第 f0 幀的距離、相對速度與速度,以及不準確的理由。"""
    res = {"frame": f0, "ego_kmh": ego_kmh, "box_input": box, "reasons": []}
    score, target = match_target(frame_dets, f0, box)
    if target is None:
        res["reasons"].append("below_hood" if box[3] >= hood_y - 2 else "no_detection")
        return res
    place(res, target, max_sens, score)
    return fit_relative(res, chain_of(frame_dets, f0, target, fps), ego_kmh)


def track(frame_dets: dict[int, list[dict]], f0: int, ego_kmh: float | None, box: list[float], fps: float,
          max_sens: float, window_s: float, ego_series: dict[int, float | None] | None = None) -> dict[int, dict]:
    """把選的車在 frame_dets 涵蓋的每一幀都量一次,做跟車影片用:回傳 {幀號: 結果},追不到的幀不在裡面。
    本車車速整段都用 ego_kmh;給 ego_series({幀號: km/h,沒有讀值為 None})時改用逐幀的值,
    沒有讀值的幀只給距離與相對速度。每一幀的相對速度只用該幀前後各半個 window_s 內的軌跡點,
    判準與 measure() 相同,所以選的那一幀與 measure() 的距離、速度一致(差在少了 match_iou)。
    車追丟(斷開超過 MAX_GAP_S)後就不再接。"""
    _, target = match_target(frame_dets, f0, box)
    if target is None:
        return {}
    chain = chain_of(frame_dets, f0, target, fps)
    half = max(1, int(round(window_s * fps / 2)))
    out = {}
    for o in chain:
        i = o["frame"]
        ego_i = ego_kmh if ego_series is None else ego_series.get(i)
        res = {"frame": i, "ego_kmh": ego_i, "box_input": box, "reasons": []}
        place(res, o["det"], max_sens)
        obs = [{"t": (p["frame"] - i) / fps, "fwd_m": p["fwd_m"]} for p in chain if abs(p["frame"] - i) <= half]
        out[i] = fit_relative(res, obs, ego_i)
    return out


def finalize(res: dict, hide_unreliable: bool) -> dict:
    """依參數決定量不準時要不要給數字。"""
    if "speed_kmh" not in res:
        res["status"] = "no_measurement"
    elif res["reasons"]:
        res["status"] = "unreliable"
        if hide_unreliable:
            res["speed_kmh"] = None
            res["rel_kmh"] = None
    else:
        res["status"] = "ok"
    return res


def draw_hud(img, frame: int, ego_kmh: float):
    text = f"frame {frame}  ego(input) {ego_kmh:.1f} km/h"
    cv2.putText(img, text, (16, 46), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 5)
    cv2.putText(img, text, (16, 46), cv2.FONT_HERSHEY_SIMPLEX, 0.8, WHITE, 2)


def draw(img, res: dict, hide_unreliable: bool):
    if res["status"] != "ok" and hide_unreliable:
        return img
    font = cv2.FONT_HERSHEY_SIMPLEX
    color = OK_COLOR if res["status"] == "ok" else WHITE
    x1, y1, x2, y2 = (int(v) for v in res.get("matched_box", res["box_input"]))
    cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
    if "ground_px" in res:
        cv2.circle(img, (int(res["ground_px"][0]), int(res["ground_px"][1])), 5, color, -1)
    if res["status"] == "no_measurement":
        text = "cannot measure: " + ",".join(res["reasons"])
    else:
        text = f"{res['class']} {res['range_m']:.1f}m  rel {res['rel_kmh']:+.1f}  ~{res['speed_kmh']:.0f}km/h"
        if res["reasons"]:
            text += "  [" + ",".join(res["reasons"]) + "]"
    (tw, th), _ = cv2.getTextSize(text, font, 0.7, 2)
    tx = int(min(max(2, x1), img.shape[1] - tw - 2))
    ty = int(max(th + 60, y1 - 8))
    cv2.putText(img, text, (tx, ty), font, 0.7, (0, 0, 0), 4)
    cv2.putText(img, text, (tx, ty), font, 0.7, color, 2)
    return img


def main() -> None:
    args = parse_args()
    frames = sorted(Path(args.frames_dir).glob("*.jpg")) + sorted(Path(args.frames_dir).glob("*.png"))
    if not 0 <= args.frame < len(frames):
        sys.exit(f"--frame {args.frame} 超出範圍(共 {len(frames)} 幀,0 起算)")
    img = cv2.imread(str(frames[args.frame]))
    boxes = []
    for b in args.box:
        xa, ya, xb, yb = (float(v) for v in b.split(","))
        boxes.append([min(xa, xb), min(ya, yb), max(xa, xb), max(ya, yb)])
    if not boxes:
        boxes.append(pick_box(img))

    ply_path = Path(args.reference_pointcloud)
    if not ply_path.is_absolute():
        ply_path = PROJECT_ROOT / ply_path
    pixel_to_plane, _ = build_geometry(ply_path, args.pointcloud_scale, img.shape[:2], args.hood_y,
                                       args.distance_correction)
    if args.distance_correction == 1.0:
        print("注意:--distance-correction 為 1.0,前向距離未校正,相對速度會帶著同比例的偏差",
              file=sys.stderr)

    from ultralytics import YOLO

    frame_dets = window_detections(frames, args.frame, YOLO(args.yolo_model), pixel_to_plane, args.fps,
                                   args.hood_y, args.conf, args.window_s)
    results = [finalize(measure(frame_dets, args.frame, args.ego_kmh, box, args.fps, args.hood_y,
                                args.max_sens_m_per_px), args.hide_unreliable) for box in boxes]
    text = json.dumps(results, ensure_ascii=False, indent=1, default=float)
    print(text)
    if args.out_json:
        Path(args.out_json).write_text(text, encoding="utf-8")
    if args.out_image:
        draw_hud(img, args.frame, args.ego_kmh)
        for res in results:
            draw(img, res, args.hide_unreliable)
        cv2.imwrite(args.out_image, img)


if __name__ == "__main__":
    main()
