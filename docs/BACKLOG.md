# 待辦清單(BACKLOG)

兩人共用的單一待辦清單。`CLAUDE.md` 自 commit 30f6f58(2026-09-17)起不進版控,只是各自的本機筆記;共享的待辦只寫在這裡。
每項盡量三行內:在解決什麼 → 下一步 → 出處。做完就移到 F 並附 commit;新發現加在對應節末。
路徑一律寫全、相對 repo 根目錄;出處標「本機,不在版控」的,只有使用者本機看得到。
下列共享文件的內容這裡不重複:

| 文件 | 放什麼 |
|---|---|
| `docs/CASE_PARAMETERS.md` | 各案執行參數與重跑旗標 |
| `docs/FAILURE_BOUNDARIES.md` | 已知失效邊界(只標示、不修掉) |
| `docs/VALIDATION_STATUS.md` | 所有對真值的比較、真值層級、可引用數字 |
| `docs/METHODOLOGY_PITFALLS.md` | 自己犯過的推論與驗證錯誤,以及以後照做的規則 |
| `docs/ODOMETER_DESIGN.md` | 虛線週期碼表的設計理由、已廢棄機制、試過失敗的做法 |

| 節 | 誰 |
|---|---|
| A | 使用者:整理與程式小修 |
| B | Terry:深度模型 benchmark 與海盛人工真值評估的交辦事項 |
| C | 兩人一起決定 |
| D | 研究待辦(未指派) |
| E | 本機資料待決(不在版控) |
| F | 已結案 / 不要做 |

最後整理:2026-09-18。

---

## A 使用者

- **A1 `tools/lane_line_fit.py` 寫死 y=620**:左右線判定、自車道配對與去重都只用 `x@620`(第 99、114–119 行;`x@500` 只用於列印),1080p 影格會選錯右線。
  下一步:改由 `--band` 或影格高度推導,修好再用它補 A9 的像素對。出處:該檔判線段;2026-09-18 盤點。
- **A2 `tools/lane_dash_calibration.py --help` 崩潰**:help 字串裡的 `%` 沒跳脫,argparse 丟 `TypeError: %o format`。
  下一步:改成 `%%`,跑一次 `--help` 確認。出處:2026-09-18 實測。
- **A3 `data/output/dashcam_demo/_calib/effect.png` 用舊係數,右圖是預測值**:dc002 / dc008 仍是 hood-y 更正前的 0.831 / 0.886;
  右圖是 `tools/report/plot_distance_calib.py` 讀 `data/output/dashcam_demo/*_trackv3/ranges.csv`(沒有就讀基底資料夾)的距離中位數再乘係數,不是端到端實測。
  下一步二選一:(1) 右圖改讀 `data/output/dashcam_demo/*_current/ranges.csv` 的端到端中位數(已套係數,不要再乘);(2) 只換成現行 json 重畫,並在圖或 README 保留「右圖是預測」的標註。
  出處:`data/output/dashcam_demo/_calib/README.md`「2026-09-18 狀態更新」;該腳本右圖段。
- **A4 環境依賴沒寫齊**:`requirements.txt` 缺 pillow;ffmpeg 系統依賴與影格重建通則(`ffmpeg -i 原片 -vsync 0 -qscale:v 2 <dir>/f%05d.jpg`)不在 `REPRODUCE.md`;
  `tools/dashcam_range_speed.py`、`tools/cctv_speed_estimation.py`、`tools/dashcam_distance_ruler.py` 寫死 `libopenh264` 編碼器。
  影格命名也不一致:`data/output/model_comparison/README.md`、`data/output/cctv_validation/qz1130221/README.md`、`data/output/dashcam_demo/hs005/README.md`、`data/output/dashcam_demo/wow001/README.md` 用 `f%04d`,其餘用 `f%05d`;
  管線以 `sorted(glob)` 排序,超過 9999 幀時 `%04d` 會排錯序,但目前沒有已知的片超過(wow001 只抽前 119 s,3570 幀)。
  下一步:補 requirements 與 REPRODUCE「環境」節,編碼器改成可設定或自動偵測;影格命名二選一:統一 `%05d` 並一併改四位數參考幀名
  (qz1130221 的 f0012、`docs/CASE_PARAMETERS.md` 的 f0270、f2101、f0900、f0001),或只註明超過 9999 幀的片才需要 `%05d`。
  通則裡順便寫「重建後先核對幀數」(最便宜的自檢):由各基底資料夾 `original_clip_h264.mp4` 重建,dc002 600、dc003 1798、dc006 1801、dc007 330、dc008 600 幀
  (hs005 536、wow001 3570 見各自 README)。出處:2026-09-18 盤點;`git grep -n 'f%04d'`;幀數為專案筆記的重建紀錄(本機,不在版控)。
