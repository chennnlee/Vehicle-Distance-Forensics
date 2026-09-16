# 重現指南

給拿到這個 repo、想自己把數字跑出來的人。

## 你有什麼、缺什麼

| | 在 repo 裡 | 怎麼補 |
|---|---|---|
| 程式碼 `tools/` | ✅ | — |
| 執行參數 | ✅ `CLAUDE.md`「各案執行參數」 | — |
| 各項成果的方法與數字 | ✅ `data/output/**/README.md` | — |
| 模型權重 | ❌ | `yolo` 首次執行自動下載,或見下方 |
| SHARP 點雲 `.ply` | ❌ | 自己跑一次(只有他車距離需要) |
| 素材 | ❌ | comma2k19 公開可下載;台灣素材見最後一節 |
| 輸出(csv/影片/圖) | ❌ | 跑出來的 |

## 環境

```bash
pip install -r requirements.txt
```

CUDA 非必要,但沒有 GPU 的話 YOLO 會慢很多(本專案在 RTX 4050 6 GB 上跑 1080p 約 50 ms/幀)。

⚠ 本機曾踩到:跑 scipy 需要 `export LD_PRELOAD=$CONDA_PREFIX/lib/libstdc++.so.6`(系統 libstdc++ 太舊)。

---

## 路徑 A:自車速 —— 最容易,不需要 SHARP,也不需要任何非公開素材

**這是本專案最紮實的一條鏈**,對兩台車 33 段 35,809 幀的公開資料集實測 MAE **2.18 km/h**。
之所以不需要 SHARP:自車速是用「法定虛線週期流過固定畫面列」的時間量的,
完全不經過點雲、平面或尺度。

```bash
# 1) 下載(8.7 GB;MIT 授權)
mkdir -p data/input/comma2k19
curl -L -o data/input/comma2k19/Chunk_1.zip \
  https://huggingface.co/datasets/commaai/comma2k19/resolve/main/raw_data/Chunk_1.zip

# 2) 先只掃真值、不解碼影格(快),看 segments.csv 挑段
python3 tools/comma2k19_prepare.py --zip data/input/comma2k19/Chunk_1.zip \
  --out-root /tmp/comma_scan --same-route --no-frames

# 3) 依「整段最低速 >= 60 km/h」選段(事前可宣告的規則,不看真值誤差)
python3 tools/comma2k19_select.py --zip data/input/comma2k19/Chunk_1.zip --min-floor 60
python3 tools/comma2k19_prepare.py --zip data/input/comma2k19/Chunk_1.zip \
  --out-root /tmp/comma_seg --segments "<上一步印出的段落>"

# 4) 評估(自動挑取樣點,不需人工指定)
python3 tools/public_dataset_ego_eval.py --batch-root /tmp/comma_seg --fps 20.0 \
  --auto-points --road-top 0.48 --road-bottom 0.68 \
  --gt-file gt_both.csv --gt-column can_kmh --alt-column pose_kmh \
  --solve-cycle --dash-cycle-m 14.63 \
  --out-json /tmp/batch.json
```

⚠ **`--dash-cycle-m 14.63` 是加州高速公路的規格(48 ft)**,不是通用常數。台灣國道實測是 10 m
(不是規範寫的 12 m)。換路網一定要先用 `--solve-cycle` 反推驗證——
虛線週期是「每條路的常數」,不是「每支影片的常數」。

**預期數字**(`data/output/comma2k19_eval/README.md` 有完整分層):

| 條件 | MAE |
|---|---|
| 兩台車 33 段合計 | 2.18 km/h(±3 內 82.2%、覆蓋 90.4%) |
| 日間高速公路 | 1.78 |
| 夜間高速公路 | 4.72(逆反射路釘是已知較弱情境) |

---

## 路徑 B:他車距離與絕對速度 —— 需要 SHARP

