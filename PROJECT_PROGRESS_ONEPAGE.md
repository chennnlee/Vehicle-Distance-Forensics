# Vehicle-Distance-Forensics 一頁式進度摘要

## 1. 專案目標
建立可重現的單鏡頭交通事故距離量測流程。現階段 demo 主軸調整為：
- SHARP 產生單張影像的 metric 3D Gaussian / 點雲
- YOLO 自動偵測車輛框
- 將 SHARP 點雲投影回原圖車輛區域
- 以地面平面約束與物理錨點尺度校正輸出車距統計

Depth Anything V2、UniDepth V2、Metric3D 仍保留作為 baseline 或後續比較組。

## 2. 目前已完成項目
- 建立可維護的專案架構（core / utils / data / checkpoints / notebooks）
- 整合 Depth Anything V2 推論路徑
- 整合 UniDepth V2 推論路徑（可由參數切換）
- 整合 Metric3D 推論路徑（可由參數切換）
- 支援單張與資料夾批次推論
- 支援 ROI 框選統計（median/mean/min/max）
- 支援尺度校正：
  - 固定尺度係數
  - Anchor-based 估計尺度係數
  - 參考物真值自動尺度校正
- 新增 SHARP PLY 點雲讀取與 BEV density map 視覺化
- 新增 SHARP + YOLO 車輛距離量測工具
- SHARP PLY loader 已可讀取 intrinsic / image_size 等 metadata
- 車距工具已支援 pointcloud scale、bbox 下半部取點、distance IQR 穩定性欄位

## 3. 目前流程（已可運行）

### SHARP demo 主流程
1) 讀取原圖與同名 SHARP `.ply`
2) 從 PLY 讀取點雲、相機內參與影像尺寸 metadata
3) YOLO 偵測車輛
4) 將點雲投影回原圖
5) 在車輛 bbox 下半部取點，並用地面平面過濾高度
6) 輸出每台車的 p10 / median / IQR 距離統計
7) 輸出 overlay、CSV、JSON summary

### baseline 深度流程
1) 讀取影像（單張或資料夾）
2) 載入指定模型（DA2 / UD2 / Metric3D）
3) 推論深度圖
4) 套用尺度校正（可選）
5) 計算中心點深度與 ROI 統計（可選）
6) 產生深度可視化圖
7) 匯出 CSV

## 4. 核心檔案
- 主程式：main.py
- 模型整合：core/depth_engine.py
- 尺度校正：core/calibration.py
- 可視化：utils/visualizer.py
- SHARP 車距 demo：tools/sharp_yolo_distance.py
- SHARP 點雲 BEV：tools/sharp_to_bev.py
- 點雲讀取：utils/pointcloud_io.py
- 重新提案：SHARP_DEMO_REPROPOSAL.md

## 5. 產出位置
- 輸出根目錄：data/output/
- 每次執行自動建立：data/output/runs/YYYYMMDD_HHMMSS/

## 6. 已知現況與限制
- SHARP 雖宣稱 metric scale，鑑識用途仍必須用標線、車牌或軸距做尺度校正與誤差驗證。
- YOLO bbox 內可能混入背景點，目前以 bbox 下半部、地面高度過濾、p10/IQR 緩解。
- BEV 現階段定位為視覺化與尺度檢查輔助，不作為第一版 demo 的核心承諾。
- BEVFormer / modern mmdetection3d 路線保留，但暫不列為 demo 第一優先。
- 真正的行車紀錄器相對運動補償尚未完成，需等單張/短序列車距 demo 穩定後再做。

## 7. 下一階段建議
- 先完成 3 到 5 張 SHARP + YOLO 車距 demo。
- 選一張含已知標線/車牌/軸距的影像，建立 `--pointcloud-scale` 校正前後比較。
- 加入 `quality_flag`，用 point_count、distance_iqr、ground inlier ratio、projection ratio 判定可信度。
- 將 SHARP 納入大專生計畫的模型比較組，與 Metric3D / UniDepth / Depth Anything 做同一批真值錨點評估。

## 8. 快速執行指令
- SHARP + YOLO 車距 demo：
  python tools/sharp_yolo_distance.py --image data/input/cctv_keyframes/043.jpg --pointcloud data/output/sharp_gaussians/043.ply --out-dir data/output/sharp_yolo_distance --yolo-model yolov8m.pt --ground-mode auto --bbox-vertical-slice 0.55

- SHARP 點雲轉 BEV 視覺化：
  python tools/sharp_to_bev.py --input data/output/sharp_gaussians --out-dir data/output/sharp_bev --reference-image data/input/cctv_keyframes

- 單模型推論（DA2）：
  python main.py --model depth_anything_v2 --img-path data/input/sample.jpg

- 單模型推論（UD2）：
  python main.py --model unidepth_v2 --img-path data/input/sample.jpg

- 單模型推論（Metric3D）：
  python main.py --model metric3d --img-path data/input/sample.jpg
