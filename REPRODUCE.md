# 重現指南

給拿到這個 repo、想自己把數字跑出來的人。
下面兩條路線(自車速/他車)都屬於**管線 B(行車紀錄器)**;管線 A 已停止投入,見「不能重現的部分」。

## 你有什麼、缺什麼

| | 在 repo 裡 | 怎麼補 |
|---|---|---|
| 程式碼 `tools/` | ✅ | — |
| 執行參數 | ✅ `docs/CASE_PARAMETERS.md` | — |
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

## 路線一:自車速 —— 最容易,不需要 SHARP,也不需要任何非公開素材

**這是本專案最紮實的一條鏈**,對兩台車 33 段 35,809 幀的公開資料集實測 MAE **2.18 km/h**
(對 GNSS/INS 位姿真值)。
之所以不需要 SHARP:自車速是用「法定虛線週期流過固定畫面列」的時間量的,
完全不經過點雲、平面或尺度。

```bash
# 1) 下載兩個 chunk(MIT 授權)。comma2k19 全資料集只有兩台車:
#    Chunk_1 = 車 1 b0c9d2(8.7 GB)、Chunk_3 = 車 2 99c94d(9.4 GB);再多抓 chunk 不會增加車輛數
#    (Chunk_2 屬車 1、Chunk_4–10 屬車 2;見 comma2k19_eval/README.md 4-2-1 的 dongle/chunk 表)
mkdir -p data/input/comma2k19
for c in 1 3; do
  curl -L -o data/input/comma2k19/Chunk_$c.zip \
    https://huggingface.co/datasets/commaai/comma2k19/resolve/main/raw_data/Chunk_$c.zip
done

# 2)–4) 對兩個 zip 各跑一次(工具一次只吃一個 --zip),輸出目錄分開;以下以 Chunk_1 為例,
#       Chunk_3 把 Chunk_1 / _c1 換成 Chunk_3 / _c3 即可

# 2) 先只掃真值、不解碼影格(快),看 segments.csv 挑段
python3 tools/comma2k19_prepare.py --zip data/input/comma2k19/Chunk_1.zip \
  --out-root /tmp/comma_scan_c1 --same-route --no-frames

# 3) 依「整段最低速 >= 60 km/h」選段(事前可宣告的規則,不看真值誤差)
#    預期挑出車 1 19 段、車 2 15 段
python3 tools/comma2k19_select.py --zip data/input/comma2k19/Chunk_1.zip --min-floor 60
python3 tools/comma2k19_prepare.py --zip data/input/comma2k19/Chunk_1.zip \
  --out-root /tmp/comma_seg_c1 --segments "<上一步印出的段落>"

# 4) 評估(自動挑取樣點,不需人工指定);--dump-dir 留下逐幀結果,合併兩車時要用
python3 tools/public_dataset_ego_eval.py --batch-root /tmp/comma_seg_c1 --fps 20.0 \
  --auto-points --road-top 0.48 --road-bottom 0.68 \
  --gt-file gt_both.csv --gt-column can_kmh --alt-column pose_kmh \
  --solve-cycle --dash-cycle-m 14.63 \
  --dump-dir /tmp/comma_dump_c1 --out-json /tmp/batch_c1.json
```

⚠ **`--dash-cycle-m 14.63` 是加州高速公路的規格(48 ft)**,不是通用常數。台灣國道實測是 10 m
(不是規範寫的 12 m)。換路網一定要先用 `--solve-cycle` 反推驗證——
虛線週期是「每條路的常數」,不是「每支影片的常數」。

**預期數字**(全表同一族群:上面的事前選段規則、cycle 14.63 m;
出處 `data/output/comma2k19_eval/README.md` 4-2-3):

⚠ 第 4 步印出的主欄 `mae_kmh` 是對 **CAN 車速**(`--gt-column can_kmh`);2.18 用的是
**GNSS/INS 位姿真值**;每個 zip 的輸出 json 裡,位姿那一欄在 `alt.mae_kmh`(車 1 為 1.98、車 2 為 4.23),
2.18 要把兩車逐幀檔合併才算得出(見表下說明)。兩台車的 CAN 相對位姿各有 0.69–1.09%
的乘性偏差、方向相反(該 README 4-2-5),所以兩欄會不同。

| 子集 | 對位姿(`alt.mae_kmh`) | 對 CAN(主欄) |
|---|---|---|
| 車 1(Chunk_1,19 段) | 1.98 | 2.80 |
| 車 2(Chunk_3,15 段全部) | 4.23 | 3.89 |
| 車 2 排除一段高速連接道(14 段) | 2.49 | 2.16 |
| **兩車合計 33 段(排除該段)** | **2.18**(±3 內 82.2%、覆蓋 90.4%) | 2.54 |
| 兩車合計 34 段(含該段) | 2.91 | 3.25 |

- 車 2 的 4.23 幾乎全由單一段 `99c94dc769b5d96e_2018-06-12--00-59-15_7` 造成(單段 MAE 40.44):
  它以 90–96 km/h 定速穿過週期約 10 m 的高速連接道,「最低速 ≥ 60」擋不住
  (見 `docs/FAILURE_BOUNDARIES.md`)。該段是事後單獨列出的,所以 33 段與 34 段兩個數字都要報。
- 合計是兩車逐幀結果合併(21,421 + 14,388 = 35,809 幀),單一 json 不會直接印出;
  要用 `--dump-dir` 留下的逐幀檔(含 CAN 與位姿真值)自己合併。
- 同一族群的日夜分層(車 1):日間 2.14、夜間 1.69。需另跑 `tools/comma2k19_domain_eval.py`
  (照度那一欄要讀影格)。
- ⚠ 舊版本表列過的「日間 1.78 / 夜間 4.72」屬於**另一族群**(Chunk_1 以中位速 ≥ 70 挑的 24 段、
  事後用位置排除幹道),是該 README 第二節的診斷分層,方向與上面相反,不要並列在同一張表。

---

## 路線二:他車距離與絕對速度 —— 需要 SHARP

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

誠實標示失效是本計畫的要求之一,完整清單在 `docs/FAILURE_BOUNDARIES.md`,最常遇到的三條:

1. **碼表取樣率下限**:每個虛線週期需 ≳8 幀,即 `fps ≳ 8 × v / cycle`。
   KITTI 的 10 Hz 在高速段只有 5 幀/週期,八度選擇會崩潰。公開資料集要用 ≥25 fps 來源。
2. **跨路類的影片**:單一週期常數在路類交界處會系統性倍速。事前依路類切分。
3. **擦身而過的側向目標**:接地點會沿車身遷移,只報距離、不要報速度。