- **A5 15 案碼表迴歸只剩案表,跑法不在 repo**:幀重建、人工真值讀取、評分與新舊比對(`rebuild_frames.py`、`manual_truth.py`、`odo_regress.py`、`odo_compare.py`)當初放在 scratchpad,
  已隨 `/tmp` 消失,訊號快取 `/tmp/odo_sig_cache/` 亦同;repo 只有案表 `tools/odometer_regression_cases.py`。任何改碼表邏輯的工作(D1)都要先過這組迴歸。
  下一步:寫成 `tools/` 下的一支工具(重建影格 → 新舊碼同點位 → 逐幀比對)。人工真值解析可沿用 `tools/haisheng_manual_truth.py`(版面只在 20251230 五案驗證過,20251029 批要先核對),
  只剩幀重建、評分與比對要新寫;素材路徑與 B4 一起定。2026-08-02 的 before 基準線(七案逐案 MAE,口徑未記錄)記在 `docs/ODOMETER_DESIGN.md` 第 1.8 節,新評分器先拿它對量級。
  出處:`docs/ODOMETER_DESIGN.md` 第 1.8 節;`docs/FAILURE_BOUNDARIES.md` 的 `_join_octaves` 迴歸敘述。
- **A6 `tools/report/gen_flowchart_a4.js` 未進版控**:A4 版面研究流程圖的產生器,輸出列在 `data/output/report_slides/_INDEX.md`(本機,不在版控)。
  下一步:決定進版控(並登記到 `tools/report/README.md`)或刪除。出處:`git status`。
- **A7 成果報告的待修處**:(a) `tools/report/build_report.py` 封面的申請人、系所、指導教授、執行期間仍是佔位列,草稿日期標籤還寫 2026-09-03;
  (b) 參考文獻列了 [1]–[17],內文卻多用作者-年份,要先選定引用體例再統一;
  (c) 第 405–406 行把 2.79(單車、事後排除幹道)寫成「可引用之數字」,與第 447 行「可引用之跨車數字為 MAE 2.18」衝突:前者改成「單車適用範圍數字」,報告只留 2.18 一個「可引用」。
  本機沒有 CJK 字型,產出要在 Word / PowerPoint 開過才算確認。出處:`tools/report/build_report.py`;`tools/report/README.md`。
- **A8 看現行 demo 影片,確認觀感**:該看的已換成 `data/output/dashcam_demo/_rerun/{hs005,dc008,dc006}_archived_vs_current.mp4`(上=封存、下=現行)與各 `data/output/dashcam_demo/*_current/range_speed_h264.mp4`,
  重點是框跳動與重複計數有沒有解決。看完把結論記進 `data/output/dashcam_demo/_rerun/README.md`。出處:同檔「怎麼看」。
- **A9 `docs/CASE_PARAMETERS.md` 補兩項**:(a) hs005、wow001 的車道寬校正像素對存在 `data/output/lane_dash_calib/{hs005_ref,wow001_ref}/lane_width.json`(本機,不在版控),抄進版控;
  dc002 / dc003 / dc006 / dc007 同樣以 3.5 m 車道寬錨定,但像素對從未記錄(`data/output/lane_dash_calib/dc002_ref/` 只有虛線校正的 json,狀態 `no_spec_match`;其餘三案沒有資料夾),
  scale 與 CV 無法重現,重做用 `tools/lane_line_fit.py`(先修 A1)。(b) dc003 由封存 scale 反推掛高 0.996 m,低於合理區間 1.1–1.5 m,距離應標低信心。
  其餘四案(dc006、dc007、hs005、wow001)08-18 重算的掛高與原記錄值已收在 `docs/VALIDATION_STATUS.md` 文末附錄,抄進 CASE_PARAMETERS 時可一併引用。出處:2026-09-18 盤點。
- **A10 使用者自己的 5 支工具 docstring 仍提到 `CLAUDE.md`**:`tools/` 下的 `comma2k19_radar_eval.py`、`lane_line_fit.py`、`lane_ridge_probe.py`、`odometer_regression_cases.py`、`solve_archived_hood.py`。
  屬歷史敘述、不影響使用。下一步:改成「專案筆記(日期)」或指向對應 docs,不急。出處:`git grep -n CLAUDE`。
- **A11 `data/output/latest_run.txt` 在版控內**,內容是一個本機絕對路徑(指向已空的 `data/output/runs/`)。
  下一步:`git rm --cached`(`data/output/**` 已在 `.gitignore`),本機目錄見 E。出處:`git ls-files data/output`。
- **A12 `tools/report/README.md` 的簡報體例只記三條**:2026-09-03 定的是五條,缺「每個數字出現前先定義它怎麼算」與「外部素材(如雷達)交代來源與處理步驟」;
  「名詞與數字都要說用途」也要寫完整:技術名詞第一次出現說明它在系統裡負責什麼,每個結果數字下附一條「怎麼解讀」。
  下一步:補成五條。出處:該 README 的 `gen_radar_validation.js` 列;2026-09-03 使用者要求(本機筆記)。
