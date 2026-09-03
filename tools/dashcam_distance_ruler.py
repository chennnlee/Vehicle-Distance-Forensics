"""把「公尺尺規」畫在路面上,讓距離修正可以用肉眼驗證。

為什麼需要這支工具:修正係數是一個數字,報告裡看不出對錯。但路面本身就是尺——
法定虛線一個週期(一條白線 + 一段空白)在國道實測是 10 公尺。所以只要把
10 / 20 / 30 / 40 公尺的刻度畫在路面上,再對照畫面裡真實的虛線:

  · 刻度間距 == 虛線週期  → 這個尺是準的
  · 刻度愈往前愈跟虛線對不上(漂移) → 這個尺是錯的

上下對照(上=修正前、下=修正後)就把「距離偏高」變成看得見的東西,
不需要相信任何數字。

用法範例:
  python tools/dashcam_distance_ruler.py --frames-dir /tmp/hs005_frames \\
      --pointcloud data/output/sharp_gaussians/hs005_ref.ply --hood-y 960 \\
      --pointcloud-scale 0.960510 --correction 0.760 --fps 29.8883 --label hs005 \\
      --out data/output/dashcam_demo/_calib/hs005_ruler.mp4
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "tools"))

from dashcam_range_speed import build_geometry                      # noqa: E402


def solve_pixel(p2p, target_lat: float, target_fwd: float, y_lo: int, y_hi: int,
                w: int) -> tuple[int, int] | None:
    """求出路面座標 (lat, fwd) 對應的像素。兩層二分:先在列上找 fwd,再在行上找 lat。"""
    def lat_at(y: int) -> tuple[float, float] | None:
        """該列上 lat = target_lat 的行號。lat 隨行號單調,但方向由 e_lat 的正負決定,
        所以先探兩端再決定二分方向 —— 寫死方向會讓刻度線整條貼到畫面邊緣。"""
        qa, qb = p2p(0.0, y), p2p(float(w - 1), y)
        if qa is None or qb is None:
            return None
        lo, hi = 0.0, float(w - 1)
        rising = qb[0] > qa[0]
        if not (min(qa[0], qb[0]) <= target_lat <= max(qa[0], qb[0])):
            return None
        for _ in range(40):
            mid = 0.5 * (lo + hi)
            q = p2p(mid, y)
            if q is None:
                return None
            if (q[0] < target_lat) == rising:
                lo = mid
            else:
                hi = mid
        q = p2p(0.5 * (lo + hi), y)
        return (0.5 * (lo + hi), float(q[1])) if q is not None else None

    lo, hi = y_lo, y_hi
    for _ in range(30):
        mid = (lo + hi) // 2
        r = lat_at(mid)
        if r is None:
            lo = mid + 1
            continue
        if r[1] > target_fwd:      # 太遠 → 往下找(列數變大)
            lo = mid + 1
        else:
            hi = mid
        if hi - lo <= 1:
            break
    r = lat_at(hi)
    return (int(round(r[0])), int(hi)) if r is not None else None


def ruler_marks(p2p, ticks: list[float], lat_lo: float, lat_hi: float,
                h: int, w: int, hood_y: int):
    """每個刻度回傳 (左端點, 右端點, 距離)。求不出來的(超過地平線)略過。"""
    out = []
    y_lo = int(h * 0.40)
    for d in ticks:
        a = solve_pixel(p2p, lat_lo, d, y_lo, hood_y - 2, w)
        b = solve_pixel(p2p, lat_hi, d, y_lo, hood_y - 2, w)
        if a is None or b is None:
            continue
        if not (y_lo < a[1] < hood_y and y_lo < b[1] < hood_y):
            continue
        out.append((a, b, d))
    return out


def line_tables(p2p, pts, h: int, w: int, hood_y: int, d_lo: float, d_hi: float,
                offset_m: float, band_m: float = 1.0, n_band: int = 9):
    """沿著「真實虛線」建兩張表:讀亮度用的(橫向一條帶)、畫合成虛線用的(往車道內側平移)。

    ⚠ 兩個坑都踩過:
    (1) 不能用「固定 lat 的縱向線」取樣 —— 自車與車道線通常有一點夾角,走到 40 m 就
        偏離漆線,量到的只是柏油(亮度剖面單調上升、完全沒有虛線結構)。
    (2) 也不能只用取樣點擬合的那一條線 —— 那些點是整支片的「駐留平台」,個別幀的自車
        橫向位置會漂,某些幀那條線根本壓在車道內。所以改成在每個距離上取**橫向 ±1 m 的
        一條帶**,取帶內最亮值:漆線亮、柏油暗,漂 0.5 m 也抓得到,而隔壁車道線在 3.5 m
        外不會被誤收。
    """
    ys = np.array([q[1] for q in pts], dtype=float)
    xs = np.array([q[0] for q in pts], dtype=float)
    a, b = np.polyfit(ys, xs, 1)                     # x = a*y + b
    ds, lats = [], []
    for y in range(int(h * 0.42), hood_y - 2):
        x = a * y + b
        if not (2 <= x < w - 2):
            continue
        q = p2p(x, y)
        if q is None or not (d_lo <= q[1] <= d_hi):
            continue
        ds.append(float(q[1])); lats.append(float(q[0]))
    if len(ds) < 20:
        return None, None
    order = np.argsort(ds)
    ds = np.array(ds)[order]; lats = np.array(lats)[order]

    offs = np.linspace(-band_m, band_m, n_band)
    band_x = np.zeros((len(ds), n_band), dtype=int)
    band_y = np.zeros((len(ds), n_band), dtype=int)
    ok = np.ones(len(ds), dtype=bool)
    for i, (d, lat) in enumerate(zip(ds, lats)):
        for j, o in enumerate(offs):
            q = solve_pixel(p2p, lat + o, d, int(h * 0.40), hood_y - 2, w)
            if q is None:
                ok[i] = False
                break
            band_x[i, j], band_y[i, j] = q
    read = (ds[ok], band_x[ok], band_y[ok])

    # 合成虛線要畫在「真虛線旁邊」才好比對,但自車橫向會漂 —— 所以每個橫向位置各備一張表,
    # 每幀再挑「這一幀漆線實際在哪一格」的那張(見 best_band)。
    sign = -1.0 if np.median(lats) > 0 else 1.0
    draws = []
    for o in offs:
        dx, dy, dd = [], [], []
        for d, lat in zip(ds[ok], lats[ok]):
            q = solve_pixel(p2p, lat + o + sign * offset_m, d, int(h * 0.40), hood_y - 2, w)
            if q is None:
                continue
            dx.append(q[0]); dy.append(q[1]); dd.append(d)
        draws.append((np.array(dd), np.array(dx), np.array(dy)) if len(dd) > 20 else None)
    return read, draws


def band_profile(gray, tbl):
    """回傳 (每個距離的帶內最亮值, 每個距離最亮的是哪一格)。"""
    ds, xs, ys = tbl
    vals = np.zeros((len(ds), xs.shape[1]))
    for i in range(len(ds)):
        for j in range(xs.shape[1]):
            x, y = xs[i, j], ys[i, j]
            vals[i, j] = gray[max(0, y - 1):y + 2, max(0, x - 1):x + 2].mean()
    return vals.max(axis=1), vals.argmax(axis=1)


def best_band(gray, tbl) -> int:
    """這一幀的漆線落在橫向的哪一格 —— 只取夠亮的樣本投票,暗處的 argmax 是雜訊。"""
    v, arg = band_profile(gray, tbl)
    if v.size < 20:
        return tbl[1].shape[1] // 2
    bright = v > np.percentile(v, 80)
    return int(np.median(arg[bright])) if bright.sum() >= 5 else tbl[1].shape[1] // 2


def dash_phase(gray, tbl, d_min: float, d_near: float = 26.0,
               dash_m: float = 4.0, cycle_m: float = 10.0) -> float | None:
    """真實漆線的相位(第一條漆線起點在幾公尺處)—— 唯一被對齊的自由度。

    用「整段剖面對理想 4/6 梳子做相關」而不是「找第一個上升緣」:單一上升緣很脆
    (一台白車、一段護欄就能把門檻拉走,實測會把相位鎖到 44 m),而相關是全域的、
    每幀都穩。⚠ 只擬合相位,不擬合間距 —— 間距固定 10 m,對不對就看畫面。
    """
    ds, xs, ys = tbl
    if len(ds) < 20:
        return None
    v, _ = band_profile(gray, tbl)
    if v.max() - v.min() < 15:
        return None
    grid = np.arange(ds.min(), ds.max(), 0.05)
    vi = np.interp(grid, ds, v)
    k = max(21, int(6.0 / 0.05) | 1)
    r = vi - np.convolve(vi, np.ones(k) / k, mode="same")
    sel = (grid >= d_min) & (grid <= d_near)
    if sel.sum() < 60:
        return None
    g, rr = grid[sel], r[sel]
    rr = rr - rr.mean()
    duty = dash_m / cycle_m
    best, best_phi = -1e18, None
    for phi in np.arange(0.0, cycle_m, 0.05):
        pat = np.where(((g - phi) % cycle_m) < dash_m, 1.0 - duty, -duty)
        score = float(rr @ pat)
        if score > best:
            best, best_phi = score, float(phi)
    if best_phi is None or best <= 0:
        return None
    start = best_phi
    while start < d_min:
        start += cycle_m
    return start


# ⚠ 這裡曾經有一個 dash_spacing():用自相關量「虛線週期在我們的尺上是幾公尺」,
# 想拿來當影片標題的數字。已刪除 —— 畫面裡只裝得下 2~3 個週期,週期估計的解析度
# 大約 ±15%(五支同型道路實測 8.7~11.1 m),做成標題會是假精確。要量尺度誤差請用
# tools/odometer_distance_calib.py(跨列時差),不要用單幀的空間週期。


def draw_synthetic_dashes(img, tbl, phase: float, dash_m: float, cycle_m: float,
                          n_cycles: int, colour):
    """把我們算出來的虛線畫在真虛線旁邊(同一條路上,往車道內側平移)。"""
    ds, xs, ys = tbl
    for k in range(n_cycles):
        a, b = phase + k * cycle_m, phase + k * cycle_m + dash_m
        sel = np.flatnonzero((ds >= a) & (ds <= b))
        if sel.size < 2:
            continue
        p0 = (int(xs[sel[-1]]), int(ys[sel[-1]]))
        p1 = (int(xs[sel[0]]), int(ys[sel[0]]))
        cv2.line(img, p0, p1, (0, 0, 0), 15, cv2.LINE_AA)
        cv2.line(img, p0, p1, colour, 9, cv2.LINE_AA)
    return img


def draw_panel(img, marks, title: str, colour, crop: int = 0, cycle_m: float = 10.0):
    for (a, b, d) in marks:
        cv2.line(img, a, b, (0, 0, 0), 7, cv2.LINE_AA)
        cv2.line(img, a, b, colour, 3, cv2.LINE_AA)
        for pt in (a, b):
            cv2.circle(img, pt, 7, (0, 0, 0), -1, cv2.LINE_AA)
            cv2.circle(img, pt, 5, colour, -1, cv2.LINE_AA)
        far = a if a[0] > b[0] else b          # 標籤放在畫面右端(車道內側),別蓋住左邊的虛線
        tx, ty = far[0] + 14, far[1] + 8
        # 標成「幾格虛線」:使用者不必相信我們的公尺,數地上的白線就好
        n = d / cycle_m
        label = (f"{d:.0f} m = {n:.0f} dash{'' if round(n) == 1 else 'es'}"
                 if abs(n - round(n)) < 0.01 else f"{d:.0f} m")
        cv2.putText(img, label, (tx, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.85,
                    (0, 0, 0), 5, cv2.LINE_AA)
        cv2.putText(img, label, (tx, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.85,
                    colour, 2, cv2.LINE_AA)
    img = img[crop:, :]
    cv2.rectangle(img, (0, 0), (img.shape[1], 52), (0, 0, 0), -1)
    cv2.putText(img, title, (16, 36), cv2.FONT_HERSHEY_SIMPLEX, 1.0, colour, 2, cv2.LINE_AA)
    return img


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--frames-dir", required=True)
    ap.add_argument("--pointcloud", required=True)
    ap.add_argument("--hood-y", type=int, required=True)
    ap.add_argument("--pointcloud-scale", type=float, required=True)
    ap.add_argument("--correction", type=float, required=True)
    ap.add_argument("--fps", type=float, required=True)
    ap.add_argument("--label", default="")
    ap.add_argument("--out", required=True)
    ap.add_argument("--ticks", default="10,20,30")
    ap.add_argument("--dash-spec", default="4,10",
                    help="虛線規格「漆線長,週期」(公尺)。台灣車道線 4 m 漆 + 6 m 空 = 週期 10 m")
    ap.add_argument("--odometer-points", default="",
                    help="碼表取樣點(x,y;...)。給了就自動把刻度線畫成「從相機軸跨到那條虛線」"
                         " —— 我們主張的 10 m 週期就是那條線量出來的,尺規當然要壓在它上面")
    ap.add_argument("--lat-range", default="",
                    help="手動指定刻度線的橫向範圍(公尺,相機為 0,正值在畫面左側)")
    ap.add_argument("--crop-top", type=int, default=-1, help="裁掉上方幾列(-1=自動:最遠刻度上方 90 列)")
    ap.add_argument("--max-seconds", type=float, default=0.0, help="0 = 全片")
    ap.add_argument("--scale-out", type=float, default=0.5, help="輸出縮放(檔案大小)")
    args = ap.parse_args()

    frames = sorted(Path(args.frames_dir).glob("*.jpg")) or sorted(Path(args.frames_dir).glob("*.png"))
    if not frames:
        sys.exit(f"{args.frames_dir}: 無影格")
    if args.max_seconds > 0:
        frames = frames[: int(args.max_seconds * args.fps)]

    img0 = cv2.imread(str(frames[0]))
    h, w = img0.shape[:2]
    ticks = [float(t) for t in args.ticks.split(",") if t.strip()]

    p2p_before, _ = build_geometry(Path(args.pointcloud), args.pointcloud_scale, (h, w),
                                   args.hood_y, 1.0)
    p2p_after, _ = build_geometry(Path(args.pointcloud), args.pointcloud_scale, (h, w),
                                  args.hood_y, args.correction)
    if args.lat_range:
        lat_lo, lat_hi = (float(v) for v in args.lat_range.split(","))
    elif args.odometer_points:
        pts = [tuple(int(v) for v in c.split(",")) for c in args.odometer_points.split(";") if c.strip()]
        lats = [p2p_after(x, y)[0] for x, y in pts if p2p_after(x, y) is not None]
        m = float(np.median(lats))
        lat_lo, lat_hi = min(0.0, m) - 0.5, max(0.0, m) + 0.5
        print(f"虛線在 lat {m:+.2f} m → 刻度線橫向範圍 {lat_lo:+.2f} ~ {lat_hi:+.2f} m")
    else:
        lat_lo, lat_hi = -0.5, 2.5
    marks_before = ruler_marks(p2p_before, ticks, lat_lo, lat_hi, h, w, args.hood_y)
    marks_after = ruler_marks(p2p_after, ticks, lat_lo, lat_hi, h, w, args.hood_y)
    print(f"{args.label}: 修正前 {len(marks_before)} 個刻度、修正後 {len(marks_after)} 個")
    for (a, _, d), (a2, _, d2) in zip(marks_before, marks_after):
        print(f"   {d:5.0f} m  修正前列 {a[1]:4d}   修正後列 {a2[1]:4d}")

    RED, GREEN = (60, 60, 235), (90, 200, 90)

    # 虛線相位要在「真虛線上」量,合成的虛線畫在往車道內側 0.7 m 的乾淨路面上,
    # 兩條並排才好比對。前/後各自用自己的幾何,兩邊都是「如果我的尺是對的,虛線該長這樣」。
    dash_m, cycle_m = (float(v) for v in args.dash_spec.split(","))
    tb_read_b = tb_draw_b = tb_read_a = tb_draw_a = None
    if args.odometer_points:
        pts = [tuple(int(v) for v in c.split(",")) for c in args.odometer_points.split(";") if c.strip()]
        tb_read_b, tb_draw_b = line_tables(p2p_before, pts, h, w, args.hood_y, 6.0, 46.0, 0.40)
        tb_read_a, tb_draw_a = line_tables(p2p_after, pts, h, w, args.hood_y, 6.0, 46.0, 0.40)
        print(f"虛線取樣表:修正前 {0 if tb_read_b is None else len(tb_read_b[0])} 點、"
              f"修正後 {0 if tb_read_a is None else len(tb_read_a[0])} 點")

    # ⚠ 這裡本來會印出「量到的虛線週期 = X m」當標題,已移除:單幀畫面裡只裝得下 2~3 個
    # 週期,不論用自相關或頻譜,週期估計的解析度都是 ±15%(本專案早就記過「窗內需 ≥2 週期」
    # 這條判準)。跨五支同型道路實測 8.7~11.1 m 就是這個雜訊。留在畫面上會變成假精確,
    # 所以只留「刻度 + 我們算的 10 m 虛線」讓眼睛自己判斷對不對齊。
    t_before = (f"{args.label}  BEFORE (x1.000)   bars = our {cycle_m:.0f} m pattern, "
                f"phase-locked once per frame -- do they stay on the painted dashes?")
    t_after = (f"{args.label}  AFTER  (x{args.correction:.3f})   bars = our {cycle_m:.0f} m pattern, "
               f"phase-locked once per frame -- do they stay on the painted dashes?")

    top_rows = [m[0][1] for m in marks_before + marks_after]
    crop = args.crop_top if args.crop_top >= 0 else max(0, min(top_rows) - 90)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    ph = h - crop
    sw, sh = int(w * args.scale_out) // 2 * 2, int(ph * args.scale_out) // 2 * 2
    proc = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24",
         "-s", f"{sw}x{sh * 2}", "-r", f"{args.fps:.4f}", "-i", "-",
         # 本機 ffmpeg 沒有 libx264,只有 openh264(管線 A/B 也是用它轉檔)
         "-c:v", "libopenh264", "-b:v", "8M", "-pix_fmt", "yuv420p", str(out)],
        stdin=subprocess.PIPE)

    for i, f in enumerate(frames):
        img = cv2.imread(str(f))
        if img is None:
            continue
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        tb, ta = img.copy(), img.copy()
        ph_b = dash_phase(gray, tb_read_b, 7.0, dash_m=dash_m, cycle_m=cycle_m) if tb_read_b is not None else None
        ph_a = dash_phase(gray, tb_read_a, 7.0, dash_m=dash_m, cycle_m=cycle_m) if tb_read_a is not None else None
        if ph_b is not None and tb_draw_b is not None:
            t = tb_draw_b[best_band(gray, tb_read_b)]
            if t is not None:
                draw_synthetic_dashes(tb, t, ph_b, dash_m, cycle_m, 4, RED)
        if ph_a is not None and tb_draw_a is not None:
            t = tb_draw_a[best_band(gray, tb_read_a)]
            if t is not None:
                draw_synthetic_dashes(ta, t, ph_a, dash_m, cycle_m, 4, GREEN)
        top = draw_panel(tb, marks_before, t_before, RED, crop, cycle_m)
        bot = draw_panel(ta, marks_after, t_after, GREEN, crop, cycle_m)
        stack = np.vstack([cv2.resize(top, (sw, sh)), cv2.resize(bot, (sw, sh))])
        proc.stdin.write(stack.tobytes())
        if i % 300 == 0:
            print(f"   {i}/{len(frames)}", flush=True)
    proc.stdin.close()
    proc.wait()
    print(f"已寫出 {out}")


if __name__ == "__main__":
    main()
