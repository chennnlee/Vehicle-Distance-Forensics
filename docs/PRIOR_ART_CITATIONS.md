# 前案清單(2026-09-27 完成驗證)

本檔是 `docs/TERRY_RESEARCH_RECORD.md` §10 的**完整書目附錄**。§10 寫結論,這裡列每一筆。

**驗證協定**:五個搜尋角度各自獨立作業,規則是「只能列自己抓到頁面的論文」;
之後每一篇再派一個獨立審查者**重新取回頁面並試圖推翻**——核對書目、確認引文屬實、
並判斷「關係」有沒有講太滿。把鬆散相關說成「同一方法」是這裡最有害的錯誤。

**結果:47 筆通過驗證**(真實存在、書目正確、引文屬實),
**11 筆未能完成驗證**(頁面 403 / 空白 / 代理未回報),列在最後一節。

⚠ 「關係」欄括號內的 `check:` 是審查者對原判定的修正。`overstated` = 原本說得太接近。
⚠ **「沒查到」不等於「不存在」**,專利檢索尤其不完備。

## 最接近:與本方法共用機制(⚠ 四篇的「關係」審查後全被判定講太滿,**沒有一篇真的是同一方法**)

(4 筆)

### A novel approach for the online initial calibration of extrinsic parameters for a car-mounted camera

- **出處**:2009 12th International IEEE Conference on Intelligent Transportation Systems (ITSC), Oct 2009, pp. 1-6
- **作者**:Stephanie Hold, Steffen Gormer, Anton Kummert, Mirko Meuter, Stefan Müller-Schneiders
- **識別碼**:`10.1109/itsc.2009.5309853`
- **連結**:https://api.openalex.org/works/doi:10.1109/itsc.2009.5309853
- **關係判定**:`same_method (check: overstated)`　引文屬實:是
- **它做什麼**:Online initial extrinsic calibration of an onboard camera. A lane-marking detector samples the image at fixed vertical coordinates ("scanlines"), producing one-dimensional time series; correlation analysis between those series plus the vehicle's velocity gives the ground distance between the scanlines; a Gauss-Newton fit then solves camera height, pitch and roll by matching those distances to a pinhole back-projection onto the ground plane.
- **與我們的差別**:This is the closest retrieved prior art to our part (2) and it shares the machinery exactly (fixed image rows -> 1-D signals -> correlation -> ground distance between rows). Three differences. (i) It NEEDS the vehicle speed as an external input ("velocity information" appears twice in the abstract); our version divides the inter-row lag by the autocorrelation-derived dash period and multiplies by the legal cycle length, so speed cancels and no CAN/GPS is required — that is precisely the step it does not take, even though it already has the dashed-marking periodicity in hand and uses the word "periodicity". (ii) It solves h, pitch and roll separately through a parameter-dependent pinhole model, so it needs intrinsics; we solve the single lumped constant A = h·f and never separate h from f, so unknown focal length is harmless. (iii) It takes the horizon implicitly from the fitted pitch, not from an independently measured lane vanishing point, and it does nothing with a monocular metric depth network.
- ⚠ **審查更正**:S. Hold, S. Görmer (索引庫拼成 "Gormer"), A. Kummert, M. Meuter, S. Müller-Schneiders, "A novel approach for the online initial calibration of extrinsic parameters for a car-mounted camera," 2009 12th International IEEE Conference on Intelligent Transportation Systems (ITSC), St. Louis, MO, 2009-10-04~07, pp. 1-6, doi:10.1109/ITSC.2009.5309853. — 引用欄位無誤,不需更正。要更正的是**關係標籤**:不是 same_method,而是「**只對我們的 part

### Automatic estimation of vehicle speed from uncalibrated video sequences

