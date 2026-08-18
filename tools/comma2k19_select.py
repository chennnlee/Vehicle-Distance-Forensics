"""挑選 comma2k19 段落 —— 用「路類」而不是「速度」當條件。

首跑（2026-08-10）用「中位速 ≥ 70 km/h」挑段,結果放進一批起點在有紅綠燈市區幹道、
後段才上 I-280 的段落。市區幹道的法定虛線週期約是高速公路的一半,套同一個常數就整段
倍速,而這件事在總體數字上看不出來（誤差中位數只有 1.20,問題只在分群檢查時才顯現）。
教訓是:**速度不能代理路類**。

本工具改用一條事前可宣告、事後可稽核的條件:

    整段的最低速度 ≥ --min-floor（預設 60 km/h）

號誌化幹道在 60 秒內幾乎一定會遇到一次減速或停等,高速公路巡航則不會。這條件不看
我方量測、不看虛線週期,因此不循環;它也不是「調到好看為止」的門檻——把它套回
Chunk_1 應該要排掉已知被污染的那幾段,這就是它的驗證方式（--validate）。

只讀 zip 內的 global_pose 與 CAN log,不解碼影片,所以掃完一個 chunk 是分鐘級。
"""
from __future__ import annotations

import argparse
import csv
import io
import re
import zipfile
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WGS84_A = 6378137.0
WGS84_E2 = (1 / 298.257223563) * (2 - 1 / 298.257223563)


def ecef_to_geodetic(pos: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    x, y, z = pos[:, 0], pos[:, 1], pos[:, 2]
    lon = np.arctan2(y, x)
    r = np.hypot(x, y)
    lat = np.arctan2(z, r * (1 - WGS84_E2))
    for _ in range(6):
        n = WGS84_A / np.sqrt(1 - WGS84_E2 * np.sin(lat) ** 2)
        h = r / np.cos(lat) - n
        lat = np.arctan2(z, r * (1 - WGS84_E2 * n / (n + h)))
    return np.degrees(lat), np.degrees(lon)


def load(zf: zipfile.ZipFile, name: str):
    try:
        with zf.open(name) as fh:
            return np.load(io.BytesIO(fh.read()), allow_pickle=False)
    except (KeyError, ValueError):
        return None


def scan(zip_path: Path) -> list[dict]:
    zf = zipfile.ZipFile(zip_path)
    segs = {}
    for n in zf.namelist():
        m = re.match(r"^(Chunk_\d+/([^/]+)/(\d+))/global_pose/frame_velocities$", n)
        if m:
            segs[(m.group(2), int(m.group(3)))] = m.group(1)
    rows = []
    for (route, num), base in sorted(segs.items()):
        fv = load(zf, f"{base}/global_pose/frame_velocities")
        ft = load(zf, f"{base}/global_pose/frame_times")
        fp = load(zf, f"{base}/global_pose/frame_positions")
        if fv is None or ft is None or fp is None or len(fv) < 100:
            continue
        v = np.linalg.norm(np.asarray(fv, float), axis=1) * 3.6
        lat, lon = ecef_to_geodetic(np.asarray(fp, float))
        rows.append({
            "tag": f"{route.replace('|', '_')}_{num}", "route": route, "segment": num,
            "seconds": float(ft[-1] - ft[0]), "n": int(len(v)),
            "median_kmh": float(np.median(v)), "min_kmh": float(v.min()),
            "p5_kmh": float(np.percentile(v, 5)), "max_kmh": float(v.max()),
            "lat": float(np.median(lat)), "lon": float(np.median(lon)),
        })
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--zip", required=True)
    ap.add_argument("--min-floor", type=float, default=60.0,
                    help="整段最低速度下限(km/h)。這是路類條件,不是速度帶條件。")
    ap.add_argument("--min-seconds", type=float, default=55.0)
    ap.add_argument("--per-route", type=int, default=2)
    ap.add_argument("--out-csv", default="")
    ap.add_argument("--validate", default="",
                    help="已知被污染的 tag,逗號分隔;檢查這條件是否確實把它們排掉。")
    args = ap.parse_args()

    rows = scan(Path(args.zip))
    print(f"掃到 {len(rows)} 段")

    long_enough = [r for r in rows if r["seconds"] >= args.min_seconds]
    passing = [r for r in long_enough if r["min_kmh"] >= args.min_floor]
    chosen, per = [], {}
    for r in sorted(passing, key=lambda r: (-r["median_kmh"])):
        if per.get(r["route"], 0) >= args.per_route:
            continue
        per[r["route"]] = per.get(r["route"], 0) + 1
        chosen.append(r)

    print(f"  長度 ≥ {args.min_seconds:.0f}s          : {len(long_enough)}")
    print(f"  最低速 ≥ {args.min_floor:.0f} km/h      : {len(passing)}  "
          f"(排掉 {len(long_enough) - len(passing)} 段)")
    print(f"  每路線最多 {args.per_route} 段        : {len(chosen)}")
    if chosen:
        med = np.array([r["median_kmh"] for r in chosen])
        mins = np.array([r["min_kmh"] for r in chosen])
        print(f"  入選段中位速 {np.median(med):.1f} km/h,最低速中位 {np.median(mins):.1f} km/h,"
              f"總長 {sum(r['seconds'] for r in chosen)/60:.1f} 分鐘")

    if args.validate:
        bad = {t.strip() for t in args.validate.split(",") if t.strip()}
        kept = {r["tag"] for r in chosen}
        caught = bad - kept
        missed = bad & kept
        print(f"\n驗證:已知污染 {len(bad)} 段 → 排掉 {len(caught)}、漏掉 {len(missed)}")
        for t in sorted(missed):
            r = next(x for x in rows if x["tag"] == t)
            print(f"    漏掉 {t}  最低速 {r['min_kmh']:.1f}  中位 {r['median_kmh']:.1f}")

    print("\n--segments 參數:")
    print(",".join(f"{r['route']}|{r['segment']}" for r in chosen))
    if args.out_csv:
        with open(args.out_csv, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(chosen[0].keys()))
            w.writeheader()
            w.writerows(chosen)
        print(f"\n已寫出 {args.out_csv}")


if __name__ == "__main__":
    main()
