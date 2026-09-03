// 單一主題簡報:第 ① 點「連結偵測器,看最準的模型算誤差範圍」(2026-08-19)
//
// 這份跟 gen_progress3.js 的風格刻意不同:那份是進度報告,一頁塞滿條列;
// 這份是單一主題的口頭報告,一頁一個想法、字少、留白多,表格才是主角。
// 使用者的要求是「AI 感不要這麼重」——所以:不用滿版粗體、不用彩色標籤、
// 不用箭頭符號串句子,句子寫成講得出口的口語。
const PptxGenJS = require("pptxgenjs");

const F = process.env.REPORT_ASSETS || "/home/s11244/tmp/pptx_build/assets";
const INK = "1A1A1A", MUTED = "6B6B6B", ACCENT = "1F4E79", LINE = "DDDDDD", SOFT = "F5F6F8";
const FONT = "Microsoft JhengHei";

const p = new PptxGenJS();
p.defineLayout({ name: "W16", width: 13.333, height: 7.5 });
p.layout = "W16";

function title(s, text, sub) {
  s.addText(text, { x: 0.9, y: 0.55, w: 11.6, h: 0.7, fontSize: 30, bold: true, color: INK, fontFace: FONT });
  if (sub) s.addText(sub, { x: 0.9, y: 1.28, w: 11.6, h: 0.4, fontSize: 15, color: MUTED, fontFace: FONT });
  s.addShape(p.ShapeType.line, { x: 0.9, y: sub ? 1.78 : 1.42, w: 1.4, h: 0, line: { color: ACCENT, width: 2.5 } });
}

// 一段話,不是條列 —— 條列太多是「AI 感」的主要來源
const para = (s, text, o = {}) =>
  s.addText(text, {
    x: o.x ?? 0.9, y: o.y ?? 2.2, w: o.w ?? 11.6, h: o.h ?? 1.0,
    fontSize: o.size ?? 18, color: o.color ?? INK, fontFace: FONT, lineSpacingMultiple: 1.35, valign: "top",
  });

const small = (s, text, y, o = {}) =>
  s.addText(text, { x: o.x ?? 0.9, y, w: o.w ?? 11.6, h: o.h ?? 0.5, fontSize: o.size ?? 13,
                    color: MUTED, fontFace: FONT, italic: o.italic ?? false });

/* ---------------------------------------------------------------- 1 封面 */
let s = p.addSlide();
s.addShape(p.ShapeType.rect, { x: 0, y: 2.55, w: 13.333, h: 0.06, fill: { color: ACCENT }, line: { color: ACCENT } });
s.addText("偵測器要用哪一個?", { x: 0.9, y: 1.5, w: 11.6, h: 0.9, fontSize: 40, bold: true, color: INK, fontFace: FONT });
s.addText("五個模型、四種場景的實測比較", { x: 0.9, y: 2.85, w: 11.6, h: 0.5, fontSize: 20, color: MUTED, fontFace: FONT });
s.addText([
  { text: "結論先講:", options: { bold: true, color: INK } },
  { text: "偵測器不是這個系統的精度瓶頸。換模型只影響 0.4 km/h,\n而尺度校正影響 2 到 11 km/h。", options: { color: INK } },
], { x: 0.9, y: 3.9, w: 11.0, h: 1.2, fontSize: 19, fontFace: FONT, lineSpacingMultiple: 1.35 });
s.addText("回應指導教授 8/03 第 ① 點　|　2026-08-19", { x: 0.9, y: 6.5, w: 11.6, h: 0.4, fontSize: 13, color: MUTED, fontFace: FONT });

/* ------------------------------------------------------ 2 偵測器的角色 */
s = p.addSlide();
title(s, "先講偵測器在系統裡負責哪一段", "不然表格上的數字會被誤解");

const boxes = [
  ["影片一格畫面", ""],
  ["YOLO", "框出車、描出輪廓"],
  ["接地點", "取輪廓的最低點"],
  ["距離與速度", "用地面幾何換算"],
];
boxes.forEach(([t, sub], i) => {
  const x = 0.9 + i * 3.0;
  s.addShape(p.ShapeType.roundRect, { x, y: 2.25, w: 2.55, h: 1.15, fill: { color: i === 2 ? SOFT : "FFFFFF" },
    line: { color: i === 2 ? ACCENT : LINE, width: i === 2 ? 2 : 1 }, rectRadius: 0.08 });
  s.addText(t, { x, y: sub ? 2.42 : 2.62, w: 2.55, h: 0.4, fontSize: 16, bold: true, align: "center", color: INK, fontFace: FONT });
  if (sub) s.addText(sub, { x, y: 2.82, w: 2.55, h: 0.4, fontSize: 12.5, align: "center", color: MUTED, fontFace: FONT });
  if (i < 3) s.addText("→", { x: x + 2.55, y: 2.62, w: 0.45, h: 0.4, fontSize: 18, align: "center", color: MUTED, fontFace: FONT });
});

