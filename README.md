# Vehicle-Distance-Forensics

單眼深度估測與交通距離量測原型。此專案整合三個模型（Depth Anything V2、UniDepth V2、Metric3D），並提供：

- 單模型推論
- BEV (Bird's Eye View) 俯視映射
- 參考物自動尺度校正
- 三模型比較與合併報表
- 比較結果評分（準確性 / 一致性 / 穩定性）

## 1. 目前架構

- main.py
	- 單模型推論主入口
	- 輸出深度圖、BEV 圖、depth_stats.csv
- compare_models.py
	- 連續呼叫 main.py 跑 DA2 / UD2 / Metric3D
	- 合併成 merged_compare.csv
- score_compare.py
	- 讀 merged_compare.csv 產生模型評分 score_summary.csv
- core/depth_engine.py
	- 三模型統一載入與推論封裝
- core/calibration.py
	- 尺度校正（固定係數、anchor 係數）
- core/geometry.py
	- 深度圖 -> 點雲 -> BEV 映射
- utils/visualizer.py
	- 深度彩圖與 BEV 散點圖輸出

## 2. 環境安裝

建議使用同一個 Python 環境執行全部指令（避免 compare 中途因套件缺失失敗）。

~~~bash
cd Vehicle-Distance-Forensics
pip install -r requirements.txt
~~~

若你使用 conda，建議固定用同一個環境呼叫 python。

## 3. 權重準備

此 repo 不包含大型權重，請自行下載。

### 3.1 Depth Anything V2

- 權重 (vits):
	- https://huggingface.co/depth-anything/Depth-Anything-V2-Small/resolve/main/depth_anything_v2_vits.pth?download=true
- 放置路徑（二選一，建議第一個）:
	- checkpoints/depth_anything_v2_vits.pth
	- depth_models/Depth-Anything-V2/checkpoints/depth_anything_v2_vits.pth

### 3.2 UniDepth V2

- 可讓程式首次執行自動從 Hugging Face 下載（需連網）
- 或手動放到 checkpoints/unidepth_v2_vits14.pth

### 3.3 Metric3D

- 目前專案內已整合推論路徑，請確認模型權重路徑可被讀取

## 4. 輸入與輸出目錄

- 輸入影像: data/input/
- 輸出根目錄: data/output/
- 每次執行自動建立: data/output/runs/YYYYMMDD_HHMMSS/
- 最新 run 指標: data/output/latest_run.txt

## 5. 單模型推論 (main.py)

### 5.1 最短指令

~~~bash
python main.py
~~~

預設為 Depth Anything V2，輸入 data/input/sample.jpg。

### 5.2 指定模型

~~~bash
# Depth Anything V2
python main.py --model depth_anything_v2 --encoder vits --img-path data/input/sample.jpg

# UniDepth V2
python main.py --model unidepth_v2 --unidepth-backbone vits14 --img-path data/input/sample.jpg

# Metric3D
python main.py --model metric3d --metric3d-variant vit_large --img-path data/input/sample.jpg
~~~

### 5.3 BBox + 自動尺度校正

若你有參考物真值距離，可啟用：

~~~bash
python main.py \
	--model depth_anything_v2 \
	--img-path data/input/sample.jpg \
	--bbox 800,500,1200,900 \
	--auto-scale-gt 10.0
~~~

邏輯：

- 在 bbox 區域取估測距離 Dest (中位數)
- 用 Dgt / Dest 算出尺度係數 s
- 對整張深度圖套用 s

### 5.4 單模型輸出內容

在該 run 目錄下產生：

- depth_vis.png
- bev.png
- depth_stats.csv

depth_stats.csv 主要欄位：

- center_depth
- roi_median / roi_mean / roi_min / roi_max
- auto_scale_gt / auto_scale_est_raw / auto_scale_enabled
- bev_center_distance_m / bev_roi_median_distance_m
- output / bev_output

## 6. 三模型比較 (compare_models.py)

### 6.1 基本比較

~~~bash
python compare_models.py --img-path data/input
~~~

### 6.2 含 BBox 與自動尺度校正

~~~bash
python compare_models.py \
	--img-path data/input \
	--bbox 800,500,1200,900 \
	--auto-scale-gt 10.0
~~~

### 6.3 比較輸出內容

在該 run 的 compare/ 目錄下產生：

- depth_stats_da2.csv
- depth_stats_ud2.csv
- depth_stats_metric3d.csv
- merged_compare.csv
- da2/*.png
- ud2/*.png
- metric3d/*.png

merged_compare.csv 主要欄位：

- 三模型深度: da_center_depth / ud_center_depth / m3_center_depth
- 三模型 ROI: da_roi_median / ud_roi_median / m3_roi_median
- 三模型 BEV: da_bev_center_distance_m / ud_bev_center_distance_m / m3_bev_center_distance_m
- 模型差值: da_ud_abs_diff / da_m3_abs_diff / ud_m3_abs_diff
- BEV 差值: da_ud_bev_abs_diff / da_m3_bev_abs_diff / ud_m3_bev_abs_diff

## 7. 比較評分 (score_compare.py)

此腳本會對 merged_compare.csv 打分：

- accuracy_score_100
- consistency_score_100
- stability_score_100
- overall_score_100

範例：

~~~bash
python score_compare.py --gt-distance 10 --prefer-bev-roi
~~~

輸出：

- compare/score_summary.csv

說明：

- 若 bev_roi 欄位為 NaN，腳本會自動 fallback 到 bev_center，再到 roi_median / center_depth。
- 當資料只有 1 張影像時，stability 分數僅供參考。

## 8. 建議完整流程

~~~bash
# 1) 先做三模型比較（可加 bbox 與 auto-scale）
python compare_models.py --img-path data/input --bbox 800,500,1200,900 --auto-scale-gt 10.0

# 2) 再產生評分
python score_compare.py --gt-distance 10 --prefer-bev-roi
~~~

## 9. 常見問題

### 9.1 為什麼 compare 資料夾沒出來？

- 若你跑的是 main.py，不會有 compare/，只會有單模型輸出。
- compare/ 只會在 compare_models.py 執行成功時建立完整內容。

### 9.2 compare 跑到一半失敗（如缺 timm）

- 常見原因是混用不同 python 環境。
- 請固定使用同一個可跑三模型的環境執行 compare。

### 9.3 ROI 欄位為 NaN

- 代表這次沒帶 --bbox，屬正常行為。

### 9.4 auto_scale_enabled 為 0

- 代表這次未啟用 --auto-scale-gt（或未提供 bbox）。

## 10. 已知非致命警告

- xFormers not available: 可跑，但可能較慢
- UniDepth KNN / EdgeGuidedLocalSSI 警告: 多為評估或效能優化相關，不一定阻斷推論
