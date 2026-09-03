// 單一主題簡報:他車距離與速度的外部儀器驗證(2026-09-01,v2)
//
// v2 依使用者要求改寫:(1) 不以「道歉/認錯」為敘事,方法學問題就用方法學講法陳述;
// (2) 每個誤差指標都要有定義頁,不能只丟數字;(3) 不用比喻;
// (4) 雷達的來源、欄位、取樣與對齊處理要交代清楚。
// 數字全部取自 data/output/comma2k19_radar_eval/README.md。
const PptxGenJS = require("pptxgenjs");

const F = process.env.REPORT_ASSETS || "/home/s11244/tmp/pptx_build/assets";
const INK = "1A1A1A", MUTED = "6B6B6B", ACCENT = "1F4E79", LINE = "DDDDDD", SOFT = "F5F6F8";
const GOOD = "2E6B2E", BAD = "A33A31";
const FONT = "Microsoft JhengHei";

const p = new PptxGenJS();
p.defineLayout({ name: "W16", width: 13.333, height: 7.5 });
p.layout = "W16";

function title(s, text, sub) {
  s.addText(text, { x: 0.9, y: 0.55, w: 11.6, h: 0.7, fontSize: 29, bold: true, color: INK, fontFace: FONT });
  if (sub) s.addText(sub, { x: 0.9, y: 1.28, w: 11.6, h: 0.4, fontSize: 15, color: MUTED, fontFace: FONT });
  s.addShape(p.ShapeType.line, { x: 0.9, y: sub ? 1.78 : 1.42, w: 1.4, h: 0, line: { color: ACCENT, width: 2.5 } });
}
const para = (s, text, o = {}) =>
  s.addText(text, {
    x: o.x ?? 0.9, y: o.y ?? 2.2, w: o.w ?? 11.6, h: o.h ?? 1.0,
    fontSize: o.size ?? 17, color: o.color ?? INK, fontFace: FONT, lineSpacingMultiple: 1.35, valign: "top",
  });
const small = (s, text, y, o = {}) =>
  s.addText(text, { x: o.x ?? 0.9, y, w: o.w ?? 11.6, h: o.h ?? 0.5, fontSize: o.size ?? 13,
                    color: o.color ?? MUTED, fontFace: FONT, lineSpacingMultiple: 1.3 });

function table(s, rows, colW, o = {}) {
  s.addTable(
    rows.map((r, i) => r.map((c, j) => ({
      text: c,
      options: {
        fontSize: i === 0 ? (o.headSize ?? 13) : (o.size ?? 14.5), fontFace: FONT, valign: "middle",
        align: j === 0 ? "left" : (o.align ?? "center"),
        bold: i === 0 || (o.highlight ?? []).includes(i - 1),
        color: i === 0 ? "FFFFFF" : ((o.rowColor && o.rowColor[i - 1]) || INK),
        fill: i === 0 ? { color: ACCENT } : { color: (o.highlight ?? []).includes(i - 1) ? SOFT : "FFFFFF" },
      },
    }))),
    { x: o.x ?? 0.9, y: o.y ?? 2.15, w: o.w ?? 11.6, colW,
      rowH: o.rowH ?? 0.44, border: { type: "solid", color: LINE, pt: 0.5 }, margin: 0.06 });
}

/* ---------------------------------------------------------------- 1 封面 */
let s = p.addSlide();
s.addShape(p.ShapeType.rect, { x: 0, y: 2.55, w: 13.333, h: 0.06, fill: { color: ACCENT }, line: { color: ACCENT } });
s.addText("他車距離與速度的外部驗證", { x: 0.9, y: 1.45, w: 11.6, h: 1.05, fontSize: 38, bold: true, color: INK, fontFace: FONT });
s.addText("以車輛原廠毫米波雷達為對照", { x: 0.9, y: 2.85, w: 11.6, h: 0.5, fontSize: 20, color: MUTED, fontFace: FONT });
s.addText([
  { text: "結論:", options: { bold: true, color: INK } },
  { text: "在系統自定的近場範圍(約 32 公尺內),跟車距離的相對誤差中位數為 7.0%,\n" +
          "目標車絕對速度的平均絕對誤差為 3.54 km/h。超出該範圍者距離誤差達 20%,不應採用。",
    options: { color: INK } },
], { x: 0.9, y: 3.85, w: 11.2, h: 1.3, fontSize: 18, fontFace: FONT, lineSpacingMultiple: 1.35 });
s.addText("資料來源:comma2k19 公開資料集(Schafer 等,2018)　|　3 個路段、908 個配對影格　|　2026-09-01",
  { x: 0.9, y: 6.5, w: 11.6, h: 0.4, fontSize: 13, color: MUTED, fontFace: FONT });