- **A13 碼表程式側兩處小修**:`ego_speed.csv` 有值但 method 為 `none` 的列、`--help` 文字過時(`--dash-cycle-m` 仍寫 12 m 等)。
  下一步與修法選項見 `docs/ODOMETER_DESIGN.md` 第 6 節,這裡不重複。
- **A14 `data/output/dashcam_demo/README.md` 沒寫管線 B 版的追蹤器 v3**:2026-07-16(commit 8c2e992)從管線 A 移植,至今仍是現行行為(已讀碼確認),
  但版控只有管線 A 版(`data/output/report_final/README.md`,門檻不同:縫合空隙 3 s、遠場 0.3 m/px、4 m/s² 加速度項)與 08-02 加的兩道閘。
  管線 B 版要寫的內容:類別群組關聯(car / bus / truck 同群、機車獨立)、同幀重複框抑制(同群兩框「交集 / 小框面積」> 0.65 留高信心)、
  斷軌縫合改成 2D 相對平面版(空隙 ≤ 2 s、靈敏度 > 0.8 m/px 的遠場端點不縫合、`merged_from` 稽核)、平行鬼影抑制(兩條四輪軌中心距 < 1.2 m 的時間 ≥ 70% 判為鬼影,機車豁免)、
  多數決類別、`targets_summary.csv` 近場中位速與遠場粗估分欄;另在「方法」第 4 點補「沒有自車速的幀,他車絕對速留空、只給距離」。
  下一步:在「2026-08-02 追蹤器修正:關聯 px 一致性閘」之前加一小節。出處:`tools/dashcam_range_speed.py` 的 `CLASS_GROUP`、`stitch_fragments`、`suppress_simultaneous_duplicates`、`abs_kmh` 計算段;逐案迴歸結果見 `docs/VALIDATION_STATUS.md` ②。
- **A15 `tools/odometer_distance_calib.py` 的檔首 docstring 有已撤回或已更正的說法**(公開可見):(1)「俯仰是對的(地平線列與碼表實測差 0.7–4.3 px)」,第 175 行註解也拿它當固定 y_h 的理由;
  (2)「前向距離均勻偏高 9–34%」;(3)「fx = 0.7955×寬」;(4)「輸出的修正係數 `A_碼表 / A_SHARP`」,實際輸出的是逐列對「實測/預測」的直接中位數(同檔 L183–196)。
  下一步改成:距離偏高 11–32%;俯仰證據用 hs005 車道線消失點(差 4.6 px),不引用兩參數擬合出的地平線;焦距依 PLY 內參,不寫固定 0.7955×寬;係數為直接中位比值。
  出處:`docs/VALIDATION_STATUS.md` 文末附錄;`docs/METHODOLOGY_PITFALLS.md` 第 11 條;SHARP 焦距的更正見 Terry 的 commit 6e70403。
- **A16 幾份 README 還沒指向 2026-09-18 新收進 docs 的技術內容**:`data/output/dashcam_demo/_calib/README.md` 與 `docs/CASE_PARAMETERS.md` 係數段的「依據」→ `docs/VALIDATION_STATUS.md` 文末附錄
  (含 09-01 內參修正對已發表係數只有 −0.17%~−0.44%、不必重算);`data/output/detector_vs_radar/README.md` 第五節之後 → `docs/VALIDATION_STATUS.md` ③ 的幾何項拆解與方向性觀測;
  `docs/FAILURE_BOUNDARIES.md` 末段「貼地視角虛線 3D 取樣」→ 量級見 `docs/VALIDATION_STATUS.md` ⑤;`data/output/dashcam_validation/README.md` 加一行「這批對方車全部不可測,只驗自車速」(見 D7)。
  下一步:各加一行指標,不複製內容。出處:2026-09-18 覆蓋率審查。

## B Terry

Terry 負責深度模型 benchmark(`docs/DEPTH_MODEL_BENCHMARK.md`、`data/output/depth_benchmark/README.md`)與海盛人工真值評估(`docs/haisheng_manual_eval/README.md`)。
使用者決定不深入稽核這兩部分,以下是交給 Terry 的問題清單;其結果以 Terry 的文件為準,本清單不把它們當成專案結論引用。

- **B1 方法 C 的 A:品質閘與取樣列敏感度**:A 隨取樣列的選擇漂約 4.6%,且逐對散布閘會放行負的 A。
  下一步:閘加上 A > 0,並在 §15 報告 A 對取樣列的敏感度(連同 §15.6 第 3 點)。出處:0918 簡報審查;`docs/DEPTH_MODEL_BENCHMARK.md` §15.2、§15.6。
- **B2 盲測有真值洩漏,且產生程式不在版控**:`tools/depth_blind_analysis.py` 的 `load()` 只保留 `paired_` 裡的列,而 `paired_` 是對雷達做幾何一致性篩選後的集合(輸出 README 自己標「這一步用了真值」),
  所以「全程不用雷達」不完全成立。`paired_`(robust fit)、`roadanchor_`、`body_` 的產生程式都不在 repo(`body_` 標為 `depth_benchmark_targets.py` 產生,但該工具沒有對應選項)。
  下一步:產生程式進版控;盲測改在未過濾的 `unf_` 集合上評分,或在 §16 明確揭露。出處:`data/output/depth_benchmark/README.md` 檔名表;`tools/depth_blind_analysis.py`。
