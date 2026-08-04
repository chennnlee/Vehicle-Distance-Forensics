# 公開資料集驗證計畫（回應 2026-08-03 教授指示）

教授報告後給了四點：

1. 連結 object detector，看最準的模型，算速度誤差範圍
2. 找資料集，看有沒有連結論文
3. 全部抓到的準確度算出來，整個資料集平均的速度跟誤差算出來
4. 資料集若有 bounding box，可以微調 object detector

四點其實是同一條線：**找一個有論文的公開資料集 → 在整個資料集上跑 → 算總體誤差 → 有 bbox 就微調偵測器**。
第 2 點是其他三點的前提,所以先做完它。以下是調查結果與可執行計畫。

---

## 一、資料集調查（回應第 2 點）

### A. 固定式相機測他車速 —— 對應本專案管線 A

| 資料集 | 論文 | 內容 | 真值來源 | 是否有 2D bbox |
|---|---|---|---|---|
| **BrnoCompSpeed** | Sochor et al., *Comprehensive Data Set for Automatic Single Camera Visual Speed Measurement*, IEEE T-ITS 2019 | 18–21 支 1920×1080 @50fps,每支約 1 小時,6 個地點,**20,865 台車** | **雷射光閘**（LIDAR-based light barrier）+ GPS 軌跡交叉驗證 | ✗（提供的是「車輛在路面平面上的點」逐幀座標 + 相機標定,非偵測框標註） |
| UTFPR | Luvizon et al., *A Video-Based System for Vehicle Speed Measurement in Urban Roadways*, IEEE T-ITS 2017 | 5 小時 1080p@30fps,市區 | 感應線圈（inductive loop） | ✗ |

**BrnoCompSpeed 是這個題目的標準 benchmark** —— 近年論文（例：*Efficient Vision-based Vehicle Speed
Estimation*, J. Real-Time Image Processing 2025）都在它上面報數字,所以在它上面跑出來的誤差**可以直接
與文獻比較**,這正是教授第 3 點想要的東西。

它同時附**相機標定參數**（消失點、主點、scale）。這給了我們一個重要選項:可以用「他們的標定」跑一次、
用「我們自己的尺度錨方法」跑一次,兩者比較就能把**量測鏈的誤差**與**標定的誤差**分開 —— 這正好呼應
我們自己的結論（誤差主要來自尺度錨,不是偵測器）。

**綜述論文（寫報告時可引用）**:Fernández Llorca, Hernández Martínez & García Daza,
*Vision-based vehicle speed estimation: A survey*, IET Intelligent Transport Systems, 2021
（arXiv:2101.06159, DOI 10.1049/itr2.12079）。該綜述明確指出:**公開且附速度真值的資料集非常少**,
主要就是 BrnoCompSpeed 與 UTFPR 兩個。

### B. 行車紀錄器自車速 —— 對應本專案管線 B（我們的主力）

| 資料集 | 論文 | 自車速真值 | 是否有 bbox | 適合度 |
|---|---|---|---|---|
| **nuScenes** | Caesar et al., *nuScenes: A multimodal dataset for autonomous driving*, CVPR 2020 | ego_pose（50 Hz）+ CAN bus `vehicle_monitor` 車速 | ✓ 3D 標註可投影成 2D | **實測不適合,見下** |
| **KITTI** | Geiger et al., *Are we ready for Autonomous Driving? The KITTI Vision Benchmark Suite*, CVPR 2012 | OXTS RT3003 GNSS/IMU 精確速度 | ✓ object benchmark 7,481 張訓練影像 | 中等（德國路型,虛線規格不同） |
| **comma2k19** | Schafer et al., *A Commute in Data: The comma2k19 Dataset*, 2018 | CAN bus 車速 | ✗ | **最貼近**（33 小時加州高速公路,連續虛線、高速帶） |

#### ⚠ 實測結論:本機已有的 nuScenes v1.0-mini 不適合當速度 benchmark

`data/nuscenes/` 已有完整 v1.0-mini（5.1 GB,10 scenes、404 keyframes、2,342 張 CAM_FRONT）。
直接用 `ego_pose.json` 差分算自車速:

```
全 mini 自車速: 中位 18.3 km/h,p90 44.1,max 55.3
>60 km/h 佔比 0.0%    >80 km/h 佔比 0.0%
```

10 個 scene 全是市區場景（路口等待、停車場、行人穿越、夜間市區）。**與本系統最紮實的驗證區間
（60–100 km/h 國道）完全不重疊**,而且市區路口/停車場沒有連續的法定虛線,虛線週期碼表無從運作。

→ **nuScenes 不當速度 benchmark,但仍可用於第 4 點（微調偵測器）**,因為它的 3D 標註可投影成 2D bbox。

### C. 為第 4 點（微調偵測器）準備的資料集

⚠ **這裡有一個容易被忽略的陷阱:我們用的是分割模型,不是偵測模型。**

本專案的接地點取「**遮罩最低 12%**」而不是「框底邊」——因為框底邊會被陰影與保險桿下緣拉走,
而接地點位置**直接決定距離與速度**。所以:

- 只有 **bbox** 的資料集（KITTI、nuScenes、UA-DETRAC、BDD100K 主集）**沒辦法微調遮罩頭**,
  只能微調偵測頭,遮罩仍是 COCO 訓練出來的 → 對我們的量測精度幫助有限。
- 而且 nuScenes 的 2D 框是 3D 立方體投影後的**軸對齊外接框**,天生比 COCO 的緊貼框鬆
  （實測投影圖可見卡車框略大於車體）。用鬆框微調會把框撐大 → 接地點下移 → 距離改變。

