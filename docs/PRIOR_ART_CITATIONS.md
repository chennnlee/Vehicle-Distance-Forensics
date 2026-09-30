# 前案清單(2026-09-27 完成驗證)

本檔是 `docs/TERRY_RESEARCH_RECORD.md` §10 的**完整書目附錄**。§10 寫結論,這裡列每一筆。

> **2026-09-30 補註**:本清單在 2026-09-28 寫成時,對照的是**舊方法 C**——它的尺度 A 來自組員(chennnlee)的時間差法(虛線流過兩個固定影像列的時間差 × 碼表車速,`odometer_distance_calib.py`)與車道線擬合(`lane_line_fit.py`)。各條目的「與我們的差別」已改寫成對照我現行的方法(見「現行方法」一節)。
> 書目、連結、「它做什麼」、「關係判定」與審查更正的書目內容保留原樣(「關係判定」是 2026-09-27 對照舊方法 C 的判定);審查更正、未驗證清單與一處「它做什麼」裡第一人稱的取回紀錄,改寫成中性的核對說明。

**驗證協定**:從五個搜尋角度分別檢索,規則是「只列取得頁面的論文」;
之後每一篇**重新取回頁面並試圖推翻**——核對書目、確認引文屬實、
並判斷「關係」有沒有講太滿。把鬆散相關說成「同一方法」是這裡最有害的錯誤。

**結果:47 個條目通過驗證**(真實存在、書目正確、引文屬實),
**但其中 4 個標題重複**(「Real-time Prediction of Automotive Collision Risk from Monocular Video」
出現 3 次,FARSEC、「Physics-Grounded … License Plate Typography」、
「Roadside Monocular Camera Calibration …」各 2 次,因為它們同時落在多個搜尋角度),
**不重複的是 42 篇**(2026-09-28 清點)。
**11 筆未能完成驗證**(頁面 403 / 空白 / 查核未取得結果),列在最後一節。

⚠ 重複的條目暫時保留原樣:它們來自不同搜尋角度,「它做什麼」與審查更正的細節不同,合併前要先對照(2026-09-30 改寫的「與我們的差別」依各筆所在小節的角度寫);
**引用篇數一律寫 42**。

⚠ 「關係」欄括號內的 `check:` 是複核時對原判定的修正。`overstated` = 原本說得太接近。
⚠ **「沒查到」不等於「不存在」**,專利檢索尤其不完備。

## 現行方法(2026-09-30 起各條目的「與我們的差別」以此為準)

全部是我自己的程式:

- **深度模型 × 虛線尺**(`tools/depth_dash_scale.py`):沿本車道虛線讀單目度量深度模型在同一批像素上的深度(模型單位),在這條剖面上量法定虛線的週期 P(完整虛線近端起點到下一條起點,塗漆比例需符合法規),`k = L / P`(L = 法定週期:台灣 10 m、聯邦 MUTCD 12.19 m、加州 Caltrans 14.63 m),距離 = k × 模型讀值。不需要相機內參(模型的公尺與餵入焦距成正比,k 由同一個模型的深度量出,會把這個比例一起吸收)、不需要擬合地面平面、不需要車速。
- **自車速**:同一條經 k 校正的公尺剖面上,相隔幾幀之間虛線邊緣往鏡頭方向的平移量 ÷ 時間。不用固定影像列的時間週期。
- **前車與多車**(`tools/depth_dash_relspeed.py`、`tools/depth_dash_multicar.py`):YOLO 框/遮罩處的深度 × k;相對速度 = 距離對時間的斜率。
- **空間版方法 C**(`tools/marking_geometry.py`):只用標線幾何;地平線 = 本車道兩條車道線的交點,`A = L / P_u`(虛線在 `u = 1/(y − y_h)` 上的空間週期,單幀量),`d = A/(py − y_h)`。它屬於下面「尺度錨相關」一節的空間量法前案,不宣稱為新方法。

**定位**:以**空間**方式量法定虛線、當縱向尺度錨,是前案(「尺度錨相關」一節的 Schoepflin & Dailey 2003、Cathey & Dailey 2005/2006 屬這一類;Ansari et al. 2018 提出以標準尺寸標線加已知掛高定尺度)。我的貢獻是**在單目度量深度模型自己的深度裡量法定虛線的週期,用它定該模型的公尺尺度**(`k = L / P`),不需要相機內參、不需要地面平面,並由同一條校正後的深度剖面讀自車速。本調查沒有查到任何論文或專利用法定標線常數定深度模型的尺度(`TERRY_RESEARCH_RECORD.md` §10.2 第 ③ 列;「深度模型的絕對尺度錨定」一節最接近的是以平均車長定常數的 FARSEC,與以車牌橫向尺寸定尺度的兩篇)。「虛線流過兩個固定影像列的時間差、車速消掉」這個量法是組員 chennnlee 的(`odometer_distance_calib.py`,2026-08-19),固定影像列時間週期的標線碼表(`dashcam_range_speed.py`)也是組員的,兩者都不是我的貢獻。

## 最接近舊方法 C 的四筆(⚠ 四篇的「關係」審查後全被判定講太滿,**沒有一篇真的是同一方法**)

(4 筆)

> 2026-09-30:這四筆的「關係判定」是對照**舊方法 C** 做的(尺度 A 來自組員 chennnlee 的列間時間差法,見檔首補註),保留原樣。對照我現行的方法時,最接近的前案是「尺度錨相關」一節的空間量法(Schoepflin & Dailey 2003、Cathey & Dailey 2005/2006、Ansari et al. 2018)與「深度模型的絕對尺度錨定」一節的 FARSEC。

### A novel approach for the online initial calibration of extrinsic parameters for a car-mounted camera

- **出處**:2009 12th International IEEE Conference on Intelligent Transportation Systems (ITSC), Oct 2009, pp. 1-6
- **作者**:Stephanie Hold, Steffen Gormer, Anton Kummert, Mirko Meuter, Stefan Müller-Schneiders
- **識別碼**:`10.1109/itsc.2009.5309853`
- **連結**:https://api.openalex.org/works/doi:10.1109/itsc.2009.5309853
- **關係判定**:`same_method (check: overstated)`　引文屬實:是
- **它做什麼**:Online initial extrinsic calibration of an onboard camera. A lane-marking detector samples the image at fixed vertical coordinates ("scanlines"), producing one-dimensional time series; correlation analysis between those series plus the vehicle's velocity gives the ground distance between the scanlines; a Gauss-Newton fit then solves camera height, pitch and roll by matching those distances to a pinhole back-projection onto the ground plane.
- **與我們的差別**:它的機制(固定影像列 → 一維時間訊號 → 相關 → 兩列之間的地面距離)與舊方法 C 借用的組員 chennnlee 時間差法相近,那部分不是我的方法。對照現行方法:它需要車速當外部輸入、在時間域比兩列的延遲,解的是相機掛高、俯仰與側傾,因此需要內參;深度模型 × 虛線尺在單幀的深度剖面上以空間方式量法定虛線週期,k = L / P 直接定深度模型的尺度,不需要車速、內參或外參。它沒有深度模型。
- ⚠ **審查更正**:S. Hold, S. Görmer (索引庫拼成 "Gormer"), A. Kummert, M. Meuter, S. Müller-Schneiders, "A novel approach for the online initial calibration of extrinsic parameters for a car-mounted camera," 2009 12th International IEEE Conference on Intelligent Transportation Systems (ITSC), St. Louis, MO, 2009-10-04~07, pp. 1-6, doi:10.1109/ITSC.2009.5309853. — 引用欄位無誤,不需更正。要更正的是**關係標籤**:不是 same_method,而是「**只對舊方法 C 的 part …**」(原紀錄在此截斷;舊方法 C 的這一部分是列間時間差量尺度,屬組員 chennnlee 的方法)

### Automatic estimation of vehicle speed from uncalibrated video sequences