- **B3 Δ 與接地點定義定案**:Δ(雷達在保險桿、相機在擋風玻璃的偏移)沒有獨立依據,接地點又有 band / lowest 兩種定義,方法 C 的絕對精度因此未定。
  Δ 定案後 C2、C6 都要跟著改。下一步:找 Δ 的獨立來源;建議優先序 Δ > 接地點定義 > 跨相機多樣本 > 盲測搬到台灣素材(台灣沒有第三方真值)。出處:同上 §15.4、§18.2、§18.4。
- **B4 `tools/odometer_regression_cases.py` 的預設素材路徑**:09-16 改成 `data/input/海盛_20251230/…`、`data/input/海盛_20251029/…`,在使用者本機不存在,要設 `VDF_HAISHENG` / `VDF_BATCH` 才跑得動。
  下一步:檔首寫明這兩個環境變數,或找不到時明確報錯;與 A5 一起定。出處:該檔路徑設定段;commit 153bf1e。
- **B5 `tools/run_blind_eval.sh`、`tools/run_fx_sweep.sh` 沒有 `pipefail`**:只有 `set -u`,推論輸出經 `| grep` 過濾,Python 失敗時錯誤被吞掉,腳本照樣印 `*_DONE`。
  下一步:加 `set -o pipefail`(或檢查 `PIPESTATUS`),並確認中途失敗不會留下被「已存在就跳過」當成完成的半成品。出處:兩支腳本本身。
- **B6 深度模型 repo 沒記來源與版本**:§1.3 列了六個 `--depth 1` clone 的 vendored repo,但沒有 clone URL 與 commit SHA,換機器取不到同一版本。
  下一步:補一張「repo URL + commit SHA」表(`git -C depth_models/<repo> rev-parse HEAD`)。出處:`docs/DEPTH_MODEL_BENCHMARK.md` §1.3、§2.1。
- **B7 海盛評估 README 的揭露**:(a) 結果表沒註明各案用哪組取樣點:檔末重現指令用 `--auto-points`,「基準線重現」段的 005 則用手挑點(逐幀 0.72),表中 005 的 0.74 用的是哪組無從查證;
  (b)「同一畫格窗內平均」的段平均程式不在 repo,檔末的 `tools/public_dataset_ego_eval.py` 指令不讀段窗,重現不出表中數字;
  (c)「本批全為 30 m」不成立,`tools/haisheng_manual_truth.py` 解出的段距在 004 / 005 / 006 有 10、20、40 m 的段(2026-09-18 本機重跑);(d) 003 表內 1.22、內文 1.38,沒標各是哪種算法。
  下一步:Terry 在 README 補這四處揭露(含表中各案用哪組點),並把段平均腳本進版控。出處:`docs/haisheng_manual_eval/README.md`。
- **B8 海盛 003「已知失效重現不了」的解釋**:本機那支片 ffprobe 實測是 1920×1080(「4K」只在檔名),README 的 4K 假說在原機器上不成立。
  較可能是程式碼版本(失效記錄早於 `_join_octaves`)或取樣點不同(原始取樣點從未記錄)。下一步:同一份片加 `--no-join-octaves` 重跑,依結果改 README 推測段與案表 hs003s 的 note。出處:同上「003」段;`tools/odometer_regression_cases.py`。
- **B9 Terry 文件裡的 `CLAUDE.md` 引用**:`docs/DEPTH_MODEL_BENCHMARK.md` 7 處、`docs/haisheng_manual_eval/README.md` 8 處,另有 `tools/haisheng_manual_truth.py`、`tools/vanishing_point_range_calib.py` 的註解。
  下一步改指:參數 / 點位 → `docs/CASE_PARAMETERS.md`;15 案表 → `tools/odometer_regression_cases.py`;週期是每條路的常數、跨路類、夜間較弱 → `docs/FAILURE_BOUNDARIES.md`;
  OSD GPS 仲裁與各驗證數字 → `docs/VALIDATION_STATUS.md`;方法論教訓(未記錄參數先反解、車牌錨、單幀空間週期)→ `docs/METHODOLOGY_PITFALLS.md`;
  OSD 秒跳在重編碼幀上略異 → `data/output/report_final/README.md`;雷達驗證 → `data/output/comma2k19_radar_eval/README.md`。出處:`git grep -n CLAUDE`。
- **B10 0918 專題進度簡報的修正點**(簡報不在 repo;意見已整理,待使用者轉交):標線常數並非全程不看雷達(同 B2);方法 C 的 A 隨取樣列漂、閘放行負 A(同 B1);第 11 張 C 列是雷達常數版本;
  焦距 1:1 是程式恆等式,不是發現;第 16 張「現有管線遠場」的結論不穩;第 15 張「每段固定 30 m」錯(同 B7c)。
  下一步:使用者轉交後,Terry 依此修正簡報,修完回報。出處:2026-09-18 簡報審查(本機,不在版控)。