/* ------------------------------------------------ 2 為什麼需要外部對照 */
s = p.addSlide();
title(s, "為什麼需要一個外部對照", "自車速已有多重外部真值,他車則沒有");

s.addShape(p.ShapeType.roundRect, { x: 0.9, y: 2.15, w: 11.6, h: 0.95,
  fill: { color: SOFT }, line: { color: LINE }, rectRadius: 0.08 });
s.addText("目標車絕對速度  =  自車速度  +  距離的時間變化率",
  { x: 0.9, y: 2.32, w: 11.6, h: 0.6, fontSize: 22, bold: true, align: "center", color: ACCENT, fontFace: FONT });

para(s, "系統原本用來自我檢查的指標是「穩定跟車時,目標車絕對速度應接近自車速度」。" +
        "由上式可知,該差值恆等於相對速度乘以 3.6;而「穩定跟車」的篩選條件本身即限制了相對速度的大小。" +
        "因此該指標無論幾何是否正確都會通過,不具備驗證能力,只能作為同一組設定下的相對比較。",
     { y: 3.3, h: 1.3 });
para(s, "自車速度已分別對人工畫格法、GPS、CAN 輪速與 GNSS/INS 位姿驗證過。" +
        "他車的距離與絕對速度則尚無任何外部量測可供對照,必須另尋一個與本系統不共用感測器、" +
        "不共用物理原理、也不共用自車速來源的獨立量測。",
     { y: 4.7, h: 1.3 });
small(s, "本節的目的即是取得該獨立量測,並以之界定系統的有效量測範圍。", 6.1, { size: 15 });

/* ------------------------------------------------------ 3 雷達資料來源 */
s = p.addSlide();
title(s, "對照用的雷達從哪裡來", "不是我們外加的設備,是受測車輛原廠就有的");

const src = [
  ["資料集", "comma2k19(comma.ai,2018,MIT 授權,附論文)。加州 280 號州際公路通勤路段,共 33 小時。"],
  ["錄製方式", "車上裝設 comma EON 行車電腦,由 OBD 埠接上車輛 CAN 匯流排,同步錄下影像、輪速與雷達訊息。"],
  ["雷達本體", "車輛原廠配備的毫米波雷達(Toyota DSU),供主動車距控制與自動煞車使用,非研究用改裝。"],
  ["檔案位置", "各路段的 processed_log/CAN/radar,含時間戳 t 與 7 欄數值 value。"],
  ["內容", "前方物體的縱向距離、橫向距離、相對速度,以及所屬的 CAN 位址(0x210–0x21F,共 16 個軌位)。"],
];
src.forEach(([a, b], i) => {
  const y = 2.15 + i * 0.92;
  s.addShape(p.ShapeType.line, { x: 0.9, y: y + 0.8, w: 11.6, h: 0, line: { color: LINE, width: 1 } });
  s.addText(a, { x: 0.9, y, w: 2.0, h: 0.75, fontSize: 16, bold: true, color: ACCENT, fontFace: FONT, valign: "top" });
  s.addText(b, { x: 3.0, y, w: 9.5, h: 0.75, fontSize: 15, color: INK, fontFace: FONT,
                 valign: "top", lineSpacingMultiple: 1.25 });
});
small(s, "雷達測距的原理是發射毫米波並量測回波的時間差與頻移,與影像幾何完全無關。", 6.85, { size: 13 });

/* ---------------------------------------------- 4 雷達資料怎麼處理才能用 */
s = p.addSlide();
title(s, "雷達資料要先處理三件事才能用");