para(s, "真正決定距離的,是輪廓最底下那一點,也就是輪胎碰到地面的位置(橫向位置另外取最低 12% 帶的中位數,避開後照鏡和陰影)。" +
        "偵測器多抓到幾台車,影響的是「量到幾台」;輪廓底緣畫高畫低幾個像素,才會讓距離變遠變近。",
     { y: 3.95, h: 1.0 });
para(s, "另外,自己的車速是看地上虛線流過畫面的節奏算的,完全不經過偵測器。換模型,自車速一個數字都不會變。",
     { y: 5.0, h: 0.8 });
small(s, "所以「抓到幾台」跟「量得準不準」是兩件事。這決定了整個比較要怎麼設計:不能只比偵測分數。", 5.95, { size: 15, italic: true });

/* ---------------------------------------------------------- 3 怎麼比 */
s = p.addSlide();
title(s, "比較怎麼做的");

s.addText("五個候選模型", { x: 0.9, y: 2.05, w: 4.6, h: 0.4, fontSize: 17, bold: true, color: ACCENT, fontFace: FONT });
s.addText("v8s-seg\nv8m-seg(目前用的)\nv8x-seg\n11m-seg\n11x-seg",
  { x: 0.9, y: 2.55, w: 4.6, h: 2.2, fontSize: 17, color: INK, fontFace: FONT, lineSpacingMultiple: 1.4 });

s.addText("四個場景,每個抽 100 幀", { x: 6.2, y: 2.05, w: 6.3, h: 0.4, fontSize: 17, bold: true, color: ACCENT, fontFace: FONT });
s.addText([
  { text: "白天行車紀錄器", options: { bold: true } }, { text: "(國道,demo 主力場景)\n", options: { color: MUTED } },
  { text: "超廣角行車紀錄器", options: { bold: true } }, { text: "(鏡頭畸變大)\n", options: { color: MUTED } },
  { text: "夜間行車紀錄器", options: { bold: true } }, { text: "(低光、576p)\n", options: { color: MUTED } },
  { text: "夜間路口監視器", options: { bold: true } }, { text: "(和訓練資料差最遠)", options: { color: MUTED } },
], { x: 6.2, y: 2.55, w: 6.3, h: 2.2, fontSize: 16, color: INK, fontFace: FONT, lineSpacingMultiple: 1.4 });

para(s, "五個模型都是現成的預訓練權重,沒有微調,信心門檻 0.3,只算汽車、機車、公車、卡車。",
     { y: 5.0, h: 0.5, size: 17 });
small(s, "沒有人工標的偵測框真值,所以查全率和查準率是用「跨模型共識」當參考:評某個模型時," +
         "其餘四個裡至少兩個同意的框才算數。這種做法只能用來比較模型之間的高低,不是絕對查全率。", 5.6, { h: 0.9 });

/* ------------------------------------------------------------ 4 表格 */
s = p.addSlide();
title(s, "比較結果", "每一格是「查全率 / 查準率」,四類車輛合計");

const rows = [
  ["模型", "白天車機", "超廣角車機", "夜間車機", "夜間路口監視器", "耗時", "端到端誤差"],
  ["v8s", "0.76 / 0.89", "0.79 / 0.94", "0.52 / 0.69", "0.72 / 0.39", "27 ms", ""],
  ["v8m(現用)", "0.86 / 0.93", "0.86 / 0.94", "0.77 / 0.69", "0.57 / 0.58", "30 ms", "−1.6%"],
  ["v8x", "0.95 / 0.88", "0.92 / 0.89", "0.76 / 0.54", "0.83 / 0.51", "48 ms", ""],
  ["11m", "0.84 / 0.96", "0.90 / 0.92", "0.58 / 0.70", "0.50 / 0.85", "33 ms", ""],
  ["11x", "0.95 / 0.89", "0.93 / 0.87", "0.70 / 0.70", "0.70 / 0.76", "48 ms", "−4.7%"],
];
s.addTable(
  rows.map((r, i) => r.map((c, j) => ({
    text: c,
    options: {
      fontSize: i === 0 ? 13.5 : 15, fontFace: FONT, valign: "middle",
      align: j === 0 ? "left" : "center",
      bold: i === 0 || i === 2,
      color: i === 0 ? "FFFFFF" : INK,
      fill: i === 0 ? { color: ACCENT } : { color: i === 2 ? SOFT : "FFFFFF" },
    },
  }))),
  { x: 0.9, y: 2.15, w: 11.6, colW: [2.0, 1.75, 1.85, 1.75, 2.2, 1.0, 1.05],
    rowH: 0.46, border: { type: "solid", color: LINE, pt: 0.5 }, margin: 0.06 });

