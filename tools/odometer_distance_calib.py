"""用碼表訊號校出行車紀錄器的距離尺度 —— 不需要 SHARP 的焦距假設。

2026-08-19 的稽核確立:SHARP 的地面平面**俯仰是對的**(地平線列與碼表實測差 0.7–4.3 px),
但它的**固定 FOV 焦距假設(fx = 0.7955×寬)逐機錯**,使前向距離均勻偏高 9–34%。
均勻是關鍵證據:俯仰誤差會隨距離變化,焦距誤差則是固定比例。

量法完全不碰平面、不碰點雲、不碰車道寬,也**不需要右車道線**(那是唯一常失敗的抽取步驟):

    同一批虛線先後流過各取樣列
    → 兩列訊號的互相關 lag ÷ 碼表週期 × 法定週期 = 兩列的實際公尺間距
    → 擬合 fwd(y) = A/(y − y_h)

`A = h·f` 是距離量測唯一需要的量:掛高與焦距永遠以乘積出現,不必分開解。
輸出的修正係數 `A_碼表 / A_SHARP` 直接乘在既有距離輸出上即可,不必重建幾何。

⚠ 品質閘:取樣列的跨幅太短時,A 與 y_h 幾乎完全交換,兩參數擬合會退化
(wow001 只跨 40 px,解出 y_h=467 這種離譜值)。跨幅不足就固定 y_h 只解 A。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "tools"))

from dashcam_range_speed import extract_odometer_signals            # noqa: E402
from tools.dashcam_lane_width_calib import build_plane              # noqa: E402

MIN_ROW_SPAN_PX = 100.0     # 兩參數擬合所需的最小取樣列跨幅
MIN_XCORR_PEAK = 0.35       # 列對互相關峰的採用門檻


def sub_frame_peak(v: np.ndarray, i: int) -> float:
    if 0 < i < len(v) - 1:
        d = v[i - 1] - 2 * v[i] + v[i + 1]
        if abs(d) > 1e-12:
            return i + 0.5 * float(v[i - 1] - v[i + 1]) / float(d)
    return float(i)


def odometer_period(sig: np.ndarray, fps: float) -> float | None:
    """碼表週期(幀)。與 dash_cycle_speeds 同法,但這裡只要一個代表值。"""
    s = sig - sig.mean()
    if s.std() < 2:
        return None
    ac = np.correlate(s, s, "full")[len(s) - 1:]
    if ac[0] <= 0:
        return None
    ac = ac / ac[0]
    lo, hi = int(0.25 * fps), int(3.0 * fps)
    if hi <= lo + 2:
        return None
    return sub_frame_peak(ac, lo + int(np.argmax(ac[lo:hi])))


def group_by_line(points, tol_px: float = 25.0) -> list[list]:
    """把取樣點依「落在同一條車道線上」分組。

    這道閘是必要的,不是保險:左右車道線的虛線縱向相位通常不同,跨線配對算出的
    互相關 lag 不是行進時間。dc003 的 6 個點分屬左右兩線,不分組會解出 5.2 倍的
    荒謬修正係數;dc006 與 wow001 也各有一個點在對側。
    """
    remaining = sorted(points, key=lambda q: q[1])
    groups = []
    while len(remaining) >= 2:
        best = None
        for i in range(len(remaining)):
            for j in range(i + 1, len(remaining)):
                (x1, y1), (x2, y2) = remaining[i], remaining[j]
                if y1 == y2:
                    continue
                m = (x2 - x1) / (y2 - y1)
                k = x1 - m * y1
                mem = [q for q in remaining if abs(m * q[1] + k - q[0]) <= tol_px]
                if best is None or len(mem) > len(best):
                    best = mem
        if best is None or len(best) < 2:
            break
        groups.append(best)
        remaining = [q for q in remaining if q not in best]
    return groups


def row_pair_distances(sig: dict, points, period: float, cycle_m: float) -> list[tuple]:
    """每一組(遠列, 近列)的實際公尺間距,由互相關 lag 換算。只配對同一條線上的點。"""
    out = []
    pairs = []
    for grp in group_by_line(points):
        g = sorted(grp, key=lambda q: q[1])          # 由遠(列小)而近
        pairs += [(g[i], g[j]) for i in range(len(g)) for j in range(i + 1, len(g))]
    for A, B in pairs:
            if A[1] == B[1]:
                continue
            sa = sig[A][:, 0].astype(float)
            sb = sig[B][:, 0].astype(float)
            n = min(len(sa), len(sb))
            sa, sb = sa[:n] - sa[:n].mean(), sb[:n] - sb[:n].mean()
            if sa.std() < 2 or sb.std() < 2:
                continue
            xc = np.correlate(sb, sa, "full") / (n * sa.std() * sb.std())
            lags = np.arange(-n + 1, n)
            w = np.flatnonzero((lags >= 0) & (lags <= period * 0.95))
            if w.size < 3:
                continue
            k = int(w[int(np.argmax(xc[w]))])
            if xc[k] < MIN_XCORR_PEAK:
                continue
            # sub_frame_peak 回傳的是索引;互相關的 lag 陣列從 −(n−1) 起算,要減掉偏移。
            # (單邊自相關的索引恰好等於 lag,所以 odometer_period 不需要這一步。)
            lag = sub_frame_peak(xc, k) - (n - 1)
            out.append((A[1], B[1], cycle_m * lag / period, float(xc[k])))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--frames-dir", required=True)
    ap.add_argument("--pointcloud", required=True)
    ap.add_argument("--hood-y", type=int, required=True)
    ap.add_argument("--pointcloud-scale", type=float, required=True)
    ap.add_argument("--odometer-points", required=True)
    ap.add_argument("--dash-cycle-m", type=float, default=10.0)
    ap.add_argument("--fps", type=float, required=True)
    ap.add_argument("--label", default="")
    ap.add_argument("--out-json", default="")
    args = ap.parse_args()

    pts = [tuple(int(v) for v in c.split(",")) for c in args.odometer_points.split(";") if c.strip()]
    frames = sorted(Path(args.frames_dir).glob("*.jpg")) or sorted(Path(args.frames_dir).glob("*.png"))
    if not frames:
        sys.exit(f"{args.frames_dir}: 無影格")
    sig = extract_odometer_signals(frames, pts, 120)

    periods = [p for p in (odometer_period(sig[q][:, 0].astype(float), args.fps) for q in pts) if p]
    if not periods:
        sys.exit("碼表無鎖定,無法校正")
    period = float(np.median(periods))

    # 影像尺寸由影格自己讀,內參由點雲帶回 —— 原本寫死 1920×1080 與 fy=1527.4,
    # 換一台感測器(comma2k19 是 1164×874)就會把地平線列算錯好幾十像素。
    with Image.open(frames[0]) as im:
        img_w, img_h = im.size
    p2p, ground, _, intr = build_plane(Path(args.pointcloud), (img_h, img_w), args.hood_y)
    fwd_sharp = {q: float(p2p(*q)[1]) * args.pointcloud_scale for q in pts}
    order = sorted(pts, key=lambda q: -fwd_sharp[q])
    # SHARP 平面的地平線列:平面消失線 dy = a·dx + b 在光心列的位置
    y_h_sharp = intr["cy"] + intr["fy"] * ground["b"]
    A_sharp = float(np.median([fwd_sharp[q] * (q[1] - y_h_sharp) for q in pts]))

    obs = row_pair_distances(sig, pts, period, args.dash_cycle_m)
    if len(obs) < 2:
        sys.exit(f"有效列對不足({len(obs)});取樣點太少或訊號太弱")

    span = max(q[1] for q in pts) - min(q[1] for q in pts)
    result = {"label": args.label, "period_frames": period, "row_pairs": len(obs),
              "row_span_px": span, "A_sharp": A_sharp, "y_h_sharp": y_h_sharp}

    if span >= MIN_ROW_SPAN_PX:
        from scipy.optimize import least_squares
        hi_y = min(o[0] for o in obs) - 15
        sol = least_squares(lambda p: [p[0] / (a - p[1]) - p[0] / (b - p[1]) - d for a, b, d, _ in obs],
                            [A_sharp, y_h_sharp], bounds=([200, 300], [8000, hi_y]))
        result["fit"] = "two-parameter"
        result["A"], result["y_h"] = float(sol.x[0]), float(sol.x[1])
        result["residual_max_m"] = float(np.abs(sol.fun).max())
    else:
        # 跨幅不足:固定地平線(兩支條件好的片證實 SHARP 俯仰只差 0.7–4.3 px),只解 A
        As = [d / (1 / (a - y_h_sharp) - 1 / (b - y_h_sharp)) for a, b, d, _ in obs
              if (a - y_h_sharp) > 5 and (b - y_h_sharp) > 5]
        result["fit"] = "one-parameter (row span too short)"
        result["A"], result["y_h"] = float(np.median(As)), y_h_sharp
        result["residual_max_m"] = float(max(
            abs(result["A"] * (1 / (a - y_h_sharp) - 1 / (b - y_h_sharp)) - d) for a, b, d, _ in obs))

    # 修正係數用「實測/SHARP 預測」的直接中位數,不用擬合出的 A 比值。
    # 理由:A 與 y_h 在 3–6 組列對下拆不穩 —— dc006 的擬合把 8% 的差異全算進地平線
    # (移 8.2 px)因而報出「不用修」,但每一組列對的實測都比預測低 8%。直接比值
    # 不需要做這個分解,而且片內一致性(hs005 ±3%、dc006 ±1.5%)本身就證明
    # 地平線大致正確 —— 地平線若錯,比值會隨列對系統性變化。
    preds = [A_sharp / (a - y_h_sharp) - A_sharp / (b - y_h_sharp) for a, b, d, _ in obs]
    ratios = [d / q for (_, _, d, _), q in zip(obs, preds)]
    # 逐列對的原始觀測也寫出來:報告的證據圖畫的就是這一組點,不必重跑量測就能重畫。
    result["row_pairs_detail"] = [[float(a), float(b), float(d), float(pk)] for a, b, d, pk in obs]
    result["pred_m"] = [float(q) for q in preds]
    result["meas_m"] = [float(o[2]) for o in obs]
    result["pair_ratios"] = [float(r) for r in ratios]
    result["ratio_spread"] = float(np.max(ratios) - np.min(ratios))
    result["distance_correction"] = float(np.median(ratios))
    # 品質閘:地平線若大致正確,各列對的比值應該一致。散布過大代表這支片的幾何
    # (或取樣點)有問題,寧可拒發也不要給一個假的修正 —— dc003 兩組列對是
    # 1.378 與 0.394,散布 0.98,而它本來就是已知的超廣角失效案。
    result["usable"] = bool(result["ratio_spread"] <= 0.10 and len(obs) >= 2)
    result["A_fit_over_A_sharp"] = result["A"] / A_sharp     # 僅供診斷

    print(f"\n=== {args.label or Path(args.pointcloud).stem} ===")
    print(f"碼表週期 {period:.2f} 幀,{len(obs)} 組列對,取樣列跨幅 {span:.0f} px,擬合 {result['fit']}")
    print(f"{'列對':>14s} {'實測間距':>9s} {'SHARP 預測':>10s} {'相關峰':>6s}")
    for a, b, d, pk in obs:
        pred = A_sharp / (a - y_h_sharp) - A_sharp / (b - y_h_sharp)
        print(f"{f'{a:.0f}→{b:.0f}':>14s} {d:8.2f}m {pred:9.2f}m {pk:6.2f}")
    print(f"\n{'':14s} {'A = h·f':>9s} {'地平線列':>9s}")
    print(f"{'碼表實測':>14s} {result['A']:9.0f} {result['y_h']:9.1f}   (殘差 {result['residual_max_m']:.3f} m)")
    print(f"{'SHARP':>14s} {A_sharp:9.0f} {y_h_sharp:9.1f}")
    print(f"\n距離修正係數 = {result['distance_correction']:.3f} "
          f"(SHARP 偏高 {100*(1/result['distance_correction']-1):+.0f}%),"
          f"逐對散布 {result['ratio_spread']:.3f} → "
          f"{'可用' if result['usable'] else '✗ 散布過大,拒發'}")
    print(f"{'列':>6s} {'SHARP 距離':>10s} {'修正後':>9s}")
    for q in order:
        print(f"{q[1]:6d} {fwd_sharp[q]:9.2f}m {fwd_sharp[q]*result['distance_correction']:8.2f}m")

    if args.out_json:
        Path(args.out_json).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\n已寫出 {args.out_json}")


if __name__ == "__main__":
    main()