const steps = [
  ["1", "確認欄位定義", "資料集未附欄位說明文件。以物理關係自行確認:靜止的路側物體,其相對速度應恰等於自車速度的負值。" +
        "實測相對速度欄的最小值為 −29.65 m/s,同一時刻的 CAN 車速為 29.2 m/s,關係成立,欄位定義即確立。"],
  ["2", "重建物體編號", "該雷達的 16 個 CAN 軌位會回收再利用,且同一台車可能同時登錄於兩個軌位,因此軌位編號不等於物體編號。" +
        "若直接以軌位追蹤,一條長 30 秒的前車軌跡會被切成 142 段(最長僅 13 影格)。改以距離與橫向位置的連續性重新串接後,最長段為 115 影格。"],
  ["3", "對齊到影格", "雷達約每秒 55 次、影片每秒 20 格,兩者時間不同步。每個影格取該軌位時間最接近的一筆,容差為半個影格," +
        "且不做內插——中斷的軌位維持中斷,不以估計值填補。"],
];
steps.forEach(([n, h, b], i) => {
  const y = 2.05 + i * 1.55;
  s.addText(n, { x: 0.9, y, w: 0.45, h: 0.55, fontSize: 20, bold: true, color: ACCENT, fontFace: FONT });
  s.addText(h, { x: 1.4, y, w: 2.8, h: 0.45, fontSize: 17, bold: true, color: INK, fontFace: FONT });
  s.addText(b, { x: 4.3, y: y - 0.06, w: 8.2, h: 1.45, fontSize: 14, color: INK, fontFace: FONT,
                 valign: "top", lineSpacingMultiple: 1.3 });
});

/* ---------------------------------------------------- 5 兩條鏈的獨立性 */
s = p.addSlide();
title(s, "兩條量測鏈沒有共用任何環節");

table(s, [
  ["量測項目", "本系統", "雷達側"],
  ["前車距離", "車輛遮罩最低點(輪胎接地處)→ 地面平面射線交點 → 法定標線尺度錨", "毫米波回波時間"],
  ["自身車速", "路面虛線週期的碼表法(純影像,不經過偵測器)", "CAN 輪速感測器"],
  ["目標車絕對速度", "自身車速 + 距離的時間變化率", "CAN 輪速 + 雷達所測相對速度"],
], [2.6, 6.0, 3.0], { size: 14, rowH: 0.78 });

para(s, "感測器不同、物理原理不同、連自身車速的來源都不同。因此若本系統的地面幾何存在尺度或俯仰誤差," +
        "雷達側不會出現同方向的偏差,誤差可被檢出。",
     { y: 5.15, h: 0.9 });
small(s, "反之亦然:本系統的自車速來自路面虛線,與輪速感測器無關,因此輪速本身的百分比級誤差" +
         "也不會傳染到本系統的量測。", 6.15, { h: 0.7 });

/* ------------------------------------------------------ 6 配對規則 */
s = p.addSlide();
title(s, "配對規則在看到結果之前就定死", "否則比較者可以挑選對自己有利的配對");

const rules = [
  ["各自認定", "兩側各自以自己的數值判定「同車道、正在移動的前方物體」(橫向位移 1.8 公尺內、絕對速度 15 km/h 以上),不參考對方。"],
  ["橫向位置作為檢查", "兩側獨立量得的橫向位置須一致(差距 1.5 公尺內)。此條用於檢查配對是否為同一台車,不作為配對依據。"],
  ["一對一", "一條本系統軌跡只能對應一個雷達物體,反之亦然。"],
];
rules.forEach(([a, b], i) => {
  const y = 2.15 + i * 1.05;
  s.addText(`${i + 1}`, { x: 0.9, y, w: 0.45, h: 0.45, fontSize: 19, bold: true, color: ACCENT, fontFace: FONT });
  s.addText(a, { x: 1.4, y, w: 3.1, h: 0.45, fontSize: 16.5, bold: true, color: INK, fontFace: FONT });
  s.addText(b, { x: 4.6, y: y - 0.05, w: 7.9, h: 0.95, fontSize: 14.5, color: INK, fontFace: FONT,
                 valign: "top", lineSpacingMultiple: 1.3 });
});
para(s, "尺度誤差是單調變換,不會改變前後車的排序,因此即使本系統的尺度有誤,第 1 條仍會選到同一台實體車輛。",
     { y: 5.45, h: 0.6, size: 16 });