- **出處**:International Symposium on Modern Technologies, Education and Professional Practice in Geodesy and Related Fields, Sofia, 3–4 November 2005, pp. 332ff
- **作者**:Lazaros Grammatikopoulos, George Karras, Elli Petsa
- **連結**:https://pcvg.geo.uniwa.gr/wp-content/uploads/sites/350/2022/12/Grammatikopoulos2005a-Automatic-Estimation-of-Vehicle-Speed-from-Uncalibrated-Video-Sequences.pdf
- **關係判定**:`same_method (check: overstated)`　引文屬實:是
- **它做什麼**:Camera on a 10 m bridge looking down the road. The road-direction vanishing point is extracted automatically from lane demarcations (least-squares intersection), the second is assumed at infinity, giving affine rectification; the metric scale along the road axis is then restored from ONE known ground distance. ±3 km/h against a control-point projective solution.
- **與我們的差別**:以車道標線的消失點加一段已知的沿路向距離定尺度,量的是固定相機的單張影像;那段已知距離靠現場測量,事故鑑識事後做不到。空間版方法 C 以本車道兩線交點當地平線,屬於這篇代表的古典做法;現行方法的沿路向長度來自法定虛線週期(不必到現場),深度模型 × 虛線尺還把它放在深度模型的深度裡量、用來定模型的尺度。它沒有深度模型。
- ⚠ **審查更正**:CITATION (essentially correct; only refinement is the page range — it is pp. 332-338, not "332ff"): Grammatikopoulos, L., Karras, G., Petsa, E., 2005. Automatic Estimation of Vehicle Speed from Uncalibrated Video Sequences. International Symposium on Modern Technologies, Education and Professional Practice in Geodesy and Related Fields, Sofia, 03-04 November 2005, pp. 332-338. No DOI (Semantic Sch

### Method of determining the roll angle of a vehicle mounted camera (patent)

- **出處**:US patent US10776942B2, priority 2017-07-26, granted 2020
- **作者**:Diane Neisius (Aptiv Technologies AG)
- **識別碼**:`US10776942B2`
- **連結**:https://patents.google.com/patent/US10776942B2/en
- **關係判定**:`same_method (check: overstated)`　引文屬實:是
- **它做什麼**:Determines the roll angle of a vehicle-mounted camera from two world points whose separation D is known. To get D it detects dashed/intermittent lane markers as "rectangular" brightness signals in multiple fixed scan-lines and autocorrelates those signals to recover timing, which is turned into a distance using the vehicle speed; alternatively D is taken as the standard legal length of a lane marker.
- **與我們的差別**:共用的元素是固定掃描線上的標線亮度訊號與標準標線長度;它以時間訊號加車速換算距離,輸出的是側傾角 ρ,掛高視為已知。這套「固定掃描線 + 相關」與舊方法 C 借用的組員 chennnlee 時間差法較近。現行方法不做側傾或外參標定,也不用固定掃描線的時間訊號:法定週期在深度模型的深度剖面上以空間方式量出,用來定模型的尺度。它沒有深度模型。
- ⚠ **審查更正**:Diane Neisius (Aptiv Technologies Ltd), "Method of determining the roll angle of a vehicle mounted camera", US 10,776,942 B2, priority 2017-07-26 (EP17183328.8), filed 2018-07-10 (US 16/031,151), granted 2020-09-15. Family: EP3435333B1, CN109308720B. RELATION SHOULD BE: shared_primitive / partial_scale_anchor, NOT same_method. Justification: the claimed invention is camera ROLL ANGLE rho, computed

### Real-time Prediction of Automotive Collision Risk from Monocular Video

- **出處**:arXiv preprint, submitted to IV2019, 4 Feb 2019
- **作者**:Derek J. Phillips, Juan Carlos Aragon, Anjali Roychowdhury, Regina Madigan, Sunil Chintakindi, Mykel J. Kochenderfer
- **識別碼**:`arXiv:1902.01293`
- **連結**:https://arxiv.org/abs/1902.01293 (full text: https://arxiv.org/pdf/1902.01293)
- **關係判定**:`same_method (check: overstated)`　引文屬實:是
- **它做什麼**:Dashcam collision-risk system. Relative longitudinal distance to other vehicles is computed geometrically as dy = hc·F/db, where db is measured from the bottom of the target's bounding box down to the image horizon, and the horizon is 'determined by obtaining the vanishing point of lines that are parallel in the real world'. Lateral offset comes from the same dy plus an assumed 1.8 m car width. As an extension, ego speed is measured from lane markings: a vertically fixed point on the reference lane records the time Δt for a marking to 'appear, disappear, and appear again', and speed = d/Δt with d the known marking spacing. Reported: lane-based estimator reads ~7 km/h below the speedometer at 65 km/h; distance error averaged ~0.42% of true distance over 5–15 m static tests.
- **與我們的差別**:有兩個元件與現行方法相關:地平線取自車道線消失點(空間版方法 C 也這樣取,屬古典做法),以及由標線計時求自車速。但測距用的 A = hc·F 是輸入(原文說焦距已知、掛高已知),不是由標線解出,所以不能用在未知的鑑識相機上;自車速是在固定影像點上對 LSD 偵測到的線段做出現/消失計時,與測距是兩個分開的模組。深度模型 × 虛線尺則由法定虛線在深度模型深度中的週期定尺度,不需要焦距或掛高,自車速取自同一條校正後深度剖面上虛線邊緣的平移。它沒有深度模型,也不是鑑識用途(以車速表驗證,不是以真值儀器)。
- ⚠ **審查更正**:Derek J. Phillips, Juan Carlos Aragon, Anjali Roychowdhury, Regina Madigan, Sunil Chintakindi, Mykel J. Kochenderfer, "Real-time Prediction of Automotive Collision Risk from Monocular Video", arXiv:1902.01293 [cs.RO], 4 Feb 2019(arXiv comments 欄原文:"Submitted to IV2019. 7 pages, 4 figures, 3 tables";查不到 IEEE 正式出版版本,引用時維持 arXiv preprint)。 關係更正:same_method → **partial_overlap / same_component**。 精確寫法

## 尺度錨相關(法定標線/已知長度當比例尺)

(11 筆)

### Algorithms for Estimating Mean Vehicle Speed Using Uncalibrated Traffic Management Cameras (WSDOT research report, Agreement T1803 Task 48) — full report behind Schoepflin & Dailey, IEEE T-ITS 4(2):90–98, 2003

- **出處**:Washington State Transportation Center (TRAC) / WSDOT, October 2003; journal version IEEE Trans. ITS 4(2):90–98, 2003
- **作者**:Todd Nelson Schoepflin, Daniel J. Dailey
- **識別碼**:`10.1109/tits.2003.821213 (journal version; report has no DOI)`
- **連結**:https://rosap.ntl.bts.gov/view/dot/37852/dot_37852_DS1.pdf
- **關係判定**:`same_scale_anchor (check: understated)`　引文屬實:是
- **它做什麼**:Three-stage calibration of an uncalibrated roadside CCTV camera: activity maps give lane boundaries and the first vanishing point, vehicle bottom edges give the second, and the scene scale comes from the lane-marker interval tau_L, which is estimated from the image by auto-covariance of the top-hat brightness signal sampled along lines emanating from the vanishing point. Section 3.7 is entirely devoted to 'Estimating the lane marker interval'. Ground truth for the interval was taken with a distance wheel over 101 intervals (mean 40.5 ft).
- **與我們的差別**:以空間方式量法定虛線週期(標線 + 間隙,不是單看線段)當已知縱向長度——這一類是前案,**空間版方法 C 屬於這一類**,差別只在情境(移動的行車紀錄器、單幀在 u = 1/(y − y_h) 座標上量週期、逐時窗追線),不宣稱為新方法。本篇在固定相機的影像內沿消失點射線以自協方差量像素週期,輸出拉直後路面條帶的像素—英尺換算,不需要 h 與 f。深度模型 × 虛線尺把同一個法定週期改在深度模型自己的深度裡量,用來定模型的公尺尺度;本篇沒有深度模型。
- ⚠ **審查更正**:CITATION (corrected/completed, copied from the document itself): Todd Nelson Schoepflin and Daniel J. Dailey, "Algorithms for Estimating Mean Vehicle Speed Using Uncalibrated Traffic Management Cameras", Research Report WA-RD 575.1, Agreement T1803 Task 48 ("Automated CCTV Cameras"), ITS Research Program, College of Engineering, University of Washington / Washington State Transportation Center (TR

### Analysis of Dashcam Video for Determination of Vehicle Speed

- **出處**:SAE Technical Paper 2020-01-0877, 2020 (WCX SAE World Congress)
- **作者**:Jack Leifer, Alvaro Marquez (Trinity University)
- **識別碼**:`10.4271/2020-01-0877`
- **連結**:https://saemobilus.sae.org/papers/analysis-dashcam-video-determination-vehicle-speed-2020-01-0877
- **關係判定**:`same_scale_anchor`　引文屬實:是
- **它做什麼**:Extracts ego vehicle speed from dashcam footage when the camera's optical parameters are unknown, by measuring road features in overhead satellite imagery instead of physically surveying the scene, then tracking individual features — explicitly including 'periodically-occurring markings such as lane lines' — as they pass through and exit the image frame, combined with the video frame rate. Tested 16–65 mph; results matched the speedometer for all but the lowest frame rates.
- **與我們的差別**:同樣處理光學參數未知的移動相機,並利用週期性標線與幀數求自車速。它的公尺錨是該地點的衛星影像(需要知道確切地點與有地理參考的影像),並逐一追蹤辨識出的特徵;現行方法只需要法定週期,不需要任何地點資訊,自車速取自深度模型經 k 校正後的公尺剖面上虛線邊緣的平移。它只給自車速,沒有他車距離、沒有深度模型。已核對:只取得出版社摘要頁、未取得全文,無法排除正文討論標準標線長度。
- ⚠ **審查更正**:引用不需更正。核對過的引用行:Leifer, J. and Marquez, A., "Analysis of Dashcam Video for Determination of Vehicle Speed," SAE Technical Paper 2020-01-0877, WCX SAE World Congress Experience, Detroit, MI, published 2020-04-14, doi:10.4271/2020-01-0877。關係標籤 "same_scale_anchor" 維持,但報告中的措辭要收緊(原紀錄的建議句指 2026-09-28 舊方法的縱向尺度錨,其後截斷)。

### Automatic camera calibration method based on dashed lines

- **出處**:Proceedings of SPIE, 2013
- **作者**:Xiuhua Li, Guoyou Wang, Jianguo Liu
- **識別碼**:`DOI 10.1117/12.2031362`
- **連結**:https://api.openalex.org/works?search=Automatic%20camera%20calibration%20method%20based%20on%20dashed%20lines
- **關係判定**:`same_scale_anchor`　引文屬實:是
- **它做什麼**:Fully automatic traffic-camera calibration from the endpoints of dashed road lane markings, found with a modified RANSAC plus pixel-based transverse projection; builds a calibration model from the geometric relation between camera and road coordinate systems. Under 5% error converting pixels to metres along the lane markings.
- **與我們的差別**:用單張影像中的虛線幾何(端點位置)標定固定式交通相機,屬空間量法前案,與空間版方法 C 同類。沒有相機運動、沒有深度模型。已核對:SPIE 為付費全文,只取得書目資料與重建的摘要,無法確認已知長度指的是線段還是整個週期。
- ⚠ **審查更正**:Citation (corrected to full precision): Xiuhua Li, Guoyou Wang, Jianguo Liu, "Automatic camera calibration method based on dashed lines," Proc. SPIE 8921, MIPPR 2013: Remote Sensing Image Processing, Geographic Information Systems, and Other Applications, 892112 (25-26 October 2013); DOI 10.1117/12.2031362. Eighth International Symposium on Multispectral Image Processing and Pattern Recognition, W

### Physics-Grounded Monocular Vehicle Distance Estimation Using Standardized License Plate Typography

- **出處**:arXiv, submitted 14 Apr 2026, revised 2 Jul 2026
- **作者**:Manognya Lokesh Reddy, Zheng Liu
- **識別碼**:`arXiv:2604.12239`
- **連結**:https://arxiv.org/abs/2604.12239
- **關係判定**:`same_scale_anchor (check: understated)`　引文屬實:是
- **它做什麼**:Monocular inter-vehicle distance estimation for ADAS that resolves scale ambiguity using the standardized typography of United States license plates as passive fiducial markers, with explicit geometric priors and no training data — deliberately avoiding learned depth networks.
- **與我們的差別**:診斷相同(單目的尺度要由法定標準化的物體打破),但錨的選擇與對深度模型的結論都相反。它的錨是目標車上的**橫向**尺寸,經針孔關係換算需要已知焦距,而且刻意不用學習式深度網路;現行方法的錨是沿行進方向的法定虛線週期,在深度模型的深度裡量,焦距造成的比例由 k 一起吸收。它是 ADAS 論文,沒有鑑識框架。
- ⚠ **審查更正**:引用本身無誤,不需更正。完整正確的引用行為:Manognya Lokesh Reddy, Zheng Liu, "Physics-Grounded Monocular Vehicle Distance Estimation Using Standardized License Plate Typography," arXiv:2604.12239v3 [cs.CV; eess.IV], v1 2026-04-14 / v2 2026-05-20(原條目未列)/ v3 2026-07-02;29 pages, 12 figures;CC BY 4.0;DOI 僅有 arXiv 自帶的 10.48550/arXiv.2604.12239,無期刊 reference(=未經同儕審查的 preprint);作者單位 University of Michigan-Dearborn。 需要更正的是「關係

### Real-time Prediction of Automotive Collision Risk from Monocular Video

- **出處**:Submitted to IEEE Intelligent Vehicles Symposium 2019; arXiv 2019
- **作者**:Derek J. Phillips, Juan Carlos Aragon, Anjali Roychowdhury, Regina Madigan, Sunil Chintakindi, Mykel J. Kochenderfer
- **識別碼**:`arXiv:1902.01293`
- **連結**:https://ar5iv.labs.arxiv.org/html/1902.01293
- **關係判定**:`same_scale_anchor (check: understated)`　引文屬實:是
- **它做什麼**:Dashcam collision-risk pipeline with detection, tracking and state estimation. Absolute ego speed is obtained from lane markings of known dimensions used as stationary references: a vertically fixed point on the reference lane records the time for a marking to appear, disappear and reappear (Δt), and speed is the known inter-marking distance divided by Δt. Range to other vehicles uses dy = hc·F/db with camera height and focal length assumed known, plus a standard 1.8 m car width for lateral offset.
- **與我們的差別**:由已知間距的標線求自車速——固定影像點、標線通過計時、已知虛線間距——說明「用標線求自車速」在原理上不是新概念,我的自車速也不宣稱這個原理是新的。差別在量法:它是門檻/事件計時;現行方法在深度模型經 k 校正的公尺剖面上量相隔幾幀之間虛線邊緣的平移。它的測距假設 hc 與 F 已知,標線計時也從不回饋去定測距尺度;現行方法由同一把虛線尺同時給距離尺度與自車速。它沒有深度模型。
- ⚠ **審查更正**:D. J. Phillips, R. Madigan, J. C. Aragon, S. Chintakindi, A. Roychowdhury, M. J. Kochenderfer, "Real-time Prediction of Automotive Collision Risk from Monocular Video," arXiv:1902.01293v1 [cs.CV], 4 Feb 2019, DOI 10.48550/arXiv.1902.01293 (comment field: "Submitted to IV2019. 7 pages, 4 figures, 3 tables"). Cite as an arXiv preprint — no IEEE-published IV 2019 version could be located. RELATION, c

### Roadside Monocular Camera Calibration Based on Adaptive Structure Tensor and Hierarchical Vanishing Point Estimation

- **出處**:Electronics (MDPI) 15(14):3215, 2026
- **作者**:Xuecong Liu, Kun Kang, Kangchao Gao
- **識別碼**:`DOI 10.3390/electronics15143215`
- **連結**:https://api.openalex.org/works/doi:10.3390/electronics15143215
- **關係判定**:`same_scale_anchor`　引文屬實:是
- **它做什麼**:Adaptive structure tensor for stable edge orientation under shadows and reflections, then a hierarchical dual-vanishing-point self-calibration (spatial focusing, Mean-Shift clustering, nonlinear optimisation); scale recovery exploits road-marking geometric priors under the two vanishing-point constraints, claiming no calibration target, no vehicle-size assumption and no motion prior.
- **與我們的差別**:最新的路側相機宣稱只靠標線幾何先驗取得公尺尺度——固定相機、單張影像幾何,(依摘要)明言不用運動先驗,屬空間量法前案,與空間版方法 C 同類。沒有深度模型。已核對:MDPI 全文回應 403,只確認書目資料,無法確認先驗是線段長、週期或車道寬,需從可連上 mdpi.com 的網路再核對一次。
- ⚠ **審查更正**:引用行完全正確,不必改:Xuecong Liu, Kun Kang, Kangchao Gao, "Roadside Monocular Camera Calibration Based on Adaptive Structure Tensor and Hierarchical Vanishing Point Estimation", Electronics (MDPI) 15(14):3215, 2026, DOI 10.3390/electronics15143215(投稿 2026-06-20、刊出 2026-07-21;Northeastern University at Qinhuangdao;Academic Editor: Dah-Jye Lee)。 引用句應改為論文原文(摘要第 3 段):"On this basis, the geometric prior informa

### Roadside Monocular Camera Calibration Based on Adaptive Structure Tensor and Hierarchical Vanishing Point Estimation

- **出處**:Electronics (MDPI), vol. 15, no. 14, article 3215, 2026
- **作者**:Xuecong Liu, Kun Kang, Kangchao Gao
- **識別碼**:`10.3390/electronics15143215`
- **連結**:https://api.semanticscholar.org/graph/v1/paper/DOI:10.3390/electronics15143215?fields=title,authors,year,venue,abstract,externalIds
- **關係判定**:`same_scale_anchor`　引文屬實:是
- **它做什麼**:Automatic self-calibration of fixed roadside traffic cameras: robust edge-orientation extraction, hierarchical two-vanishing-point estimation, then scene scale recovered from the geometric prior of road markings via a marking-contour optimisation model constrained by the two vanishing points. Applied to vehicle speed measurement, evaluated on BrnoCompSpeed (5.31% mean relative calibration error, 1.79 km/h mean speed error).
- **與我們的差別**:與空間版方法 C 同樣用消失點定方向、用標線定尺度,但對象是固定路側相機,標線在影像內以輪廓量測(空間量法),屬同一類前案。它是純古典幾何標定,沒有使用或校正任何單目深度網路,所以不涉及深度模型 × 虛線尺的核心(在深度模型的深度裡量法定週期、定模型的尺度)。
- ⚠ **審查更正**:Citation is correct as given; canonical form: Liu, X.; Kang, K.; Gao, K. "Roadside Monocular Camera Calibration Based on Adaptive Structure Tensor and Hierarchical Vanishing Point Estimation." Electronics 2026, 15(14), 3215. https://doi.org/10.3390/electronics15143215 (published 21 July 2026, CC BY 4.0; 35 pp., 49 refs; all three authors at Northeastern University at Qinhuangdao). Relation label "

### The Automated Use of Un-Calibrated CCTV Cameras as Quantitative Speed Sensors — Phase 3 (WA-RD 635.1); companion to Cathey & Dailey, IEEE Intelligent Vehicles Symposium 2005, pp. 777–782

- **出處**:WSDOT report WA-RD 635.1, January 2006; conference version IEEE IV Symposium 2005, pp. 777–782
- **作者**:Daniel J. Dailey, Frederick W. Cathey
- **識別碼**:`WA-RD 635.1; conference version 10.1109/ivs.2005.1505199`
- **連結**:https://www.wsdot.wa.gov/research/reports/fullreports/635.1.pdf
- **關係判定**:`same_scale_anchor (check: understated)`　引文屬實:是
- **它做什麼**:Vanishing point from road lines → a 'straightening' transformation that maps road-parallel lines to vertical image lines → autocorrelation of the straightened background image along a column, whose period is the image length from the start of one lane stripe to the start of the next → scale factor kappa = L/lambda in feet per pixel. The software's default stripe period is 40 feet, and a warning is given that 'the default stripe period may be wrong (some highway stripes...)'. Vehicle pixel speed then comes from cross-correlating successive straightened frames.
- **與我們的差別**:錨的概念相同(線段起點到下一條起點 = 一個週期,軟體預設 40 ft = 12.19 m),在拉直後的影像上以自相關量像素週期,換成比例 κ = L/λ——這是以空間量法定尺度的前案,**空間版方法 C 在 u = 1/(y − y_h) 上量週期、A = L / P_u,與此同類**。它是固定相機,且刻意不解 h 與 f;相鄰幀之間的互相關用來追車,不是用來量尺度。深度模型 × 虛線尺把週期改在深度模型的深度剖面上量、用來定模型的尺度,這一步本篇沒有;它沒有自車速量測,也沒有度量深度模型。
- ⚠ **審查更正**:Dailey, D. J., & Cathey, F. W. (2006). "The Automated Use of Un-Calibrated CCTV Cameras as Quantitative Speed Sensors — Phase 3." Final Research Report, Agreement T2695, Task 55, WA-RD 635.1, Washington State Transportation Center (TRAC), University of Washington / WSDOT, January 2006, 37 pp. https://www.wsdot.wa.gov/research/reports/fullreports/635.1.pdf (mirror: https://rosap.ntl.bts.gov/view/do

### The Earth ain't Flat: Monocular Reconstruction of Vehicles on Steep and Graded Roads from a Moving Camera

- **出處**:IROS 2018
- **作者**:Junaid Ahmed Ansari, Sarthak Sharma, Anshuman Majumdar, J. Krishna Murthy, K. Madhava Krishna
- **識別碼**:`arXiv:1803.02057`
- **連結**:https://ar5iv.labs.arxiv.org/html/1803.02057
- **關係判定**:`same_scale_anchor`　引文屬實:是
- **它做什麼**:Monocular localisation and shape estimation of other vehicles on non-planar roads, approximating the road by local planar patches and using vehicle semantic keypoints in a bundle-adjustment-like optimisation. In discussing how to obtain metric scale it explicitly proposes using road markings of standard dimensions together with a known camera height.
- **與我們的差別**:這是「以標準尺寸的標線定公尺尺度」最直接的已發表陳述,而且是**空間、單幀**的版本:在一張影像裡量標線的外觀尺寸,並需要已知的相機掛高 h。空間版方法 C 同屬空間量法,差別是由單幀內一個法定週期在 u 座標上佔的範圍解出乘積 A = h·f,不需要分開知道 h 或 f。深度模型 × 虛線尺不需要掛高:法定週期在深度模型的深度裡量,直接定模型的尺度。本篇沒有深度網路(2018 年,早於度量深度基礎模型),也不用車道線消失點當地平線。
- ⚠ **審查更正**:Nothing needed correcting. Full verified citation (enriched with page numbers and the publication DOI, which the original entry lacked): J. A. Ansari, S. Sharma, A. Majumdar, J. K. Murthy, K. M. Krishna, "The Earth Ain't Flat: Monocular Reconstruction of Vehicles on Steep and Graded Roads from a Moving Camera," 2018 IEEE/RSJ International Conference on Intelligent Robots and Systems (IROS), Oct 20

### Using road markers as fiducials for automatic speed estimation in road videos

- **出處**:2017 IEEE Western New York Image and Signal Processing Workshop (WNYISPW)
- **作者**:Deepali D. Kamat, Thomas B. Kinsman
- **識別碼**:`DOI 10.1109/wnyipw.2017.8356258`
- **連結**:https://api.openalex.org/works?search=Using%20road%20markers%20as%20fiducials%20for%20automatic%20speed%20estimation%20in%20road%20videos
- **關係判定**:`same_scale_anchor (check: understated)`　引文屬實:否(僅摘要可讀)
- **它做什麼**:Ego-speed estimation from an ordinary dashcam using the uniformly spaced dashed lines painted on US roads as fiducials, with a line-detection technique and no LiDAR, GPS, accelerometer, odometry or CNN; works on 30 fps internet video from unknown cameras. Cites forensic analysis as an application.
- **與我們的差別**:由未知相機的行車紀錄器、以均勻虛線間距為基準求自車速,並列出鑑識用途——與現行方法的自車速部分目標相同,應該引用。它是標記偵測式做法,虛線間距只拿來算速度,不轉成距離尺度,也不校正深度網路;現行方法的同一把虛線尺(深度模型深度中的法定週期)同時定距離尺度與自車速。已核對:IEEE Xplore 拒絕存取,只取得書目資料與重建的摘要,內部方法細節未確認。
- ⚠ **審查更正**:引用行(已逐欄對帳 Crossref,可直接用): D. D. Kamat and T. B. Kinsman, "Using road markers as fiducials for automatic speed estimation in road videos," 2017 IEEE Western New York Image and Signal Processing Workshop (WNYISPW), Rochester, NY, USA, 17 Nov. 2017, pp. 1–5, doi: 10.1109/WNYIPW.2017.8356258. 應一併引用的長版(同一批作者、同一件工作、內含完整方法,而且可公開取得全文): D. D. Kamat, "Vehicle Movement and Speed Estimation using a Cost Effec

### Vision-based Vehicle Speed Estimation: A Survey

- **出處**:IET Intelligent Transport Systems, 2021
- **作者**:David Fernández Llorca, Antonio Hernández Martínez, Iván García Daza
- **識別碼**:`arXiv:2101.06159, DOI 10.1049/itr2.12079`
- **連結**:https://ar5iv.labs.arxiv.org/html/2101.06159
- **關係判定**:`same_scale_anchor`　引文屬實:是
- **它做什麼**:Systematic review and taxonomy of vision-based vehicle speed estimation from infrastructure cameras, including how the metres-per-pixel scale factor is obtained. It lists lane-marking length and frequency as one established family of scale cues, with eleven citations attached.
- **與我們的差別**:這是「標線當比例尺」本身**不是新概念**的最強證據:在本領域的標準綜述裡它是一個有名稱的類別,背後有十一篇前案。綜述範圍是固定式基礎設施相機(明言排除車載相機),長度與「頻率」指影像內量到的標線空間間距;綜述裡沒有單目深度網路或度量深度模型。所以現行方法能宣稱的範圍要收窄為:在單目度量深度模型自己的深度裡量法定虛線週期,用它定該模型的公尺尺度(不需要內參與地面平面),並由同一條校正後的深度剖面讀自車速。空間版方法 C 屬於綜述已涵蓋的這一類。
- ⚠ **審查更正**:書目應補齊為期刊正式版(原引文只寫「IET ITS, 2021」,不算錯但不完整):Fernández Llorca, D., Hernández Martínez, A., García Daza, I., "Vision‐based vehicle speed estimation: A survey", IET Intelligent Transport Systems, 2021, 15(8), pp. 987–1005, DOI 10.1049/itr2.12079(線上出版 2021-05-21、印刷 2021-08);預印本 arXiv:2101.06159(v1 2021-01-15、v2 2021-05-26,arXiv 版標題大寫作 "Vision-based Vehicle Speed Estimation: A Survey")。關係標籤 same_scale_an

## 深度模型的絕對尺度錨定

(10 筆)

### AnchorD: Metric Grounding of Monocular Depth Using Factor Graphs

- **出處**:arXiv preprint, 4 May 2026
- **作者**:Simon Dorer, Martin Büchner, Nick Heppert, Abhinav Valada
- **識別碼**:`arXiv:2605.02667`
- **連結**:https://arxiv.org/abs/2605.02667
- **關係判定**:`same_depth_anchoring (check: overstated)`　引文屬實:是
- **它做什麼**:A training-free framework that anchors the priors of a monocular depth foundation model in raw depth-sensor measurements via factor-graph optimisation, to fix mis-scaled or skewed predictions for robotic manipulation and navigation.
- **與我們的差別**:架構相同——凍結的基礎模型、外部公尺錨、不需訓練——連「anchor」這個字都一樣。但錨是深度感測器,不是場景幾何,保留了現行方法要拿掉的感測器需求;場景是室內機器人,沒有路面、標線或地平線。深度模型 × 虛線尺的錨是法定虛線週期,在模型自己的深度裡量。
- ⚠ **審查更正**:引用（補上正式出版資訊，原本只寫 arXiv preprint）： Simon Dorer, Martin Büchner, Nick Heppert, Abhinav Valada. "AnchorD: Metric Grounding of Monocular Depth Using Factor Graphs." 2026 IEEE/RSJ International Conference on Intelligent Robots and Systems (IROS), Pittsburgh, USA, 2026. arXiv:2605.02667v1 [cs.RO], submitted 4 May 2026 14:48:52 UTC. DOI: 10.48550/arXiv.2605.02667. Comments: 8 pages, 9 Figures, 3 Tables. 

### Camera Height Doesn't Change: Unsupervised Training for Metric Monocular Road-Scene Depth Estimation

- **出處**:ECCV 2024
- **作者**:Genki Kinoshita, Ko Nishino
- **識別碼**:`arXiv:2312.04530`
- **連結**:https://arxiv.org/abs/2312.04530
- **關係判定**:`same_depth_anchoring (check: overstated)`　引文屬實:是
- **它做什麼**:Training method (FUMET) that makes any monocular depth network learn absolute scale from ordinary driving video: it detects cars, estimates their sizes, aggregates the scale information into an estimate of the camera height, and enforces that height's consistency across the whole sequence as scale supervision.
- **與我們的差別**:以由車輛尺寸推得的相機掛高定深度網路的公尺尺度,而且是在**訓練**時做,不是部署時對每支片套一個常數。現行方法是部署時在實際影片上量一個全域乘數 k(法定週期 ÷ 模型深度中量到的週期),可稽核;k 由同一個模型的深度量出,餵入焦距造成的比例會一起被吸收。它不用標線、不用標線週期,也沒有處理以內參為條件的度量模型其公尺與焦距成正比的問題。
- ⚠ **審查更正**:Genki Kinoshita, Ko Nishino, "Camera Height Doesn't Change: Unsupervised Training for Metric Monocular Road-Scene Depth Estimation," in Computer Vision – ECCV 2024, Springer Nature Switzerland, 2024, pp. 57–73. DOI: 10.1007/978-3-031-73337-6_4. arXiv:2312.04530v3 (submitted 2023-12-07, v3 2024-10-01). cs.CV; cs.RO. 關係標籤應由 same_depth_anchoring 改為 **same_goal_different_anchor_and_stage**(同一個問題:單目深度的

### DrivingDepth: Sparse-Prompted Pixel-wise Scale Correction for Driving Depth Estimation

- **出處**:arXiv preprint, 30 June 2026
- **作者**:Chi Huang, Wenhao Zhang, Hang Yin, YuAn Wang, Hao Li, Bosheng Wang, Xun Sun, Liang Wang
- **識別碼**:`arXiv:2606.31488`
- **連結**:https://arxiv.org/abs/2606.31488
- **關係判定**:`same_depth_anchoring (check: overstated)`　引文屬實:是
- **它做什麼**:Treats sparse projected LiDAR as geometric prompts that locally calibrate a frozen depth foundation prior through residual per-pixel scale correction, on the argument that the foundation model's relative geometry is already coherent and only a scale mapping is missing. Evaluated on nuScenes.
- **與我們的差別**:幾乎逐字陳述了現行方法的前提——形狀是對的,只缺尺度——是這個前提最強的已發表支持。我自己的乾淨結果方向一致:AV2 c865c156 上 da3_metric 直接輸出的近場距離誤差 29.00%,乘上虛線尺 k 後 1.64%(不經任何車道線擬合重評,`TERRY_RESEARCH_RECORD.md` §11.4 補註)。(另有舊評分:comma2k19 直接輸出 2.3–40%、乘上以雷達本身擬合的單一常數後 2.1–4.4%,以組員匯出的雷達檔評分,見 `DEPTH_MODEL_BENCHMARK.md` §12,不放進大專生計畫。)但它的公尺錨是光達——主動感測器,本方法的前提就是沒有——而且修正是逐像素,不是單一全域常數;它沒有從影像內容或法定道路幾何推尺度。
- ⚠ **審查更正**:Huang, C., Zhang, W., Yin, H., Wang, Y., Li, H., Wang, B., Sun, X., Wang, L. (Baidu Inc.). "DrivingDepth: Sparse-Prompted Pixel-wise Scale Correction for Driving Depth Estimation." arXiv:2606.31488 [cs.CV], submitted 30 Jun 2026. https://arxiv.org/abs/2606.31488 (code: https://github.com/HCaelrs/DrivingDepth) 關係應改為 same_premise_for_part3_only(不是 same_depth_anchoring)。正確敘述:此文以文獻形式支持舊紀錄所稱第 (3) 部分(以外部常數定深度模型的尺度)的「前提」——度…(原紀錄在此截斷)

### FARSEC: A Reproducible Framework for Automatic Real-Time Vehicle Speed Estimation Using Traffic Cameras

- **出處**:arXiv preprint, 2023
- **作者**:Lucas Liebe, Franz Sauerwald, Sylwester Sawicki, Matthias Schneider, Leo Schuhmann, Tolga Buz, Paul Boes, Ahmad Ahmadov, Gerard de Melo
- **識別碼**:`arXiv:2309.14468`
- **連結**:https://ar5iv.labs.arxiv.org/html/2309.14468
- **關係判定**:`same_depth_anchoring`　引文屬實:是
- **它做什麼**:Traffic-camera speed estimation that estimates the length of road segments via monocular depth-map prediction, explicitly acknowledging that the depth model is only defined up to an unknown scaling factor s_m, and solving for s_m by least squares against average car lengths (a mean vehicle length of about six metres) derived from 2D tracking boxes.
- **與我們的差別**:結構上最接近深度模型 × 虛線尺的已發表例子——單目深度網路 + 一個由外部資訊擬出的全域尺度常數。但外部資訊是平均車長,不是法定標線週期,而且是固定路側相機。錨是車隊統計量,常數帶著車隊變異,在法庭上不可稽核;現行方法的 k 來自法定週期,在同一個模型的深度裡量。它也沒有討論度量深度模型的公尺與餵入焦距成正比。
- ⚠ **審查更正**:不需更正。arXiv 頁面上的標準引用:Lucas Liebe, Franz Sauerwald, Sylwester Sawicki, Matthias Schneider, Leo Schuhmann, Tolga Buz, Paul Boes, Ahmad Ahmadov, Gerard de Melo, "FARSEC: A Reproducible Framework for Automatic Real-Time Vehicle Speed Estimation Using Traffic Cameras", arXiv:2309.14468 [cs.CV], submitted 25 September 2023, DOI 10.48550/arXiv.2309.

### FARSEC: A Reproducible Framework for Automatic Real-Time Vehicle Speed Estimation Using Traffic Cameras

- **出處**:arXiv, 25 Sep 2023 (cs.CV)
- **作者**:Lucas Liebe, Franz Sauerwald, Sylwester Sawicki, Matthias Schneider, Leo Schuhmann, Tolga Buz, Paul Boes, Ahmad Ahmadov, Gerard de Melo
- **識別碼**:`arXiv:2309.14468`
- **連結**:https://arxiv.org/abs/2309.14468 (full text: https://arxiv.org/pdf/2309.14468)
- **關係判定**:`same_depth_anchoring`　引文屬實:是
- **它做什麼**:Speed estimation from traffic surveillance video. Runs the PixelFormer monocular depth model (KITTI-pretrained) to get RELATIVE depth, then estimates one global scalar s_M by least squares against a set of point pairs with known real-world distances — in practice the assumed mean vehicle length of six metres, derived from cumulative bounding-box tracking. Evaluated on BrnoCompSpeed; accuracy validated against 'road markings at a fixed distance'. States explicitly that depth models give depth only up to a scaling factor that is independent of the image.
- **與我們的差別**:做法在結構上與深度模型 × 虛線尺相同——對網路的深度輸出乘一個全域常數——但周邊全都不同:錨是假設的 6 m 平均車長(弱、隨車隊而變的先驗;作者提到也可改用各國特有的特徵),不是法定沿路向的標線週期;相機是固定路側 CCTV,不是移動的行車紀錄器;網路是**相對**深度模型,所以不會遇到度量模型的公尺隨餵入焦距等比例改變的問題,也沒有宣稱與焦距無關;道路標線只出現在評估參考,從來不是尺度錨。輸出是整體車流速度,不是逐目標的鑑識距離。
- ⚠ **審查更正**:Citation stands as given: Lucas Liebe, Franz Sauerwald, Sylwester Sawicki, Matthias Schneider, Leo Schuhmann, Tolga Buz, Paul Boes, Ahmad Ahmadov, Gerard de Melo. "FARSEC: A Reproducible Framework for Automatic Real-Time Vehicle Speed Estimation Using Traffic Cameras." arXiv:2309.14468 [cs.CV; also cs.LG, cs.SI], submitted 25 Sep 2023. DOI 10.48550/arXiv.2309.14468. No journal-ref on the arXiv rec

### Language as Prior, Vision as Calibration: Metric Scale Recovery for Monocular Depth Estimation

- **出處**:arXiv preprint, 4 January 2026
- **作者**:Mingxia Zhan, Li Zhang, Beibei Wang, Yingjie Wang, Zenglin Shi
- **識別碼**:`arXiv:2601.01457`
- **連結**:https://arxiv.org/abs/2601.01457
- **關係判定**:`same_depth_anchoring (check: overstated)`　引文屬實:是
- **它做什麼**:Under a frozen-backbone setting, recovers metric depth by an image-specific affine transform in inverse depth, training only lightweight calibration heads; a CLIP text encoder predicts an uncertainty-aware envelope of feasible calibration parameters and pooled visual features select within it.
- **與我們的差別**:同樣是凍結骨幹加校正,但校正參數是學習出的頭由影像與文字特徵**預測**,不是由已知的實體長度量出——對鑑識用途方向相反:沒有東西可以交互詰問,作者也承認文字線索有雜訊。它對每張影像擬一個仿射轉換;深度模型 × 虛線尺的 k 是每支片由法定週期量出的一個常數(comma2k19 同一台車不同日期的兩段量到 0.972 / 0.959,`TERRY_RESEARCH_RECORD.md` §11.4)。(舊方法 C 的常數跨段漂 0.1–1.2%,尺度來自組員的時間差法,不放進大專生計畫。)
- ⚠ **審查更正**:Zhan, Mingxia; Zhang, Li; Wang, Beibei; Wang, Yingjie; Shi, Zenglin. "Language as Prior, Vision as Calibration: Metric Scale Recovery for Monocular Depth Estimation." arXiv preprint arXiv:2601.01457, submitted 4 January 2026 (v1), last revised 9 January 2026 (v3). No peer-reviewed venue. https://arxiv.org/abs/2601.01457 Corrected relation: related_work_same_problem_different_anchor (NOT same_depth

### Physics-Grounded Monocular Vehicle Distance Estimation Using Standardized License Plate Typography

- **出處**:arXiv preprint, 14 April 2026
- **作者**:Manognya Lokesh Reddy, Zheng Liu
- **識別碼**:`arXiv:2604.12239`
- **連結**:https://arxiv.org/abs/2604.12239
- **關係判定**:`same_depth_anchoring`　引文屬實:是
- **它做什麼**:Inter-vehicle distance estimation for ADAS that uses the standardised typography of US licence plates (character height, stroke width, spacing) as a passive fiducial for metric ranging, then fuses that geometric distance with a deep depth estimate via inverse-variance weighting and an online scale alignment, followed by a constant-velocity Kalman filter for distance, relative velocity and time-to-collision.
- **與我們的差別**:這是「以法定標準化的場景物體給深度估計加上絕對公尺尺度」最接近的已發表例子。三個具體差別:(i) 錨是**橫向**尺寸,經針孔關係 d = f·W/w 換算,需要已知焦距——現行方法正是不假設焦距,錨因此取沿行進方向的法定虛線週期,並在深度模型的深度裡量;(ii) 它的對齊是逐偵測尺度因子的線上指數移動平均,畫面裡要看得到車牌;現行方法的 k 由路面虛線量出,之後與畫面裡有什麼車無關;(iii) 距離來自字元的外觀尺寸,不是來自目標碰到路面的那一列(深度模型 × 虛線尺讀的是車碰到路面處的深度,空間版方法 C 用 d = A/(py − y_h))。
- ⚠ **審查更正**:引用正確,以下補上原條目缺的細節:Manognya Lokesh Reddy, Zheng Liu. "Physics-Grounded Monocular Vehicle Distance Estimation Using Standardized License Plate Typography." arXiv:2604.12239 [cs.CV; eess.IV]. v1 submitted 14 Apr 2026; v2 20 May 2026; v3 2 Jul 2026 (current). 29 pages, 12 figures. DOI 10.48550/arXiv.2604.12239. 取得來源:https://arxiv.org/abs/2604.…(原紀錄在此截斷)

### Radar Meets Vision: Robustifying Monocular Metric Depth Prediction for Mobile Robotics

- **出處**:arXiv preprint, October 2024 (ETH Zürich, cs.RO)
- **作者**:Marco Job, Thomas Stastny, Tim Kazik, Roland Siegwart, Michael Pantic
- **識別碼**:`arXiv:2410.00736`
- **連結**:https://arxiv.org/html/2410.00736
- **關係判定**:`same_depth_anchoring`　引文屬實:是
- **它做什麼**:Fuses sparse mmWave radar returns with a monocular metric depth network, learning a per-pixel blending weight between the network's own metres and radar-averaged depth. Reports AbsRel for three settings on three validation sets: metric baseline 0.194 / 1.632 / 2.669, naive (global) radar scaling 2.705 / 0.952 / 0.247, their fusion 0.170 / 0.313 / 0.223.
- **與我們的差別**:結構相同——外部公尺量測修正單目深度模型的絕對尺度——但外部量測是車載雷達(鑑識案件預設沒有),修正是學習出的逐像素場,不是由道路幾何取得的單一常數。它顯示單一全域重新縮放在某些場景可能比原始度量輸出差很多,這是對「單一常數」做法最強的已發表警告,現行方法必須回答。目前的回答:品質閘(k 中位數的 95% 區塊 bootstrap 信賴區間半寬 ≤ 3%、左右兩線一致 10%)拒發量不準的片;隨距離變的尺 k(z) 在 2026-09-30 試過,在虛線尺量得到的範圍內比例幾乎固定、沒有改善,尺的範圍外只給距離並標示可能偏近(`TERRY_DEV_LOG.md` 2026-09-30 12:05–12:20)。(舊方法 C 的常數跨段漂 0.1–1.2%,尺度來自組員的時間差法,不放進大專生計畫。)
- ⚠ **審查更正**:Marco Job, Thomas Stastny, Tim Kazik, Roland Siegwart, Michael Pantic, "Radar Meets Vision: Robustifying Monocular Metric Depth Prediction for Mobile Robotics," arXiv:2410.00736v1 [cs.RO], submitted 1 Oct 2024; DOI 10.48550/arXiv.2410.00736; arXiv comments field: "Submitted to ICRA 2025"; all authors: Autonomous Systems Lab, ETH Zürich. 只有 v1,dblp 僅以 CoRR 收錄(找不到 ICRA/IEEE 正式論文集版本),所以「arXiv preprin

### Typography-Based Monocular Distance Estimation Framework for Vehicle Safety Systems

- **出處**:arXiv preprint, 24 March 2026
- **作者**:Manognya Lokesh Reddy, Zheng Liu
- **識別碼**:`arXiv:2603.22781`
- **連結**:https://arxiv.org/abs/2603.22781
- **關係判定**:`same_depth_anchoring (check: overstated)`　引文屬實:是
- **它做什麼**:Earlier companion of the above: licence-plate character height measured by detection plus segmentation, distance computed through the pinhole model, with camera pose compensation from lane-based horizon estimation, hybrid deep-learning fusion, and Kalman filtering. Reports 2.3% coefficient of variation in character height and 7.7% mean absolute error in a controlled indoor setup.
- **與我們的差別**:這是與現行方法元件組合最接近的一篇:唯一同時用到車道線導出的地平線、深度模型與已知法定尺寸的論文。但地平線只拿來補償相機**俯仰**;公尺尺度仍由車牌經針孔模型給出,所以仍需要焦距;驗證是室內受控環境,不是道路鑑識。現行方法的尺度來自沿行進方向的法定虛線週期、在深度模型的深度裡量,結果不依賴焦距;空間版方法 C 的車道線交點則直接進距離公式 d = A/(py − y_h)。
- ⚠ **審查更正**:引用正確;照 arXiv 頁面抄錄:Manognya Lokesh Reddy, Zheng Liu, "Typography-Based Monocular Distance Estimation Framework for Vehicle Safety Systems", arXiv:2603.22781 [cs.CV], submitted 24 Mar 2026, 25 pages / 11 figures, DOI 10.48550/arXiv.2603.22781, no journal reference (preprint, not peer-reviewed). Relation should be downgraded from `same_depth_anchoring` to `

### Zero-Shot Metric Depth Estimation via Monocular Visual-Inertial Rescaling for Autonomous Aerial Navigation

- **出處**:arXiv preprint, 9 September 2025
- **作者**:Steven Yang, Xiaoyu Tian, Kshitij Goel, Wennie Tabib
- **識別碼**:`arXiv:2509.08159`
- **連結**:https://arxiv.org/abs/2509.08159
- **關係判定**:`same_depth_anchoring (check: overstated)`　引文屬實:是
- **它做什麼**:Lightweight zero-shot strategies (including monotonic spline fitting) that rescale relative depth predictions into metric depth using the sparse 3D feature map produced by a visual-inertial navigation system, for collision avoidance on aerial vehicles.
- **與我們的差別**:另一個以外部來源重新縮放深度模型的例子,這次用 VIO 地圖(因 IMU 而有公尺尺度)。它需要 IMU 與執行中的 VIO;現行方法只需要影片與路面上的法定虛線。它在深度範圍上擬單調樣條,而不是單一全域常數;我在 2026-09-30 試過類似的隨距離變的尺 k(z)(二次式),在虛線尺量得到的範圍內沒有改善,不採用(`TERRY_DEV_LOG.md` 2026-09-30 12:05–12:20)。
- ⚠ **審查更正**:Steven Yang, Xiaoyu Tian, Kshitij Goel, Wennie Tabib, "Zero-Shot Metric Depth Estimation via Monocular Visual-Inertial Rescaling for Autonomous Aerial Navigation," arXiv:2509.08159v1 [cs.RO; cs.AI], submitted 9 Sep 2025 (v1, 21:39:13 UTC). URL as given is correct. Relation should be downgraded from "same_depth_anchoring" to "related_concept / different_scale_source": it rescales a RELATIVE-depth n

## 同一應用領域(車速/測距/事故鑑識)

(22 筆)

### A dataset for audio-video based vehicle speed estimation (VS13)

- **出處**:30th Telecommunications Forum (TELFOR) 2022, Belgrade
- **作者**:Slobodan Djukanović, Nikola Bulatović, Ivana Čavor
- **識別碼**:`arXiv:2212.01651`
- **連結**:https://arxiv.org/abs/2212.01651 (dataset page: https://slobodan.ucg.ac.me/science/vs13/)
- **關係判定**:`same_application`　引文屬實:是
- **它做什麼**:400 annotated audio-video recordings of 13 diverse passenger vehicles passing a roadside camera at 30–105 km/h; speeds held by on-board cruise control and used as the annotation.
- **與我們的差別**:三個真實車速資料集中的第三個。真值是車輛自己的定速設定,屬車速表等級、沒有獨立驗證——比 BrnoCompSpeed 的光達光閘與 ForeSpeed 經雷射驗證的車速表弱。路側相機從側面拍攝;沒有距離真值、沒有自車運動、與尺度錨無關,不能用來測現行方法(需要移動相機與路面虛線)。
- ⚠ **審查更正**:S. Djukanović, N. Bulatović, I. Čavor, "A dataset for audio-video based vehicle speed estimation," 2022 30th Telecommunications Forum (TELFOR), Belgrade, Serbia, 15–16 Nov 2022, pp. 1–4. DOI: 10.1109/TELFOR56187.2022.9983773. Preprint arXiv:2212.01651 (submitted 3 Dec 2022). Dataset: https://slobodan.ucg.ac.me/science/vs13/ — Relation: same_application only (roadside single-camera vehicle speed es

### An accurate and practical calibration method for roadside camera using two vanishing points

- **出處**:Neurocomputing 204:222–230, 2016
- **作者**:Xinhua You, Yuan Zheng
- **識別碼**:`DOI 10.1016/j.neucom.2015.09.132`
- **連結**:https://api.openalex.org/works?search=An%20accurate%20and%20practical%20calibration%20method%20for%20roadside%20camera%20using%20two%20vanishing%20points
- **關係判定**:`same_application`　引文屬實:否(僅摘要可讀)
- **它做什麼**:Two vanishing points (road direction from lane markings, vertical from poles/pedestrians) estimated by least squares over many video observations; intrinsics and rotation follow, and the translation (scale) is fixed by a known length on the road or a known camera height above the road.
- **與我們的差別**:尺度靠人工提供——測量的路段長度或量測的掛高;固定相機。它清楚說明這批文獻的縱向錨是要有人到現場量的東西。現行方法的縱向錨是法定虛線週期(不必到現場),並在深度模型的深度裡量、用來定模型的尺度。已核對:ScienceDirect 拒絕存取,未取得全文;DOI、期刊、卷期、頁碼已確認。
- ⚠ **審查更正**:CITATION (as given — verified correct, no change needed): Xinhua You, Yuan Zheng, "An accurate and practical calibration method for roadside camera using two vanishing points", Neurocomputing 204:222-230, 2016. DOI 10.1016/j.neucom.2015.09.132. THE QUOTE MUST BE RE-ATTRIBUTED. Its actual source is a DIFFERENT paper by DIFFERENT authors: Yuan Zheng, Silong Peng, "A Practical Roadside Camera Calibra

### Analysis of video recordings in accident reconstruction

- **出處**:Archives of Transport, vol. 69, no. 1, 2024, pp. 127–143
- **作者**:Michał Mariusz Abramowski, Andrzej Reński
- **識別碼**:`10.61089/xvvscd77`
- **連結**:https://www.archivesoftransport.com/index.php/aot/article/view/19
- **關係判定**:`same_application`　引文屬實:是
- **它做什麼**:Survey/methods paper on quantitative analysis of video from both fixed cameras and vehicle-mounted DVRs for accident reconstruction, covering speeds, accelerations and directions of motion, the extra difficulty of a camera moving with the vehicle, the influence of recording quality (resolution, distortion, sharpness, frame rate) on usability, and a method for estimating the uncertainty of the results.
- **與我們的差別**:取回的文獻裡唯一明言可在不知相機參數下分析、並把移動相機當成獨立問題的鑑識領域論文——與現行方法面對的兩個限制相同(相機未知、相機在動)。已核對:期刊 PDF 連結 404,未取得全文,無法判斷它用什麼尺度來源,不宣稱它有或沒有用標線;僅就摘要看,沒有提到標線週期、A = h·f 或任何學習式深度模型,取向是人工定量分析而不是自動化流程。
- ⚠ **審查更正**:Citation line is correct exactly as given; no correction needed: Abramowski, M.M., Reński, A. (2024). "Analysis of video recordings in accident reconstruction." Archives of Transport, 69(1), 127-143. https://doi.org/10.61089/xvvscd77 (ISSN 0866-9546 / e-ISSN 2300-8830, CC BY 4.0, Warsaw University of Technology). Relation label "same_application" is CONFIRMED and is the right label. It is NOT same

### Assessing the influence of variables on vehicle speed determination through reverse projection analysis

- **出處**:Science & Justice, vol. 66, no. 1, 2026, article 101369
- **作者**:Walter E. Bruehs, Dorothy Stout
- **識別碼**:`10.1016/j.scijus.2025.101369`
- **連結**:https://api.crossref.org/works?query.bibliographic=Assessing+the+influence+of+variables+on+vehicle+speed+determination+through+reverse+projection+analysis
- **關係判定**:`same_application`　引文屬實:是
- **它做什麼**:Follow-up to the 2022 JFS validation, extending it to assess how individual variables influence the vehicle-speed result obtained by reverse projection analysis.
- **與我們的差別**:最新的鑑識領域影片測速誤差預算研究,是現行方法報告不確定度時的自然比較對象;但仍是固定相機、需要到現場的反投影。已核對:ScienceDirect 回應 403,只核對了 Crossref 紀錄(DOI、作者、期刊、卷期、文章編號),未讀到摘要或變數清單,不宣稱它的結論。
- ⚠ **審查更正**:Nothing was wrong. Verified citation, in full: Walter E. Bruehs, Dorothy Stout, "Assessing the influence of variables on vehicle speed determination through reverse projection analysis", Science & Justice 66(1):101369, January 2026 (epub 2025-12-03), doi:10.1016/j.scijus.2025.101369, PMID 41506828. Affiliations: FBI Digital Forensic Analysis Unit, Forensic Audio, Video and Image Analysis Program, 

### AutoCalib: Automatic Traffic Camera Calibration at Scale

- **出處**:ACM BuildSys 2017 (also ACM Transactions on Sensor Networks 14(3–4), 2018)
- **作者**:Romil Bhardwaj, Gopi Krishna Tummala, Ganesan Ramalingam, Ramachandran Ramjee, Prasun Sinha
- **識別碼**:`DOI 10.1145/3199667 (TOSN version)`
- **連結**:https://www.microsoft.com/en-us/research/wp-content/uploads/2017/09/AutoCalib.pdf
- **關係判定**:`same_application`　引文屬實:是
- **它做什麼**:Deliberately abandons vanishing points and road features; uses a CNN to extract car key-points, solves calibration per vehicle from known car geometry, then filters and aggregates hundreds of noisy per-vehicle calibrations. Under 12% real-world distance error on city traffic cameras.
- **與我們的差別**:明確反對以道路標線等靜態特徵當錨(「靜態特徵的尺寸可能因道路、依城市而不同」)——與現行方法的立場相反:法定標準讓標線在鑑識場合可稽核;不同轄區的週期不同,但都有法規可查(台灣 10 m、聯邦 MUTCD 12.19 m、加州高速公路 14.63 m)。固定相機、以車輛幾何定尺度、沒有深度模型。
- ⚠ **審查更正**:Nothing was wrong. Verified citation line (with one added precision): Romil Bhardwaj, Gopi Krishna Tummala, Ganesan Ramalingam, Ramachandran Ramjee, Prasun Sinha. "AutoCalib: Automatic Traffic Camera Calibration at Scale." Proc. 4th ACM Int. Conf. on Systems for Energy-Efficient Built Environments (BuildSys '17), Delft, Nov 6-8 2017, pp. 1-10, DOI 10.1145/3137133.3137149; extended version ACM Tran

### Automatic Camera Calibration for Traffic Understanding

- **出處**:BMVC 2014
- **作者**:Markéta Dubská, Adam Herout, Jakub Sochor
- **連結**:https://bmva-archive.org.uk/bmvc/2014/papers/paper013/index.html
- **關係判定**:`same_application`　引文屬實:是
- **它做什麼**:Three vanishing points (vehicle motion via KLT + diamond-space accumulator, vehicle edges, vertical) calibrate a surveillance camera up to scale; scale is then fixed by matching the statistics of constructed 3D vehicle bounding-box dimensions against known mean vehicle dimensions for the country. Reports under 2% mean speed and distance error.
- **與我們的差別**:「該國平均車輛尺寸」的錨是統計量,只在整體上成立,不能為單一車輛的速度背書,而鑑識要的正是單一車輛。固定相機;沒有標線長度、沒有自車速、沒有深度模型。
- ⚠ **審查更正**:Markéta Dubská, Adam Herout, Jakub Sochor. "Automatic Camera Calibration for Traffic Understanding." Proceedings of the British Machine Vision Conference (BMVC) 2014, BMVA Press. DOI 10.5244/C.28.42. [Venue BibTeX gives no page numbers. Note: the camera-ready PDF's printed byline and running header order is Dubská, Sochor, Herout — the venue metadata and dblp both use Dubská, Herout, Sochor as cit

### Calibration-Free Vehicle Speed Estimation: A Monocular Keypoint-Template Approach

- **出處**:arXiv preprint, 17 August 2026
- **作者**:Gaofeng Su, Keya Li, Raja Sengupta, Kara M. Kockelman
- **識別碼**:`arXiv:2608.16785`
- **連結**:https://arxiv.org/abs/2608.16785
- **關係判定**:`same_application`　引文屬實:是
- **它做什麼**:Estimates speed without camera calibration or roadway features, using a 36-keypoint vehicle template and a per-frame homography; evaluated on 400+ clips from VS13 and BrnoCompSpeed, 30–100 mph. MAE 15.0% (VS13) and 9.7% (BrnoCompSpeed); 77.9% / 93.1% of estimates within ±20%, improving to 11.7% / 7.6% after outlier removal.
- **與我們的差別**:刻意完全不用道路幾何錨——尺度來自通用車形模板(「已知物體尺寸」這一類),精度(約 10–15% MAE)比標線錨定的方法寬一個數量級。只有固定相機。它也確認截至 2026 年這個任務的評估集仍是 VS13 + BrnoCompSpeed,兩者都是路側相機,不能用來測現行方法。
- ⚠ **審查更正**:引用不需更正。arXiv 頁面上的標準格式:Gaofeng Su, Keya Li, Raja Sengupta, Kara M. Kockelman, "Calibration-Free Vehicle Speed Estimation: A Monocular Keypoint-Template Approach", arXiv:2608.16785v1 [cs.CV], submitted 2026-08-17T16:39:06Z, 19 pages, 7 figures, no journal reference or DOI. Relation: same_application is correct and should NOT be upgraded. Tw

### Camera-based vehicle velocity estimation from monocular video

- **出處**:Computer Vision Winter Workshop (CVWW) 2018; winning entry, CVPR 2017 Autonomous Driving Velocity Estimation Challenge
- **作者**:Moritz Kampelmühler, Michael G. Müller, Christoph Feichtenhofer
- **識別碼**:`arXiv:1802.07094`
- **連結**:https://arxiv.org/abs/1802.07094 (PDF read: https://arxiv.org/pdf/1802.07094)
- **關係判定**:`same_application`　引文屬實:是
- **它做什麼**:Regresses relative velocity of annotated target vehicles from monocular dashcam clips using tracking, optical-flow and depth features. Documents the TuSimple velocity dataset: 1074 freeway sequences, 1280×720 at 20 fps, 40 frames each, 1442 annotated vehicles with position and velocity ground truth from range sensors, split into near (<20 m, ~12%), medium (20–45 m, ~65%) and far (>45 m, ~23%) evaluation bins. Reports 1.12 m/s average error against a stated ~0.71 m/s ground-truth accuracy; challenge leaderboard velocity MSE near 0.18, medium 0.66, far 3.07 m²/s².
- **與我們的差別**:唯一與現行方法的前車評估量同一件事的公開基準——移動單目相機量目標車的距離與速度,以光達 + 雷達驗證,並按距離分層。但它量的是**相對**速度,自車速這一環不會被測到;真值只在最後一幀,沒有時間連續性評估;方法是在同一款相機上訓練的學習式回歸,沒有校正、沒有尺度錨,也沒有會出錯的公尺幾何。它也給出這類驗證的誠實上限:參考感測器本身只準到約 0.71 m/s。
- ⚠ **審查更正**:Citation is correct as given; only tightened wording is needed. Verified form: Moritz Kampelmühler, Michael G. Müller, Christoph Feichtenhofer, "Camera-based vehicle velocity estimation from monocular video", in Zuzana Kúkelová and Júlia Škovierová (eds.), Proceedings of the 23rd Computer Vision Winter Workshop (CVWW 2018), Český Krumlov, Czech Republic, February 5–7, 2018, 8 pp.; arXiv:1802.07094

### Comprehensive Data Set for Automatic Single Camera Visual Speed Measurement (BrnoCompSpeed)

- **出處**:IEEE Transactions on Intelligent Transportation Systems, 2018/2019
- **作者**:Jakub Sochor, Roman Juránek, Jakub Špaňhel, Lukáš Maršík, Adam Široký, Adam Herout, Pavel Zemčík
- **識別碼**:`arXiv:1702.06441; DOI 10.1109/TITS.2018.2825609`
- **連結**:https://arxiv.org/abs/1702.06441
- **關係判定**:`same_application`　引文屬實:是
- **它做什麼**:18 full-HD hour-long videos at six sites, 20,865 annotated vehicles with LiDAR optical-gate speed ground truth plus GPS verification, released with calibration and measured in-image lengths. Section II is an explicit survey (Table I) classifying every prior calibration method by what it uses for scale.
- **與我們的差別**:本領域權威的分類,只有兩個尺度家族——場景內一段已知距離(常是標線線段)與車輛尺寸;沒有一個家族涉及移動相機、自車速或深度網路,同一張表裡也沒有以深度網路取得尺度的方法。資料集只有路側相機,不能用來測現行方法(行車紀錄器、需要路面虛線)。
- ⚠ **審查更正**:J. Sochor, R. Juránek, J. Špaňhel, L. Maršík, A. Široký, A. Herout, P. Zemčík, "Comprehensive Data Set for Automatic Single Camera Visual Speed Measurement," IEEE Transactions on Intelligent Transportation Systems, vol. 20, pp. 1633–1643, 2019 (early access 2018). DOI 10.1109/TITS.2018.2825609; arXiv:1702.06441 (v1 2017-02-21, v2 2018-05-09). Relation: same_application (monocular-camera vehicle sp

### Detection of 3D bounding boxes of vehicles using perspective transformation for accurate speed measurement

- **出處**:Machine Vision and Applications, 2020
- **作者**:Viktor Kocur, Milan Ftáčnik
- **識別碼**:`arXiv:2003.13137; DOI 10.1007/s00138-020-01117-x`
- **連結**:https://arxiv.org/abs/2003.13137
- **關係判定**:`same_application`　引文屬實:是
- **它做什麼**:Improves 3D vehicle bounding-box detection and tracking for speed measurement by using the known vanishing-point geometry of the surveilled scene to build a perspective transformation; evaluated on BrnoCompSpeed.
- **與我們的差別**:消失點與場景尺度都直接取自資料集提供的標定,工作在偵測/追蹤端。固定相機,沒有自己的尺度錨、沒有標線、沒有自車運動、沒有深度模型;列入是為了說明這條線的近期工作已轉向偵測品質,尺度問題留給 BrnoCompSpeed 提供的標定。
- ⚠ **審查更正**:Citation is correct; only made more precise: Viktor Kocur, Milan Ftáčnik, "Detection of 3D bounding boxes of vehicles using perspective transformation for accurate speed measurement", Machine Vision and Applications, vol. 31, no. 7-8, article 62, 2020 (online 2020-09-04). DOI 10.1007/s00138-020-01117-x; preprint arXiv:2003.13137 (v1 2020-03-29, v2 2020-08-04). Relation "same_application" stands an

### Determination of average vehicle speed utilizing reverse projection

- **出處**:Journal of Forensic Sciences, vol. 67, no. 1, 2022 (online 8 Oct 2021), pp. 188–199
- **作者**:Walter E. Bruehs, Dorothy Stout
- **識別碼**:`10.1111/1556-4029.14891`
- **連結**:https://api.crossref.org/works/10.1111/1556-4029.14891
- **關係判定**:`same_application`　引文屬實:是
- **它做什麼**:Controlled validation of reverse projection photogrammetry for vehicle speed: five digital video recorders captured a vehicle on a track with speed verified by Doppler radar and speedometer; frames were selected to establish vehicle position at two points and distance/time computed.
- **與我們的差別**:在受控條件下、以外部真值儀器(都卜勒雷達)記錄既有做法精度的研究——與現行方法用 comma2k19 原廠雷達、AV2 光達 3D 框與海盛人工畫格法當真值的角色相同。它是固定相機、需要到現場的反投影;沒有標線尺度錨、沒有消失點測距公式、沒有移動相機、沒有深度模型。已核對:只經 Crossref 取得書目資料與部分引用的摘要,未取得全文。
- ⚠ **審查更正**:No correction needed — every field matches. Canonical form for the bibliography: Bruehs, W. E., & Stout, D. (2022). Determination of average vehicle speed utilizing reverse projection. Journal of Forensic Sciences, 67(1), 188-199. https://doi.org/10.1111/1556-4029.14891 (first published online 8 October 2021; PMID 34622955). Relation stands as same_application. Two minor presentational notes: (a) 

### Evaluation of Tesla Dashcam Video System for Speed Determination Via Reverse Projection Photogrammetry

- **出處**:SAE Technical Paper 2023-01-0629, 2023
- **作者**:Benjamin T. Molnar, Louis R. Peck
- **識別碼**:`10.4271/2023-01-0629`
- **連結**:https://saemobilus.sae.org/papers/evaluation-tesla-dashcam-video-system-speed-determination-via-reverse-projection-photogrammetry-2023-01-0629
- **關係判定**:`same_application`　引文屬實:是
- **它做什麼**:Calibrates a 2019 Tesla Model 3's front and rear cameras for focal length and lens distortion, then determines (a) host-vehicle speed from the distance between solved camera locations in a time-distance analysis and (b) surrounding-vehicle speed by reverse projection against a point cloud of the approaching vehicle, with the Tesla stationary. Compared against onboard GPS: mean difference 0.38–0.72 mph across all tests.
- **與我們的差別**:以行車紀錄器等級相機量**他車**的最接近鑑識研究,也是精度要超越的數字。但每一個成立條件都與現行方法的情境相反:相機事先實際取得並標定了焦距與畸變;目標速度由該車的 3D 點雲反投影取得;他車測試時本車**靜止**,完全沒有移動相機的測距問題。沒有標線尺度、沒有深度模型。
- ⚠ **審查更正**:引用完全正確,不需更正。SAE 官方引用字串(照 SAE Mobilus 頁面原文):Molnar, B. and Peck, L., "Evaluation of Tesla Dashcam Video System for Speed Determination Via Reverse Projection Photogrammetry," WCX SAE World Congress Experience, Detroit, Michigan, United States, April 18, 2023, https://doi.org/10.4271/2023-01-0629. 補齊細節:SAE Technical Paper Series 2023-01-0629,線上出版日 2023-04-11,作者單位 Benjamin T. Molnar(J.S. Held, LLC)、L

### ForeSpeed: A real-world video dataset of CCTV cameras with different settings for vehicle speed estimation

- **出處**:arXiv preprint, 22 December 2025
- **作者**:Massimo Iuliani, Blake Sawyer, Marco Fontani, David Spreadborough, Martino Jerian (Amped Software)
- **識別碼**:`arXiv:2512.19364`
- **連結**:https://arxiv.org/abs/2512.19364 (PDF read: https://arxiv.org/pdf/2512.19364)
- **關係判定**:`same_application`　引文屬實:是
- **它做什麼**:A new public dataset built specifically for forensic speed estimation: one vehicle driven at known speeds (29–31 mph) past three digital and three analog CCTV cameras on three DVRs, exported in multiple codecs/containers/frame-rate modes (including variable frame rate), 269 passes / 322 videos, plus surveyed road reference measures so the analyst can rectify the road plane. Speed truth = speedometer plus an independent GPS app, both filmed by a separate camera, with the speedometer itself validated against a laser speed sensor. Case study benchmarks the manual Amped FIVE method: mean error −0.96 mph, 85% of cases within ±2 mph, with uncertainty boxes on tyre–road contact points and Δt = 5 ms.
- **與我們的差別**:鑑識框架相同、也用輪胎—路面接觸點,但它是固定 CCTV 資料集與人工、需要現場測量的流程:路面由現場量的地面格線尺寸校正,事故鑑識事後做不到。沒有自車相機、沒有標線錨、沒有深度模型,真值只有目標車自己的速度,完全沒有距離真值。它是 2024 年「只有三個」之後出現的第四個公開真實車速資料集。
- ⚠ **審查更正**:Citation line (verified, use as-is): Massimo Iuliani, Blake Sawyer, Marco Fontani, David Spreadborough, Martino Jerian. "ForeSpeed: A real-world video dataset of CCTV cameras with different settings for vehicle speed estimation." arXiv:2512.19364v1 [eess.IV], submitted 22 Dec 2025. DOI 10.48550/arXiv.2512.19364. No journal-ref, no comments. Affiliations: Amped Software (Trieste, Italy) and Amped S

### Forensic application of inverse and reverse projection photogrammetry to determine subject location and orientation when both camera and subject move relative to the scene

- **出處**:Forensic Science International, vol. 331, 2022, article 111145
- **作者**:Geoffrey T. Desmoulin, Manraj Kalkat, Theodore E. Milner
- **識別碼**:`10.1016/j.forsciint.2021.111145`
- **連結**:https://api.semanticscholar.org/graph/v1/paper/DOI:10.1016/j.forsciint.2021.111145
- **關係判定**:`same_application`　引文屬實:是
- **它做什麼**:Handles the forensic case where BOTH the camera and the subject move relative to the scene (a chest-mounted action camera on a mountain bicycle). Inverse photogrammetry establishes the location and orientation of the camera relative to the scene; reverse projection with a reference bicycle placed in the scene fixes the bike-to-camera relationship; rider placement is estimated by comparing synchronised side views with the chest-camera view from a preceding descent.
- **與我們的差別**:鑑識領域對「相機與對象都在動」問題的已發表解法,也顯示那個解法的代價:要到現場、在現場擺實體參考物、另外拍一次同一對象的參考行程。現行方法只用畫面裡本來就有的法定虛線。沒有標線週期、沒有由道路幾何取得的尺度錨、沒有深度模型。已核對:DOI、期刊、卷、頁經 Crossref 確認,並讀了 Semantic Scholar 紀錄;出版社摘要頁回應 403,引文是該紀錄的片段,不是論文的完整句子。
- ⚠ **審查更正**:不需更正。照 Crossref 與 Semantic Scholar 紀錄抄錄的標準引用:Geoffrey T. Desmoulin, Manraj Kalkat, Theodore E. Milner, "Forensic application of inverse and reverse projection photogrammetry to determine subject location and orientation when both camera and subject move relative to the scene," Forensic Science International, vol. 331, Feb. 2022, art. 111145. DOI: 10.1016/j.fors

### Multi-Stream Attention Learning for Monocular Vehicle Velocity and Inter-Vehicle Distance Estimation (MSANet)

- **出處**:BMVC 2021
- **作者**:Kuan-Chih Huang, Yu-Kai Huang, Winston H. Hsu
- **識別碼**:`arXiv:2110.11608`
- **連結**:https://arxiv.org/abs/2110.11608 (PDF read: https://arxiv.org/pdf/2110.11608)
- **關係判定**:`same_application`　引文屬實:是
- **它做什麼**:Best published numbers found in this survey on the TuSimple velocity dataset: position MSE 7.56 m², velocity MSE 0.10 / 0.26 / 1.58 m²/s² for near / medium / far, and inter-vehicle distance AbsRel 0.034, SqRel 0.105, RMSE 2.416 m, δ<1.25 = 0.997.
- **與我們的差別**:給出現行方法前車距離該對照的數字:移動相機、光達 + 雷達真值下 3.4% AbsRel——但它在同一款相機、同一個高速公路領域上監督訓練,接觸點定義為「每台車最近的點」而不是輪胎著地列,沒有相機幾何、沒有尺度錨、沒有跨裝置轉移。這裡沒有零樣本做法,也沒有處理未知焦距。
- ⚠ **審查更正**:CITATION STANDS AS GIVEN — nothing to correct. Verified copy-able form: Kuan-Chih Huang, Yu-Kai Huang, Winston H. Hsu. "Multi-Stream Attention Learning for Monocular Vehicle Velocity and Inter-Vehicle Distance Estimation." British Machine Vision Conference (BMVC) 2021, paper 0606. arXiv:2110.11608 (submitted 22 Oct 2021; arXiv Comments field reads "Accepted to BMVC 2021"). National Taiwan Universi

### Real-time Prediction of Automotive Collision Risk from Monocular Video

- **出處**:arXiv preprint, 2019
- **作者**:Derek J. Phillips, Regina Madigan, Juan Carlos Aragon, Sunil Chintakindi, Anjali Roychowdhury, Mykel J. Kochenderfer
- **識別碼**:`arXiv:1902.01293`
- **連結**:https://ar5iv.labs.arxiv.org/html/1902.01293
- **關係判定**:`same_application (check: understated)`　引文屬實:是
- **它做什麼**:A monocular collision-risk pipeline whose absolute-speed component uses lane markings of known dimensions as stationary references instead of optical flow: it detects the reference lanes, watches a vertically fixed point on the lane, times how long a marking takes to appear, disappear and appear again, and converts that with the known marking spacing into ego speed.
- **與我們的差別**:與組員 chennnlee 的標線碼表(`dashcam_range_speed.py`,固定影像列上標線訊號的時間週期)物理原理相同;我的自車速不用固定影像列計時,而是在深度模型經 k 校正的公尺剖面上量虛線邊緣在相隔幾幀之間的平移。本篇以邊緣/外觀事件計時、只用一個固定點,不取任何尺度常數;自車速只用於風險預測,不拿來校正測距,也沒有重新縮放深度網路。
- ⚠ **審查更正**:Derek J. Phillips, Regina Madigan, Juan Carlos Aragon, Sunil Chintakindi, Anjali Roychowdhury, Mykel J. Kochenderfer, "Real-time Prediction of Automotive Collision Risk from Monocular Video", arXiv:1902.01293, submitted 4 Feb 2019. arXiv comments field: "Submitted to IV2019. 7 pages, 4 figures, 3 tables"; arXiv 上沒有 journal-ref,也查不到它收錄於 IV 2019 論文集的證據,…(原紀錄在此截斷)

### Robust video-based vehicle speed estimation for occluded scenes for forensic analysis of traffic accidents

- **出處**:Multimedia Tools and Applications, 2026
- **作者**:Youngsoo Choi, Seung-Hyun Kong
- **識別碼**:`10.1007/s11042-026-21222-9`
- **連結**:https://api.crossref.org/works/10.1007/s11042-026-21222-9
- **關係判定**:`same_application`　引文屬實:是
- **它做什麼**:Estimates vehicle speed from fixed-camera footage with no prior camera or scene information, even under full occlusion of parts of the trajectory. SiamRPN tracking + Kalman filtering for occlusions, Mask R-CNN instance segmentation to extract wheel centres, a smoothed unscented Kalman filter to predict occluded wheel coordinates, and speed from the geometric CROSS-RATIO (a perspective-invariant distance ratio) combined with the known wheelbase specification. Errors: 0.30 and 1.70 km/h in straight/curved simulation, 0.41 km/h constant-speed and 0.57 km/h accelerating real tests, 0.49–3.05 km/h on real accident cases vs field measurements.
- **與我們的差別**:近期鑑識論文中「不需要相機或場景的任何先驗」最強的宣稱,是新穎性論證必須區分的對象。區分很清楚:尺度錨是**目標車**的已知軸距(要先辨識車型、取得規格,是被量物體的性質,不是道路的性質);幾何是投影交比,不是地面測距公式;固定相機;沒有深度模型。軸距是沿行進方向的長度,這也是交比能用的原因——現行方法的錨(法定虛線週期)同樣沿行進方向。
- ⚠ **審查更正**:Citation is correct; only added precision, nothing changed. Full form: Youngsoo Choi and Seung-Hyun Kong, "Robust video-based vehicle speed estimation for occluded scenes for forensic analysis of traffic accidents," Multimedia Tools and Applications, vol. 85, no. 2, article 90, published 2 February 2026. DOI: 10.1007/s11042-026-21222-9. Landing page: https://link.springer.com/article/10.1007/s1104

### Speed Analysis from Video: A Method for Determining a Range in the Calculations

- **出處**:SAE Technical Paper 2021-01-0887, 2021
- **作者**:Gray Beauchamp, David Pentecost, Daniel Koch, Alireza Hashemian, James Marr, Rheana Cordero
- **識別碼**:`10.4271/2021-01-0887`
- **連結**:https://saemobilus.sae.org/papers/speed-analysis-video-a-method-determining-a-range-calculations-2021-01-0887
- **關係判定**:`same_application`　引文屬實:是
- **它做什麼**:Gives a procedure for reporting vehicle speed from video as a RANGE rather than a point value, propagating two uncertainty sources: uncertainty in locating the vehicle's position (from photogrammetry best-fit) and uncertainty in the time interval between positions. Validated against recordings of an instrumented vehicle at known speeds.
- **與我們的差別**:鑑識領域報告車速的範本(以範圍呈現並列出各成分)。組員 chennnlee 的管線 A 以擬合標準誤 ⊕ 尺度 CV 報 ±95% 信賴區間,與此類似,但沒有拿真值檢驗覆蓋率。我的封存版(2026-09-29)只報 k 的 95% 區塊 bootstrap 信賴區間(當品質閘用);第二版(`docs/DEPTH_DASH_V2_PREREG.md`,草稿)為每個速度附上 95% 範圍,放大倍數在一段開發片上定、另一段驗證覆蓋率。本篇在尺度錨上沒有創新:位置來自對現場的一般相機匹配攝影測量;沒有標線、沒有深度模型。
- ⚠ **審查更正**:No correction needed. Exact citation as the publisher page gives it: Beauchamp, G., Pentecost, D., Koch, D., Hashemian, A., Marr, J., and Cordero, R., "Speed Analysis from Video: A Method for Determining a Range in the Calculations," SAE Technical Paper 2021-01-0887, SAE WCX Digital Summit, published 2021-04-06, doi:10.4271/2021-01-0887 (all authors Kineticorp LLC). Relation stands as same_applica

### Speed Determination Using Audio Analysis of Dash Camera Video from Passenger Vehicle Tires Frequencies for Vehicle Accident Reconstruction

- **出處**:SAE Technical Paper 2025-01-8682, 2025
- **作者**:Henry V. Vega, Long Justin Ngo, Ziad Hatab, Anthony Cornetto, Krystina Engleman, Eric Hunter
- **識別碼**:`10.4271/2025-01-8682`
- **連結**:https://saemobilus.sae.org/papers/speed-determination-using-audio-analysis-dash-camera-video-passenger-vehicle-tires-frequencies-vehicle-accident-reconstruction-2025-01-8682
- **關係判定**:`same_application`　引文屬實:是
- **它做什麼**:Determines ego speed from the AUDIO track of dashcam video: the tyre tread pattern in contact with the roadway generates a frequency component that varies with speed. Uses commercial dashcams, remote microphones to localise the frequency source and a VBox Sport for ground-truth speed; prior work in the same line used audio plus a known wheelbase.
- **與我們的差別**:值得知道,因為它是鑑識實務中另一個「以週期當里程計」的想法——已知物理週期(輪胎周長/胎紋節距)讀成頻率——動機也是不信任光流(現行方法的自車速同樣不用光流)。但週期訊號是聲學、由車輛本身產生,取決於輪胎與路面而不是道路幾何,只給自車速,對距離、尺度或深度沒有貢獻。已核對:取得的摘要頁沒有列出精度數字。
- ⚠ **審查更正**:無需更正。經 Crossref 獨立核對後的標準引用行為:Vega, H. V., Ngo, L. J., Hatab, Z., Cornetto, A., Engleman, K., & Hunter, E. (2025). "Speed Determination Using Audio Analysis of Dash Camera Video from Passenger Vehicle Tires Frequencies for Vehicle Accident Reconstruction." SAE Technical Paper 2025-01-8682, SAE International, published 2025-04-01. DOI: 10.4271/2025-01-8682. 關係標籤 same_application 維持不變(非 same_method、非

### The Accuracy of Vehicle Speeds, Decelerations, and Brake Onset Times Calculated from Onboard Dash Cameras

- **出處**:SAE Technical Paper 2025-01-8691, 2025
- **作者**:Thomas Flynn, Matthew Ahrens, Cole Young, Gunter P. Siegmund
- **識別碼**:`10.4271/2025-01-8691`
- **連結**:https://saemobilus.sae.org/papers/accuracy-vehicle-speeds-decelerations-brake-onset-times-calculated-onboard-dash-cameras-2025-01-8691
- **關係判定**:`same_application`　引文屬實:是
- **它做什麼**:Quantifies dashcam-derived kinematics across five cameras using match-moving, with scale and location supplied by a 3D laser scan of the test site. Speed estimates ranged from underestimating by 0.45 ± 0.05 km/h to overestimating by 0.80 ± 0.16 km/h; deceleration from −0.012 ± 0.013 g to +0.049 ± 0.012 g; brake onset detection lagged actual brake application by 14 ± 41 ms to 94 ± 29 ms.
- **與我們的差別**:鑑識實務中由行車紀錄器求自車運動學的現行最佳做法,次 1 km/h 的數字是自車速方法該對照的誠實基準(組員 chennnlee 的標線碼表、我由虛線尺求的自車速都要拿來比)。我的自車速目前在海盛 002 / 006 對人工畫格法 MAE 1.36 / 3.62 km/h(2026-09-29 封存),2026-09-30 改用虛線邊緣平移的開發版 1.38 / 1.70(答案已開過,`TERRY_DEV_LOG.md`),仍比這個基準寬。決定性的差別是它的公尺尺度完全來自現場的 3D 雷射掃描——現場必須到得了、掃得了;它是對一般場景特徵做相機追蹤/匹配移動,不是週期標線量測,只報自車運動,沒有目標距離、沒有深度模型。
- ⚠ **審查更正**:Flynn, T., Ahrens, M., Young, C., and Siegmund, G.P., "The Accuracy of Vehicle Speeds, Decelerations, and Brake Onset Times Calculated from Onboard Dash Cameras," SAE Technical Paper 2025-01-8691, WCX SAE World Congress Experience, Detroit, MI, April 8, 2025 (publication date listed as 2025-04-01), doi:10.4271/2025-01-8691. Relation: same_application only — a forensic-practice accuracy benchmark f

### The Effect of Tracker and Control Point Distributions on Vehicle Position and Speed Estimates from Dash Camera Video

- **出處**:SAE Technical Paper 2025-01-8697, 2025
- **作者**:Cole Young, Matthew Ahrens, Thomas Flynn, Gunter P. Siegmund
- **識別碼**:`10.4271/2025-01-8697`
- **連結**:https://saemobilus.sae.org/papers/effect-tracker-control-point-distributions-vehicle-position-speed-estimates-dash-camera-video-2025-01-8697
- **關係判定**:`same_application`　引文屬實:是
- **它做什麼**:Degrades the available 2D trackers and 3D control points in SynthEyes camera-tracking solutions of a dashcam braking run to mimic feature-poor environments. For six of eight test conditions the camera solutions had mean absolute position errors of 32–119 mm and speed errors <1 km/h against the full-feature reference; one condition failed to solve and one with few, poorly distributed control points had larger errors.
- **與我們的差別**:它是主流替代做法的失效邊界研究:場景貧乏時公認的行車紀錄器做法會退化,而只剩路面與標線的空曠高速公路正是這種情境——現行方法在那裡仍可運作,因為標線本身就是特徵(反過來,沒有法定虛線的路段現行方法會拒發)。但它仍需要場景內的 3D 控制點與參考解,不是尺度錨定的幾何方法,沒有深度模型。
- ⚠ **審查更正**:Citation is correct as given; no correction needed. Canonical form: Young, C., Ahrens, M., Flynn, T., and Siegmund, G.P., "The Effect of Tracker and Control Point Distributions on Vehicle Position and Speed Estimates from Dash Camera Video," SAE Technical Paper 2025-01-8697, 2025, doi:10.4271/2025-01-8697 (WCX SAE World Congress Experience, Detroit, 1 April 2025; MEA Forensic Engineers & Scientist

### Traffic Surveillance Camera Calibration by 3D Model Bounding Box Alignment for Accurate Vehicle Speed Measurement

- **出處**:Computer Vision and Image Understanding, 2017
- **作者**:Jakub Sochor, Roman Juránek, Adam Herout
- **識別碼**:`arXiv:1702.06451; DOI 10.1016/j.cviu.2017.05.015`
- **連結**:https://arxiv.org/abs/1702.06451
- **關係判定**:`same_application`　引文屬實:是
- **它做什麼**:Fully automatic roadside calibration: two vanishing points from tracked keypoints and vehicle edgelets, then scene scale by rendering 3D CAD models of fine-grained-classified vehicles and matching their projected bounding boxes to the detected ones. 1.10 km/h mean speed error on BrnoCompSpeed, beating the authors' own manual calibration (1.35 km/h).
- **與我們的差別**:尺度來自車輛 CAD 尺寸,也就是由被量的物體提供尺;鑑識上目標車型可能未知或有爭議,所以現行方法不採用這種錨。固定相機、沒有自車運動、沒有標線週期、沒有深度模型。它自己的 ManualCalib 基準線用的是現場測量的路面距離——現行方法以法定虛線週期取代的正是這種現場測量。論文也確認以車道分隔線交點求第一個消失點是古典做法(原文 "in agreement with the previous papers"),空間版方法 C 的地平線屬於這個古典做法。
- ⚠ **審查更正**:No correction required. Complete citation line (volume/pages added for completeness, confirmed against the BUT FIT publication record): Sochor, J.; Juránek, R.; Herout, A. "Traffic surveillance camera calibration by 3D model bounding box alignment for accurate vehicle speed measurement." Computer Vision and Image Understanding, 2017, vol. 161, pp. 87-98. ISSN 1077-3142. DOI 10.1016/j.cviu.2017.05.

## 未能完成驗證(引用前必須自行取回)

- **MapAnything: Evaluating Monocular Metric Depth Models for 3D Urban Asset Localization**　(depth-anchor)　https://arxiv.org/abs/2509.14839
  - 原因:已取得 https://arxiv.org/abs/2509.14839 的 abs 頁(v1/v2/v3)與 v3 全文 HTML(256 KB)並做全文搜尋;原紀錄在此截斷,沒有留下結論。
- **Determination of Vehicle Speed from Recorded Video Using Reverse Projection Photogrammetry and File Metadata**　(forensic)　https://brycewestlake.com/wp-content/uploads/2021/03/Westlake-JForensicSci-Determination-of-Vehicle-Speed-Epstein-Westlake-2019_stamped.pdf
  - 原因:查核未取得結果
- **Simulation-based reconstruction of traffic incidents from moving vehicle mono-camera**　(forensic)　https://api.crossref.org/works?query.bibliographic=Simulation-based+reconstruction+of+traffic+incidents+from+moving+vehicle+mono-camera
  - 原因:已從三個獨立來源取得紀錄,第一個是 Crossref REST(https://api.crossref.org/works/10.1016/j.scijus.2021.11.001 與 ?query.bibliographic= 查詢);原紀錄在此截斷,沒有留下未完成驗證的理由。
- **Dynamic driving metric output generation using computer vision methods (patent family)**　(marking-odometer)　https://patents.google.com/patent/US10817729B2/en
  - 原因:查核未取得結果
- **The study on the estimation of vehicles speed using a dashboard camera**　(marking-odometer)　https://link.springer.com/article/10.1007/s11042-023-17171-2?error=cookies_not_supported
  - 原因:論文確實存在,已由三個獨立來源取得紀錄——Crossref API(api.crossref.org/works/10.1007/s11042-023-17171-2)、Semantic Scholar…;原紀錄在此截斷,沒有留下未完成驗證的理由。
- **End-to-end Learning for Inter-Vehicle Distance and Relative Velocity Estimation in ADAS with a Monocular Camera**　(benchmarks)　https://arxiv.org/abs/2006.04082 (PDF read: https://arxiv.org/pdf/2006.04082)
  - 原因:查核未取得結果
- **A Video-Based System for Vehicle Speed Measurement in Urban Roadways (UTFPR dataset)**　(benchmarks)　https://api.crossref.org/works/10.1109/tits.2016.2606369 (Crossref record retrieved; publisher page not accessible)
  - 原因:查核未取得結果
- **Efficient Vision-based Vehicle Speed Estimation**　(benchmarks)　https://arxiv.org/abs/2505.01203
  - 原因:查核未取得結果
- **GVDepth: Zero-Shot Monocular Depth Estimation for Ground Vehicles based on Probabilistic Cue Fusion**　(benchmarks)　https://arxiv.org/abs/2412.06080
  - 原因:查核未取得結果
- **Vehicle distance estimation using a mono-camera for FCW/AEB systems**　(benchmarks)　https://api.crossref.org/works/10.1007/s12239-016-0050-9 (Crossref record retrieved; Springer landing page requires authentication)
  - 原因:查核未取得結果
- **Vehicle Speed Measurement Methodology Robust to Playback Speed-Manipulated Video File**　(benchmarks)　https://api.crossref.org/works/10.1109/access.2021.3115500 (Crossref record retrieved; IEEE Xplore page not retrievable)
  - 原因:查核未取得結果

另有搜尋階段列為 `unverified`(抓不到頁面)的候選未列入本檔;
其中 `Sensors 18(9):2956, 2018`(Around View Monitor 的車道標線自標定)是值得追的近似前案。
