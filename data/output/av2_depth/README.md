# Argoverse 2 外部驗證輸出(2026-09-21,Terry)

**方法、全部數據表與誠實界線在 `docs/TERRY_RESEARCH_RECORD.md` §4–§7。**
這裡只說明檔案是什麼;csv/json 不進版控(可由下方指令重建)。

> ⚠ **2026-09-30 補註(舊方法/組員程式)**:`eval_<log>.json` / `_rows.csv` 的 `method_c` 欄位,以及 `av2_results.png`
> 的「標線 A vs 原廠 A」,都來自已刪除的 `tools/av2_marking_calib.py`(它呼叫組員的 `lane_line_fit.py` 與時間差程式),
> 屬於舊方法,不放進大專生計畫。c865c156、cf5aaa11、dc9077b9、f668074d 四支當初挑目標時也讀了這份 `calib.json` 的車道線;
> 這四支答案已開過的片已用完全不擬合車道線的方式重評(`av2_targets.py --no-lanes`,檔名 `nolane_*`),
> 結果不變(c865c156 × k 1.64%),見 `docs/TERRY_RESEARCH_RECORD.md` §11.4 的補註。

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