para(s, "「端到端誤差」是拿唯一有人工真值的案子(前鎮 1130221,人工畫格法 48.37 km/h,目標是一台機車)" +
        "實際跑出來的速度誤差。只跑了目前用的 v8m 和最強的挑戰者 11x,因為這一欄才是真正的判準。",
     { y: 5.4, h: 1.0, size: 16 });

/* ------------------------------------------- 5 為什麼不選最會抓的那個 */
s = p.addSlide();
title(s, "為什麼不選查全率最高的那個");

s.addShape(p.ShapeType.roundRect, { x: 0.9, y: 2.15, w: 5.4, h: 2.05, fill: { color: SOFT }, line: { color: LINE }, rectRadius: 0.08 });
s.addText("v8m(現用)", { x: 1.15, y: 2.35, w: 4.9, h: 0.4, fontSize: 16, color: MUTED, fontFace: FONT });
s.addText("−1.6%", { x: 1.15, y: 2.72, w: 4.9, h: 0.95, fontSize: 42, bold: true, color: ACCENT, fontFace: FONT });
s.addText("對人工真值的誤差", { x: 1.15, y: 3.70, w: 4.9, h: 0.35, fontSize: 13, color: MUTED, fontFace: FONT });

s.addShape(p.ShapeType.roundRect, { x: 7.1, y: 2.15, w: 5.4, h: 2.05, fill: { color: "FFFFFF" }, line: { color: LINE }, rectRadius: 0.08 });
s.addText("11x(偵測分數較高)", { x: 7.35, y: 2.35, w: 4.9, h: 0.4, fontSize: 16, color: MUTED, fontFace: FONT });
s.addText("−4.7%", { x: 7.35, y: 2.72, w: 4.9, h: 0.95, fontSize: 42, bold: true, color: INK, fontFace: FONT });
s.addText("對人工真值的誤差", { x: 7.35, y: 3.70, w: 4.9, h: 0.35, fontSize: 13, color: MUTED, fontFace: FONT });

para(s, "偵測分數比較好的模型,最後算出來的速度反而比較差。原因是它的輪廓底緣位置有系統性的小偏移" +
        "(同一個時間窗量到的位移是 8.92 公尺,v8m 是 9.20 公尺)。",
     { y: 4.45, h: 0.9, size: 17 });
para(s, "而 x 系列多抓到的那 7 到 9 個百分點,幾乎都在 40 公尺以外。系統在那裡本來就標示「遠場、不發速度」," +
        "所以多抓到的是不會被採用的目標,卻要多花 1.6 倍的運算時間。",
     { y: 5.4, h: 0.9, size: 17 });

/* ---------------------------------------------------------- 6 結論 */
s = p.addSlide();
title(s, "所以誤差範圍是誰決定的");

const budget = [
  ["偵測器和接地點這條鏈", "約 0.4 km/h"],
  ["尺度校正的不確定度", "2 到 11 km/h"],
  ["前後距離的尺度(這個月新查出來的)", "距離偏高 11 到 32%"],
];
budget.forEach(([a, b], i) => {
  const y = 2.15 + i * 0.85;
  s.addShape(p.ShapeType.line, { x: 0.9, y: y + 0.62, w: 11.6, h: 0, line: { color: LINE, width: 1 } });
  s.addText(a, { x: 0.9, y, w: 8.0, h: 0.5, fontSize: 18, color: INK, fontFace: FONT });
  s.addText(b, { x: 8.9, y, w: 3.6, h: 0.5, fontSize: 18, bold: i > 0, align: "right",
                 color: i === 0 ? MUTED : ACCENT, fontFace: FONT });
});

para(s, "三者差一到兩個數量級。所以要讓速度更準,要投資的是尺度校正,不是換模型。這也是這個階段把力氣放在距離尺度的原因。",
     { y: 4.95, h: 0.9, size: 18 });
small(s, "唯一的例外是夜間路口監視器:那個場景五個模型分歧最大,11x 的查全和查準同時比現用的好。" +
         "但還沒換,因為還沒拿有人工真值的夜間案做端到端驗證。", 5.95, { h: 0.9, size: 14 });

p.writeFile({ fileName: "/home/s11244/code/114/Vehicle-Distance-Forensics/data/output/report_slides/偵測器比較_第一點_20260819.pptx" })
  .then(f => console.log("已寫出", f));