small(s, "第 3 條為必要條件:未加入時,同一路段出現兩條本系統軌跡同時對應同一個雷達物體,兩者分別回報" +
         "0.94 與 1.15 的距離比值,而該處實際上只有一台車。", 6.15, { h: 0.7 });

/* ---------------------------------------------- 7 指標定義(使用者要求) */
s = p.addSlide();
title(s, "先定義三個數字的意思", "後面所有結果都用這三個指標");

const defs = [
  ["配對影格", "同一個時間點,本系統與雷達都判定「前方有同一台車」的影格。三個路段合計 908 個,即樣本數。"],
  ["距離相對誤差(%)", "每個配對影格計算 |本系統距離 − 雷達距離| ÷ 雷達距離,再取中位數。" +
    "數值 7% 表示:雷達量得 20 公尺時,本系統多半落在 18.6 至 21.4 公尺之間。"],
  ["平均絕對誤差 MAE(km/h)", "每個配對影格計算 |本系統目標速度 − 雷達目標速度|,再取平均。" +
    "此處的目標速度是該車對地面的實際速度,不是相對速度。"],
  ["偏差 bias(km/h)", "同一個差值但保留正負號後取平均。接近 0 表示沒有系統性高估或低估,誤差是隨機分布。"],
  ["p90(km/h)", "把誤差由小排到大,第 90 個百分位。表示最差的十分之一也不超過這個值。"],
];
defs.forEach(([a, b], i) => {
  const y = 2.15 + i * 0.9;
  s.addShape(p.ShapeType.line, { x: 0.9, y: y + 0.78, w: 11.6, h: 0, line: { color: LINE, width: 1 } });
  s.addText(a, { x: 0.9, y, w: 3.3, h: 0.7, fontSize: 15.5, bold: true, color: ACCENT, fontFace: FONT, valign: "top" });
  s.addText(b, { x: 4.4, y, w: 8.1, h: 0.75, fontSize: 14, color: INK, fontFace: FONT,
                 valign: "top", lineSpacingMultiple: 1.25 });
});

/* -------------------------------------------------------------- 8 結果 */
s = p.addSlide();
title(s, "結果", "分層依據是系統自己輸出的量測靈敏度,不是事後劃定的界線");

table(s, [
  ["分層", "配對影格", "距離相對誤差(中位)", "速度 bias", "速度 MAE", "速度 p90"],
  ["近場(約 32 公尺內)", "434", "7.0 %", "+0.39", "3.54", "6.18"],
  ["遠場(約 32 公尺外)", "474", "20.5 %(最差 72%)", "−3.39", "6.53", "11.86"],
  ["全部", "908", "9.6 %", "−1.62", "5.13", "7.75"],
], [3.3, 1.7, 2.9, 1.4, 1.3, 1.0], { highlight: [0], rowColor: [GOOD, BAD, INK], rowH: 0.58 });

para(s, "量測靈敏度定義為「畫面上一個像素對應路面上多少公尺」,數值等於前向距離的平方除以掛高與焦距之積。" +
        "系統原本即以 0.8 公尺/像素為界,超過者標示為遠場並拒絕輸出速度;在這台相機上該界線約對應 32 公尺。",
     { y: 4.4, h: 1.1 });
small(s, "本次驗證顯示該界線的位置是正確的:界線內距離誤差 7.0%,界線外 20.5%,差距接近三倍。" +
         "近場的距離中位數比值為 0.946,即本系統的讀數平均比雷達長約 5.7%。", 5.65, { h: 0.8 });

