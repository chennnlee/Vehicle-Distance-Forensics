"""The fifteen Taiwanese odometer regression cases, as data.

Any change to the fundamental-selection logic has to prove it does not move
these. The set spans every regime the odometer has been shown to work in and
several it fails in on purpose: 12 m-class freeway cruise at 100 km/h, urban
40 km/h, a 10 fps resampled clip at the sampling-rate floor, a wide-FOV Mio that
samples a continuous longitudinal smear instead of dashes, and two clips with
machine-readable manual frame-by-frame truth.

This file exists because the previous copy lived in /tmp and did not survive a
WSL restart -- the frame directories are disposable, but the case parameters are
the actual asset and belong somewhere durable.

`points` are the hand-aimed sampling columns recorded in CLAUDE.md. Two cases
(hs003s, hs006s) were added during the 2026-08-02 GPS arbitration and their
points were never written down; they carry `points=None`, meaning
`auto_odometer_points.py` picks them. That is fine for a before/after
regression, which only requires the SAME points on both sides.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ROOT = Path("/home/s11244/code/114/Vehicle-Distance-Forensics")
DEMO = ROOT / "data/output/dashcam_demo"
HAISHENG = ROOT / "data/20260317_AI辨速系統案例/20251230_海盛_AI辨速系統案例/汽車行車紀錄器 - 人工標註"
BATCH = ROOT / "data/20260317_AI辨速系統案例/20251029_第三代AI辨速系統-案例/汽車行車紀錄器"


@dataclass
class Case:
    name: str
    src: Path
    fps: float
    points: str | None
    cycle_m: float = 10.0
    frames_dir: str = ""
    ss: float | None = None          # extract window start (s)
    dur: float | None = None         # extract window length (s)
    frame_limit: int | None = None   # keep only the first N frames after extraction
    resample_fps: float | None = None  # rebuild by uniform pts resampling (c1416u)
    truth_xlsx: Path | None = None
    note: str = ""

    @property
    def frames(self) -> Path:
        return Path("/tmp") / (self.frames_dir or f"{self.name}_frames")


def _batch(pattern: str) -> Path:
    hits = sorted(p for p in BATCH.rglob("*.mp4") if pattern in p.name and "_pred" not in p.name
                  and "_manual" not in p.name)
    if not hits:
        raise FileNotFoundError(pattern)
    return hits[0]


CASES: list[Case] = [
    # --- five demos: rebuilt from the archived clips, verified frame counts ---
    Case("dc002", DEMO / "dc002/original_clip_h264.mp4", 30.0,
         "586,800;546,850;672,750", note="002 白天高速 25-45s,600 幀"),
    Case("dc003", DEMO / "dc003/original_clip_h264.mp4", 29.97,
         "1000,700;1180,750;1450,800;704,700;700,750;654,800",
         note="Mio 超廣角,自車 3 次換道,1798 幀"),
    Case("dc006", DEMO / "dc006/original_clip_h264.mp4", 29.97,
         "720,700;675,760;1319,820;595,860", note="國1 五股,第 4 點=遠列,1801 幀"),
    Case("dc007", DEMO / "dc007/original_clip_h264.mp4", 30.0,
         "1110,900;1216,960;1306,1010", note="台86 危險駕駛 11s,330 幀"),
    Case("dc008", DEMO / "dc008/original_clip_h264.mp4", 30.0,
         "1223,800;1272,840;1295,860", note="008 街道 10-30s,600 幀;舊碼半速錯的那支"),
    # --- 20251029 car batch: OSD-derived frame rates, three timebase traps ---
    Case("c0135", _batch("109年第01次第35案"), 25.0, "1065,700;1115,760;1195,820"),
    Case("c1005", _batch("109年第10次第05案"), 29.85, "1030,780;1100,840;1140,900;1185,960",
         note="fps 由 OSD 定,容器值不可信"),
    Case("c3323", _batch("109年第33次第23案"), 28.75, "690,720;615,770;510,830;450,880",
         note="容器謊報 29.97,真 28.75;左側虛線"),
    Case("c4316", _batch("第43次第16案"), 30.5, "1010,720;1105,780;1165,840;1215,880",
         note="fps 30.5 由 OSD 時基定"),
    Case("c1416u", _batch("113年第14次第16案"), 10.0, "545,380;505,420;480,470",
         resample_fps=10.0, note="VFR 原片,pts 均勻重取樣成 10fps,302 幀;取樣率下限案"),
    Case("c4407a", _batch("113年第44次第07案"), 30.0,
         "1075,700;1165,760;1250,820;1330,880;820,700;880,760;950,820",
         frame_limit=810, note="f811 起是剪掉 60s 後的撞擊段,只取前 810 幀"),
    # --- Haisheng clips with machine-readable manual frame-by-frame truth ---
    Case("hs005", DEMO / "hs005/original_clip_h264.mp4", 29.8883,
         "779,700;710,750;643,800;572,850",
         truth_xlsx=HAISHENG / "005_白天_短1_O_A3min_B4min/Garmin GDR E530 壓線測試_manual.xlsx",
         note="最佳一案:對人工 MAE 0.69;左側虛線(右側是實線)"),
    Case("hs003s", HAISHENG / "003_白天_短1_O_A4min_B6min/Mio MiVue D908 後視鏡型行車記錄器(4K主機)_4K30fps日間實拍(請以4K解析度觀看).mp4",
         30.0, None,
         truth_xlsx=HAISHENG / "003_白天_短1_O_A4min_B6min/Mio MiVue D908 後視鏡型行車記錄器(4K主機)_4K30fps日間實拍(請以4K解析度觀看)_manual.xlsx",
         note="Mio 超廣角,已知失效(覆蓋 31%、MAE 25.3):取樣點落在連續縱向亮痕上"),
    Case("hs006s", HAISHENG / "006_白天_短1_O_A4min_B5min/GDR E350 白天-高速公路.mp4",
         30.0, None,
         truth_xlsx=HAISHENG / "006_白天_短1_O_A4min_B5min/GDR E350 白天-高速公路_manual.xlsx",
         note="仲裁案:我方 MAE 1.30 vs 該機 GPS 2.91(系統性低報 −2.89)"),
    # --- WoWtchout public clip: ego speed did NOT pass against its OSD ---
    Case("wow001", DEMO / "wow001/original_clip_h264.mp4", 30.0,
         "1073,700;1116,720;1152,740;728,700;703,720", dur=119.0,
         note="國三寶山,只抽前 119s(120s 起是片尾卡片);對 abee OSD MAE 11.97"),
]

BY_NAME = {c.name: c for c in CASES}