三段有原廠雷達的 comma2k19 片段,近場距離誤差中位 **7.0%**、目標絕對速 MAE **3.54 km/h**。
完整參數在 `data/output/comma2k19_radar_eval/README.md` 第三節(ply、scale、碼表取樣點、車道線像素對全部列出)。

```bash
# 1) 取一張參考幀跑 SHARP(見 https://github.com/apple/ml-sharp)
#    CPU-only,GPU 6 GB 會 OOM;約 90 秒,整支片只需跑這一次
sharp predict -i <參考幀.jpg> -o data/output/sharp_gaussians/ --device cpu --no-render

# 2) 用車道寬錨定尺度(comma2k19 用 12 ft = 3.6576 m)
python3 tools/lane_line_fit.py --frames-dir <frames> --rows 500,540,580,615   # 印出 --pairs
python3 tools/dashcam_lane_width_calib.py --pointcloud <ply> --hood-y 630 \
  --pairs "<上一步的輸出>" --lane-width-m 3.6576 --out-json <out>/lane_width_calib.json

# 3) 量測
python3 tools/dashcam_range_speed.py --frames-dir <frames> --fps 20.0 \
  --reference-pointcloud <ply> --pointcloud-scale <scale> --hood-y 630 \
  --odometer-points "<點位>" --dash-cycle-m 14.63 --out-dir <out>

# 4) 對雷達評估
python3 tools/comma2k19_radar_export.py --zip ... --segment ... --out <out>/radar.csv
python3 tools/comma2k19_radar_eval.py --ranges <out>/ranges.csv --radar <out>/radar.csv ...
```

⚠ **距離要看 `ranges.csv` 的 `far_field` 欄**。遠場(靈敏度 > 0.8 m/px)的距離中位偏 20%、
最壞偏 72%;近場才是 7%。標註影片與 `targets_summary.csv` 已自動處理,逐幀檔靠這個旗標。

---

## 自我檢查:怎麼知道你跑對了

- **尺度標定**:車道寬解出的相機掛高應落在 **1.1–1.5 m**。算出 0.6 或 2.5 就是錯了,
  即使車道寬殘差看起來很緊。
- **距離修正係數**:逐對散布 > 0.10 就該拒發(工具會自己拒)。
- **重跑既有輸出**:同一個點雲 + 同一個 `hood-y`,平面擬合是**確定性的**——
  平面係數應該逐位元相同。不同就是參數對不上,
  可用 `tools/solve_archived_hood.py` 從 `tracks.json` 反解出實際用過的 `hood-y`。
- **換偵測器不該改變量測**:對雷達的受控比較顯示目標速度差 +0.03 km/h(區間含 0),
  85% 的幀接地點落在完全相同的像素列(`data/output/detector_vs_radar/README.md`)。

## 不能重現的部分

- **台灣鑑定案素材**(海盛案例包、20251029 批量):真實事故鑑定案,不隨 repo 分發。
  相關數字與方法都寫在各 `README.md` 裡,但影片本身要向原提供單位取得。
- **WoWtchout 公開影片**:YouTube 公開來源,可自行下載;報告引用須標出處、不可商用。
- **管線 A(固定式路口監視器)**:本計畫已停止投入(素材面原因:可用案件的交比目標全是機車,
  而本計畫收斂到汽車)。程式碼與既有成果保留,但不再更新。

## 已知失效邊界(不要當成 bug)

誠實標示失效是本計畫的要求之一,完整清單在 `CLAUDE.md`,最常遇到的三條:

1. **碼表取樣率下限**:每個虛線週期需 ≳8 幀,即 `fps ≳ 8 × v / cycle`。
   KITTI 的 10 Hz 在高速段只有 5 幀/週期,八度選擇會崩潰。公開資料集要用 ≥25 fps 來源。
2. **跨路類的影片**:單一週期常數在路類交界處會系統性倍速。事前依路類切分。
3. **擦身而過的側向目標**:接地點會沿車身遷移,只報距離、不要報速度。
