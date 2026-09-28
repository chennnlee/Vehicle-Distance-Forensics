# Vehicle-Distance-Forensics

交通事故影像鑑識:從**監視器(CCTV)與行車紀錄器**影片量測車輛**速度與距離**。
大專生研究計畫;主要目標為汽車測速(含對方車/他車),誠實標示量測失效邊界。
**現行主線是管線 B(行車紀錄器)**;管線 A(固定路口 CCTV)自 2026-09-16 起停止投入,程式與成果保留。

**要自己把數字跑出來 → [REPRODUCE.md](REPRODUCE.md)**(含一條只用公開資料集、
不需要點雲重建的完整路徑,以及各項成果的預期數字)。

## 方法總覽

**幾何骨架(兩管線共用)**:挑一張參考幀跑 [SHARP](https://github.com/apple/ml-sharp) 得點雲
→ RANSAC 擬合地面平面 → 之後所有像素用「射線 × 平面求交 × scale」轉成路面公尺座標。
SHARP 只跑一次,不逐幀。SHARP 為固定 FOV 假設,每台裝置 scale 不同,**必須用法定尺寸錨校正**:

- **行車紀錄器**(貼地視角,虛線 3D 取樣失效):改用車道寬(國道 3.5m,`tools/dashcam_lane_width_calib.py`)、
  相機高度轉移或 GPS。
- **CCTV**(管線 A):台灣法定虛線(車道線 4m/6m、高速公路 4m/8m、路口導引線 0.5m/0.5m),
  `tools/lane_dash_calibration.py` 自動偵測虛線鏈、量 3D 長度、以 gap/dash 比免尺度識別規格。

⚠ **行車紀錄器的前向距離還要再修一次**:車道寬錨是橫向量的,管不到 SHARP 固定焦距假設
造成的前向誤差——距離偏高 11–32%,逐機不同。用碼表訊號自己校出修正係數
(`tools/odometer_distance_calib.py`),量測時帶 `--distance-correction`;只縮前向、不動橫向。
各案係數見 [docs/CASE_PARAMETERS.md](docs/CASE_PARAMETERS.md),量法與證據見
[data/output/dashcam_demo/_calib/README.md](data/output/dashcam_demo/_calib/README.md)。
自車速不受影響(碼表不經過 SHARP)。

### 管線 B:行車紀錄器測速測距 — `tools/dashcam_range_speed.py`

移動相機,但平路上地面平面「相對相機」不變。
- **自車速 = 虛線週期碼表**:法定虛線週期流過固定畫面列,滑動自相關取週期,
  免 scale、免畸變、免震動。多道防護鏈(假鎖/八度/換道/分裂鎖),無讀值誠實標 no lock。
  畫面 GPS OSD 是非循環的對照,但**不是金標準**(對照對象本身有 ±3 km/h 級不確定度,且逐機種不同);
  有人工畫格法真值時以人工為準(見 [data/output/dashcam_demo/README.md](data/output/dashcam_demo/README.md))。
- **他車**:接地點 → 平面 → 跟車距離;絕對速 = 自車速 + d(距離)/dt。
  遠場(靈敏度 > 0.8 m/px)距離偏差大(對原廠雷達中位偏 20%):標注影片只標 `far-range`、
  `targets_summary.csv` 把遠場速度另立一欄、逐幀的 `ranges.csv` 以 `far_field` 欄標示。

### 管線 A:固定 CCTV 測速 — `tools/cctv_speed_estimation.py`

> ⚠ **2026-09-16 起停止投入,程式與成果保留**:可用案件的交比目標全是機車,而本計畫收斂到汽車。
> 以下為既有方法說明,不再更新。

OSD 時鐘秒跳定時(NVR 串流謊報 fps)→ YOLOv8-seg 接地點 → 平面座標 →
匈牙利關聯(類別群組+方向閘+尺寸閘)→ 等速擬合 ±95%CI。
品質防護:淨位移門檻、遠場拒發(靈敏度 m/px 門檻)、斷軌縫合(`merged_from` 稽核)、
同幀重複框抑制、平行鬼影抑制。輸出標注影片(校正線上屏=尺的出處可見)。

## 驗證摘要

| 量什麼 | 對照真值 | 結果 | 詳見 |
|---|---|---|---|
| 自車速(公開資料集) | comma2k19 GNSS/INS 位姿;兩台車 33 段 35,809 幀 | MAE **2.18 km/h**(±3 內 82.2%) | [comma2k19_eval](data/output/comma2k19_eval/README.md) 4-2-3 |
| 自車速(台灣國道) | hs005 海盛人工畫格法,同窗 12 段 | MAE **0.69 km/h**、bias +0.01、12/12 在 ±3 內 | [hs005](data/output/dashcam_demo/hs005/README.md) |
| 他車距離與絕對速度 | comma2k19 原廠雷達,3 段 908 配對幀 | 近場(≲32 m):距離誤差中位 **7.0%**、目標絕對速 MAE **3.54 km/h**;遠場 20.5% / 6.53 | [comma2k19_radar_eval](data/output/comma2k19_radar_eval/README.md) 第四節 |
| 前向距離修正係數 | 碼表跨列法自校;量法另對雷達驗證,一致到 1.6–3.6% | 7 支 demo 中 5 支通過(0.760–0.903);dc003/dc007 拒發、維持未校正 | [_calib](data/output/dashcam_demo/_calib/README.md)、[雷達第五節](data/output/comma2k19_radar_eval/README.md) |
| 偵測器影響 | 同一組雷達真值的受控比較(`yolov8m-seg` vs `yolo11x-seg`,547 共同幀) | 目標速度配對差 +0.03 km/h(CI 含 0);近場距離誤差 7.49% → 5.77%(近場實質上只有一台車) | [detector_vs_radar](data/output/detector_vs_radar/README.md) |

- 2.18 排除了車 2 一段高速連接道(含該段的 34 段為 2.91,兩個數字都列在該 README)。
- 雷達驗證的是**量法**,不是台灣五支 demo 的係數本身(該台相機需要的修正接近 1.0)。
- 重跑步驟與各項預期數字見 [REPRODUCE.md](REPRODUCE.md);全部驗證(含各案、失敗與已撤回的數字)的總表見 [docs/VALIDATION_STATUS.md](docs/VALIDATION_STATUS.md)。

## 主要工具

**管線 B(行車紀錄器)**

| 工具 | 用途 |
|---|---|
| `tools/dashcam_range_speed.py` | 管線 B:行車紀錄器自車速/跟車距離/他車絕對速 |
| `tools/dashcam_lane_width_calib.py` | 車道寬尺度錨;反推相機掛高當自洽檢查 |
| `tools/lane_line_fit.py` | 從多幀累積脊線擬出左右車道線,印出 `--pairs` 與消失點(不靠目視挑點) |
| `tools/odometer_distance_calib.py` | 用碼表訊號校出逐機前向距離修正係數(`--distance-correction`) |
| `tools/dashcam_distance_ruler.py` | 在路面畫公尺刻度,用肉眼驗證距離修正 |
| `tools/solve_archived_hood.py` | 由封存 `tracks.json` 的平面係數反解當次用的 `hood-y` |
| `tools/odometer_lag_audit.py` | 碼表 lag 修正觸發稽核(不跑 YOLO) |
| `tools/odometer_regression_cases.py` | 台灣 15 案碼表迴歸的案表 |
| `tools/plot_ego_vs_gps.py` | 自車速 vs GPS 驗證圖 |

**公開資料集評估(comma2k19)**

| 工具 | 用途 |
|---|---|
| `tools/comma2k19_select.py` / `tools/comma2k19_prepare.py` | 事前選段(整段最低速 ≥ 60 km/h)/解壓、抽影格、產生 CAN 與位姿真值 CSV |
| `tools/public_dataset_ego_eval.py` / `tools/auto_odometer_points.py` | 碼表對資料集自帶真值的批次評估/自動挑取樣點 |
| `tools/comma2k19_domain_eval.py` | 依路類與實測路面照度分層重算(不重跑量測) |
| `tools/comma2k19_radar_export.py` / `tools/comma2k19_radar_eval.py` | 原廠雷達對齊到影格時間軸/他車距離與速度對雷達評估 |
| `tools/detector_radar_compare.py` | 兩個偵測器在同一量測鏈、同一雷達真值上的受控比較 |

**兩管線共用**

| 工具 | 用途 |
|---|---|
| `tools/lane_dash_calibration.py` | 地面平面 RANSAC 擬合(兩管線共用);CCTV 法定虛線尺度錨(規格識別+多鏈互驗) |

**管線 A(2026-09-16 起停止投入)**

| 工具 | 用途 |
|---|---|
| `tools/cctv_speed_estimation.py` | 管線 A:CCTV 多目標測速+標注影片 |
| `tools/frame_timeline_export.py` | 逐幀時間軸稽核表(OSD 秒跳) |
| `tools/fetch_tdx_cctv.py` | 抓取 TDX 即時 CCTV(憑證在 `.env`) |

**2026-07 單幀原型(已由管線 B 取代)**

| 工具 | 用途 |
|---|---|
| `tools/sharp_yolo_distance.py` | 單幀 SHARP+YOLO 車輛距離量測(設計說明見 [docs/archive/SHARP_DEMO_REPROPOSAL.md](docs/archive/SHARP_DEMO_REPROPOSAL.md)) |
| `tools/detect_plate_anchor.py` / `tools/refine_anchor_point.py` | 車牌尺寸錨/亞像素錨點(現行管線未使用) |

深度模型 benchmark 與海盛人工真值比對的工具由同學 Terry 的文件說明,見下方「文件地圖」。

## 輸出資料夾

正式輸出在 `data/output/`(每資料夾有 README;版控只含 README,csv/影片/圖不隨 repo 分發):
- 管線 B:`dashcam_demo/`(行車紀錄器 demo,含白天多車三支與 hs005/wow001)、`dashcam_validation/`
  (含 GT 對照的驗證案,20251029 批量 28 段 MAE 1.93 km/h、可信真值 23 段 1.37)、
  `odometer_lag_audit/`(碼表邏輯稽核)、`comma2k19_eval/`、`comma2k19_radar_eval/`、
  `detector_vs_radar/`。
  ⚠ `dashcam_demo/*_current/` 是 2026-09-16 用現行程式碼重跑、**已套距離修正係數**的版本(不要再乘);
  `dashcam_demo/` 其餘封存輸出(基底與 `*_trackv3/`)的距離是修正前數值;dc003/dc007 係數維持 1.0,
  連 `_current/` 也未經縱向校正。分層說明見 `dashcam_demo/README.md`,新舊對照見 `dashcam_demo/_rerun/README.md`。
- 管線 A(已停止投入):`report_final/`(CCTV 四台)、`cctv_validation/`(交比法對照 +0.5%)。
- 兩管線共用:`model_comparison/`(偵測器五模型比較,2026-07-11;速度結論的依據已由 `detector_vs_radar/` 取代,見其檔首)。

詳細執行參數見 `docs/CASE_PARAMETERS.md`,失效邊界見 `docs/FAILURE_BOUNDARIES.md`。

## 文件地圖

| 文件 | 內容 | 狀態 |
|---|---|---|
| [REPRODUCE.md](REPRODUCE.md) | 重跑步驟、預期數字、自我檢查 | 現行 |
| [docs/CASE_PARAMETERS.md](docs/CASE_PARAMETERS.md) | 各案執行參數與距離修正係數 | 現行 |
| [docs/FAILURE_BOUNDARIES.md](docs/FAILURE_BOUNDARIES.md) | 已知失效邊界 | 現行 |
| [docs/VALIDATION_STATUS.md](docs/VALIDATION_STATUS.md) | 全部驗證的總表:真值層級、每個數字的族群與出處;文末附前向距離修正的技術證據 | 現行 |
| [docs/ODOMETER_DESIGN.md](docs/ODOMETER_DESIGN.md) | 虛線週期碼表的設計、已廢棄的機制與試過失敗的做法 | 現行 |
| [docs/METHODOLOGY_PITFALLS.md](docs/METHODOLOGY_PITFALLS.md) | 方法論上踩過的錯:怎麼發現、以後的規則 | 現行 |
| [docs/BACKLOG.md](docs/BACKLOG.md) | 單一待辦清單,依負責人分節(含同學 Terry 的部分) | 現行 |
| `data/output/**/README.md` | 各項成果的方法、數字與重跑指令(入口見上方「驗證摘要」「輸出資料夾」) | 現行 |
| [tools/report/README.md](tools/report/README.md) | 報告與簡報產生器 | 現行 |
| [docs/PUBLIC_DATASET_BENCHMARK_PLAN.md](docs/PUBLIC_DATASET_BENCHMARK_PLAN.md) | 2026-08 公開資料集驗證計畫(回應教授四點指示);現況見檔首 | 歷史規劃 |
| [docs/PLAN_20260819_MARKING_CALIBRATION.md](docs/PLAN_20260819_MARKING_CALIBRATION.md) | 2026-08-19 標線標定規劃;方向結論已被推翻,工作項已由 `tools/odometer_distance_calib.py` 取代 | 已取代 |
| [docs/archive/PROJECT_PROGRESS_ONEPAGE.md](docs/archive/PROJECT_PROGRESS_ONEPAGE.md) | 2026-07 初,單幀 SHARP+YOLO demo 時期的一頁式進度摘要 | 封存 |
| [docs/archive/SHARP_DEMO_REPROPOSAL.md](docs/archive/SHARP_DEMO_REPROPOSAL.md) | 同期的 bbox 點雲距離方案(`tools/sharp_yolo_distance.py` 的設計說明) | 封存 |
| [docs/DEPTH_MODEL_BENCHMARK.md](docs/DEPTH_MODEL_BENCHMARK.md) | 以 comma2k19 原廠雷達為真值的單眼深度模型 benchmark(計畫書階段一);輸出說明在 `data/output/depth_benchmark/README.md` | 同學 Terry |
| [docs/haisheng_manual_eval/README.md](docs/haisheng_manual_eval/README.md) | 自車速對海盛人工畫格法真值(20251230 批)的比對 | 同學 Terry |

> 早期探索(BEVFormer/MonoLayout 的 BEV 管線、當時隨 repo 附帶的 Depth-Anything/UniDepth/Metric3D
> 原始碼與 `core/depth_engine.py`)已於 2026-07-18 移除(commit 842abaa),程式碼見 git 歷史。
> 2026-09 另有同學 Terry 以 comma2k19 原廠雷達真值做的單眼深度模型 benchmark,
> 見 [docs/DEPTH_MODEL_BENCHMARK.md](docs/DEPTH_MODEL_BENCHMARK.md)。