/* ------------------------------------------------------------ 9 證據圖 */
s = p.addSlide();
title(s, "誤差隨距離的變化");
s.addImage({ path: `${F}/radar_eval.png`, x: 0.75, y: 1.9, w: 11.9, h: 4.45 });
small(s, "左圖:橫軸為雷達量得的真實距離,縱軸為「雷達距離 ÷ 本系統距離」,等於 1 表示完全一致。" +
         "綠色區域為系統自定的近場範圍,曲線在該區域內貼近 1.0,超出後單調發散。" +
         "右圖:對同一組配對取不同長度的時間窗平均後,速度誤差降低的情形。", 6.5, { h: 0.85 });

/* --------------------------------------------------- 10 誤差來源分解 */
s = p.addSlide();
title(s, "3.54 km/h 由兩個來源組成", "兩者為代數上的恆等關係,實測相加殘差小於 0.11 km/h");

s.addShape(p.ShapeType.roundRect, { x: 0.9, y: 2.1, w: 11.6, h: 0.95,
  fill: { color: SOFT }, line: { color: LINE }, rectRadius: 0.08 });
s.addText("速度誤差  =  (本系統自車速 − CAN 車速)  +  3.6 × (本系統相對速 − 雷達相對速)",
  { x: 0.9, y: 2.22, w: 11.6, h: 0.72, fontSize: 17, bold: true, align: "center", color: ACCENT, fontFace: FONT });

const parts = [
  ["自車速項", "1.94 km/h", "路面虛線碼表法所得自車速,與車輛輪速感測器之間的差異"],
  ["幾何項", "3.28 km/h", "接地點定位、地面平面與尺度錨這條鏈本身的誤差"],
];
parts.forEach(([a, b, c], i) => {
  const y = 3.35 + i * 1.0;
  s.addShape(p.ShapeType.line, { x: 0.9, y: y + 0.72, w: 11.6, h: 0, line: { color: LINE, width: 1 } });
  s.addText(a, { x: 0.9, y, w: 2.6, h: 0.6, fontSize: 18, bold: true, color: INK, fontFace: FONT });
  s.addText(b, { x: 3.5, y, w: 2.3, h: 0.6, fontSize: 20, bold: true, color: ACCENT, align: "right", fontFace: FONT });
  s.addText(c, { x: 6.2, y: y + 0.05, w: 6.3, h: 0.55, fontSize: 14.5, color: MUTED, fontFace: FONT });
});
para(s, "兩項為同一量級。將自車速替換為 CAN 車速、保留本系統的距離變化率後,誤差為 3.28 km/h、偏差 −0.33," +
        "此即幾何鏈本身的貢獻。因此只改善其中一項,最多僅能消去約一半的誤差。",
     { y: 5.5, h: 1.0, size: 16 });

/* -------------------------------------------------------- 11 時間窗平均 */
s = p.addSlide();
title(s, "時間窗平均的效果", "平均僅在同一組配對的連續區段內進行,不跨車輛");

table(s, [
  ["平均窗長", "樣本數", "MAE", "同一批影格未平均的 MAE", "平均本身的貢獻"],
  ["不平均", "890", "5.13", "—", "—"],
  ["1 秒", "636", "3.99", "4.72", "× 0.84"],
  ["2 秒", "484", "1.90", "2.73", "× 0.70"],
  ["3 秒", "283", "1.44", "2.90", "× 0.50"],
], [2.0, 1.8, 1.8, 3.9, 2.1], { highlight: [3], rowH: 0.5 });

para(s, "5.13 降至 1.44 的改善須拆解為兩部分。第四欄為同一批影格在未平均時的誤差:" +
        "3 秒窗下為 2.90,平均後為 1.44,即平均本身將誤差減半;其餘部分(5.13 至 2.90)來自樣本選擇——" +
        "能維持 3 秒以上的配對本身即為條件較佳的區段。引用平均後的數值時,兩者須分別說明。",
     { y: 4.85, h: 1.3, size: 16 });
small(s, "此外,平均必須限制在同一組配對內。跨區段平均會將前後兩台不同車輛的數值混合," +
         "實測會使某路段 3 秒窗的 p90 由 14.63 惡化為 28.76。", 6.25, { h: 0.7 });

/* --------------------------------------------------------- 12 時間延遲 */
s = p.addSlide();
title(s, "兩個感測器之間是否有時間延遲", "檢驗結果:無系統性延遲");

