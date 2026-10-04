# Repo 導覽:方法細節、工具與輸出

首頁 [README](../README.md) 是給第一次來的人看的摘要。這份文件列出技術細節:兩條量測管線怎麼運作、每支工具做什麼、輸出放在哪裡,以及其他文件各自的內容。

## 方法細節

**幾何骨架(兩條管線共用)**:挑一張參考幀跑 [SHARP](https://github.com/apple/ml-sharp) 得到點雲,用 RANSAC 擬合地面平面;之後每個像素都用「射線 × 平面求交 × 尺度」換成路面上的公尺座標。SHARP 只跑一次,不逐幀;它的逐像素深度不進入量測,只提供三個平面係數。SHARP 對沒有 EXIF 的影像假設固定視角,每台相機的尺度都不同,所以要用已知尺寸校正:

- **行車紀錄器**:用車道寬(取 3.5 m,`tools/dashcam_lane_width_calib.py`;這是設計值,不是法定值,見下方說明)、同機種的相機高度,或 GPS 校正。貼近地面的視角下,直接在 3D 點雲上量虛線長度並不可靠,所以不用這個方法。
- **路口監視器**:用台灣法定虛線(車道線為 4 m 線段加 6 m 間隔,依《道路交通標誌標線號誌設置規則》第 182 條;路口導引線 0.5 m / 0.5 m)。`tools/lane_dash_calibration.py` 自動找出虛線、量 3D 長度,並用線段與間隔的比例判斷是哪一種規格。

**行車紀錄器的前後方向距離還要再校正一次**:車道寬是左右方向的尺,管不到 SHARP 焦距假設造成的前後方向誤差(台灣五支示範影片距離偏長 11–32%,每台相機不同)。`tools/odometer_distance_calib.py` 用虛線流過不同畫面列的時間差,算出每台相機的修正係數,量測時以 `--distance-correction` 帶入;只縮前後方向,左右方向不動。各案係數見 [CASE_PARAMETERS.md](CASE_PARAMETERS.md),量法與證據見 [data/output/dashcam_demo/_calib/README.md](../data/output/dashcam_demo/_calib/README.md)。自車速不受影響,因為它不經過 SHARP。

**車道寬是設計範圍,不是固定的法定值**:交通部《公路路線設計規範》表 2.2.1 依設計速率訂每車道寬的範圍——80 km/h 以上 3.50–3.75 m、50–80 km/h 3.25–3.50 m、50 km/h 以下 3.00–3.50 m(市區或地形受限時還可再窄),實際寬度依路段而異;本專案取國道範圍的下限 3.5 m。影響範圍:有前向修正係數的影片,前後距離由虛線時間差決定,與車道寬無關(係數用同一個尺度求得,車道寬造成的比例差會互相抵消);受影響的是左右方向的位置,以及沒有修正係數的影片(dc003、dc007)的前後距離,實際車道寬若是 3.75 m,兩者都會偏小約 7%。相機高度的自洽檢查(1.1–1.5 m)分不出這個差異。

### 管線 B:行車紀錄器(現行主線)— `tools/dashcam_range_speed.py`

相機會移動,但在平路上,地面平面相對於相機不變。

- **自車速(虛線週期碼表)**:法定虛線流過畫面上固定的幾列,亮度隨之週期變化;用滑動自相關取週期,換算車速。不需要尺度、不受鏡頭畸變與車身震動影響。週期抓錯一倍的問題用三層機制處理(見 [ODOMETER_DESIGN.md](ODOMETER_DESIGN.md));讀不到時標示「沒有讀值」,最多內插 2 秒。畫面上燒錄的 GPS 車速可以拿來對照,但它本身也有 ±3 km/h 等級的誤差;有人工逐格真值時以人工為準(見 [data/output/dashcam_demo/README.md](../data/output/dashcam_demo/README.md))。
- **他車**:遮罩最低點(車輪碰地處)投到路面平面得到距離;絕對時速 = 自車速 + 距離變化率。遠距離(靈敏度 > 0.8 m/px,約 32 m 外)的距離偏差大,對原廠雷達中位偏約 20%:標註影片只寫 `far-range`、`targets_summary.csv` 把遠距離時速另立一欄、逐幀的 `ranges.csv` 有 `far_field` 欄。

### 管線 A:固定路口監視器(2026-09-16 起停止投入)— `tools/cctv_speed_estimation.py`

> 停止投入的原因:固定式監視器素材的畫質、幀率與拍攝距離條件不佳(路口串流實際約 1–2 fps、車輛多半離鏡頭很遠、部分素材是螢幕翻拍),不適合用來驗證汽車測速。程式與成果保留,不再更新。

畫面時鐘秒跳定時(錄影主機回報的 fps 不可信)→ YOLOv8-seg 接地點 → 平面座標 → 匈牙利法關聯(類別群組、方向閘、尺寸閘)→ 等速擬合並附 95% 信賴區間。防護包括淨位移門檻、遠距離不給數字、斷軌縫合(`merged_from` 可稽核)、同幀重複框抑制、平行鬼影抑制。標註影片會把校正用的標線畫在畫面上,讓比例尺的來源看得到。

## 工具

**管線 B(行車紀錄器)**

| 工具 | 用途 |
|---|---|
| `tools/dashcam_range_speed.py` | 行車紀錄器自車速、跟車距離、他車絕對時速 |
| `tools/selected_vehicle_speed.py` | 在一張畫面上框選一台車、輸入自車速,算出它的距離與時速;量不準時標白框或不回傳 |
| `tools/dashcam_lane_width_calib.py` | 車道寬尺度校正;反推相機高度當自洽檢查 |
| `tools/lane_line_fit.py` | 從多幀累積的亮線擬出左右車道線,印出 `--pairs` 與消失點(不靠目視挑點) |
| `tools/odometer_distance_calib.py` | 用碼表訊號算出每台相機的前後方向距離修正係數 |
| `tools/dashcam_distance_ruler.py` | 在路面畫公尺刻度,用肉眼檢查距離修正 |
| `tools/solve_archived_hood.py` | 從封存的 `tracks.json` 平面係數反解當次用的 `hood-y` |
| `tools/odometer_lag_audit.py` | 碼表週期選擇的觸發稽核(不跑 YOLO) |
| `tools/odometer_regression_cases.py` | 台灣 15 案碼表迴歸的案表 |
| `tools/plot_ego_vs_gps.py` | 自車速對 GPS 的驗證圖 |
| `tools/report/render_demo_video.py` | 從一次量測的 `tracks.json` 畫出首頁的中文示範影片(只畫圖,不重新量測) |
| `tools/report/render_selected_demo.py` | 畫出首頁「選一台車量時速」的中文示範圖(量測交給 `selected_vehicle_speed.py`) |

**公開資料集評估(comma2k19)**

| 工具 | 用途 |
|---|---|
| `tools/comma2k19_select.py` / `tools/comma2k19_prepare.py` | 事前選段(整段最低速 ≥ 60 km/h)/解壓、抽影格、產生 CAN 與位姿真值 CSV |
| `tools/public_dataset_ego_eval.py` / `tools/auto_odometer_points.py` | 碼表對資料集真值的批次評估/自動挑取樣點 |
| `tools/comma2k19_domain_eval.py` | 依道路種類與實測路面亮度分層重算(不重跑量測) |
| `tools/comma2k19_radar_export.py` / `tools/comma2k19_radar_eval.py` | 原廠雷達對齊到影格時間軸/他車距離與時速對雷達評估 |
| `tools/detector_radar_compare.py` | 兩個偵測器在同一量測流程、同一雷達真值上的受控比較 |

**兩條管線共用**

| 工具 | 用途 |
|---|---|
| `tools/lane_dash_calibration.py` | 地面平面 RANSAC 擬合;路口監視器的法定虛線尺度校正(規格識別、多條虛線互相驗證) |

**管線 A(已停止投入)**

| 工具 | 用途 |
|---|---|
| `tools/cctv_speed_estimation.py` | 路口監視器多目標測速與標註影片 |
| `tools/frame_timeline_export.py` | 逐幀時間軸稽核表(畫面時鐘秒跳) |
| `tools/fetch_tdx_cctv.py` | 抓取 TDX 即時監視器影像(憑證放在 `.env`) |

**2026-07 單幀原型(已由管線 B 取代)**

| 工具 | 用途 |
|---|---|
| `tools/sharp_yolo_distance.py` | 單幀 SHARP + YOLO 車輛距離量測(設計說明見 [archive/SHARP_DEMO_REPROPOSAL.md](archive/SHARP_DEMO_REPROPOSAL.md)) |
| `tools/detect_plate_anchor.py` / `tools/refine_anchor_point.py` | 車牌尺寸校正/亞像素錨點(現行流程未使用) |

深度模型比較與海盛人工真值比對的工具由 Terry 撰寫,說明見下方文件表。

## 輸出資料夾

正式輸出在 `data/output/`,每個資料夾都有 README。版控只收 README,csv、影片與圖不隨 repo 分發。

- 管線 B:`dashcam_demo/`(行車紀錄器示範)、`dashcam_validation/`(有人工真值的驗證案)、`odometer_lag_audit/`(碼表邏輯稽核)、`comma2k19_eval/`、`comma2k19_radar_eval/`、`detector_vs_radar/`。
  `dashcam_demo/*_current/` 是 2026-09-16 用現行程式重跑、已套距離修正係數的版本,不要再乘係數;其餘封存輸出的距離是修正前的數值。分層說明見 `dashcam_demo/README.md`,新舊對照見 `dashcam_demo/_rerun/README.md`。
- 管線 A(已停止投入):`report_final/`(路口監視器四台)、`cctv_validation/`(交比法對照)。
- 兩條管線共用:`model_comparison/`(2026-07-11 偵測器五模型比較;時速的結論已由 `detector_vs_radar/` 取代,見其檔首)。
- 首頁示範影片:`docs/media/`(來源為 comma2k19 公開資料集,產生方式見首頁)。

## 文件

| 文件 | 內容 |
|---|---|
| [REPRODUCE.md](../REPRODUCE.md) | 重跑步驟、預期數字、自我檢查 |
| [VALIDATION_STATUS.md](VALIDATION_STATUS.md) | 全部驗證的總表:每個數字用哪些資料、對照什麼真值;文末附前後方向距離修正的技術證據 |
| [FAILURE_BOUNDARIES.md](FAILURE_BOUNDARIES.md) | 已知會量不準的情況 |
| [ODOMETER_DESIGN.md](ODOMETER_DESIGN.md) | 虛線週期碼表的設計、已廢棄的機制與試過失敗的做法 |
| [METHODOLOGY_PITFALLS.md](METHODOLOGY_PITFALLS.md) | 方法上踩過的錯:怎麼發現、之後的規則 |
| [CASE_PARAMETERS.md](CASE_PARAMETERS.md) | 各案執行參數與距離修正係數 |
| [BACKLOG.md](BACKLOG.md) | 待辦清單,依負責人分節 |
| `data/output/**/README.md` | 各項成果的方法、數字與重跑指令 |
| [tools/report/README.md](../tools/report/README.md) | 報告與簡報產生器 |
| [PUBLIC_DATASET_BENCHMARK_PLAN.md](PUBLIC_DATASET_BENCHMARK_PLAN.md) | 2026-08 公開資料集驗證規劃;現況見檔首(歷史規劃) |
| [PLAN_20260819_MARKING_CALIBRATION.md](PLAN_20260819_MARKING_CALIBRATION.md) | 2026-08-19 標線標定規劃,已由 `tools/odometer_distance_calib.py` 取代 |
| [archive/](archive/) | 2026-07 單幀原型時期的進度摘要與設計說明(封存) |
| [DEPTH_MODEL_BENCHMARK.md](DEPTH_MODEL_BENCHMARK.md) | 以 comma2k19 原廠雷達為真值的單眼深度模型比較(Terry) |
| [haisheng_manual_eval/README.md](haisheng_manual_eval/README.md) | 自車速對海盛人工逐格真值(20251230 批)的比對(Terry) |

早期探索(BEVFormer/MonoLayout 的鳥瞰圖流程,以及當時一起放在 repo 裡的深度模型原始碼)已於 2026-07-18 移除,程式碼見 git 歷史(commit 842abaa)。
