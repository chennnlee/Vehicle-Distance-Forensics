# 主流程(簡化版)

一個指令,從行車紀錄器影片算出本車速度、他車距離與車速,並輸出一支數字標在車上的影片。
現行管線 B(`tools/dashcam_range_speed.py`)和各研究資料夾都保留不動。這裡只放最後決定要用的四塊,每塊只做一件事。

```
影片 ──▶ 1 影格 ──▶ 2 本車速度(碼表)────────────────┐
                 └─▶ 3 他車:偵測+追蹤 ─▶ 4 距離(深度模型 × 尺度)─▶ 相對速度 ─▶ 他車車速 = 本車 + 相對
                                                                         │
                                                         輸出:表格、影片、摘要
```

## 四塊

| | 做什麼 | 用什麼 | 來源 |
|---|---|---|---|
| 1 影格 | 影片拆成影格 | 固定版本的 ffmpeg(`$FFMPEG`) | 解碼器版本會改變影格,一律指定 |
| 2 本車速度 | 數路面虛線經過的週期 → 車速 | 自動選取量測點 + 碼表 | `tools/auto_odometer_points.py`、`tools/dashcam_range_speed.py` 的碼表函式;讀不到就留空,不補成 0 |
| 3 偵測與追蹤 | 找出每台車、給同一台車同一個編號 | YOLOv8m-seg + BoT-SORT | 追蹤在影像座標上做,不需要路面平面 |
| 4 距離 | 每台車的距離 | Depth Anything 3 公制版(DA3METRIC-LARGE)量車框下半中央的深度,乘上尺度 | 深度讀值與點對的做法同 `research/sharp_free/depth_run.py` |

**尺度只有一條規則**,依序取第一個可用的:
1. 同一台相機事先算好的尺度(`--camera-scale`);
2. 這段片自己用碼表定的尺度:靜止點在畫面上的擴張 + 碼表走的距離(`research/sharp_free/motion_scale.py`);
3. 都不行時用 30 mm 規則焦距,並在輸出標「尺度未校正」。

**速度**:
- 他車相對速度 = 前後約 1 秒距離的直線斜率;他車車速 = 本車速度 + 相對速度。
- 只在 30 m 內標他車車速,遠的車只給距離。30 m 外的相對速度,開發資料上不比「直接猜跟本車一樣快」準。

## 輸出(`--out` 資料夾)

- `ego.csv`:每幀本車速度與來源(碼表、內插、無)。
- `objects.csv`:每幀每台車的框、距離、相對速度、他車車速、旗標。
- `video.mp4`:數字標在車上,一支影片只有這一種方法。
- `summary.md`:片長、碼表有讀值的比例、尺度來源與數值、車輛數。

`pipeline.batch` 的輸出不同:`ego.csv` 只列有處理的幀(每兩幀一幀,評分的範圍),沒有影片與摘要,參數寫在 `meta.json`。

## 怎麼跑

一支影片:

```bash
export LD_PRELOAD=~/anaconda3/envs/VisionVelocity/lib/libstdc++.so.6
FFMPEG=$HOME/anaconda3/envs/VisionVelocity/bin/ffmpeg ~/venvs/da3/bin/python -m pipeline.run \
    --video <影片> --out <輸出資料夾> --road-class tw
```

`--road-class` 決定虛線週期(共同評分 `docs/SPEC.md` 2.3):`tw` = 台灣 10 m、`ca_highway` = 加州速限 45 mph 以上 14.63 m、
`ca_local` = 加州速限 40 mph 以下 7.315 m。要在 repo 根目錄執行(碼表函式在 `tools/`,載入時會帶入同層的模組)。

共同評分的一批片段(`segment.json` + 影格,輸出共同格式 `ego.csv`、`objects.csv`、`meta.json`):

```bash
FFMPEG=<約定的 ffmpeg> ~/venvs/da3/bin/python -m pipeline.batch --segments-root <segments> --ids <清單> \
    --out-root <predictions/A_depth_odometer> --cache <快取資料夾> [--camera-scale S] --hood-row 630 --picker comma2k19
```

- 路類讀 `segment.json` 的 `road_class`;`unknown` 用 14.63 m。
- 每段寫兩個版本:`v2own`(這段片自己定的尺度)、`v2`(同機尺度,有給 `--camera-scale` 才寫)。
- 快取存每段的偵測、深度、本車速度與靜止點,換尺度不必重跑模型。
- 單段失敗寫成拒發(`meta.json` 的 `status: refused` 與原因),整批繼續;`meta.json` 記程式與權重的雜湊。
- 選項(預設都不開):
  - `--rel-window` 相對速度擬合窗(秒,預設 1);
  - `--camera-scale-night` 夜間片段(`segment.json` 的 `light`)改用的同機尺度;
  - `--distance-correction` 距離修正表(開發資料學的 `{d_m, factor}`,只用在同機尺度版,相對速度仍用修正前的距離算);
  - `--cycle-select` 一段片中途換路類時,用影像在加州兩個法定週期(7.315 / 14.63 m)之間逐秒挑一個(`cycle.py`;影像不提供速度值,台灣 10 m 時不動作)。

## 沒有放進來的東西

研究資料夾保留,當紀錄:
- SHARP 路面平面:被深度模型取代,權重也限研究用。
- 補本車速度的洞:四版都贏不了「假設車速不變」。
- 去模糊、夜間增強。
- 其他尺度變體、交叉比對版本。

## 規則

- 一次只換一塊。
- 新東西要進來,先在共同評分(`monocular-driving-distance` 的 `mddbench`)上比現在的版本好。
- 偵測器 YOLOv8 是 AGPL,商用前要處理授權。

## 已做的檢查(2026-10-18)

- **台灣 hs005**(18 秒):一個指令跑完,約 2 分鐘。
  - 本車速度和現有輸出的逐幀差中位 0.3 km/h,和畫面上的 GPS 車速一致。
  - 碼表定出的尺度是規則焦距的 0.88 倍,和先前研究的 0.87 一致。
- **comma2k19 開發資料 6 段**(`research/pipeline_check/RESULTS.md`),和舊管線軌跡上的研究版比,同一批車:
  - 30 m 內 5.5% 對 5.8%,30–60 m 7.4% 對 7.4%,60–100 m 13.7% 對 12.4%;
  - 30 m 內相對速度 2.6 對 3.1 km/h;
  - 量到的車 48% 對 38%。
  - 開發資料、只有 6 段,不是確認。
