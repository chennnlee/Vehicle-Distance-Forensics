# 報告與簡報產生器

成果報告書(docx)與簡報(pptx)都是**由程式產生**的,不是手改的檔案 —— 數字一改就重跑,
不必逐頁手動同步。這個資料夾放產生器本身。

**為什麼在版控裡**:這些程式原本住在 `~/tmp/report_build/` 與 `~/tmp/pptx_build/`,
不在版控內。2026-08-17 一次誤判(把兩個資料夾一起 `ls` 又被 `head` 截斷)讓人以為
`build_report.py` 已經隨目錄消失,而事實上「輸出還在、產生器不見了」這個情境是真的會發生的
——`~/tmp/pptx_build/assets` 裡的圖確實有一份是舊 scratchpad 產的、路徑已失效。
產生器是真正的資產,所以搬進來。

| 檔案 | 產出 |
|---|---|
| `build_report.py` | `data/output/report_draft/成果報告草稿_<日期>.docx`(A4、標楷體正文、微軟正黑體標題) |
| `gen.js` | 18 頁完整專案簡報(2026-07-12) |
| `gen_progress.js` | 進度報告簡報(2026-08-03,教授看過並給四點指示的那份) |
| `gen_progress2.js` | 進度報告簡報(2026-08-17,逐項答覆四點指示) |
| `prep_assets.sh` / `prep_assets2.sh` / `render_ply.py` | 從 `data/output/` 裁出簡報用圖與點雲渲染 |

## 跑法

```bash
# docx（只需要 python-docx）
python3 tools/report/build_report.py

# pptx（需要 pptxgenjs;node_modules 在 ~/tmp/pptx_build/,沒必要複製一份進版控）
NODE_PATH=~/tmp/pptx_build/node_modules node tools/report/gen_progress2.js
```

## 圖片素材

素材約 17 MB,**不進版控**——它們是從 `data/output/` 的渲染輸出與影格裁出來的衍生檔,
而 `data/output/` 本身就是 gitignored。預設放在 `~/tmp/pptx_build/assets/`,
可用環境變數覆寫:

```bash
REPORT_ASSETS=/path/to/assets python3 tools/report/build_report.py
```

2026-08-17 新增的四張圖(`fig_odo_fix.png`、`fig_position_step.png`、`fig_roadclass.jpg`、
`fig_xt_daynight.png`)由 comma2k19 的評估輸出產生,重跑方式見
`data/output/comma2k19_eval/README.md` 第六節與該次的 scratchpad 腳本。

## 檢查產出

本機沒有 LibreOffice 也沒有 CJK 字型,所以**無法把 pptx／docx 轉圖目視**。
替代做法是結構檢查:投影片檢查越界、圖片變形(放置比例 vs 檔案比例)與文字溢出;
2026-08-17 那次就靠它抓到兩張圖被拉扁(其中一張差 66%)與一行註腳掉出版面。
產出後請仍在 PowerPoint / Word 裡開一次確認觀感。

## 待補（使用者）

報告書封面留了佔位列:**申請人、系所／年級、指導教授、實際執行期間**。
另有參考文獻編號需與內文引用對齊後定稿。