- **B11 `DEPTH_MODEL_BENCHMARK.md` §10「下一步」已過時**:列的四步已在 §12–§18 做完;真正未做的散在各節(§9 第 5 點 Video-Depth-Anything 未寫成 backend、B3 各項)。
  Terry 版筆記的第四輪摘要與「下一步候選」只剩 git 歷史(`316df7c:CLAUDE.md`)。下一步:§10 改成指向本節,需要保留的摘要移進他自己的文件。出處:同檔 §9、§10。

## C 兩人一起決定

- **C1 ✅ 已決(2026-09-18):`CLAUDE.md` 的共享方式**:不進版控(commit 30f6f58),兩人各自保留本機筆記;共享知識一律進 `docs/`:
  參數 → `docs/CASE_PARAMETERS.md`、失效邊界 → `docs/FAILURE_BOUNDARIES.md`、驗證數字 → `docs/VALIDATION_STATUS.md`、方法論錯誤 → `docs/METHODOLOGY_PITFALLS.md`、碼表設計 → `docs/ODOMETER_DESIGN.md`、待辦 → 本檔。
  提醒:Terry pull 30f6f58 之後的 main 前,先把本機 `CLAUDE.md` 備份到 repo 外(該 commit 把它移出追蹤,pull 會動到工作目錄裡那份)。
- **C2 教授第④點(微調偵測器)**:現況「建議不做,待教授確認」。兩條理由中,(a) 換更大現成模型只改善近場距離 1.7 個百分點、速度不動,站得住;
  (b)「近場與遠場所需的接地點修正符號相反」是在 Δ=0 下算的(近場 +2.88 px、遠場 −4.97 px);Δ≈1 m 時近場所需修正已趨近 0(+0.08 px),Δ=2 m 時兩者同號(−1.79 / −6.86 px),(b) 就不成立。
  重算法:合併 `data/output/comma2k19_radar_eval/seg{21,6,10}_pairs.csv`(n=908,由 `tools/comma2k19_radar_eval.py --dump-csv` 產生,指令見該 README 第三節),以 `sens_m_per_px ≤ 0.8` 分近/遠場取中位;
  所需修正(px,正=往下)= `(range_ours_m − range_radar_m − Δ) / sens_m_per_px`。
  下一步:與教授確認;若不做,理由只用 (a),並同步 `docs/PUBLIC_DATASET_BENCHMARK_PLAN.md` 檔首④與報告結論後續建議 (3);之後再決定 E 的 nuScenes。Δ 定案見 B3。
  出處:`data/output/detector_vs_radar/README.md`;Δ 重算為 2026-09-18 盤點(本機,不在版控;照上列公式可重現)。
- **C3 8/19 簡報的定位**:`data/output/report_slides/專題進度報告_20260819.pptx` 是全案進度版(教授看過的是 0803 版),含已被取代的內容(循環的 0.4 km/h、舊係數、BrnoCompSpeed 待辦),
  版本索引已標不要對外;`偵測器比較_第一點_20260819.pptx` 也含 0.4 km/h。
  下一步:決定下次向教授報告用哪一份(重產、改用 Terry 的 0918 版、或另做),兩份 8/19 是否只當存證。出處:`data/output/report_slides/_INDEX.md`(本機,不在版控;簡報檔本身也不在版控)。
- **C4 hs005 自車速的正式 MAE 口徑**:目前有 0.69(原始同窗 12 段,`README.md` 驗證摘要用它)、0.687→0.708(`data/output/dashcam_demo/_rerun/` 的封存 / 現行)、0.72(Terry 手挑點、重建影格逐幀)、
  0.74(Terry 結果表,段平均)、0.76(OSD 仲裁表與 08-02 碼表迴歸基準線,口徑未記錄),彼此差不到 0.08,但多數沒標定義。
  `docs/VALIDATION_STATUS.md` ①節已標為「暫用 0.69,待本項定案」。
  下一步:定一個正式口徑,其他出處註明是哪種重算。出處:`data/output/dashcam_demo/hs005/README.md`、`data/output/dashcam_demo/_rerun/README.md`、`data/output/dashcam_demo/README.md`、
  `data/output/dashcam_demo/wow001/README.md`「補充仲裁」、`docs/haisheng_manual_eval/README.md`、`docs/VALIDATION_STATUS.md`。
- **C5 `validation_report.md` 要不要進版控**:`data/output/dashcam_validation/<案>/validation_report.md`(9 案)不在版控,但 `data/output/dashcam_validation/README.md` 有引用;這些報告含完整案號。
  下一步:決定只留本機(README 註明),或去識別化後進版控。出處:`data/output/dashcam_validation/README.md`。