para(s, "以 ±2 秒的範圍平移本系統的速度序列,尋找使誤差最小的位移量。三個路段的結果為:",
     { y: 2.05, h: 0.6, size: 16.5 });
const lags = [["路段 1", "+1.95 秒"], ["路段 2", "−1.60 秒"], ["路段 3", "+2.00 秒"]];
lags.forEach(([a, b], i) => {
  const x = 0.9 + i * 3.95;
  s.addShape(p.ShapeType.roundRect, { x, y: 2.75, w: 3.5, h: 1.45, fill: { color: "FFFFFF" }, line: { color: LINE }, rectRadius: 0.08 });
  s.addText(a, { x, y: 2.95, w: 3.5, h: 0.35, fontSize: 15, align: "center", color: MUTED, fontFace: FONT });
  s.addText(b, { x, y: 3.32, w: 3.5, h: 0.7, fontSize: 29, bold: true, align: "center",
                 color: i === 1 ? BAD : ACCENT, fontFace: FONT });
});
para(s, "三者正負號不一致,且其中兩者落在搜尋範圍的邊界上。真實的感測器延遲應在三個路段指向同一方向、" +
        "且不會恰好落在搜尋邊界。",
     { y: 4.5, h: 0.8 });
para(s, "速度序列本身變化甚小,平移後誤差下降係因兩條各自緩慢漂移的誤差被對齊,屬於過度配適。" +
        "結論為不施行延遲補償。",
     { y: 5.4, h: 0.9 });

/* ------------------------------------------------ 13 距離修正係數的仲裁 */
s = p.addSlide();
title(s, "同時確定了距離修正係數的幅度", "此前僅能確定方向,幅度因量法之間不一致而未定");

para(s, "8 月的量測顯示系統輸出的距離偏長,並以路面虛線推出每台相機的修正係數。" +
        "但以已知尺寸物體所做的抽樣量測給出 0.71、0.89、0.93 三個互不一致的數值,故當時僅記為「方向確定、幅度未定」。",
     { y: 2.05, h: 1.05, size: 16 });

table(s, [
  ["路段", "虛線碼表法推得之係數", "該量測自身的逐對散布", "雷達近場實測比值", "差異"],
  ["路段 1", "1.031", "0.053", "0.995", "+3.6 %"],
  ["路段 2", "0.919", "0.083", "0.934", "−1.6 %"],
  ["路段 3", "1.028(品質閘拒發)", "0.113", "無近場觀測", "—"],
], [1.9, 3.4, 3.0, 2.1, 1.2], { y: 3.3, highlight: [0, 1], rowH: 0.5 });

para(s, "兩個路段的差異為 1.6% 與 3.6%,皆落在該量測自身的散布範圍內;第三個路段則被系統既有的品質閘正確拒發。",
     { y: 5.2, h: 0.6, size: 16 });
small(s, "適用範圍須明確界定:本結果驗證的是該量測方法不存在系統性偏差(準確度約 ±4%)," +
         "而非台灣五支影片的個別係數——本次相機所需的修正接近 1.0,未涵蓋 0.76 這類大幅修正的情形。", 5.95, { h: 0.8 });

/* --------------------------------------------- 14 遠場距離的處理待修正 */
s = p.addSlide();
title(s, "本次檢出的一項待修正項目");

s.addShape(p.ShapeType.roundRect, { x: 0.9, y: 2.1, w: 11.6, h: 1.75,
  fill: { color: "FFF6F5" }, line: { color: "E8C9C5" }, rectRadius: 0.08 });
s.addText("遠場的速度已由系統拒絕輸出,但遠場的距離仍照常寫入標註影片與資料檔,且未附任何警語。",
  { x: 1.15, y: 2.3, w: 11.1, h: 0.65, fontSize: 19, bold: true, color: BAD, fontFace: FONT });
s.addText("該範圍的距離誤差中位數為 20.5%,最差的一筆為:本系統 38 公尺、雷達 66 公尺(偏差 72%)。",
  { x: 1.15, y: 2.95, w: 11.1, h: 0.8, fontSize: 16.5, color: INK, fontFace: FONT, lineSpacingMultiple: 1.25 });

