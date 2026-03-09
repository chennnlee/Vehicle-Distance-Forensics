# Vehicle-Distance-Forensics

整合單目深度推論流程（目前可切換 `Depth Anything V2` 與 `UniDepth V2`）。

## 1) 環境安裝

```bash
cd Vehicle-Distance-Forensics
pip install -r requirements.txt
```

## 2) 權重準備（必要）

> 本 repo 不含大型權重檔（避免 GitHub 大檔限制），請自行下載到指定路徑。

### Depth Anything V2 (vits)

下載：
- https://huggingface.co/depth-anything/Depth-Anything-V2-Small/resolve/main/depth_anything_v2_vits.pth?download=true

放置到其中一個路徑（建議第一個）：
- `checkpoints/depth_anything_v2_vits.pth`
- `depth_models/Depth-Anything-V2/checkpoints/depth_anything_v2_vits.pth`

### UniDepth V2

可二選一：
- 直接讓程式首次執行時自動從 Hugging Face 下載（需可連網）
- 或手動放本地權重到 `checkpoints/unidepth_v2_vits14.pth`

## 3) 輸入 / 輸出資料夾

- 輸入：`data/input/`
- 輸出：`data/output/`
- 每次執行會自動建立：`data/output/runs/YYYYMMDD_HHMMSS/`
- 最新 run 指標：`data/output/latest_run.txt`
- 根目錄保留最新摘要：`data/output/summary_latest.txt`、`data/output/summary_latest.md`

範例測試圖：`data/input/sample.jpg`

## 4) 執行推論

### A. Depth Anything V2

```bash
python main.py --model depth_anything_v2 --encoder vits --img-path data/input/sample.jpg --out-path data/output/depth_vis_da2.png
```

### B. UniDepth V2

```bash
python main.py --model unidepth_v2 --unidepth-backbone vits14 --img-path data/input/sample.jpg --out-path data/output/depth_vis_ud2.png
```

## 5) 最短指令

- Depth Anything 預設：
```bash
python main.py
```

- UniDepth：
```bash
python main.py --model unidepth_v2
```

> `main.py` 若不指定 `--out-path`、`--csv-path`，會自動寫到本次 run 資料夾。

## 6) 已知提示（非致命）

- `xFormers not available`：可跑，但可能較慢
- `EdgeGuidedLocalSSI ... slowdown`：UniDepth 可跑，但未編譯加速算子時較慢
- `KNN ... compile.sh`：主要影響評估，不影響一般推論

## 7) 雙模型比較與報告輸出

### A. 一鍵跑 DA2 + UD2 並合併 CSV

```bash
python compare_models.py --img-path data/input --bbox 800,500,1200,900 --out-dir data/output/compare --merged-csv data/output/compare/merged_compare.csv
```

會產生：
- `data/output/compare/depth_stats_da2.csv`
- `data/output/compare/depth_stats_ud2.csv`
- `data/output/compare/merged_compare.csv`
- `data/output/compare/da2/*.png`
- `data/output/compare/ud2/*.png`

### B. 產生摘要報告（txt + markdown）

```bash
python summarize_compare.py --merged-csv data/output/compare/merged_compare.csv --report-path data/output/compare/summary_report.txt --markdown-path data/output/compare/summary_report.md
```

會產生：
- `data/output/compare/summary_report.txt`
- `data/output/compare/summary_report.md`