- **C6 雷達 README 要不要揭露 Δ=0**:`data/output/comma2k19_radar_eval/README.md` 第四節的分層表直接拿雷達讀值比,等於假設 Δ=0,只有第五節附帶處提到 Δ。
  重算(資料與分層同 C2,距離誤差 = `|range_ours_m − (range_radar_m + Δ)| / (range_radar_m + Δ)` 取中位):Δ=0 / 1 / 2 m 時近場誤差 7.0 / 5.1 / 5.7%、遠場 20.5 / 21.7 / 22.9%;
  係數仲裁的「差 1.6–3.6%」也會動幾個百分點。
  下一步:先加一行「未扣 Δ」與敏感度,或等 B3 定案一起改(報告同步);C2、C6 的重算若要留存,由使用者寫成 `tools/` 下的小腳本。
  出處:同 README;2026-09-18 盤點重算(本機,不在版控;照上列公式可重現)。
- **C7 刪 `origin/terry/depth-benchmark`**:PR #2 已於 09-17 合併、本機已整合。下一步:Terry 確認分支上沒有未合併的東西後刪。出處:2026-09-18 整理紀錄。
- **C8 公開 repo 裡已有的案件識別資訊**:`tools/odometer_regression_cases.py` 用完整鑑定案號比對片檔名,`data/output/cctv_validation/qz1130221/README.md` 首段也寫了完整案號。
  下一步:決定是否改成短代號(案號對應放本機或環境變數);注意 git 歷史仍保留原文,而 main 的規則集禁止強推。出處:`git grep`。
- **C9 報告與 README 何時納入 Terry 的結果**:最新報告 `data/output/report_draft/成果報告草稿_20260916b.docx`(本機,不在版控)沒有深度模型 benchmark 與海盛 20251230 評估,
  4.5 節仍用修正前距離(`data/output/dashcam_demo/*_current/` 已有修正後實測),文獻回顧仍寫「管線 A 對應 BrnoCompSpeed」。
  下一步:等 B 節處理完,兩人列出「可寫進報告的定案結論」,再一次更新 `tools/report/build_report.py` 與 README 驗證摘要;與 Terry 無關、現在就能改的「兩個可引用」矛盾見 A7(c)。
  完整報告不急。出處:`tools/report/build_report.py` 文獻回顧段;2026-09-18 盤點。
- **C10 海盛 AI 版三方對照**:Terry 發現 `_ai.xlsx` 14 段中 13 段無法用表上自己的畫格數與距離重現速率,且 002 / 003 / 006 在相同畫格位置印出同一個 98.08。
  確認前不可做「我方 vs 海盛 AI vs 人工」三方對照。下一步:決定要不要做;要做就由平常聯絡海盛的一方去問欄位定義。出處:Terry 版筆記(`316df7c:CLAUDE.md`)。

## D 研究待辦

- **D1 `_join_octaves` 加跨路類斷點旗標**(前提:A5):影片跨路類時交界處會系統性倍速;comma2k19 車 2 一段連接道(週期約 10 m)單段 MAE 40.44,所以可引用的 2.18 排除了它(含該段的 34 段為 2.91)。
  讀碼:現行轉移項已對超過每秒 1.5 的 log 變化收費(`rel_tol = 1.5/fps`,30 fps 時約 0.05/幀,comma2k19 20 fps 時為 0.075/幀),缺的是「維持舊速度」候選與旗標;
  而該段約 700 幀穩定錯在約 140 km/h(真值約 96),階躍只在交界,閘只能標出斷點、判斷不了哪一側錯。
  下一步:設計成「標斷點 → 兩側降級或逐段反推週期」,先在該段逐幀 npz 上驗,再跑台灣 15 案迴歸。
  出處:`docs/ODOMETER_DESIGN.md` 第 5 節第 1 項;`docs/FAILURE_BOUNDARIES.md` 路類兩條;`data/output/comma2k19_eval/README.md`。
- **D2 自動挑點在換道段是否過度發話**:dc003 自動挑點覆蓋 84.4%、人工 57.8%(同時鎖定的幀 mean +2.37、max 66),懷疑自動版在換道段發話;該片只有 OSD GPS(±4 km/h)判不出來。
  海盛評估的重現指令用 `--auto-points`(結果表中 005 用哪組點未註明,見 B7a),所以這條變重要了。
  下一步:目視確認海盛 003(與 dc003 同為 Mio 機種、附人工真值)有沒有換道;有就拿來仲裁,沒有就在報告與 README 註明「auto-points 未在換道段驗證」。
  出處:`data/output/comma2k19_eval/README.md` 自動挑點對照表;`docs/haisheng_manual_eval/README.md`;`docs/ODOMETER_DESIGN.md` 第 1.2 節。
- **D3 case7828 / case7829 用現行碼重跑**:兩個夜間案的輸出早於 `_join_octaves`,也不在 15 案迴歸內,而 `_join_octaves` 影響最大的正是夜間;這 3 段仍計入 28 段 MAE 1.93 / 23 段 1.37。
  下一步:重跑;不變就在 README 註記「已用現行碼確認」,變了再決定引用數字。出處:`data/output/dashcam_validation/README.md`。