- **出處**:International Symposium on Modern Technologies, Education and Professional Practice in Geodesy and Related Fields, Sofia, 3–4 November 2005, pp. 332ff
- **作者**:Lazaros Grammatikopoulos, George Karras, Elli Petsa
- **連結**:https://pcvg.geo.uniwa.gr/wp-content/uploads/sites/350/2022/12/Grammatikopoulos2005a-Automatic-Estimation-of-Vehicle-Speed-from-Uncalibrated-Video-Sequences.pdf
- **關係判定**:`same_method (check: overstated)`　引文屬實:是
- **它做什麼**:Camera on a 10 m bridge looking down the road. The road-direction vanishing point is extracted automatically from lane demarcations (least-squares intersection), the second is assumed at infinity, giving affine rectification; the metric scale along the road axis is then restored from ONE known ground distance. ±3 km/h against a control-point projective solution.
- **與我們的差別**:This is our part (1) plus the exact gap our part (2) fills — they need 'one known ground distance ALONG the road axis' and they get it by manual survey, which is precisely what is impossible in a retrospective accident case. They never consider obtaining that longitudinal distance from the dash cycle, and the camera is static so no temporal route exists for them. No depth model.
- ⚠ **審查更正**:CITATION (essentially correct; only refinement is the page range — it is pp. 332-338, not "332ff"): Grammatikopoulos, L., Karras, G., Petsa, E., 2005. Automatic Estimation of Vehicle Speed from Uncalibrated Video Sequences. International Symposium on Modern Technologies, Education and Professional Practice in Geodesy and Related Fields, Sofia, 03-04 November 2005, pp. 332-338. No DOI (Semantic Sch

### Method of determining the roll angle of a vehicle mounted camera (patent)

- **出處**:US patent US10776942B2, priority 2017-07-26, granted 2020
- **作者**:Diane Neisius (Aptiv Technologies AG)
- **識別碼**:`US10776942B2`
- **連結**:https://patents.google.com/patent/US10776942B2/en
- **關係判定**:`same_method (check: overstated)`　引文屬實:是
- **它做什麼**:Determines the roll angle of a vehicle-mounted camera from two world points whose separation D is known. To get D it detects dashed/intermittent lane markers as "rectangular" brightness signals in multiple fixed scan-lines and autocorrelates those signals to recover timing, which is turned into a distance using the vehicle speed; alternatively D is taken as the standard legal length of a lane marker.
- **與我們的差別**:Same primitive as ours — fixed scan-lines, correlation of the marking brightness signal, standard marking length — but pointed at a different unknown and closed differently. It autocorrelates each scan-line to get timing and then needs speed to convert that timing into metres; we cross-correlate two rows against each other and divide by the dash period so no speed is needed. Its output is the roll angle ρ (a lateral/attitude quantity) with camera height h treated as already known; it never solves the forward range constant A = h·f, never uses a lane vanishing point as y_h, and never rescales a depth network.
- ⚠ **審查更正**:Diane Neisius (Aptiv Technologies Ltd), "Method of determining the roll angle of a vehicle mounted camera", US 10,776,942 B2, priority 2017-07-26 (EP17183328.8), filed 2018-07-10 (US 16/031,151), granted 2020-09-15. Family: EP3435333B1, CN109308720B. RELATION SHOULD BE: shared_primitive / partial_scale_anchor, NOT same_method. Justification: the claimed invention is camera ROLL ANGLE rho, computed

### Real-time Prediction of Automotive Collision Risk from Monocular Video

- **出處**:arXiv preprint, submitted to IV2019, 4 Feb 2019
- **作者**:Derek J. Phillips, Juan Carlos Aragon, Anjali Roychowdhury, Regina Madigan, Sunil Chintakindi, Mykel J. Kochenderfer
- **識別碼**:`arXiv:1902.01293`
- **連結**:https://arxiv.org/abs/1902.01293 (full text: https://arxiv.org/pdf/1902.01293)
- **關係判定**:`same_method (check: overstated)`　引文屬實:是
- **它做什麼**:Dashcam collision-risk system. Relative longitudinal distance to other vehicles is computed geometrically as dy = hc·F/db, where db is measured from the bottom of the target's bounding box down to the image horizon, and the horizon is 'determined by obtaining the vanishing point of lines that are parallel in the real world'. Lateral offset comes from the same dy plus an assumed 1.8 m car width. As an extension, ego speed is measured from lane markings: a vertically fixed point on the reference lane records the time Δt for a marking to 'appear, disappear, and appear again', and speed = d/Δt with d the known marking spacing. Reported: lane-based estimator reads ~7 km/h below the speedometer at 65 km/h; distance error averaged ~0.42% of true distance over 5–15 m static tests.
- **與我們的差別**:This is the closest single hit and it independently reproduces two of our three parts — the vanishing-point horizon in d = A/(py − y_h), and ego speed from markings crossing a fixed image row rather than optical flow. But it never closes the loop we close: it states 'we know the camera parameters such as focal length for our input device' and uses a known camera height hc, so A = hc·F is an INPUT, not something solved from the markings. Consequently it cannot run on an unknown forensic camera. The marking timing is event-based (appear/disappear/appear) on LSD-detected line segments, not a brightness autocorrelation, and there is no cross-correlation between two rows, so it never converts a lag into a ground distance between two image rows. Ego speed and range are two separate modules; the marking measurement is never used to fix the range scale. No depth model anywhere, and no forensic framing (it is a real-time ADAS risk system, validated against a speedometer, not against a truth instrument).
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
- **與我們的差別**:This is the single closest prior art to our part (2) ANCHOR: the legal dash cycle (mark + gap), not the stripe alone, used as the known longitudinal length. But the cycle is measured SPATIALLY, in a single static camera's image, by auto-covariance along VP-rays — never in time, and there is no moving camera. Consequently speed does not cancel out of anything; it is the output. They produce a pixel-to-foot factor for a rectified roadway strip, not the constant A = h·f of a d = A/(py − y_h) range model, and they never separate or need h and f. No depth model anywhere.
- ⚠ **審查更正**:CITATION (corrected/completed, copied from the document itself): Todd Nelson Schoepflin and Daniel J. Dailey, "Algorithms for Estimating Mean Vehicle Speed Using Uncalibrated Traffic Management Cameras", Research Report WA-RD 575.1, Agreement T1803 Task 48 ("Automated CCTV Cameras"), ITS Research Program, College of Engineering, University of Washington / Washington State Transportation Center (TR

### Analysis of Dashcam Video for Determination of Vehicle Speed

- **出處**:SAE Technical Paper 2020-01-0877, 2020 (WCX SAE World Congress)
- **作者**:Jack Leifer, Alvaro Marquez (Trinity University)
- **識別碼**:`10.4271/2020-01-0877`
- **連結**:https://saemobilus.sae.org/papers/analysis-dashcam-video-determination-vehicle-speed-2020-01-0877
- **關係判定**:`same_scale_anchor`　引文屬實:是
- **它做什麼**:Extracts ego vehicle speed from dashcam footage when the camera's optical parameters are unknown, by measuring road features in overhead satellite imagery instead of physically surveying the scene, then tracking individual features — explicitly including 'periodically-occurring markings such as lane lines' — as they pass through and exit the image frame, combined with the video frame rate. Tested 16–65 mph; results matched the speedometer for all but the lowest frame rates.
- **與我們的差別**:This is the closest thing in the forensic/AR practice literature to our marking odometer, and it shares the premise (unknown optics, moving camera, periodic lane markings, frame counting). Three differences that matter: (a) the metric anchor is satellite imagery of that specific site — it needs the actual location and a georeferenced image, whereas we need only the legal cycle length and nothing site-specific; (b) it tracks individual identified features through the frame rather than correlating a brightness signal, so it has no autocorrelation period, no octave/harmonic problem and no two-row lag; (c) it yields ego speed only — no A = h·f, no range to other vehicles, no depth model. I could not retrieve the full text, only the publisher abstract page, so I cannot rule out that the body discusses standard stripe lengths.
- ⚠ **審查更正**:Citation needs no correction. Verified line: Leifer, J. and Marquez, A., "Analysis of Dashcam Video for Determination of Vehicle Speed," SAE Technical Paper 2020-01-0877, WCX SAE World Congress Experience, Detroit, MI, published 2020-04-14, doi:10.4271/2020-01-0877. Relation label "same_scale_anchor" is sustained, but tighten the wording in the report to this: "Shares our longitudinal scale anchor

### Automatic camera calibration method based on dashed lines

- **出處**:Proceedings of SPIE, 2013
- **作者**:Xiuhua Li, Guoyou Wang, Jianguo Liu
- **識別碼**:`DOI 10.1117/12.2031362`
- **連結**:https://api.openalex.org/works?search=Automatic%20camera%20calibration%20method%20based%20on%20dashed%20lines
- **關係判定**:`same_scale_anchor`　引文屬實:是
- **它做什麼**:Fully automatic traffic-camera calibration from the endpoints of dashed road lane markings, found with a modified RANSAC plus pixel-based transverse projection; builds a calibration model from the geometric relation between camera and road coordinate systems. Under 5% error converting pixels to metres along the lane markings.
- **與我們的差別**:Uses dash GEOMETRY (endpoint positions in a single image) rather than the dash CYCLE measured over time, from a static camera. Only metadata and a reconstructed abstract were retrievable (SPIE is closed access), so I cannot confirm whether the known length is the stripe or the full cycle — either way there is no ego motion, no temporal cross-correlation, and no depth model.
- ⚠ **審查更正**:Citation (corrected to full precision): Xiuhua Li, Guoyou Wang, Jianguo Liu, "Automatic camera calibration method based on dashed lines," Proc. SPIE 8921, MIPPR 2013: Remote Sensing Image Processing, Geographic Information Systems, and Other Applications, 892112 (25-26 October 2013); DOI 10.1117/12.2031362. Eighth International Symposium on Multispectral Image Processing and Pattern Recognition, W

### Physics-Grounded Monocular Vehicle Distance Estimation Using Standardized License Plate Typography

- **出處**:arXiv, submitted 14 Apr 2026, revised 2 Jul 2026
- **作者**:Manognya Lokesh Reddy, Zheng Liu
- **識別碼**:`arXiv:2604.12239`
- **連結**:https://arxiv.org/abs/2604.12239
- **關係判定**:`same_scale_anchor (check: understated)`　引文屬實:是
- **它做什麼**:Monocular inter-vehicle distance estimation for ADAS that resolves scale ambiguity using the standardized typography of United States license plates as passive fiducial markers, with explicit geometric priors and no training data — deliberately avoiding learned depth networks.
- **與我們的差別**:Same diagnosis (monocular scale ambiguity must be broken by a legally standardized object), opposite choice of anchor and opposite conclusion about depth models. Its anchor is a TRANSVERSE dimension on the target, which — as our own algebra shows (apparent px = W·(y − y_h)/h, focal cancels) — constrains camera height and pitch but cannot recover A = h·f; it works for them only because they solve a different, target-centred projection rather than a ground-plane range. It also rejects metric depth networks outright instead of anchoring one, and it is an ADAS paper with no forensic framing.
- ⚠ **審查更正**:引用本身無誤,不需更正。完整正確的引用行為:Manognya Lokesh Reddy, Zheng Liu, "Physics-Grounded Monocular Vehicle Distance Estimation Using Standardized License Plate Typography," arXiv:2604.12239v3 [cs.CV; eess.IV], v1 2026-04-14 / v2 2026-05-20(對方未提)/ v3 2026-07-02;29 pages, 12 figures;CC BY 4.0;DOI 僅有 arXiv 自帶的 10.48550/arXiv.2604.12239,無期刊 reference(=未經同儕審查的 preprint);作者單位 University of Michigan-Dearborn。 需要更正的是「關係

### Real-time Prediction of Automotive Collision Risk from Monocular Video

- **出處**:Submitted to IEEE Intelligent Vehicles Symposium 2019; arXiv 2019
- **作者**:Derek J. Phillips, Juan Carlos Aragon, Anjali Roychowdhury, Regina Madigan, Sunil Chintakindi, Mykel J. Kochenderfer
- **識別碼**:`arXiv:1902.01293`
- **連結**:https://ar5iv.labs.arxiv.org/html/1902.01293
- **關係判定**:`same_scale_anchor (check: understated)`　引文屬實:是
- **它做什麼**:Dashcam collision-risk pipeline with detection, tracking and state estimation. Absolute ego speed is obtained from lane markings of known dimensions used as stationary references: a vertically fixed point on the reference lane records the time for a marking to appear, disappear and reappear (Δt), and speed is the known inter-marking distance divided by Δt. Range to other vehicles uses dy = hc·F/db with camera height and focal length assumed known, plus a standard 1.8 m car width for lateral offset.
- **與我們的差別**:This is the marking odometer in its simplest form — a fixed image point, marking passage timing, known dash spacing — and it confirms our ego-speed idea is not novel in principle. But it is threshold/event-based rather than autocorrelation-based (no period estimate, no octave ambiguity handling, no lock/no-lock honesty), and the two halves are kept separate: the marking timing is never fed back to determine the range constant. Their ranging instead ASSUMES hc and F are known, which is exactly the assumption our part (2) refuses. No depth model.
- ⚠ **審查更正**:D. J. Phillips, R. Madigan, J. C. Aragon, S. Chintakindi, A. Roychowdhury, M. J. Kochenderfer, "Real-time Prediction of Automotive Collision Risk from Monocular Video," arXiv:1902.01293v1 [cs.CV], 4 Feb 2019, DOI 10.48550/arXiv.1902.01293 (comment field: "Submitted to IV2019. 7 pages, 4 figures, 3 tables"). Cite as an arXiv preprint — no IEEE-published IV 2019 version could be located. RELATION, c

### Roadside Monocular Camera Calibration Based on Adaptive Structure Tensor and Hierarchical Vanishing Point Estimation

- **出處**:Electronics (MDPI) 15(14):3215, 2026
- **作者**:Xuecong Liu, Kun Kang, Kangchao Gao
- **識別碼**:`DOI 10.3390/electronics15143215`
- **連結**:https://api.openalex.org/works/doi:10.3390/electronics15143215
- **關係判定**:`same_scale_anchor`　引文屬實:是
- **它做什麼**:Adaptive structure tensor for stable edge orientation under shadows and reflections, then a hierarchical dual-vanishing-point self-calibration (spatial focusing, Mean-Shift clustering, nonlinear optimisation); scale recovery exploits road-marking geometric priors under the two vanishing-point constraints, claiming no calibration target, no vehicle-size assumption and no motion prior.
- **與我們的差別**:The most recent roadside claim to get metric scale from road-marking priors alone — but static camera, single-image geometry, and (per the abstract) explicitly 'without motion priors', which is the opposite of our route. MDPI refused the full text (403), so I could not confirm whether the prior is dash length, dash cycle or lane width; treat this entry as metadata-confirmed only and worth re-checking from a network that can reach mdpi.com.
- ⚠ **審查更正**:引用行完全正確,不必改:Xuecong Liu, Kun Kang, Kangchao Gao, "Roadside Monocular Camera Calibration Based on Adaptive Structure Tensor and Hierarchical Vanishing Point Estimation", Electronics (MDPI) 15(14):3215, 2026, DOI 10.3390/electronics15143215(投稿 2026-06-20、刊出 2026-07-21;Northeastern University at Qinhuangdao;Academic Editor: Dah-Jye Lee)。 引用句應改為論文原文(摘要第 3 段):"On this basis, the geometric prior informa

### Roadside Monocular Camera Calibration Based on Adaptive Structure Tensor and Hierarchical Vanishing Point Estimation

- **出處**:Electronics (MDPI), vol. 15, no. 14, article 3215, 2026
- **作者**:Xuecong Liu, Kun Kang, Kangchao Gao
- **識別碼**:`10.3390/electronics15143215`
- **連結**:https://api.semanticscholar.org/graph/v1/paper/DOI:10.3390/electronics15143215?fields=title,authors,year,venue,abstract,externalIds
- **關係判定**:`same_scale_anchor`　引文屬實:是
- **它做什麼**:Automatic self-calibration of fixed roadside traffic cameras: robust edge-orientation extraction, hierarchical two-vanishing-point estimation, then scene scale recovered from the geometric prior of road markings via a marking-contour optimisation model constrained by the two vanishing points. Applied to vehicle speed measurement, evaluated on BrnoCompSpeed (5.31% mean relative calibration error, 1.79 km/h mean speed error).
- **與我們的差別**:Same two ingredients as our parts (1) and (2) — vanishing points for orientation and road markings for scale — but for a STATIONARY roadside camera, where the marking is measured as a contour within the image (spatially). With no camera motion there is no temporal sweep of markings across image rows, so our lag-based longitudinal measurement does not exist in this setting. It is a pure classical-geometry calibration pipeline: no monocular depth network is scaled or even used, so it says nothing about our part (3).
- ⚠ **審查更正**:Citation is correct as given; canonical form: Liu, X.; Kang, K.; Gao, K. "Roadside Monocular Camera Calibration Based on Adaptive Structure Tensor and Hierarchical Vanishing Point Estimation." Electronics 2026, 15(14), 3215. https://doi.org/10.3390/electronics15143215 (published 21 July 2026, CC BY 4.0; 35 pp., 49 refs; all three authors at Northeastern University at Qinhuangdao). Relation label "

### The Automated Use of Un-Calibrated CCTV Cameras as Quantitative Speed Sensors — Phase 3 (WA-RD 635.1); companion to Cathey & Dailey, IEEE Intelligent Vehicles Symposium 2005, pp. 777–782

- **出處**:WSDOT report WA-RD 635.1, January 2006; conference version IEEE IV Symposium 2005, pp. 777–782
- **作者**:Daniel J. Dailey, Frederick W. Cathey
- **識別碼**:`WA-RD 635.1; conference version 10.1109/ivs.2005.1505199`
- **連結**:https://www.wsdot.wa.gov/research/reports/fullreports/635.1.pdf
- **關係判定**:`same_scale_anchor (check: understated)`　引文屬實:是
- **它做什麼**:Vanishing point from road lines → a 'straightening' transformation that maps road-parallel lines to vertical image lines → autocorrelation of the straightened background image along a column, whose period is the image length from the start of one lane stripe to the start of the next → scale factor kappa = L/lambda in feet per pixel. The software's default stripe period is 40 feet, and a warning is given that 'the default stripe period may be wrong (some highway stripes...)'. Vehicle pixel speed then comes from cross-correlating successive straightened frames.
- **與我們的差別**:Same anchor concept as ours (start-of-stripe to start-of-stripe = the cycle, default 40 ft = 12.19 m) but again purely spatial and from a static camera. It also deliberately AVOIDS solving h and f ('it is not necessary to completely calibrate the camera'), so it never obtains A = h·f and cannot give a per-pixel range to an arbitrary target row. Cross-correlation is used between consecutive frames to track vehicles, not between two fixed image rows to recover the metres separating those rows. No ego-speed measurement, no metric depth model.
- ⚠ **審查更正**:Dailey, D. J., & Cathey, F. W. (2006). "The Automated Use of Un-Calibrated CCTV Cameras as Quantitative Speed Sensors — Phase 3." Final Research Report, Agreement T2695, Task 55, WA-RD 635.1, Washington State Transportation Center (TRAC), University of Washington / WSDOT, January 2006, 37 pp. https://www.wsdot.wa.gov/research/reports/fullreports/635.1.pdf (mirror: https://rosap.ntl.bts.gov/view/do

### The Earth ain't Flat: Monocular Reconstruction of Vehicles on Steep and Graded Roads from a Moving Camera

- **出處**:IROS 2018
- **作者**:Junaid Ahmed Ansari, Sarthak Sharma, Anshuman Majumdar, J. Krishna Murthy, K. Madhava Krishna
- **識別碼**:`arXiv:1803.02057`
- **連結**:https://ar5iv.labs.arxiv.org/html/1803.02057
- **關係判定**:`same_scale_anchor`　引文屬實:是
- **它做什麼**:Monocular localisation and shape estimation of other vehicles on non-planar roads, approximating the road by local planar patches and using vehicle semantic keypoints in a bundle-adjustment-like optimisation. In discussing how to obtain metric scale it explicitly proposes using road markings of standard dimensions together with a known camera height.
- **與我們的差別**:This is the nearest published statement of our scale anchor, and it is explicitly the SPATIAL, single-frame version: it measures the marking's apparent size inside one image and it REQUIRES a known camera height h. Our measurement is temporal — the same markings sweep past two fixed image rows and the cross-correlation lag between those rows, divided by the autocorrelation period and multiplied by the legal cycle length, gives the true ground separation of the two rows — so it solves A = h*f as a single product and never needs h separately, never needs f, and never needs the marking to be resolvable as a shape in any one frame. It also does not use the lane-line vanishing point for the horizon, and there is no depth network in it at all (2018, pre-dates metric depth foundation models).
- ⚠ **審查更正**:Nothing needed correcting. Full verified citation (enriched with page numbers and the publication DOI, which the original entry lacked): J. A. Ansari, S. Sharma, A. Majumdar, J. K. Murthy, K. M. Krishna, "The Earth Ain't Flat: Monocular Reconstruction of Vehicles on Steep and Graded Roads from a Moving Camera," 2018 IEEE/RSJ International Conference on Intelligent Robots and Systems (IROS), Oct 20

### Using road markers as fiducials for automatic speed estimation in road videos

- **出處**:2017 IEEE Western New York Image and Signal Processing Workshop (WNYISPW)
- **作者**:Deepali D. Kamat, Thomas B. Kinsman
- **識別碼**:`DOI 10.1109/wnyipw.2017.8356258`
- **連結**:https://api.openalex.org/works?search=Using%20road%20markers%20as%20fiducials%20for%20automatic%20speed%20estimation%20in%20road%20videos
- **關係判定**:`same_scale_anchor (check: understated)`　引文屬實:否(僅摘要可讀)
- **它做什麼**:Ego-speed estimation from an ordinary dashcam using the uniformly spaced dashed lines painted on US roads as fiducials, with a line-detection technique and no LiDAR, GPS, accelerometer, odometry or CNN; works on 30 fps internet video from unknown cameras. Cites forensic analysis as an application.
- **與我們的差別**:The closest published relative of our 'marking odometer' idea and it should be cited: same anchor (uniform dash spacing), same sensor (unknown-camera dashcam), same stated application (forensics). But it is a fiducial/marker-detection scheme, not a signal-processing one — no brightness signal at a fixed row, no autocorrelation period, no octave/harmonic disambiguation, and critically no inversion of the measurement into a distance scale: the marking spacing is consumed to produce speed only, never to produce A = h·f or to rescale a depth network. Only metadata and a reconstructed abstract were retrievable (IEEE Xplore refused), so its internal method details are unconfirmed.
- ⚠ **審查更正**:引用行(已逐欄對帳 Crossref,可直接用): D. D. Kamat and T. B. Kinsman, "Using road markers as fiducials for automatic speed estimation in road videos," 2017 IEEE Western New York Image and Signal Processing Workshop (WNYISPW), Rochester, NY, USA, 17 Nov. 2017, pp. 1–5, doi: 10.1109/WNYIPW.2017.8356258. 應一併引用的長版(同一批作者、同一件工作、內含完整方法,而且可公開取得全文): D. D. Kamat, "Vehicle Movement and Speed Estimation using a Cost Effec

### Vision-based Vehicle Speed Estimation: A Survey

- **出處**:IET Intelligent Transport Systems, 2021
- **作者**:David Fernández Llorca, Antonio Hernández Martínez, Iván García Daza
- **識別碼**:`arXiv:2101.06159, DOI 10.1049/itr2.12079`
- **連結**:https://ar5iv.labs.arxiv.org/html/2101.06159
- **關係判定**:`same_scale_anchor`　引文屬實:是
- **它做什麼**:Systematic review and taxonomy of vision-based vehicle speed estimation from infrastructure cameras, including how the metres-per-pixel scale factor is obtained. It lists lane-marking length and frequency as one established family of scale cues, with eleven citations attached.
- **與我們的差別**:This is the strongest evidence that 'lane markings as a scale ruler' is NOT novel in itself — it is a named category in the standard survey of our field, with eleven prior works behind it. What the survey covers is fixed infrastructure cameras (it states its scope excludes onboard cameras), where length and 'frequency' mean the spatial pitch of markings measured inside the image. It contains no monocular depth network, no metric depth model, and no measurement of marking cycle in the time domain. Our claim therefore has to be narrowed to: (a) measuring that cycle temporally across two image rows on a MOVING camera, with ego speed cancelling out, and (b) using the resulting A = h*f to scale a metric depth foundation model.
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
- **與我們的差別**:Same architectural pattern as ours — frozen foundation model, external metric anchor, training-free — and even the same word, 'anchor'. The anchor is a depth sensor, not scene geometry, so it inherits the sensor requirement we are trying to eliminate. Indoor robotics rather than road scenes; no ground plane, no markings, no horizon.
- ⚠ **審查更正**:引用（補上正式出版資訊，原本只寫 arXiv preprint）： Simon Dorer, Martin Büchner, Nick Heppert, Abhinav Valada. "AnchorD: Metric Grounding of Monocular Depth Using Factor Graphs." 2026 IEEE/RSJ International Conference on Intelligent Robots and Systems (IROS), Pittsburgh, USA, 2026. arXiv:2605.02667v1 [cs.RO], submitted 4 May 2026 14:48:52 UTC. DOI: 10.48550/arXiv.2605.02667. Comments: 8 pages, 9 Figures, 3 Tables. 

### Camera Height Doesn't Change: Unsupervised Training for Metric Monocular Road-Scene Depth Estimation

- **出處**:ECCV 2024
- **作者**:Genki Kinoshita, Ko Nishino
- **識別碼**:`arXiv:2312.04530`
- **連結**:https://arxiv.org/abs/2312.04530
- **關係判定**:`same_depth_anchoring (check: overstated)`　引文屬實:是
- **它做什麼**:Training method (FUMET) that makes any monocular depth network learn absolute scale from ordinary driving video: it detects cars, estimates their sizes, aggregates the scale information into an estimate of the camera height, and enforces that height's consistency across the whole sequence as scale supervision.
- **與我們的差別**:Anchors a depth network's metric scale on camera height inferred from car sizes, and does so during TRAINING rather than as a per-camera constant applied at inference. Ours is a single global multiplier k measured at deployment from road markings on the actual footage, which is what makes it auditable and what makes the result independent of the focal length fed in. They do not use markings, do not use marking periodicity, and do not address the focal-length proportionality of intrinsics-conditioned metric models.
- ⚠ **審查更正**:Genki Kinoshita, Ko Nishino, "Camera Height Doesn't Change: Unsupervised Training for Metric Monocular Road-Scene Depth Estimation," in Computer Vision – ECCV 2024, Springer Nature Switzerland, 2024, pp. 57–73. DOI: 10.1007/978-3-031-73337-6_4. arXiv:2312.04530v3 (submitted 2023-12-07, v3 2024-10-01). cs.CV; cs.RO. 關係標籤應由 same_depth_anchoring 改為 **same_goal_different_anchor_and_stage**(同一個問題:單目深度的

### DrivingDepth: Sparse-Prompted Pixel-wise Scale Correction for Driving Depth Estimation

- **出處**:arXiv preprint, 30 June 2026
- **作者**:Chi Huang, Wenhao Zhang, Hang Yin, YuAn Wang, Hao Li, Bosheng Wang, Xun Sun, Liang Wang
- **識別碼**:`arXiv:2606.31488`
- **連結**:https://arxiv.org/abs/2606.31488
- **關係判定**:`same_depth_anchoring (check: overstated)`　引文屬實:是
- **它做什麼**:Treats sparse projected LiDAR as geometric prompts that locally calibrate a frozen depth foundation prior through residual per-pixel scale correction, on the argument that the foundation model's relative geometry is already coherent and only a scale mapping is missing. Evaluated on nuScenes.
- **與我們的差別**:States our part-(3) premise almost word for word — the shape is right, only the scale is missing — and is the strongest published support for that framing, which matches our own finding that raw error of 2.3-40% falls to 2.1-4.4% after a single constant. But the metric anchor is LiDAR, i.e. an active sensor we by definition do not have, and the correction is per-pixel rather than one global constant. Nothing here derives the scale from image content or from legal road geometry.
- ⚠ **審查更正**:Huang, C., Zhang, W., Yin, H., Wang, Y., Li, H., Wang, B., Sun, X., Wang, L. (Baidu Inc.). "DrivingDepth: Sparse-Prompted Pixel-wise Scale Correction for Driving Depth Estimation." arXiv:2606.31488 [cs.CV], submitted 30 Jun 2026. https://arxiv.org/abs/2606.31488 (code: https://github.com/HCaelrs/DrivingDepth) 關係應改為 same_premise_for_part3_only(不是 same_depth_anchoring)。正確敘述:此文以文獻形式支持我方第(3)部分的「前提」——度

### FARSEC: A Reproducible Framework for Automatic Real-Time Vehicle Speed Estimation Using Traffic Cameras

- **出處**:arXiv preprint, 2023
- **作者**:Lucas Liebe, Franz Sauerwald, Sylwester Sawicki, Matthias Schneider, Leo Schuhmann, Tolga Buz, Paul Boes, Ahmad Ahmadov, Gerard de Melo
- **識別碼**:`arXiv:2309.14468`
- **連結**:https://ar5iv.labs.arxiv.org/html/2309.14468
- **關係判定**:`same_depth_anchoring`　引文屬實:是
- **它做什麼**:Traffic-camera speed estimation that estimates the length of road segments via monocular depth-map prediction, explicitly acknowledging that the depth model is only defined up to an unknown scaling factor s_m, and solving for s_m by least squares against average car lengths (a mean vehicle length of about six metres) derived from 2D tracking boxes.
- **與我們的差別**:The closest published instance of our part (3) structure — monocular depth network + one unknown global scale constant fitted from outside information — but the outside information is mean car length, not a legal road-marking length, and the camera is a static roadside one. Because the anchor is a vehicle statistic, the constant inherits fleet variance and is not auditable in court; because the camera is static, the temporal marking route is unavailable to them. They also do not raise the focal-length proportionality of metric depth models.
- ⚠ **審查更正**:No correction needed. Canonical citation as printed on the page I retrieved: Lucas Liebe, Franz Sauerwald, Sylwester Sawicki, Matthias Schneider, Leo Schuhmann, Tolga Buz, Paul Boes, Ahmad Ahmadov, Gerard de Melo, "FARSEC: A Reproducible Framework for Automatic Real-Time Vehicle Speed Estimation Using Traffic Cameras", arXiv:2309.14468 [cs.CV], submitted 25 September 2023, DOI 10.48550/arXiv.2309.

### FARSEC: A Reproducible Framework for Automatic Real-Time Vehicle Speed Estimation Using Traffic Cameras

- **出處**:arXiv, 25 Sep 2023 (cs.CV)
- **作者**:Lucas Liebe, Franz Sauerwald, Sylwester Sawicki, Matthias Schneider, Leo Schuhmann, Tolga Buz, Paul Boes, Ahmad Ahmadov, Gerard de Melo
- **識別碼**:`arXiv:2309.14468`
- **連結**:https://arxiv.org/abs/2309.14468 (full text: https://arxiv.org/pdf/2309.14468)
- **關係判定**:`same_depth_anchoring`　引文屬實:是
- **它做什麼**:Speed estimation from traffic surveillance video. Runs the PixelFormer monocular depth model (KITTI-pretrained) to get RELATIVE depth, then estimates one global scalar s_M by least squares against a set of point pairs with known real-world distances — in practice the assumed mean vehicle length of six metres, derived from cumulative bounding-box tracking. Evaluated on BrnoCompSpeed; accuracy validated against 'road markings at a fixed distance'. States explicitly that depth models give depth only up to a scaling factor that is independent of the image.
- **與我們的差別**:Structurally the same move as our part (3) — one global multiplicative constant applied to a network's depth output — but everything around it differs. The anchor is an assumed 6 m mean car length (a weak, fleet-dependent prior; they note 'other, for example country-specific, characteristics could be used'), not a legal longitudinal marking cycle; the camera is a fixed roadside CCTV, not a moving dashcam; the network is a RELATIVE-depth model, so the issue of metric networks whose metres scale strictly with the focal length you feed them never arises, and they make no claim of focal-length independence; road markings appear only as an evaluation reference, never as the scale anchor. Output is aggregate traffic speed, not per-target forensic range.
- ⚠ **審查更正**:Citation stands as given: Lucas Liebe, Franz Sauerwald, Sylwester Sawicki, Matthias Schneider, Leo Schuhmann, Tolga Buz, Paul Boes, Ahmad Ahmadov, Gerard de Melo. "FARSEC: A Reproducible Framework for Automatic Real-Time Vehicle Speed Estimation Using Traffic Cameras." arXiv:2309.14468 [cs.CV; also cs.LG, cs.SI], submitted 25 Sep 2023. DOI 10.48550/arXiv.2309.14468. No journal-ref on the arXiv rec

### Language as Prior, Vision as Calibration: Metric Scale Recovery for Monocular Depth Estimation

- **出處**:arXiv preprint, 4 January 2026
- **作者**:Mingxia Zhan, Li Zhang, Beibei Wang, Yingjie Wang, Zenglin Shi
- **識別碼**:`arXiv:2601.01457`
- **連結**:https://arxiv.org/abs/2601.01457
- **關係判定**:`same_depth_anchoring (check: overstated)`　引文屬實:是
- **它做什麼**:Under a frozen-backbone setting, recovers metric depth by an image-specific affine transform in inverse depth, training only lightweight calibration heads; a CLIP text encoder predicts an uncertainty-aware envelope of feasible calibration parameters and pooled visual features select within it.
- **與我們的差別**:Same frozen-backbone-plus-calibration structure, but the calibration parameters are PREDICTED by learned heads from image and caption features rather than measured from a known physical length. For a forensic use that is the wrong direction: there is nothing to cross-examine, and the caption cues are acknowledged as noisy. It also fits a per-image affine transform, whereas our k is one constant per camera, reusable across days, which is why we care that its drift is only 0.1-1.2% across segments.
- ⚠ **審查更正**:Zhan, Mingxia; Zhang, Li; Wang, Beibei; Wang, Yingjie; Shi, Zenglin. "Language as Prior, Vision as Calibration: Metric Scale Recovery for Monocular Depth Estimation." arXiv preprint arXiv:2601.01457, submitted 4 January 2026 (v1), last revised 9 January 2026 (v3). No peer-reviewed venue. https://arxiv.org/abs/2601.01457 Corrected relation: related_work_same_problem_different_anchor (NOT same_depth

### Physics-Grounded Monocular Vehicle Distance Estimation Using Standardized License Plate Typography

- **出處**:arXiv preprint, 14 April 2026
- **作者**:Manognya Lokesh Reddy, Zheng Liu
- **識別碼**:`arXiv:2604.12239`
- **連結**:https://arxiv.org/abs/2604.12239
- **關係判定**:`same_depth_anchoring`　引文屬實:是
- **它做什麼**:Inter-vehicle distance estimation for ADAS that uses the standardised typography of US licence plates (character height, stroke width, spacing) as a passive fiducial for metric ranging, then fuses that geometric distance with a deep depth estimate via inverse-variance weighting and an online scale alignment, followed by a constant-velocity Kalman filter for distance, relative velocity and time-to-collision.
- **與我們的差別**:This is the closest published instance of our part (3): a legally standardised in-scene object used to put absolute metric scale on a deep depth estimate. Three concrete differences. (i) The anchor is a TRANSVERSE dimension used through the pinhole relation d = f*W/w, which requires a known focal length — precisely the quantity we refuse to assume, and the reason we argue the anchor must lie along the direction of travel. (ii) The alignment is an online exponential moving average of a per-detection scale factor, i.e. a running correction that needs a plate visible in frame; ours is one global constant k solved once from road geometry and thereafter independent of what is in the scene. (iii) No lane-line vanishing-point horizon and no ground-plane range formula d = A/(py - y_h); the distance comes from apparent character size, not from the contact row.
- ⚠ **審查更正**:Citation is correct; only completed with detail the researcher omitted: Manognya Lokesh Reddy, Zheng Liu. "Physics-Grounded Monocular Vehicle Distance Estimation Using Standardized License Plate Typography." arXiv:2604.12239 [cs.CV; eess.IV]. v1 submitted 14 Apr 2026; v2 20 May 2026; v3 2 Jul 2026 (current). 29 pages, 12 figures. DOI 10.48550/arXiv.2604.12239. Retrieved https://arxiv.org/abs/2604.

### Radar Meets Vision: Robustifying Monocular Metric Depth Prediction for Mobile Robotics

- **出處**:arXiv preprint, October 2024 (ETH Zürich, cs.RO)
- **作者**:Marco Job, Thomas Stastny, Tim Kazik, Roland Siegwart, Michael Pantic
- **識別碼**:`arXiv:2410.00736`
- **連結**:https://arxiv.org/html/2410.00736
- **關係判定**:`same_depth_anchoring`　引文屬實:是
- **它做什麼**:Fuses sparse mmWave radar returns with a monocular metric depth network, learning a per-pixel blending weight between the network's own metres and radar-averaged depth. Reports AbsRel for three settings on three validation sets: metric baseline 0.194 / 1.632 / 2.669, naive (global) radar scaling 2.705 / 0.952 / 0.247, their fusion 0.170 / 0.313 / 0.223.
- **與我們的差別**:Same structural idea as our part (3) — an external metric measurement repairs a monocular depth model's absolute scale — but the external measurement is an onboard radar, i.e. a sensor we by assumption do not have in forensic casework, and the correction is a learned per-pixel field rather than one global constant from road geometry. Their result that a single global rescale can be much worse than the raw metric output in some scenes is the strongest published warning against our one-constant approach, and is the thing our per-camera k-stability check (0.1–1.2% drift) has to answer.
- ⚠ **審查更正**:Marco Job, Thomas Stastny, Tim Kazik, Roland Siegwart, Michael Pantic, "Radar Meets Vision: Robustifying Monocular Metric Depth Prediction for Mobile Robotics," arXiv:2410.00736v1 [cs.RO], submitted 1 Oct 2024; DOI 10.48550/arXiv.2410.00736; arXiv comments field: "Submitted to ICRA 2025"; all authors: Autonomous Systems Lab, ETH Zürich. 只有 v1,dblp 僅以 CoRR 收錄(找不到 ICRA/IEEE 正式論文集版本),所以「arXiv preprin

### Typography-Based Monocular Distance Estimation Framework for Vehicle Safety Systems

- **出處**:arXiv preprint, 24 March 2026
- **作者**:Manognya Lokesh Reddy, Zheng Liu
- **識別碼**:`arXiv:2603.22781`
- **連結**:https://arxiv.org/abs/2603.22781
- **關係判定**:`same_depth_anchoring (check: overstated)`　引文屬實:是
- **它做什麼**:Earlier companion of the above: licence-plate character height measured by detection plus segmentation, distance computed through the pinhole model, with camera pose compensation from lane-based horizon estimation, hybrid deep-learning fusion, and Kalman filtering. Reports 2.3% coefficient of variation in character height and 7.7% mean absolute error in a controlled indoor setup.
- **與我們的差別**:The single closest near-miss to our full combination, because it is the only retrieved paper that puts a lane-derived horizon and a deep depth model and a known legal dimension in the same pipeline. But the horizon is used only to compensate camera PITCH, not as y_h in a range formula; the metric scale still comes from the plate through the pinhole model and therefore still needs the focal length; and the validation is an indoor controlled setup, not roadway forensics. Our lane-line vanishing point is load-bearing in the range equation itself, and our scale comes from a longitudinal marking cycle measured over time, which makes the result independent of focal length rather than dependent on it.
- ⚠ **審查更正**:Citation is correct as given; copied from the page I fetched: Manognya Lokesh Reddy, Zheng Liu, "Typography-Based Monocular Distance Estimation Framework for Vehicle Safety Systems", arXiv:2603.22781 [cs.CV], submitted 24 Mar 2026, 25 pages / 11 figures, DOI 10.48550/arXiv.2603.22781, no journal reference (preprint, not peer-reviewed). Relation should be downgraded from `same_depth_anchoring` to `

### Zero-Shot Metric Depth Estimation via Monocular Visual-Inertial Rescaling for Autonomous Aerial Navigation

- **出處**:arXiv preprint, 9 September 2025
- **作者**:Steven Yang, Xiaoyu Tian, Kshitij Goel, Wennie Tabib
- **識別碼**:`arXiv:2509.08159`
- **連結**:https://arxiv.org/abs/2509.08159
- **關係判定**:`same_depth_anchoring (check: overstated)`　引文屬實:是
- **它做什麼**:Lightweight zero-shot strategies (including monotonic spline fitting) that rescale relative depth predictions into metric depth using the sparse 3D feature map produced by a visual-inertial navigation system, for collision avoidance on aerial vehicles.
- **與我們的差別**:Another instance of external-source rescaling of a depth model, this time with a VIO map that is itself metric because of the IMU. It needs an IMU and a running VIO stack; we need one static piece of road geometry and a video. It also fits a spline over the depth range rather than a single global constant, which is worth noting as an alternative to our single k if our residuals ever turn out to be depth-dependent.
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
- **與我們的差別**:The third of the three real-speed datasets. Ground truth is the vehicle's own cruise-control setting, i.e. a speedometer-class reference with no independent verification — weaker than BrnoCompSpeed's lidar gates and than ForeSpeed's laser-validated speedometer. Roadside camera passing broadside; no distance ground truth, no ego-motion, nothing about scale anchoring.
- ⚠ **審查更正**:S. Djukanović, N. Bulatović, I. Čavor, "A dataset for audio-video based vehicle speed estimation," 2022 30th Telecommunications Forum (TELFOR), Belgrade, Serbia, 15–16 Nov 2022, pp. 1–4. DOI: 10.1109/TELFOR56187.2022.9983773. Preprint arXiv:2212.01651 (submitted 3 Dec 2022). Dataset: https://slobodan.ucg.ac.me/science/vs13/ — Relation: same_application only (roadside single-camera vehicle speed es

### An accurate and practical calibration method for roadside camera using two vanishing points

- **出處**:Neurocomputing 204:222–230, 2016
- **作者**:Xinhua You, Yuan Zheng
- **識別碼**:`DOI 10.1016/j.neucom.2015.09.132`
- **連結**:https://api.openalex.org/works?search=An%20accurate%20and%20practical%20calibration%20method%20for%20roadside%20camera%20using%20two%20vanishing%20points
- **關係判定**:`same_application`　引文屬實:否(僅摘要可讀)
- **它做什麼**:Two vanishing points (road direction from lane markings, vertical from poles/pedestrians) estimated by least squares over many video observations; intrinsics and rotation follow, and the translation (scale) is fixed by a known length on the road or a known camera height above the road.
- **與我們的差別**:Scale is supplied manually — either a surveyed road length or a measured mounting height. Static camera. It is the clearest statement that in this literature the longitudinal anchor is something a human goes and measures; nobody derives it from the periodicity of the markings in time. Full text not retrieved (ScienceDirect refused); DOI, venue, volume, pages confirmed.
- ⚠ **審查更正**:CITATION (as given — verified correct, no change needed): Xinhua You, Yuan Zheng, "An accurate and practical calibration method for roadside camera using two vanishing points", Neurocomputing 204:222-230, 2016. DOI 10.1016/j.neucom.2015.09.132. THE QUOTE MUST BE RE-ATTRIBUTED. Its actual source is a DIFFERENT paper by DIFFERENT authors: Yuan Zheng, Silong Peng, "A Practical Roadside Camera Calibra

### Analysis of video recordings in accident reconstruction

- **出處**:Archives of Transport, vol. 69, no. 1, 2024, pp. 127–143
- **作者**:Michał Mariusz Abramowski, Andrzej Reński
- **識別碼**:`10.61089/xvvscd77`
- **連結**:https://www.archivesoftransport.com/index.php/aot/article/view/19
- **關係判定**:`same_application`　引文屬實:是
- **它做什麼**:Survey/methods paper on quantitative analysis of video from both fixed cameras and vehicle-mounted DVRs for accident reconstruction, covering speeds, accelerations and directions of motion, the extra difficulty of a camera moving with the vehicle, the influence of recording quality (resolution, distortion, sharpness, frame rate) on usability, and a method for estimating the uncertainty of the results.
- **與我們的差別**:The one retrieved forensic-domain paper that explicitly claims analysis without knowing camera parameters and that treats the moving-camera case as its own problem — i.e. the same two constraints we work under. I could not retrieve the full text (the journal's PDF link 404'd), so I cannot say what scale source it uses and I am NOT claiming it does or does not use markings; on the abstract alone there is no mention of a marking cycle, of A = h·f, or of any learned depth model, and its framing is manual quantitative analysis rather than an automated pipeline.
- ⚠ **審查更正**:Citation line is correct exactly as given; no correction needed: Abramowski, M.M., Reński, A. (2024). "Analysis of video recordings in accident reconstruction." Archives of Transport, 69(1), 127-143. https://doi.org/10.61089/xvvscd77 (ISSN 0866-9546 / e-ISSN 2300-8830, CC BY 4.0, Warsaw University of Technology). Relation label "same_application" is CONFIRMED and is the right label. It is NOT same

### Assessing the influence of variables on vehicle speed determination through reverse projection analysis

- **出處**:Science & Justice, vol. 66, no. 1, 2026, article 101369
- **作者**:Walter E. Bruehs, Dorothy Stout
- **識別碼**:`10.1016/j.scijus.2025.101369`
- **連結**:https://api.crossref.org/works?query.bibliographic=Assessing+the+influence+of+variables+on+vehicle+speed+determination+through+reverse+projection+analysis
- **關係判定**:`same_application`　引文屬實:是
- **它做什麼**:Follow-up to the 2022 JFS validation, extending it to assess how individual variables influence the vehicle-speed result obtained by reverse projection analysis.
- **與我們的差別**:The most recent forensic-domain error-budget work on video speed, and therefore the natural comparator for our uncertainty reporting — but still reverse projection on a fixed camera with scene access. ScienceDirect returned 403 in this environment, so I verified only the Crossref record (DOI, authors, journal, volume, issue, article number); I could not read the abstract or the list of variables, and I am not claiming what it concludes.
- ⚠ **審查更正**:Nothing was wrong. Verified citation, in full: Walter E. Bruehs, Dorothy Stout, "Assessing the influence of variables on vehicle speed determination through reverse projection analysis", Science & Justice 66(1):101369, January 2026 (epub 2025-12-03), doi:10.1016/j.scijus.2025.101369, PMID 41506828. Affiliations: FBI Digital Forensic Analysis Unit, Forensic Audio, Video and Image Analysis Program, 

### AutoCalib: Automatic Traffic Camera Calibration at Scale

- **出處**:ACM BuildSys 2017 (also ACM Transactions on Sensor Networks 14(3–4), 2018)
- **作者**:Romil Bhardwaj, Gopi Krishna Tummala, Ganesan Ramalingam, Ramachandran Ramjee, Prasun Sinha
- **識別碼**:`DOI 10.1145/3199667 (TOSN version)`
- **連結**:https://www.microsoft.com/en-us/research/wp-content/uploads/2017/09/AutoCalib.pdf
- **關係判定**:`same_application`　引文屬實:是
- **它做什麼**:Deliberately abandons vanishing points and road features; uses a CNN to extract car key-points, solves calibration per vehicle from known car geometry, then filters and aggregates hundreds of noisy per-vehicle calibrations. Under 12% real-world distance error on city traffic cameras.
- **與我們的差別**:Explicitly argues AGAINST road markings as an anchor ('the dimensions of static features may vary across roads depending on the city') — the opposite of our position, which is that the legal standard makes them auditable in a forensic setting. Static camera, vehicle-geometry scale, no temporal marking signal, no depth model.
- ⚠ **審查更正**:Nothing was wrong. Verified citation line (with one added precision): Romil Bhardwaj, Gopi Krishna Tummala, Ganesan Ramalingam, Ramachandran Ramjee, Prasun Sinha. "AutoCalib: Automatic Traffic Camera Calibration at Scale." Proc. 4th ACM Int. Conf. on Systems for Energy-Efficient Built Environments (BuildSys '17), Delft, Nov 6-8 2017, pp. 1-10, DOI 10.1145/3137133.3137149; extended version ACM Tran

### Automatic Camera Calibration for Traffic Understanding

- **出處**:BMVC 2014
- **作者**:Markéta Dubská, Adam Herout, Jakub Sochor
- **連結**:https://bmva-archive.org.uk/bmvc/2014/papers/paper013/index.html
- **關係判定**:`same_application`　引文屬實:是
- **它做什麼**:Three vanishing points (vehicle motion via KLT + diamond-space accumulator, vehicle edges, vertical) calibrate a surveillance camera up to scale; scale is then fixed by matching the statistics of constructed 3D vehicle bounding-box dimensions against known mean vehicle dimensions for the country. Reports under 2% mean speed and distance error.
- **與我們的差別**:The 'mean vehicle dimensions for a given country' anchor is statistical and only valid in aggregate — it cannot certify a single vehicle's speed, which is what forensic use demands. Static camera; no road-marking length, no temporal signal, no ego speed, no depth model.
- ⚠ **審查更正**:Markéta Dubská, Adam Herout, Jakub Sochor. "Automatic Camera Calibration for Traffic Understanding." Proceedings of the British Machine Vision Conference (BMVC) 2014, BMVA Press. DOI 10.5244/C.28.42. [Venue BibTeX gives no page numbers. Note: the camera-ready PDF's printed byline and running header order is Dubská, Sochor, Herout — the venue metadata and dblp both use Dubská, Herout, Sochor as cit

### Calibration-Free Vehicle Speed Estimation: A Monocular Keypoint-Template Approach

- **出處**:arXiv preprint, 17 August 2026
- **作者**:Gaofeng Su, Keya Li, Raja Sengupta, Kara M. Kockelman
- **識別碼**:`arXiv:2608.16785`
- **連結**:https://arxiv.org/abs/2608.16785
- **關係判定**:`same_application`　引文屬實:是
- **它做什麼**:Estimates speed without camera calibration or roadway features, using a 36-keypoint vehicle template and a per-frame homography; evaluated on 400+ clips from VS13 and BrnoCompSpeed, 30–100 mph. MAE 15.0% (VS13) and 9.7% (BrnoCompSpeed); 77.9% / 93.1% of estimates within ±20%, improving to 11.7% / 7.6% after outlier removal.
- **與我們的差別**:Deliberately avoids road-geometry anchors altogether — the scale comes from a generic vehicle-shape template, which is the 'known object size' anchor family, and its accuracy (≈10–15% MAE) is an order of magnitude looser than marking-anchored methods. Fixed cameras only. It does confirm that as of 2026 the evaluation set for this task is still VS13 + BrnoCompSpeed.
- ⚠ **審查更正**:Citation needs no correction. Canonical form as printed on the pages I retrieved: Gaofeng Su, Keya Li, Raja Sengupta, Kara M. Kockelman, "Calibration-Free Vehicle Speed Estimation: A Monocular Keypoint-Template Approach", arXiv:2608.16785v1 [cs.CV], submitted 2026-08-17T16:39:06Z, 19 pages, 7 figures, no journal reference or DOI. Relation: same_application is correct and should NOT be upgraded. Tw

### Camera-based vehicle velocity estimation from monocular video

- **出處**:Computer Vision Winter Workshop (CVWW) 2018; winning entry, CVPR 2017 Autonomous Driving Velocity Estimation Challenge
- **作者**:Moritz Kampelmühler, Michael G. Müller, Christoph Feichtenhofer
- **識別碼**:`arXiv:1802.07094`
- **連結**:https://arxiv.org/abs/1802.07094 (PDF read: https://arxiv.org/pdf/1802.07094)
- **關係判定**:`same_application`　引文屬實:是
- **它做什麼**:Regresses relative velocity of annotated target vehicles from monocular dashcam clips using tracking, optical-flow and depth features. Documents the TuSimple velocity dataset: 1074 freeway sequences, 1280×720 at 20 fps, 40 frames each, 1442 annotated vehicles with position and velocity ground truth from range sensors, split into near (<20 m, ~12%), medium (20–45 m, ~65%) and far (>45 m, ~23%) evaluation bins. Reports 1.12 m/s average error against a stated ~0.71 m/s ground-truth accuracy; challenge leaderboard velocity MSE near 0.18, medium 0.66, far 3.07 m²/s².
- **與我們的差別**:This is the one public benchmark that measures the same thing we measure against radar — target-vehicle distance and velocity from a moving monocular camera, validated against lidar+radar, stratified by range. But the quantity is RELATIVE velocity, so the ego-speed chain (our marking odometer, and half of our near-field error budget) is never exercised; ground truth is single-frame (last frame only) so there is no time-continuity evaluation; the method is learned regression trained on the same camera, with no calibration, no scale anchor and no metric geometry to be wrong. It also gives the honest ceiling for this kind of validation: the reference sensor itself is only good to ~0.71 m/s.
- ⚠ **審查更正**:Citation is correct as given; only tightened wording is needed. Verified form: Moritz Kampelmühler, Michael G. Müller, Christoph Feichtenhofer, "Camera-based vehicle velocity estimation from monocular video", in Zuzana Kúkelová and Júlia Škovierová (eds.), Proceedings of the 23rd Computer Vision Winter Workshop (CVWW 2018), Český Krumlov, Czech Republic, February 5–7, 2018, 8 pp.; arXiv:1802.07094

### Comprehensive Data Set for Automatic Single Camera Visual Speed Measurement (BrnoCompSpeed)

- **出處**:IEEE Transactions on Intelligent Transportation Systems, 2018/2019
- **作者**:Jakub Sochor, Roman Juránek, Jakub Špaňhel, Lukáš Maršík, Adam Široký, Adam Herout, Pavel Zemčík
- **識別碼**:`arXiv:1702.06441; DOI 10.1109/TITS.2018.2825609`
- **連結**:https://arxiv.org/abs/1702.06441
- **關係判定**:`same_application`　引文屬實:是
- **它做什麼**:18 full-HD hour-long videos at six sites, 20,865 annotated vehicles with LiDAR optical-gate speed ground truth plus GPS verification, released with calibration and measured in-image lengths. Section II is an explicit survey (Table I) classifying every prior calibration method by what it uses for scale.
- **與我們的差別**:This is the field's authoritative taxonomy and it contains exactly two scale families — one known distance in the scene (often a line-marking stripe) and vehicle dimensions. Neither family measures anything in the time domain and none involves a moving camera, ego speed, or a depth network. The dataset is roadside-camera only, so it cannot be used to test our dashcam pipeline; and the same table is our best evidence that the temporal variant is absent from the literature it surveys.
- ⚠ **審查更正**:J. Sochor, R. Juránek, J. Špaňhel, L. Maršík, A. Široký, A. Herout, P. Zemčík, "Comprehensive Data Set for Automatic Single Camera Visual Speed Measurement," IEEE Transactions on Intelligent Transportation Systems, vol. 20, pp. 1633–1643, 2019 (early access 2018). DOI 10.1109/TITS.2018.2825609; arXiv:1702.06441 (v1 2017-02-21, v2 2018-05-09). Relation: same_application (monocular-camera vehicle sp

### Detection of 3D bounding boxes of vehicles using perspective transformation for accurate speed measurement

- **出處**:Machine Vision and Applications, 2020
- **作者**:Viktor Kocur, Milan Ftáčnik
- **識別碼**:`arXiv:2003.13137; DOI 10.1007/s00138-020-01117-x`
- **連結**:https://arxiv.org/abs/2003.13137
- **關係判定**:`same_application`　引文屬實:是
- **它做什麼**:Improves 3D vehicle bounding-box detection and tracking for speed measurement by using the known vanishing-point geometry of the surveilled scene to build a perspective transformation; evaluated on BrnoCompSpeed.
- **與我們的差別**:Takes the vanishing points and the scene scale as GIVEN (from the dataset's calibration) and works on the detection/tracking side. Static camera, no scale anchor of its own, no markings, no ego motion, no depth model — included to show that recent work in this line has moved to detection quality while leaving the scale question to BrnoCompSpeed's supplied calibration.
- ⚠ **審查更正**:Citation is correct; only made more precise: Viktor Kocur, Milan Ftáčnik, "Detection of 3D bounding boxes of vehicles using perspective transformation for accurate speed measurement", Machine Vision and Applications, vol. 31, no. 7-8, article 62, 2020 (online 2020-09-04). DOI 10.1007/s00138-020-01117-x; preprint arXiv:2003.13137 (v1 2020-03-29, v2 2020-08-04). Relation "same_application" stands an

### Determination of average vehicle speed utilizing reverse projection

- **出處**:Journal of Forensic Sciences, vol. 67, no. 1, 2022 (online 8 Oct 2021), pp. 188–199
- **作者**:Walter E. Bruehs, Dorothy Stout
- **識別碼**:`10.1111/1556-4029.14891`
- **連結**:https://api.crossref.org/works/10.1111/1556-4029.14891
- **關係判定**:`same_application`　引文屬實:是
- **它做什麼**:Controlled validation of reverse projection photogrammetry for vehicle speed: five digital video recorders captured a vehicle on a track with speed verified by Doppler radar and speedometer; frames were selected to establish vehicle position at two points and distance/time computed.
- **與我們的差別**:This is the study that documents the accuracy of the accepted practice under controlled conditions with an external truth instrument (Doppler radar) — the role that comma2k19 radar and the Haisheng manual frame-counting truth play for us. It is fixed-camera reverse projection with scene access; it contains no marking-based scale anchor, no vanishing-point range formula, no moving camera and no depth model. I retrieved metadata and a partially quoted abstract via Crossref only; I did not obtain the full text.
- ⚠ **審查更正**:No correction needed — every field matches. Canonical form for the bibliography: Bruehs, W. E., & Stout, D. (2022). Determination of average vehicle speed utilizing reverse projection. Journal of Forensic Sciences, 67(1), 188-199. https://doi.org/10.1111/1556-4029.14891 (first published online 8 October 2021; PMID 34622955). Relation stands as same_application. Two minor presentational notes: (a) 

### Evaluation of Tesla Dashcam Video System for Speed Determination Via Reverse Projection Photogrammetry

- **出處**:SAE Technical Paper 2023-01-0629, 2023
- **作者**:Benjamin T. Molnar, Louis R. Peck
- **識別碼**:`10.4271/2023-01-0629`
- **連結**:https://saemobilus.sae.org/papers/evaluation-tesla-dashcam-video-system-speed-determination-via-reverse-projection-photogrammetry-2023-01-0629
- **關係判定**:`same_application`　引文屬實:是
- **它做什麼**:Calibrates a 2019 Tesla Model 3's front and rear cameras for focal length and lens distortion, then determines (a) host-vehicle speed from the distance between solved camera locations in a time-distance analysis and (b) surrounding-vehicle speed by reverse projection against a point cloud of the approaching vehicle, with the Tesla stationary. Compared against onboard GPS: mean difference 0.38–0.72 mph across all tests.
- **與我們的差別**:Closest forensic work on measuring OTHER vehicles from a dashcam-class camera, and the accuracy figure to beat. But it is the opposite of our setting on every enabling assumption: the camera was physically available and calibrated for focal length and distortion beforehand; the target's speed is obtained by reverse-projecting a 3D point cloud of that specific approaching vehicle; and the host vehicle is STATIONARY for the other-vehicle tests, so there is no moving-camera range problem at all. No marking-based scale, no depth model.
- ⚠ **審查更正**:引用完全正確,不需更正。SAE 官方引用字串(照 SAE Mobilus 頁面原文):Molnar, B. and Peck, L., "Evaluation of Tesla Dashcam Video System for Speed Determination Via Reverse Projection Photogrammetry," WCX SAE World Congress Experience, Detroit, Michigan, United States, April 18, 2023, https://doi.org/10.4271/2023-01-0629. 補齊細節:SAE Technical Paper Series 2023-01-0629,線上出版日 2023-04-11,作者單位 Benjamin T. Molnar(J.S. Held, LLC)、L

### ForeSpeed: A real-world video dataset of CCTV cameras with different settings for vehicle speed estimation

- **出處**:arXiv preprint, 22 December 2025
- **作者**:Massimo Iuliani, Blake Sawyer, Marco Fontani, David Spreadborough, Martino Jerian (Amped Software)
- **識別碼**:`arXiv:2512.19364`
- **連結**:https://arxiv.org/abs/2512.19364 (PDF read: https://arxiv.org/pdf/2512.19364)
- **關係判定**:`same_application`　引文屬實:是
- **它做什麼**:A new public dataset built specifically for forensic speed estimation: one vehicle driven at known speeds (29–31 mph) past three digital and three analog CCTV cameras on three DVRs, exported in multiple codecs/containers/frame-rate modes (including variable frame rate), 269 passes / 322 videos, plus surveyed road reference measures so the analyst can rectify the road plane. Speed truth = speedometer plus an independent GPS app, both filmed by a separate camera, with the speedometer itself validated against a laser speed sensor. Case study benchmarks the manual Amped FIVE method: mean error −0.96 mph, 85% of cases within ±2 mph, with uncertainty boxes on tyre–road contact points and Δt = 5 ms.
- **與我們的差別**:Same forensic framing and the same contact-point primitive, but it is a fixed CCTV dataset with a manual, surveyed-scene workflow: the road plane is rectified from known ground-grid dimensions measured on site, which is precisely what we cannot do in accident casework. No ego camera, no lane-marking anchor, no depth model, and the only ground truth is the target vehicle's own speed — no distance ground truth at all. Note it is the fourth public real-speed dataset, appearing after the 2024 'only three' count.
- ⚠ **審查更正**:Citation line (verified, use as-is): Massimo Iuliani, Blake Sawyer, Marco Fontani, David Spreadborough, Martino Jerian. "ForeSpeed: A real-world video dataset of CCTV cameras with different settings for vehicle speed estimation." arXiv:2512.19364v1 [eess.IV], submitted 22 Dec 2025. DOI 10.48550/arXiv.2512.19364. No journal-ref, no comments. Affiliations: Amped Software (Trieste, Italy) and Amped S

### Forensic application of inverse and reverse projection photogrammetry to determine subject location and orientation when both camera and subject move relative to the scene

- **出處**:Forensic Science International, vol. 331, 2022, article 111145
- **作者**:Geoffrey T. Desmoulin, Manraj Kalkat, Theodore E. Milner
- **識別碼**:`10.1016/j.forsciint.2021.111145`
- **連結**:https://api.semanticscholar.org/graph/v1/paper/DOI:10.1016/j.forsciint.2021.111145
- **關係判定**:`same_application`　引文屬實:是
- **它做什麼**:Handles the forensic case where BOTH the camera and the subject move relative to the scene (a chest-mounted action camera on a mountain bicycle). Inverse photogrammetry establishes the location and orientation of the camera relative to the scene; reverse projection with a reference bicycle placed in the scene fixes the bike-to-camera relationship; rider placement is estimated by comparing synchronised side views with the chest-camera view from a preceding descent.
- **與我們的差別**:The published forensic answer to the moving-camera problem, and it shows what that answer costs: scene access, a physical reference object placed at the scene, and a separately filmed reference run of the same subject. Our method replaces all of that with markings already in the frame. No marking cycle, no scale anchor from road geometry, no depth model. I verified DOI/journal/volume/pages via Crossref and read a Semantic Scholar record; the publisher abstract itself returned 403, so the quote above is a fragment from that record rather than a full sentence from the paper.
- ⚠ **審查更正**:No correction needed. Canonical citation line, copied from the records I fetched: Geoffrey T. Desmoulin, Manraj Kalkat, Theodore E. Milner, "Forensic application of inverse and reverse projection photogrammetry to determine subject location and orientation when both camera and subject move relative to the scene," Forensic Science International, vol. 331, Feb. 2022, art. 111145. DOI: 10.1016/j.fors

### Multi-Stream Attention Learning for Monocular Vehicle Velocity and Inter-Vehicle Distance Estimation (MSANet)

- **出處**:BMVC 2021
- **作者**:Kuan-Chih Huang, Yu-Kai Huang, Winston H. Hsu
- **識別碼**:`arXiv:2110.11608`
- **連結**:https://arxiv.org/abs/2110.11608 (PDF read: https://arxiv.org/pdf/2110.11608)
- **關係判定**:`same_application`　引文屬實:是
- **它做什麼**:Best published numbers I could retrieve on the TuSimple velocity dataset: position MSE 7.56 m², velocity MSE 0.10 / 0.26 / 1.58 m²/s² for near / medium / far, and inter-vehicle distance AbsRel 0.034, SqRel 0.105, RMSE 2.416 m, δ<1.25 = 0.997.
- **與我們的差別**:Gives the number our near-field distance should be read against: 3.4% AbsRel on a moving camera with lidar+radar truth — but supervised on the same camera and same freeway domain, with the contact point defined as 'the closest point for each vehicle' rather than the tyre-ground row, and with no camera geometry, no scale anchor and no cross-device transfer. Nothing here is zero-shot and nothing addresses an unknown focal length.
- ⚠ **審查更正**:CITATION STANDS AS GIVEN — nothing to correct. Verified copy-able form: Kuan-Chih Huang, Yu-Kai Huang, Winston H. Hsu. "Multi-Stream Attention Learning for Monocular Vehicle Velocity and Inter-Vehicle Distance Estimation." British Machine Vision Conference (BMVC) 2021, paper 0606. arXiv:2110.11608 (submitted 22 Oct 2021; arXiv Comments field reads "Accepted to BMVC 2021"). National Taiwan Universi

### Real-time Prediction of Automotive Collision Risk from Monocular Video

- **出處**:arXiv preprint, 2019
- **作者**:Derek J. Phillips, Regina Madigan, Juan Carlos Aragon, Sunil Chintakindi, Anjali Roychowdhury, Mykel J. Kochenderfer
- **識別碼**:`arXiv:1902.01293`
- **連結**:https://ar5iv.labs.arxiv.org/html/1902.01293
- **關係判定**:`same_application (check: understated)`　引文屬實:是
- **它做什麼**:A monocular collision-risk pipeline whose absolute-speed component uses lane markings of known dimensions as stationary references instead of optical flow: it detects the reference lanes, watches a vertically fixed point on the lane, times how long a marking takes to appear, disappear and appear again, and converts that with the known marking spacing into ego speed.
- **與我們的差別**:Same physical idea as our marking odometer (a fixed image location, legal marking spacing, timing rather than flow), but implemented as edge/appearance event timing, not as autocorrelation of a brightness signal — so it has no principled handling of the half-/double-period ambiguity that dominates our night-time and cross-road-class failures. It uses a single fixed point, not two rows, so it extracts no scale constant; the ego speed is consumed for risk prediction, not used to calibrate a range formula, and no depth network is rescaled.
- ⚠ **審查更正**:Derek J. Phillips, Regina Madigan, Juan Carlos Aragon, Sunil Chintakindi, Anjali Roychowdhury, Mykel J. Kochenderfer, "Real-time Prediction of Automotive Collision Risk from Monocular Video", arXiv:1902.01293, submitted 4 Feb 2019. arXiv comments field: "Submitted to IV2019. 7 pages, 4 figures, 3 tables"; no journal-ref shown on arXiv and I found no evidence it appeared in the IV 2019 proceedings,

### Robust video-based vehicle speed estimation for occluded scenes for forensic analysis of traffic accidents

- **出處**:Multimedia Tools and Applications, 2026
- **作者**:Youngsoo Choi, Seung-Hyun Kong
- **識別碼**:`10.1007/s11042-026-21222-9`
- **連結**:https://api.crossref.org/works/10.1007/s11042-026-21222-9
- **關係判定**:`same_application`　引文屬實:是
- **它做什麼**:Estimates vehicle speed from fixed-camera footage with no prior camera or scene information, even under full occlusion of parts of the trajectory. SiamRPN tracking + Kalman filtering for occlusions, Mask R-CNN instance segmentation to extract wheel centres, a smoothed unscented Kalman filter to predict occluded wheel coordinates, and speed from the geometric CROSS-RATIO (a perspective-invariant distance ratio) combined with the known wheelbase specification. Errors: 0.30 and 1.70 km/h in straight/curved simulation, 0.41 km/h constant-speed and 0.57 km/h accelerating real tests, 0.49–3.05 km/h on real accident cases vs field measurements.
- **與我們的差別**:The strongest recent forensic claim of 'no prior information about the camera or scene', so it is the paper our novelty argument must distinguish itself from. It does so cleanly: the scale anchor is the TARGET VEHICLE's known wheelbase (requires identifying the model and obtaining its specification, and it is a property of the measured object, not of the road), the geometry is the projective cross-ratio rather than a ground-plane range formula with a vanishing-point horizon, the camera is fixed, and there is no depth model. Note the parallel to our own finding that only a length ALONG the direction of travel can serve — a wheelbase is longitudinal, which is why the cross-ratio works for them.
- ⚠ **審查更正**:Citation is correct; only added precision, nothing changed. Full form: Youngsoo Choi and Seung-Hyun Kong, "Robust video-based vehicle speed estimation for occluded scenes for forensic analysis of traffic accidents," Multimedia Tools and Applications, vol. 85, no. 2, article 90, published 2 February 2026. DOI: 10.1007/s11042-026-21222-9. Landing page: https://link.springer.com/article/10.1007/s1104

### Speed Analysis from Video: A Method for Determining a Range in the Calculations

- **出處**:SAE Technical Paper 2021-01-0887, 2021
- **作者**:Gray Beauchamp, David Pentecost, Daniel Koch, Alireza Hashemian, James Marr, Rheana Cordero
- **識別碼**:`10.4271/2021-01-0887`
- **連結**:https://saemobilus.sae.org/papers/speed-analysis-video-a-method-determining-a-range-calculations-2021-01-0887
- **關係判定**:`same_application`　引文屬實:是
- **它做什麼**:Gives a procedure for reporting vehicle speed from video as a RANGE rather than a point value, propagating two uncertainty sources: uncertainty in locating the vehicle's position (from photogrammetry best-fit) and uncertainty in the time interval between positions. Validated against recordings of an instrumented vehicle at known speeds.
- **與我們的差別**:This is the forensic-domain template for how a speed number must be reported (a range with stated components), which our ±95% CI = fit standard error ⊕ scale CV is the analogue of. It contains no scale-anchoring innovation: positions come from ordinary camera-match photogrammetry against the scene. No markings-as-clock, no A = h·f, no depth model.
- ⚠ **審查更正**:No correction needed. Exact citation as the publisher page gives it: Beauchamp, G., Pentecost, D., Koch, D., Hashemian, A., Marr, J., and Cordero, R., "Speed Analysis from Video: A Method for Determining a Range in the Calculations," SAE Technical Paper 2021-01-0887, SAE WCX Digital Summit, published 2021-04-06, doi:10.4271/2021-01-0887 (all authors Kineticorp LLC). Relation stands as same_applica

### Speed Determination Using Audio Analysis of Dash Camera Video from Passenger Vehicle Tires Frequencies for Vehicle Accident Reconstruction

- **出處**:SAE Technical Paper 2025-01-8682, 2025
- **作者**:Henry V. Vega, Long Justin Ngo, Ziad Hatab, Anthony Cornetto, Krystina Engleman, Eric Hunter
- **識別碼**:`10.4271/2025-01-8682`
- **連結**:https://saemobilus.sae.org/papers/speed-determination-using-audio-analysis-dash-camera-video-passenger-vehicle-tires-frequencies-vehicle-accident-reconstruction-2025-01-8682
- **關係判定**:`same_application`　引文屬實:是
- **它做什麼**:Determines ego speed from the AUDIO track of dashcam video: the tyre tread pattern in contact with the roadway generates a frequency component that varies with speed. Uses commercial dashcams, remote microphones to localise the frequency source and a VBox Sport for ground-truth speed; prior work in the same line used audio plus a known wheelbase.
- **與我們的差別**:Worth knowing because it is the other 'periodicity as an odometer' idea in forensic practice — a known physical period (tyre circumference/tread pitch) read out as a frequency — and it shares our motivation of not trusting optical flow. But the periodic signal is acoustic and vehicle-borne, so it depends on the tyre and road surface rather than on road geometry, gives only ego speed, and contributes nothing to range, scale or depth. No accuracy figure was stated on the abstract page I retrieved.
- ⚠ **審查更正**:無需更正。經 Crossref 獨立核對後的標準引用行為:Vega, H. V., Ngo, L. J., Hatab, Z., Cornetto, A., Engleman, K., & Hunter, E. (2025). "Speed Determination Using Audio Analysis of Dash Camera Video from Passenger Vehicle Tires Frequencies for Vehicle Accident Reconstruction." SAE Technical Paper 2025-01-8682, SAE International, published 2025-04-01. DOI: 10.4271/2025-01-8682. 關係標籤 same_application 維持不變(非 same_method、非

### The Accuracy of Vehicle Speeds, Decelerations, and Brake Onset Times Calculated from Onboard Dash Cameras

- **出處**:SAE Technical Paper 2025-01-8691, 2025
- **作者**:Thomas Flynn, Matthew Ahrens, Cole Young, Gunter P. Siegmund
- **識別碼**:`10.4271/2025-01-8691`
- **連結**:https://saemobilus.sae.org/papers/accuracy-vehicle-speeds-decelerations-brake-onset-times-calculated-onboard-dash-cameras-2025-01-8691
- **關係判定**:`same_application`　引文屬實:是
- **它做什麼**:Quantifies dashcam-derived kinematics across five cameras using match-moving, with scale and location supplied by a 3D laser scan of the test site. Speed estimates ranged from underestimating by 0.45 ± 0.05 km/h to overestimating by 0.80 ± 0.16 km/h; deceleration from −0.012 ± 0.013 g to +0.049 ± 0.012 g; brake onset detection lagged actual brake application by 14 ± 41 ms to 94 ± 29 ms.
- **與我們的差別**:This is the current state of the art for ego kinematics from a dashcam in forensic practice, and its sub-1 km/h numbers are the honest benchmark for our marking odometer. The decisive difference is that its metric scale comes entirely from a laser scan of the site — the scene must be reachable and scannable. It is camera-tracking/match-moving over general scene features, not a periodic-marking measurement, and it reports only ego motion, no target range and no depth model.
- ⚠ **審查更正**:Flynn, T., Ahrens, M., Young, C., and Siegmund, G.P., "The Accuracy of Vehicle Speeds, Decelerations, and Brake Onset Times Calculated from Onboard Dash Cameras," SAE Technical Paper 2025-01-8691, WCX SAE World Congress Experience, Detroit, MI, April 8, 2025 (publication date listed as 2025-04-01), doi:10.4271/2025-01-8691. Relation: same_application only — a forensic-practice accuracy benchmark f

### The Effect of Tracker and Control Point Distributions on Vehicle Position and Speed Estimates from Dash Camera Video

- **出處**:SAE Technical Paper 2025-01-8697, 2025
- **作者**:Cole Young, Matthew Ahrens, Thomas Flynn, Gunter P. Siegmund
- **識別碼**:`10.4271/2025-01-8697`
- **連結**:https://saemobilus.sae.org/papers/effect-tracker-control-point-distributions-vehicle-position-speed-estimates-dash-camera-video-2025-01-8697
- **關係判定**:`same_application`　引文屬實:是
- **它做什麼**:Degrades the available 2D trackers and 3D control points in SynthEyes camera-tracking solutions of a dashcam braking run to mimic feature-poor environments. For six of eight test conditions the camera solutions had mean absolute position errors of 32–119 mm and speed errors <1 km/h against the full-feature reference; one condition failed to solve and one with few, poorly distributed control points had larger errors.
- **與我們的差別**:Directly relevant as a failure-boundary study of the mainstream alternative: it shows the accepted dashcam method degrades when the scene is barren, which is exactly the regime (empty motorway, road surface only) where our marking odometer still works because the markings themselves are the feature. But it still needs 3D control points in the scene and a reference solution; it is not a scale-anchored geometric method, and there is no depth model.
- ⚠ **審查更正**:Citation is correct as given; no correction needed. Canonical form: Young, C., Ahrens, M., Flynn, T., and Siegmund, G.P., "The Effect of Tracker and Control Point Distributions on Vehicle Position and Speed Estimates from Dash Camera Video," SAE Technical Paper 2025-01-8697, 2025, doi:10.4271/2025-01-8697 (WCX SAE World Congress Experience, Detroit, 1 April 2025; MEA Forensic Engineers & Scientist

### Traffic Surveillance Camera Calibration by 3D Model Bounding Box Alignment for Accurate Vehicle Speed Measurement

- **出處**:Computer Vision and Image Understanding, 2017
- **作者**:Jakub Sochor, Roman Juránek, Adam Herout
- **識別碼**:`arXiv:1702.06451; DOI 10.1016/j.cviu.2017.05.015`
- **連結**:https://arxiv.org/abs/1702.06451
- **關係判定**:`same_application`　引文屬實:是
- **它做什麼**:Fully automatic roadside calibration: two vanishing points from tracked keypoints and vehicle edgelets, then scene scale by rendering 3D CAD models of fine-grained-classified vehicles and matching their projected bounding boxes to the detected ones. 1.10 km/h mean speed error on BrnoCompSpeed, beating the authors' own manual calibration (1.35 km/h).
- **與我們的差別**:Scale comes from vehicle CAD dimensions, i.e. the object being measured supplies the ruler; we refuse that because in forensic work the target vehicle's model may be unknown or disputed. Static camera, no ego motion, no marking periodicity, no depth model. Their own ManualCalib baseline uses surveyed distances on the road — the very thing our part (2) removes. Note their paper confirms part (1) is classical: they use lane dividing line intersection for the first vanishing point 'in agreement with the previous papers'.
- ⚠ **審查更正**:No correction required. Complete citation line (volume/pages added for completeness, confirmed against the BUT FIT publication record): Sochor, J.; Juránek, R.; Herout, A. "Traffic surveillance camera calibration by 3D model bounding box alignment for accurate vehicle speed measurement." Computer Vision and Image Understanding, 2017, vol. 161, pp. 87-98. ISSN 1077-3142. DOI 10.1016/j.cviu.2017.05.

## 未能完成驗證(引用前必須自行取回)

- **MapAnything: Evaluating Monocular Metric Depth Models for 3D Urban Asset Localization**　(depth-anchor)　https://arxiv.org/abs/2509.14839
  - 原因:HOW VERIFIED: fetched https://arxiv.org/abs/2509.14839 and the v1/v2/v3 abs pages, plus the full v3 HTML (256 KB, saved to scratchpad as map3.html / map3.flat) and grepped the whol
- **Determination of Vehicle Speed from Recorded Video Using Reverse Projection Photogrammetry and File Metadata**　(forensic)　https://brycewestlake.com/wp-content/uploads/2021/03/Westlake-JForensicSci-Determination-of-Vehicle-Speed-Epstein-Westlake-2019_stamped.pdf
  - 原因:agent did not return a check
- **Simulation-based reconstruction of traffic incidents from moving vehicle mono-camera**　(forensic)　https://api.crossref.org/works?query.bibliographic=Simulation-based+reconstruction+of+traffic+incidents+from+moving+vehicle+mono-camera
  - 原因:RETRIEVED BY ME (3 independent sources, all fetched this session): 1. Crossref REST (https://api.crossref.org/works/10.1016/j.scijus.2021.11.001 and the raw ?query.bibliographic= f
- **Dynamic driving metric output generation using computer vision methods (patent family)**　(marking-odometer)　https://patents.google.com/patent/US10817729B2/en
  - 原因:agent did not return a check
- **The study on the estimation of vehicles speed using a dashboard camera**　(marking-odometer)　https://link.springer.com/article/10.1007/s11042-023-17171-2?error=cookies_not_supported
  - 原因:THE PAPER IS REAL. Not fabricated, not misremembered. I retrieved it three independent ways: Crossref API (api.crossref.org/works/10.1007/s11042-023-17171-2), the Semantic Scholar
- **End-to-end Learning for Inter-Vehicle Distance and Relative Velocity Estimation in ADAS with a Monocular Camera**　(benchmarks)　https://arxiv.org/abs/2006.04082 (PDF read: https://arxiv.org/pdf/2006.04082)
  - 原因:agent did not return a check
- **A Video-Based System for Vehicle Speed Measurement in Urban Roadways (UTFPR dataset)**　(benchmarks)　https://api.crossref.org/works/10.1109/tits.2016.2606369 (Crossref record retrieved; publisher page not accessible)
  - 原因:agent did not return a check
- **Efficient Vision-based Vehicle Speed Estimation**　(benchmarks)　https://arxiv.org/abs/2505.01203
  - 原因:agent did not return a check
- **GVDepth: Zero-Shot Monocular Depth Estimation for Ground Vehicles based on Probabilistic Cue Fusion**　(benchmarks)　https://arxiv.org/abs/2412.06080
  - 原因:agent did not return a check
- **Vehicle distance estimation using a mono-camera for FCW/AEB systems**　(benchmarks)　https://api.crossref.org/works/10.1007/s12239-016-0050-9 (Crossref record retrieved; Springer landing page requires authentication)
  - 原因:agent did not return a check
- **Vehicle Speed Measurement Methodology Robust to Playback Speed-Manipulated Video File**　(benchmarks)　https://api.crossref.org/works/10.1109/access.2021.3115500 (Crossref record retrieved; IEEE Xplore page not retrievable from here)
  - 原因:agent did not return a check

另有搜尋階段列為 `unverified`(抓不到頁面)的候選,見工作流輸出;
其中 `Sensors 18(9):2956, 2018`(Around View Monitor 的車道標線自標定)是值得追的近似前案。
