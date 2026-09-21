# Argoverse 2 外部驗證輸出(2026-09-21,Terry)

**方法、全部數據表與誠實界線在 `docs/TERRY_RESEARCH_RECORD.md` §4–§7。**
這裡只說明檔案是什麼;csv/json 不進版控(可由下方指令重建)。

| 檔名 | 內容 | 由誰產生 |
|---|---|---|
| `targets_<log>.csv` | 目標車像素:`py_max`(遮罩最低點=著地處)與 `py`(最低 12% 列中位=車身)。⚠ **不含任何真值** | `av2_targets.py` |
| `pred_<log>__<model>.csv` | 深度模型在 `py` 上的讀值(公尺)。餵**預設焦距**,不是原廠焦距 | `depth_model_benchmark.py run` |
| `seal.json` | 上列預測檔的 sha256 + 封存時間 + git commit,並記錄**封存當下真值檔不存在** | `seal_predictions.py` |
| `eval_<log>.json` / `_rows.csv` | 對光達 3D 框的評分;逐筆含 `gt_m`(最近框角前向距離)與 `method_c` | `av2_eval.py` |
| `av2_results.png` | 三面板圖:標線 A vs 原廠 A、預測 vs 真值、誤差對距離 | `report/plot_av2_eval.py` |

⚠ **真值 `annotations.feather` 位於 `data/input/av2/<log>/`,是評分時才下載的**;
要重跑盲測必須先把它刪掉,否則 `seal_predictions.py` 會拒絕封存。

⚠ 資料集為 **CC BY-NC-SA 4.0,不可商用**。

重建指令見 `docs/TERRY_RESEARCH_RECORD.md` §8。