para(s, "鑑識用途下,一個未經標示的大幅偏差值被輸出為量測結果具有實質風險——閱讀者無從判斷該數值是否可用。" +
        "建議的修正方式為:遠場距離比照速度的處理,標註為僅供參考或不予輸出。系統內部已具備遠場判定," +
        "僅需將該資訊傳遞至距離欄位。",
     { y: 4.15, h: 1.4 });
small(s, "另一併確立一項適用邊界:自側方擦身而過的車輛(路側停放車、切入車),其車輛遮罩的最低點會沿車身移動," +
         "使距離變化率失真,故此類目標僅應輸出距離而不輸出速度。", 5.5, { h: 0.8 });

/* -------------------------------------------- 15 整體驗證完成度一覽 */
s = p.addSlide();
title(s, "全案驗證狀態一覽", "打勾者為已對外部真值完成比對");

table(s, [
  ["量測項目", "外部真值", "誤差", "狀態"],
  ["固定式監視器測他車速度", "人工交比法", "+0.5 %", "✔"],
  ["同上,公開資料集", "BrnoCompSpeed", "—", "未完成(資料約 200 GB,官方主機無法連線)"],
  ["行車紀錄器測自身車速", "人工畫格法", "0.69 ~ 1.30 km/h", "✔"],
  ["同上,公開資料集", "comma2k19,兩車 33 段", "2.18 km/h", "✔"],
  ["行車紀錄器測前車距離", "車輛原廠雷達", "7.0 %(近場)", "✔ 本次新增"],
  ["行車紀錄器測前車速度", "車輛原廠雷達", "3.54 km/h(近場)", "✔ 本次新增"],
  ["偵測器選型", "五模型端到端比較", "換模型差 0.4 km/h", "✔ 非精度瓶頸"],
  ["以資料集微調偵測器", "nuImages", "—", "未執行(見下方說明)"],
], [3.9, 3.2, 2.4, 2.1], { size: 13, headSize: 12.5, rowH: 0.42, highlight: [4, 5] });

small(s, "兩項未完成者的理由:BrnoCompSpeed 受限於下載量與官方主機連線,需透過校內網路或由指導教授具名索取;" +
         "微調偵測器則因實測顯示偵測器對誤差的貢獻約 0.4 km/h,而尺度校正為 2 至 11 km/h,投入標註成本的效益不成比例。",
     6.2, { h: 0.9 });

/* ------------------------------------------------------------ 16 結語 */
s = p.addSlide();
title(s, "結語");
s.addText("系統的有效量測範圍已由外部儀器界定:32 公尺內距離誤差 7.0%、速度誤差 3.54 km/h;超出範圍者不應採用。",
  { x: 0.9, y: 2.2, w: 11.6, h: 1.4, fontSize: 23, bold: true, color: ACCENT, fontFace: FONT, lineSpacingMultiple: 1.3 });
para(s, "對鑑識用途而言,明確界定不可用的範圍與提高可用範圍內的精度同等重要,兩者皆為本次工作的產出。",
     { y: 3.75, h: 0.7 });

s.addText("後續工作", { x: 0.9, y: 4.55, w: 11.6, h: 0.4, fontSize: 17, bold: true, color: ACCENT, fontFace: FONT });
[["1", "為遠場距離加上警語或停止輸出(本次唯一直接檢出的程式缺陷)"],
 ["2", "取得 BrnoCompSpeed,補足固定式監視器管線的公開資料集驗證"],
 ["3", "補齊成果報告封面之姓名、系所、指導教授與執行期間"]].forEach(([n, t], i) => {
  s.addText(`${n}.  ${t}`, { x: 1.15, y: 5.05 + i * 0.5, w: 11.3, h: 0.45, fontSize: 16, color: INK, fontFace: FONT });
});

p.writeFile({ fileName: "/home/s11244/code/114/Vehicle-Distance-Forensics/data/output/report_slides/他車量測驗證_雷達_20260903.pptx" })
  .then(f => console.log("已寫出", f));
