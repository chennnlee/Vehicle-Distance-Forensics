# Vehicle-Distance-Forensics 一頁式進度摘要

## 1. 專案目標
建立可重現的單目深度估測與比較流程，支援：
- Depth Anything V2
- UniDepth V2

並將結果輸出為：
- 深度可視化圖（PNG）
- 每張影像的深度統計（CSV）
- 雙模型比較摘要（TXT / Markdown）

## 2. 目前已完成項目
- 建立可維護的專案架構（core / utils / data / checkpoints / notebooks）
- 整合 Depth Anything V2 推論路徑
- 整合 UniDepth V2 推論路徑（可由參數切換）
- 支援單張與資料夾批次推論
- 支援 ROI 框選統計（median/mean/min/max）
- 支援尺度校正：
  - 固定尺度係數
  - Anchor-based 估計尺度係數
- 支援雙模型一鍵比較與合併 CSV
- 支援比較結果自動摘要報告（txt + md）
- 完成 README 操作文件與 GitHub 推送

## 3. 目前流程（已可運行）
1) 讀取影像（單張或資料夾）
2) 載入指定模型（DA2 / UD2）
3) 推論深度圖
4) 套用尺度校正（可選）
5) 計算中心點深度與 ROI 統計（可選）
6) 產生深度可視化圖
7) 匯出 CSV
8) 進行雙模型比較並輸出摘要報告

## 4. 核心檔案
- 主程式：main.py
- 模型比較入口：compare_models.py
- 比較摘要入口：summarize_compare.py
- 模型整合：core/depth_engine.py
- 尺度校正：core/calibration.py
- 幾何轉換：core/geometry.py
- 可視化：utils/visualizer.py
- 評估工具：utils/evaluation.py

## 5. 產出位置
- 一般推論輸出：data/output/
- 雙模型比較輸出：data/output/compare/
  - depth_stats_da2.csv
  - depth_stats_ud2.csv
  - merged_compare.csv
  - summary_report.txt
  - summary_report.md

## 6. 已知現況與限制
- 目前重點在深度估測與比較流程，尚未完成最終「車距公尺值」產品化介面
- 警告如 xFormers / KNN / EdgeGuidedLocalSSI 多為效能或評估相關，不阻斷推論
- 不同模型輸出尺度差異大，需靠校正策略統一量尺

## 7. 下一階段建議
- 加入目標偵測（車輛框）並自動提取 ROI
- 將 ROI 深度經校正後轉成可解釋距離指標
- 增加多圖批次比較報表（統計圖表）
- 補齊論文/報告用圖（流程圖、比較圖、誤差圖）

## 8. 快速執行指令
- 單模型推論（DA2）：
  python main.py --model depth_anything_v2 --img-path data/input/sample.jpg --out-path data/output/depth_vis_da2.png

- 單模型推論（UD2）：
  python main.py --model unidepth_v2 --img-path data/input/sample.jpg --out-path data/output/depth_vis_ud2.png

- 雙模型比較：
  python compare_models.py --img-path data/input --bbox 800,500,1200,900 --out-dir data/output/compare --merged-csv data/output/compare/merged_compare.csv

- 生成摘要報告：
  python summarize_compare.py --merged-csv data/output/compare/merged_compare.csv --report-path data/output/compare/summary_report.txt --markdown-path data/output/compare/summary_report.md
