# Vehicle-Distance-Forensics

交通事故影像鑑識:從**監視器(CCTV)與行車紀錄器**影片量測車輛**速度與距離**。
大專生研究計畫;主要目標為汽車測速(含對方車/他車),誠實標示量測失效邊界。

**要自己把數字跑出來 → [REPRODUCE.md](REPRODUCE.md)**(含一條只用公開資料集、
不需要點雲重建的完整路徑,以及各項成果的預期數字)。

## 方法總覽

**幾何骨架(兩管線共用)**:挑一張參考幀跑 [SHARP](https://github.com/apple/ml-sharp) 得點雲
→ RANSAC 擬合地面平面 → 之後所有像素用「射線 × 平面求交 × scale」轉成路面公尺座標。
SHARP 只跑一次,不逐幀。SHARP 為固定 FOV 假設,每台裝置 scale 不同,**必須用法定尺寸錨校正**:

- **CCTV**:台灣法定虛線(車道線 4m/6m、高速公路 4m/8m、路口導引線 0.5m/0.5m),
  `tools/lane_dash_calibration.py` 自動偵測虛線鏈、量 3D 長度、以 gap/dash 比免尺度識別規格。
- **行車紀錄器**(貼地視角,虛線 3D 取樣失效):改用車道寬(國道 3.5m)、相機高度轉移或 GPS。

### 管線 A:固定 CCTV 測速 — `tools/cctv_speed_estimation.py`

OSD 時鐘秒跳定時(NVR 串流謊報 fps)→ YOLOv8-seg 接地點 → 平面座標 →
匈牙利關聯(類別群組+方向閘+尺寸閘)→ 等速擬合 ±95%CI。
品質防護:淨位移門檻、遠場拒發(靈敏度 m/px 門檻)、斷軌縫合(`merged_from` 稽核)、
同幀重複框抑制、平行鬼影抑制。輸出標注影片(校正線上屏=尺的出處可見)。

### 管線 B:行車紀錄器測速測距 — `tools/dashcam_range_speed.py`

移動相機,但平路上地面平面「相對相機」不變。
- **自車速 = 虛線週期碼表**:法定虛線週期流過固定畫面列,滑動自相關取週期,
  免 scale、免畸變、免震動;GPS OSD 為非循環真值。多道防護鏈(假鎖/八度/換道/分裂鎖),
  無讀值誠實標 no lock。
- **他車**:接地點 → 平面 → 跟車距離;絕對速 = 自車速 + d(距離)/dt;
  遠場只給距離不給速度。輸出 `targets_summary.csv`(近場可信速度與遠場粗估分欄)。

## 主要工具

| 工具 | 用途 |
|---|---|
| `tools/cctv_speed_estimation.py` | 管線 A:CCTV 多目標測速+標注影片 |
| `tools/dashcam_range_speed.py` | 管線 B:行車紀錄器自車速/跟車距離/他車絕對速 |
| `tools/lane_dash_calibration.py` | 法定虛線尺度錨(規格識別+多鏈互驗) |
| `tools/odometer_lag_audit.py` | 碼表 lag 修正觸發稽核(不跑 YOLO) |
| `tools/sharp_yolo_distance.py` | 單幀 SHARP+YOLO 車輛距離量測 |
| `tools/detect_plate_anchor.py` / `tools/refine_anchor_point.py` | 車牌尺寸錨/亞像素錨點 |
| `tools/frame_timeline_export.py` | 逐幀時間軸稽核表(OSD 秒跳) |
| `tools/plot_ego_vs_gps.py` | 自車速 vs GPS 驗證圖 |
| `tools/fetch_tdx_cctv.py` | 抓取 TDX 即時 CCTV(憑證在 `.env`) |

## 成果與驗證

正式輸出在 `data/output/`(每資料夾有 README):`report_final/`(CCTV 四台)、
`dashcam_demo/`(行車紀錄器 demo,含白天多車三支)、`dashcam_validation/`
(含 GT 對照的驗證案,20251029 批量 28 段 MAE 1.93 km/h、可信真值 23 段 1.37)、
`cctv_validation/`(交比法對照 +0.5%)、`odometer_lag_audit/`(碼表邏輯稽核)。
詳細執行參數見 `docs/CASE_PARAMETERS.md`,失效邊界見 `docs/FAILURE_BOUNDARIES.md`。

> 早期探索(單眼深度估測 BEV:Depth-Anything/UniDepth/Metric3D/BEVFormer/MonoLayout)
> 已於 2026-07 移除,程式碼見 git 歷史。