- **D4 遠場距離偏 20%:已標示、未修**:三個輸出介面都已標遠場,偏差本身與偵測器無關。附帶發現(未定案):在 repo 的雷達配對上把 SHARP 地平線換成「車道線消失點 + 一致的 A」,
  遠場中位誤差 seg21 41.8→21.8%、seg6 21.9→2.5%(Δ=0)。下一步:寫成可重跑的對照實驗,注意消失點對抽線參數敏感(seg10 為 374.9–383.4,§15.2)且 Δ 未定(B3),與 Terry 協作。
  附帶待查:近場幾何項(速度)誤差中位 2.75 km/h 裡約八成是持續數秒的慢漂移、來源未定,可能與 y_h 同屬幾何參數問題(未驗證;拆解見 `docs/VALIDATION_STATUS.md` ③)。
  俯仰誤差對各距離的影響量級見 `docs/VALIDATION_STATUS.md` 文末附錄的敏感度表。
  出處:`docs/FAILURE_BOUNDARIES.md` 遠場段;`data/output/comma2k19_radar_eval/README.md` 第五節;2026-09-18 附帶發現(本機,不在版控)。
- **D5 關聯層橫移預算**:縫合層已加橫移預算閘,但 gap ≤0.8 s 的關聯層仍有超額橫移接點(dc006 35 筆、dc007 3、hs005 3、wow001 1,橫移率 4.3–7.7 m/s);遠場橫向讀值本來就雜訊大,直接加閘會誤殺。
  只影響目標 id 記帳,不影響自車速。下一步:另一輪校準再加閘,低優先。出處:`data/output/dashcam_demo/README.md`「追蹤器修正之二」段末。
- **D6 夜間逆反射標記殘留**:`_join_octaves` 之後夜間仍有 3.2% 半週期幀、MAE 4.72(車 1 24 段、事後排除幹道的舊選段口徑,不可與 2.18 並列);五個脈衝形狀特徵已全部否證,單窗內無解。
  下一步:沒有新的獨立線索前不投入。出處:`docs/FAILURE_BOUNDARIES.md` 夜間兩段;`docs/ODOMETER_DESIGN.md` 第 5 節第 2 項。
- **D7 素材缺口:汽車目標 + 路人視角**:wow001 補了一部分但自車速未過驗證,目前最接近的成品是 dc007。已下載、判定堪用但從未處理的有 `data/input/wowtchout/wow_d_rvslHBvxE.mp4`(被檢舉截圖切成 5–6 段);
  另有一支從未判定的 `wow_baoshan_aHXcGNydRsE.mp4`(見 E)。
  已知:(a) 20251029 的 8 支汽車行車紀錄器案,對方車全部不可測(橫向穿越、被剪掉、是行人、或在視野死角;44-07 的撞擊瞬間正好落在被剪掉的 60 秒內),只能驗自車速;
  (b) WoWtchout 頻道擴充法:`yt-dlp --flat-playlist` 抓約 200 支的中繼資料 → 依「汽車目標 + 時長 ≥ 40 s」篩 → 抓 `i.ytimg.com/vi/<id>/hqdefault.jpg` 縮圖判白天與路型 → 只下載入選的片驗結構;
  片尾卡片約佔 24 s,選片時長要扣掉;YouTube 公開影片,報告引用須標出處、不可商用;
  (c) 海盛 20251230 包的 001、009(夜間)從未處理,只在「汽車行車紀錄器 - AI標註」資料夾,沒有人工真值(004 已由 Terry 評估)。
  下一步:決定要不要投入;要的話先試 `wow_d_rvslHBvxE`,或向海盛要汽車目標案(白天 TDX 重錄已作廢,見 F)。出處:`data/output/dashcam_demo/README.md`「2026-08-02 新增兩支」段;(a)(b) 為 2026-07-12、08-02 素材盤點的記錄(本機專案筆記);(c) 2026-09-18 核對素材資料夾。
- **D8 擱置:wow001 自車速**:對該機 OSD MAE 11.97,OSD 疑似高報與真失效段糾纏,沒有第三方真值拆不開。引用只用距離與相對速度;取得人工畫格真值再重開。出處:`data/output/dashcam_demo/wow001/README.md`。

## E 本機資料待決(不在版控)

大小為 2026-09-18 在本機以 `du -h` 量的值(二進位單位 GiB / MiB)。當日已另刪約 9.3 GiB(有 h264 版本的中間影片、BEV 時期的 repo / 權重 / venv 等),不再列;
舊探索期輸出封存在 `data/output/_legacy_sharp_yolo_bev/`。

