# SHARP Demo 重新提案

## 1. 申請書核心目標重述

大專生計畫的主軸不是單純產生深度圖，而是建立一套可被交通事故鑑識檢驗的單鏡頭距離量測流程。關鍵要求有四個：

- 從 CCTV 或行車紀錄器單眼影像還原可量測的三維空間。
- 用車牌、道路標線、車型軸距、號誌尺寸等已知物理錨點做尺度校正。
- 量化誤差與失效邊界，而不是只輸出一個距離數字。
- 最終支援車輛位移與相對運動分析，供事故調查參考。

因此目前 demo 應收斂成：

> SHARP 產生單張影像的 metric 3DGS/點雲，YOLO 偵測車輛，將點雲投影回影像 bbox，估計車輛前緣距離，並輸出可審查的品質指標與尺度校正欄位。

## 2. 已發現的邏輯漏洞

### A. 尺度來源必須被明確標示

SHARP README 宣稱輸出具 absolute scale 的 metric representation，但交通鑑識不能只信模型聲明。demo 必須提供 `--pointcloud-scale` 讓使用者用已知標線或車牌做一次尺度校正，並在報表保留 scale factor。

修正：`tools/sharp_yolo_distance.py` 已加入 `--pointcloud-scale`，CSV/JSON 會記錄該值。

### B. PLY 內參不能用 FOV 猜測取代

SHARP PLY 會保存 `intrinsic` 與 `image_size`，原本 loader 只讀 vertex，導致投影點回原圖時只能靠 `--fov-deg` 猜焦距。這會讓 bbox 取點錯位，是 demo 被質疑的第一個風險。

修正：`utils/pointcloud_io.py` 現在會讀出 PLY metadata；`sharp_yolo_distance.py` 會優先用 PLY intrinsics，只有缺 metadata 才 fallback 到 `--fov-deg`。

### C. bbox 內點雲會混入背景

單純取整個 YOLO bbox 裡所有點，容易把車窗後方、車頂背景、遮擋物點一起算進距離。這會讓 median 偏遠，min 又容易被近距離雜訊污染。

修正：預設只取 bbox 下方 55% 的點，並輸出 `distance_p10_m`、`distance_p25_m`、`distance_median_m`、`distance_p75_m`、`distance_iqr_m`。建議 demo 主報 `distance_p10_m`，用 IQR 當穩定性檢查。

### D. BEV 不應被包裝成已完成鑑識解法

目前 repo 同時存在 Metric3D/BEVFormer/Monolayout/SHARP 路線，容易讓計畫顯得發散。下一階段應把 BEV 定位成「輔助視覺化與尺度校正驗證」，不是 demo 的核心成果。

修正策略：第一版 demo 以 SHARP + YOLO distance 為核心；BEV 只保留 `sharp_to_bev.py` 作為視覺輔助圖。

### E. 缺少失效判定

申請書要求誤差量化與失效邊界。demo 若只輸出距離，不輸出 projected point ratio、ground plane residual、point_count、IQR，會缺乏審查依據。

修正：summary 已有 ground plane residual/inlier ratio；本次新增 projected point ratio、distance IQR，並在 IQR 超過門檻時自動標記 `unstable_depth_iqr`。

## 3. 修正後 demo 流程

1. 輸入原始影像或影像資料夾。
2. 使用 SHARP 產生同名 `.ply`。
3. 讀取 PLY vertex、intrinsics、image_size。
4. YOLO 偵測車輛類別。
5. 以 PLY intrinsics 將 3DGS center 投影回原圖。
6. 在每個車輛 bbox 下半部收集點雲。
7. 自動擬合地面平面，過濾非車身高度點。
8. 輸出車輛距離統計、穩定性欄位、overlay。
9. 若有標線/車牌真值，使用 `--pointcloud-scale` 重跑，形成校正前後比較。

## 4. Demo 最小可交付版本

### 輸入

- 3 到 5 張道路/CCTV/行車紀錄器影像。
- 每張影像對應一個 SHARP `.ply`。
- 至少 1 張影像含有已知尺度錨點，例如 4 m 標線或車牌寬度。

### 輸出

- `sharp_yolo_distances.csv`
- `sharp_yolo_distance_summary.json`
- `overlays/*_sharp_yolo_distance.png`
- 可選：`sharp_to_bev.py` 產生的 BEV density map

### Demo 評估表

每張圖至少報告：

- 車輛偵測數量
- 有效投影點比例
- ground plane residual / inlier ratio
- 每台車的 p10 / median / IQR 距離
- 是否通過 `point_count` 與 IQR 門檻
- 若有真值，回報 absolute error 與 relative error

## 5. 下一步規劃

### 第 1 週：把 demo 跑通

- 準備 3 到 5 張樣本影像。
- 用 `sharp predict` 產生 `.ply`。
- 跑 `tools/sharp_yolo_distance.py`。
- 人工檢查 overlay：投影點是否落在車身附近。

### 第 2 週：補尺度校正

- 選一張含標線/車牌/已知軸距的樣本。
- 計算校正係數 `s = D_gt / D_est`。
- 用 `--pointcloud-scale s` 重跑。
- 產出校正前後比較表。

### 第 3 週：建立品質門檻

- 擴充目前 `status`：
  - `ok`
  - `few_points`
  - `unstable_depth_iqr`
  - `weak_ground_plane`
  - `low_projection_coverage`
- 寫一頁式 demo report，把成功案例與失敗案例都列出。

### 第 4 週：銜接申請書研究方法

- 將 SHARP 加入原本「現有度量深度模型誤差量化」的比較組。
- 保留 UniDepth/Metric3D/Depth Anything 作 baseline。
- 把 SHARP demo 定位成第一個可視化 prototype，不直接宣稱已完成行車紀錄器相對運動補償。

## 6. 目前建議指令

```bash
python tools/sharp_yolo_distance.py \
  --image data/input/cctv_keyframes/043.jpg \
  --pointcloud data/output/sharp_gaussians/043.ply \
  --out-dir data/output/sharp_yolo_distance \
  --yolo-model checkpoints/yolov8m.pt \
  --ground-mode auto \
  --bbox-vertical-slice 0.55
```

如果已用 4 m 標線得到尺度係數，例如 `s=1.18`：

```bash
python tools/sharp_yolo_distance.py \
  --image data/input/cctv_keyframes/043.jpg \
  --pointcloud data/output/sharp_gaussians/043.ply \
  --out-dir data/output/sharp_yolo_distance_scaled \
  --yolo-model checkpoints/yolov8m.pt \
  --ground-mode auto \
  --bbox-vertical-slice 0.55 \
  --pointcloud-scale 1.18
```

## 7. 重新提案一句話

本研究第一階段不再分散追求多種 BEV 架構，而是以 SHARP 的 metric 3D Gaussian 點雲作為單眼三維重建核心，結合 YOLO 目標偵測、地面平面約束與物理錨點尺度校正，建立可輸出距離、穩定性指標與校正前後誤差的交通事故影像量測 demo。
