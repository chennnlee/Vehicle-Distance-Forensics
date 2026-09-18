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
| `build_report.py` | `data/output/report_draft/成果報告草稿_<日期>.docx`(A4、標楷體正文、微軟正黑體標題);現行輸出 `成果報告草稿_20260916b.docx`(13 表 17 圖) |
| `gen.js` | ⚠ **歷史快照,不要重跑後對外使用**(含循環的 0.4 km/h,見表下說明)。18 頁完整專案簡報(2026-07-12) |
| `gen_progress.js` | ⚠ **歷史快照,不要重跑後對外使用**(含循環的 0.4 km/h);**圖檔已消失,無法重跑**(圖路徑指向已消失的 scratchpad,輸出 `專題進度報告_20260803.pptx` 仍在)。進度報告簡報(2026-08-03,教授看過並給四點指示的那份) |
| `gen_progress2.js` | ⚠ **歷史快照,不要重跑後對外使用**(含循環的 0.4 km/h、BrnoCompSpeed 待辦)。進度報告簡報(2026-08-17,逐項答覆四點指示) |
| `gen_progress3.js` | ⚠ **歷史快照,不要重跑後對外使用**(含循環的 0.4 km/h、09-16 前的舊係數 0.831/0.886、BrnoCompSpeed 待辦)。進度報告簡報(2026-08-19,當時的口試/繳交版,21 張) —— 8/17 的內容全留(教授還沒看過),再加跨車輛驗證、第三種路類、SHARP 稽核、距離自校與前後對照 |
| `gen_point1.js` | ⚠ **歷史快照,不要重跑後對外使用**(含循環的 0.4 km/h,而且是封面結論)。單一主題簡報(2026-08-19):偵測器比較,回應教授第 ① 點。刻意與進度報告不同調——一頁一個想法、字少、表格當主角 |
| `gen_radar_validation.js` | **單一主題簡報:他車距離與速度對車載雷達的驗證。現行輸出 `他車量測外部驗證_雷達_20260916b.pptx`(20 張,校外版,自帶背景可獨立閱讀)** —— 沿革:2026-09-03 版(17 張,`他車量測驗證_雷達_20260903.pptx`)是寫給使用者自己照著講的;09-04 起改成能單獨寄給不熟悉本專案的研究者,補上系統背景、量測原理、素材與參數、雷達資料實例、跨國適用性與限制;09-16 寄出前的稽核改正三處事實錯誤(素材表的時間欄、雷達串接的成效、欄位語意的自我驗證),0916b 再更新遠場旗標與偵測器受控比較的敘述。現行版第 2 張先講系統怎麼算出距離與速度,第 10 張(0903 版是第 8 張)定義誤差指標,之後的數字都照這組定義。**體例三條:不採「自我更正」框架、不用比喻、名詞與數字都要說用途**(成果報告 4.7/4.10/4.12 的自我更正寫法維持不變,兩者定位不同) |
| `gen_flowchart_a4.js` | 推甄用 A4 研究流程圖(單頁),輸出 `data/output/report_slides/研究流程圖_推甄_A4.pptx`。⚠ **此檔目前未進版控**,只在本機工作目錄,公開 repo 裡看不到 |
| `plot_distance_calib.py` | `data/output/dashcam_demo/_calib/effect.png`(讀 `_calib/*.json` 重畫,不必重跑量測) |
| `plot_demo_rerun.py` | `data/output/dashcam_demo/_rerun/rerun_{ego,range}.png` 與 `rerun_summary.csv`:七支 demo 的封存輸出對照現行程式碼重跑(`*_current/`,已套距離修正係數)。只讀兩邊的 csv,不重跑量測;說明見 `data/output/dashcam_demo/_rerun/README.md`(2026-09-16) |
| `prep_assets.sh` / `prep_assets2.sh` / `render_ply.py` | 從 `data/output/` 裁出簡報用圖與點雲渲染 |

> ⚠ 2026-09-18 狀態更新:標「歷史快照」的五支(`gen.js`、`gen_progress.js`、`gen_progress2.js`、
> `gen_progress3.js`、`gen_point1.js`)產出的簡報內含已被取代的結論,**不要重跑後對外使用**。
> 程式本身保留不動(舊檔保留、日期即版本)。已被取代的三項:
> - **循環的 0.4 km/h**:「偵測器不是瓶頸」原本的依據是 dc006 的跟車自洽檢查,那個檢查是循環的。
>   2026-09-16 已改用對原廠雷達的受控比較(速度配對差 +0.03 km/h、區塊自助 CI 含 0;
>   近場距離 7.49%→5.77%),見 `data/output/detector_vs_radar/README.md` 與成果報告 4.11 節。
> - **09-16 前的舊係數 0.831/0.886**:dc002/dc008 的距離修正係數已用反解的 hood-y=900 更正為
>   0.811/0.854,現行值見 `docs/CASE_PARAMETERS.md`。
> - **BrnoCompSpeed 待辦**:管線 A(固定路口 CCTV)已於 2026-09-16 停止投入(程式與既有成果保留),
>   BrnoCompSpeed 因此移出範圍。
>
> `gen_progress3.js` 與 `gen_point1.js` 的輸出檔名寫死為 `_20260819.pptx`;若要更新內容,
> 先改成新日期的檔名再產生,不要覆蓋原檔。