| 項目 | 大小 | 待決什麼 |
|---|---|---|
| `data/output/report_kh012`、`data/output/report_kh013`、`data/output/report_kh013_v2`、`data/output/report_hsinchu006`、`data/output/report_kh019` | 0.6 GiB | 刪了以後 `data/output/report_final/` 三支原片成為唯一副本;先外接備份再刪。(當日刪掉其中 0.73 GiB 中間影片前為 1.3 GiB,其他筆記若寫 1.3 GiB 是刪前的量) |
| `data/output/sharp_gaussians/` 內 31 個未被引用的點雲 | 1.9 GiB | 被引用的點雲不能刪(`docs/CASE_PARAMETERS.md`:點雲不隨 repo 分發,重現封存輸出要同一份) |
| KITTI raw(`data/input/ex/kitti/`):`2011_10_03_drive_0042_sync.zip` 與已解壓的 `2011_10_03/` | 4.0 GiB + 0.8 GiB | 取樣率下限那條失效邊界已量完,是否留存;解壓資料夾可由 zip 重建 |
| `data/nuscenes/` | 5.1 GiB | 取決於 C2(教授第④點) |
| `checkpoints/depth_anything_v2_vitl.pth` | 1.3 GiB | 先問 Terry 是否還用 |
| conda env `bevformer` | 7.6 GiB | BEV 時期環境,程式碼已於 commit 842abaa 移除 |
| `data/output/runs/`(空目錄) | — | 與 A11 一起清 |
| 本機分支 `backup/pre-coauthor-rewrite`、`refs/original/` | — | 改寫歷史時留下的備份,確認不需要後刪 |
| `data/input/wowtchout/` 三支已判出局的片(`aGNjgRMqYoc` 塗鴉遮罩蓋住路面、`jv9HgCqsJBM` 11 秒後全是放大裁切、`zSsRp-LihSQ` 後半是翻拍螢幕) | 約 86 MiB | 可刪 |
| `data/input/wowtchout/wow_baoshan_aHXcGNydRsE.mp4`(07-13 下載,從未處理;wow001 用的是 `wow_lb0uDMYUbaY.mp4`) | 8 MiB | 去留沒有記錄;要留就與 D7 一起判定堪不堪用 |

## F 已結案 / 不要做

- **把修好的碼表回灌台灣封存輸出**:七支 demo 已於 09-16 重跑到 `data/output/dashcam_demo/*_current/`;20251029 六案在 15 案迴歸中 `_join_octaves` 0 幀變動,不必重跑(case7828 / 7829 例外,見 D3)。
- **dc003 / dc007 補距離校正**:沒過品質閘本身就是方法邊界的誠實標示,硬補是在掩蓋邊界;`data/output/dashcam_demo/_rerun/` 也把它們當係數 1.0 的對照組。見 `docs/CASE_PARAMETERS.md`。
- **`data/output/dashcam_demo/_calib/` 對照影片用現行係數重算**:與現行係數差 ≤3.6%,肉眼不可辨,決定不重算(`effect.png` 另見 A3)。
- **白天重錄 TDX、夜間 CCTV 改用 11x**:管線 A 已於 2026-09-16 停止投入,程式與成果保留、不刪。
- **機車(含量測目標是機車的案)**:2026-07-12 決定只做汽車;兩個案例包的固定式 CCTV 案交比目標全是機車,一併出局。
- **BrnoCompSpeed**:隨管線 A 移出範圍;教授第③點已由 comma2k19 兩車 33 段 MAE 2.18(事前選段、對 GNSS/INS 位姿真值)完整交付。見 `docs/PUBLIC_DATASET_BENCHMARK_PLAN.md` 檔首。
- **路釘半週期的脈衝寬度匹配濾波**:前提不成立(四個脈衝形狀特徵都不交替),已放棄。見 `docs/FAILURE_BOUNDARIES.md`。
- **碼表的跨列相位「速度」閘**:試過,週期訊號的互相關多峰不可辨,會誤殺好段,勿重試;現行辨別引擎震動的跨列相位檢查是另一件事,保留。
- **拿 KITTI / nuScenes 的框微調**:只有框、微調不到遮罩頭;nuScenes 的框是 3D 投影外接框、偏鬆,會把接地點往下拉、距離系統性改變。見 `docs/PUBLIC_DATASET_BENCHMARK_PLAN.md` 第一節 C。
- **雷達時間延遲補償**:三段最佳延遲正負號不一致,是過擬合。見 `data/output/comma2k19_radar_eval/README.md`「時間延遲」。
- **再多抓 comma2k19 chunk**:全資料集只有兩台車,多抓只增加同一台車的樣本。見 `REPRODUCE.md` 路線一。
- **09-18 已修好的文件問題**(commit a878d2e):dashcam_demo 分層警語與「`*_current/` 不要再乘」、絕對速度不能整個乘係數、0.4 km/h 標為循環已取代、`PLAN_20260819` 作廢橫幅、
  `FAILURE_BOUNDARIES` 縫合層敘述、`--octave-threshold` 標無作用、BrnoCompSpeed 狀態、使用者文件裡指向 `CLAUDE.md` 的引用。