| 資料集 | 有 instance mask？ | 內容 |
|---|---|---|
| **nuImages** | ✅ **有** | 93,000 張、**80 萬個物件**,同時有 instance mask + 2D box + 語意分割;nuScenes 團隊出品,同一套類別,取自約 500 個 log（比 nuScenes 的 83 個更多樣） |
| Cityscapes | ✅ 有 | 街景 instance segmentation,但車輛樣本數較少 |
| BDD100K | 部分 | 10 萬張有 bbox,另有 1 萬張的 instance segmentation 子集 |
| KITTI / nuScenes / UA-DETRAC | ✗ 只有框 | 可微調偵測頭,不能微調遮罩頭 |

→ **第 4 點若要做,正解是 nuImages**,不是 nuScenes。

#### 已完成的準備工作

`tools/nuscenes_to_yolo_bbox.py`（本機 nuScenes v1.0-mini 實跑通過）:
把 3D 立方體經 global → ego → camera 轉換後投影成 2D 框,輸出 **YOLO 格式標註**,
class id 直接用 **COCO 編號**（car 2 / motorcycle 3 / bus 5 / truck 7）,
這樣微調出來的模型可以直接丟回現有管線,不必改任何過濾邏輯。

實跑結果（CAM_FRONT、visibility ≥ 2）:404 張影像、**1,724 個車輛框**
（car 1273、truck 213、bus 145、motorcycle 93）。已輸出驗證圖目視確認投影正確。
同一套轉換邏輯可以直接套用到 nuImages（同團隊、同座標慣例）。

---

## 二、對四點的逐項回應與計畫

### 第 1 點:連結 object detector、用最準的模型算速度誤差範圍

我們**已經做過**五模型比較（`data/output/model_comparison/`,2026-07-11）,但只在自有素材上。
教授要的是在公開資料集上重做,讓結論可被外部檢驗 —— 這個要求合理,值得做。

執行時建議把「誤差範圍」報成**分布**而不是單一數字:

- MAE、bias
- 誤差分位數 p50 / p90 / p95
- ±95% 信賴區間（本專案 CCTV 管線已有此機制:擬合標準誤 ⊕ scale CV）

**要先講清楚的前提**:我們自己的量級分析顯示接地點鏈雜訊約 **0.4 km/h**,而尺度校正不確定度是
**2–11 km/h**（差一個數量級）。所以「換最準的模型」在我們的架構下**預期不會顯著改變速度誤差**。
在公開資料集上把這件事量出來,本身就是一個可以寫進報告的結論。

### 第 2 點:找資料集與論文 ✅ 已完成（見上表）

### 第 3 點:整個資料集的平均速度與誤差

**BrnoCompSpeed 就是為此設計的**（20,865 台車、雷射真值),而且能直接與文獻對照。

輸出建議:
- 逐地點（6 個 location）與整體的 MAE / 誤差分布
- 速度分布直方圖（資料集平均速度）
- 與文獻已發表數字的對照表

### 第 4 點:若有 bbox 就微調偵測器

可行,但**建議先量再決定**,理由同第 1 點。建議順序:

1. 先在公開資料集上量出「現用 v8m」與「最準模型」的**速度**誤差差距
2. 若差距 < 尺度不確定度 → 用數據說明微調的邊際效益有限,並把資源投在尺度錨
3. 若差距顯著 → 才用 KITTI / nuScenes / BDD100K / UA-DETRAC 的 bbox 做微調

這樣不論結果如何都有可寫的結論,也不會把時間花在事後證明沒有幫助的事情上。

---

## 三、目前的阻塞與所需資源

| 項目 | 狀況 |
|---|---|
| BrnoCompSpeed 下載 | 完整 tar 約 **200 GB**；本機根分割區只剩 **139 GB** → 空間不足 |
| BrnoCompSpeed 連線 | `medusa.fit.vutbr.cz` 在目前開發環境**無法解析/連線** → 需用學校網路 |
| 取得方式 | README 指定可 email 作者（`ispanhel@fit.vutbr.cz`；論文作者 `{isochor,herout,ijuranek}@fit.vutbr.cz`）索取,亦可直接抓 tar |
| 授權 | README **未載明正式授權條款**,存取似需作者同意 → 學術使用前建議先去信說明用途 |

**建議動作（需使用者執行）**:去信作者說明是大專生研究計畫、用途為單相機測速方法驗證,詢問
是否有**較小的子集**（例如單一 location 或抽樣片段）可供下載。同時準備外接空間或改用學校主機。

在 BrnoCompSpeed 到手之前,**可以先做的替代路徑**:

- comma2k19 或 KITTI raw 的小 subset → 先把「管線 B 自車速 vs 公開真值」的評估腳本寫好跑通
- nuScenes mini（已在本機）→ 先把「3D 標註投影成 2D bbox」的流程做好,為第 4 點的微調預備

---

## 四、要注意的方法學問題（跑之前要想清楚）

1. **尺度錨的移植性**:本系統的尺度來源是**台灣法定標線**（車道線 4m+6m、車道寬 3.5m）。在捷克
   （BrnoCompSpeed）或美國（comma2k19）路上,標線規格不同。兩個選項:
   - 用資料集自帶的相機標定 → 評估的是「量測鏈」而非「完整系統」
   - 查當地標線法規後自行錨定 → 評估的是完整系統,但多一層不確定度
   兩者都做並比較,反而是最有價值的呈現方式。

2. **管線 A 與管線 B 不要混談**:BrnoCompSpeed 是固定相機（管線 A）,comma2k19/KITTI 是行車紀錄器
   （管線 B）。兩條管線的誤差來源不同,報告時要分開。

3. **虛線週期**:我們在台灣實測發現國道實際是 **10 m** 而非規範的 12 m（已用 GPS 反驗）。到了別的
   國家一定要重新反驗,不能直接套規範值。