> ⚠ 2026-09-18 狀態更新:產出檔的版本(`data/output/` 不進版控,以下檔案只在本機)
> - 雷達簡報:`他車量測外部驗證_雷達_20260916b.pptx` 是最新版;`_20260916.pptx`(無 b)是寄給校外讀者的版本,
>   保留不動,兩者的差異只有「遠場旗標已修正」的敘述與偵測器受控比較的結論;
>   `他車量測驗證_雷達_20260903.pptx` 與 `他車量測外部驗證_雷達_20260904.pptx` **內容有誤,不要再寄**。
> - 成果報告:`成果報告草稿_20260916b.docx` 是最新版;`_20260916.docx`(無 b)同樣是寄給校外讀者的版本,保留不動;
>   本機的 `_20260903.docx` 已在 09-16 10:33 被改正後的產生器覆寫(4.12 已含三處改正,係數仍是舊的
>   0.831/0.886),不是 09-03 當時的內容,不要引用。0916b 比 0916 多了 4.11 節的偵測器受控比較(新增表 8,其後表號順移)、
>   表 6 的 dc002/dc008 係數更正(0.831/0.886→0.811/0.854),以及結論章寫明管線 A 停止投入、遠場旗標已修正;
>   **0916(無 b)仍是舊係數**。
> - 8/19 的 `專題進度報告_20260819.pptx`、`偵測器比較_第一點_20260819.pptx` 是上面說的歷史快照。

## 跑法

```bash
# docx（只需要 python-docx）
python3 tools/report/build_report.py

# pptx（需要 pptxgenjs;node_modules 在 ~/tmp/pptx_build/,沒必要複製一份進版控）
NODE_PATH=~/tmp/pptx_build/node_modules node tools/report/gen_radar_validation.js

# 版面結構檢查(本機無法轉圖目視,這是替代品)
python3 tools/report/check_pptx.py data/output/report_slides/他車量測外部驗證_雷達_20260916b.pptx
```

## 圖片素材

素材約 17 MB,**不進版控**——它們是從 `data/output/` 的渲染輸出與影格裁出來的衍生檔,
而 `data/output/` 本身就是 gitignored。預設放在 `~/tmp/pptx_build/assets/`,
可用環境變數覆寫:

```bash
REPORT_ASSETS=/path/to/assets python3 tools/report/build_report.py
```

2026-08-19 新增的三張圖,重畫方式如下(全部可從版控內的程式重建):

```bash
# 距離校正的證據圖與效果圖
python3 tools/report/plot_distance_calib.py
cp data/output/dashcam_demo/_calib/effect.png ~/tmp/pptx_build/assets/

# 修正前後對照(從 _calib 的對照影片抓一幀;t=8s 有三台帶距離標籤的車)
ffmpeg -ss 8 -i data/output/dashcam_demo/_calib/hs005_before_after.mp4 -frames:v 1 \
       -q:v 2 ~/tmp/pptx_build/assets/fig_dist_before_after.jpg
ffmpeg -i ~/tmp/pptx_build/assets/fig_dist_before_after.jpg -filter_complex \
  "[0:v]crop=1200:340:0:340[a];[0:v]crop=1200:340:0:1150[b];[a][b]vstack" \
  -q:v 2 ~/tmp/pptx_build/assets/fig_dist_ba_zoom.jpg
```

2026-09-01 新增一張圖 `radar_eval.png`(4.12 節,對車載雷達的驗證證據圖),由

```bash
python3 tools/plot_radar_eval.py --json data/output/comma2k19_radar_eval/seg{21,6,10}.json \
        --out data/output/comma2k19_radar_eval/radar_eval.png
cp data/output/comma2k19_radar_eval/radar_eval.png ~/tmp/pptx_build/assets/
```

產生。該圖只讀評估器的 JSON,不必重跑量測;重跑量測的完整指令見
`data/output/comma2k19_radar_eval/README.md`。

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
