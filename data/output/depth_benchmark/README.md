# 深度模型 benchmark 輸出(計畫書階段一)

**方法、全部數字與重現指令在 `docs/DEPTH_MODEL_BENCHMARK.md`(19 節;§18 是 2026-09-17 的更正紀錄,§19 是 2026-09-19 依指導教授會議的修訂)。**
這裡只說明這個資料夾裡的檔案是什麼 —— csv/json 本身不進版控(可由下方指令重建)。

## 檔名規則

| 前綴 | 內容 | 由誰產生 |
|---|---|---|
| `targets_<seg>.csv` | (影格, 目標像素, 雷達距離);像素由 YOLO 接地點決定,雷達值不影響它 | `depth_benchmark_targets.py` |
| `paired_<seg>.csv` | 上者再過「幾何一致性對雷達」的篩選 ⚠ **這一步用了真值** | 同上 + robust fit |
| `roadanchor_<seg>.csv` | 沿車道線的路面像素 + 方法 C 距離(`d = A/(py − y_h)`),**不用雷達**。⚠ `marking_d_m` 欄是用**撤回的 A**(1153 / 1139)寫的,不要直接讀:分析工具一律由 `py` 重算,`blind` 子命令要加 `--geom` | 方法 C 幾何 |
| `body_<seg>.csv` | `paired_` 同一批車的**車身中心**像素(接地點不可用時的替代取樣點) | `body_centre_targets.py` |
| `pred_<seg>__<model>.csv` | 模型在 `paired_` 像素上的讀值(§12 的正式結果) | `depth_model_benchmark.py run` |
| `unf_<seg>__<model>.csv` | 同上但在**未過濾**的 `targets_` 上 | `run_blind_eval.sh` |
| `anchor_<seg>__<model>.csv` | 模型在路面錨點上的讀值 → 盲測的尺度常數來源(`marking_d_m` 欄同上,已過時) | `run_blind_eval.sh` |
| `contact_defs.csv` | 每個目標兩種接地點:`py_band`(本 benchmark 的取樣像素)與 `py_max`(管線 B 的遮罩最低點) | `contact_point_definitions.py` |
| `body_pred_<seg>__<model>.csv` | 模型在車身中心上的讀值(§14、§19.6) | `run_blind_eval.sh` |
| `fx<N>_<seg>__<model>.csv` | 改餵焦距 N px 的讀值(§17) | `run_fx_sweep.sh` |
| `smoke_*.json` | 各 backend 的載入/推論時間、峰值 VRAM、預測焦距 | `depth_model_benchmark.py smoke` |
| `radar_<seg>.csv` | 原廠雷達真值 | `comma2k19_radar_export.py` |

`<seg>` 是 comma2k19 的 `<route>_<segment>`,例如
`b0c9d2329ad1606b_2018-07-30--13-44-30_10`。

## 重建

```bash
P=~/venvs/depthbench/bin/python          # 環境見文件 §2.1
bash tools/run_blind_eval.sh             # 三趟模型推論(含車身中心),可續跑
bash tools/run_fx_sweep.sh               # 焦距掃描,可續跑
$P tools/contact_point_definitions.py --frames-root data/input/_frames_cache/c2k19 \
   --out data/output/depth_benchmark/contact_defs.csv
$P tools/depth_blind_analysis.py --all --delta-m 2.0   # 六個檢查:methodc / marking / sources / samerow / holdout / transfer
$P tools/depth_blind_analysis.py --all --delta-m 0     # Δ 未定案,兩組都跑
```

⚠ 影格在 `/tmp` 每個 session 結束就消失,腳本會改找
`data/input/_frames_cache/c2k19`(同樣不進版控,由 zip 重解)。
