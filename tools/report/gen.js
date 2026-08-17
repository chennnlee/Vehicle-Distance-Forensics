/* Vehicle-Distance-Forensics 專案報告簡報產生器 */
const pptxgen = require("pptxgenjs");
const p = new pptxgen();
p.layout = "LAYOUT_WIDE"; // 13.333 x 7.5 in
p.author = "Vehicle-Distance-Forensics";
p.title = "交通事故影像鑑識:車輛速度與距離量測";

const F = "Microsoft JhengHei";
p.theme = { headFontFace: F, bodyFontFace: F };

// palette: 深夜柏油路 + 標線黃
const NAVY = "111A2E";   // 深夜藍(深色頁背景)
const NAVY2 = "1D2C4C";  // 深色頁卡片
const INK = "222B3C";    // 內文深色
const MUT = "5C6675";    // 次要文字
const AMBER = "F5A800";  // 標線黃(深色頁強調)
const AMBER_TXT = "C98A00"; // 淺色頁上的黃(可讀)
const STEEL = "31527B";  // 鋼藍
const GREEN = "1F9D55";
const RED = "C0392B";
const CARD = "F4F6FA";   // 淺色卡片底
const CARD_LINE = "E2E7EF";
const RED_BG = "FBF0EF";
const AMBER_BG = "FFF6DE";
const PAGEW = 13.333, PAGEH = 7.5;

let pageNo = 0;

function footer(s, dark, skipBrand) {
  pageNo += 1;
  if (pageNo === 1) return; // 標題頁不放
  if (!skipBrand) s.addText("Vehicle-Distance-Forensics", {
    x: 0.62, y: 7.06, w: 4.0, h: 0.3, fontFace: F, fontSize: 9.5,
    color: dark ? "6C7A93" : "9AA3B0", margin: 0, valign: "middle",
  });
  s.addText(String(pageNo), {
    x: 12.55, y: 7.06, w: 0.55, h: 0.3, fontFace: F, fontSize: 10,
    color: dark ? "6C7A93" : "9AA3B0", align: "right", margin: 0, valign: "middle",
  });
}

function dashRow(s, x, y, n, opts) {
  const o = opts || {};
  const w = o.w || 0.5, gap = o.gap || 0.3, h = o.h || 0.075, color = o.color || AMBER;
  for (let i = 0; i < n; i++) {
    s.addShape(p.ShapeType.roundRect, {
      x: x + i * (w + gap), y: y, w: w, h: h, rectRadius: h / 2,
      fill: { color: color }, line: { type: "none" },
    });
  }
}

function kicker(s, label) {
  s.addShape(p.ShapeType.roundRect, {
    x: 0.64, y: 0.42, w: 0.34, h: 0.07, rectRadius: 0.035,
    fill: { color: AMBER }, line: { type: "none" },
  });
  s.addText(label, {
    x: 1.06, y: 0.30, w: 5.0, h: 0.3, fontFace: F, fontSize: 11.5, bold: true,
    color: STEEL, charSpacing: 3, margin: 0, valign: "middle",
  });
}

function title(s, text) {
  s.addText(text, {
    x: 0.62, y: 0.62, w: 12.1, h: 0.62, fontFace: F, fontSize: 27, bold: true,
    color: NAVY, margin: 0, valign: "middle",
  });
}

function lightSlide(kick, titleText) {
  const s = p.addSlide();
  s.background = { color: "FFFFFF" };
  kicker(s, kick);
  title(s, titleText);
  footer(s, false);
  return s;
}

function bullets(s, x, y, w, h, items, opts) {
  const o = opts || {};
  const runs = items.map((t, i) => ({
    text: t,
    options: {
      bullet: { code: "2022", indent: o.indent || 12 },
      color: o.color || INK,
      breakLine: true,
      paraSpaceAfter: o.gap == null ? 8 : o.gap,
    },
  }));
  s.addText(runs, {
    x: x, y: y, w: w, h: h, fontFace: F, fontSize: o.size || 14,
    margin: 0, valign: o.valign || "top", lineSpacingMultiple: 1.12,
  });
}

function card(s, x, y, w, h, fillColor, lineColor) {
  s.addShape(p.ShapeType.roundRect, {
    x: x, y: y, w: w, h: h, rectRadius: 0.09,
    fill: { color: fillColor || CARD }, line: { color: lineColor || CARD_LINE, width: 1 },
  });
}

function circleNum(s, x, y, txt, bg, fg, d) {
  const dd = d || 0.34;
  s.addShape(p.ShapeType.ellipse, {
    x: x, y: y, w: dd, h: dd, fill: { color: bg }, line: { type: "none" },
  });
  s.addText(txt, {
    x: x - 0.06, y: y - 0.03, w: dd + 0.12, h: dd + 0.06, fontFace: F, fontSize: dd > 0.3 ? 13 : 11,
    bold: true, color: fg || "FFFFFF", align: "center", valign: "middle", margin: 0,
  });
}

function caption(s, x, y, w, text) {
  s.addText(text, {
    x: x, y: y, w: w, h: 0.42, fontFace: F, fontSize: 10.5, color: MUT,
    margin: 0, valign: "top", italic: false,
  });
}

/* ---------------- S1 標題 ---------------- */
(function () {
  const s = p.addSlide();
  s.background = { path: "assets/kh013_t25.jpg" };
  s.addShape(p.ShapeType.rect, {
    x: 0, y: 0, w: PAGEW, h: PAGEH, fill: { color: NAVY, transparency: 14 }, line: { type: "none" },
  });
  dashRow(s, 0.9, 2.18, 4, { w: 0.55, gap: 0.34 });
  s.addText("交通事故影像鑑識", {
    x: 0.86, y: 2.42, w: 11.8, h: 1.05, fontFace: F, fontSize: 44, bold: true,
    color: "FFFFFF", margin: 0, valign: "middle",
  });
  s.addText("從監視器與行車紀錄器影片量測車輛速度與距離", {
    x: 0.88, y: 3.52, w: 11.8, h: 0.6, fontFace: F, fontSize: 21, bold: true,
    color: AMBER, margin: 0, valign: "middle",
  });
  s.addText("單幀 3D 幾何  ×  台灣法定標線尺度錨  ×  誠實不確定度", {
    x: 0.88, y: 4.28, w: 11.8, h: 0.45, fontFace: F, fontSize: 14,
    color: "C9D4E6", margin: 0, valign: "middle",
  });
  s.addText("大專學生研究計畫 · 成果報告 · 2026 年 7 月", {
    x: 0.88, y: 6.62, w: 8.0, h: 0.4, fontFace: F, fontSize: 13,
    color: "9FB0C9", margin: 0, valign: "middle",
  });
  footer(s, true);
  s.addNotes("開場:本計畫把路口監視器與行車紀錄器影片,變成可稽核的車速與距離量測工具。背景是系統實際輸出的成果影片畫面。");
})();

/* ---------------- S2 背景與目標 ---------------- */
(function () {
  const s = lightSlide("背景", "研究背景與目標");
  s.addText("為什麼需要這套系統", {
    x: 0.62, y: 1.32, w: 6.1, h: 0.4, fontFace: F, fontSize: 16.5, bold: true, color: INK, margin: 0,
  });
  bullets(s, 0.62, 1.82, 6.15, 3.4, [
    "事故責任釐清的關鍵證據是「車速」——但影像本身不會直接告訴你",
    "現行人工畫格法(交比法)費時、依賴專家經驗,難以批量處理",
    "路口 CCTV 與行車紀錄器已無所不在:證據現成,缺的是可信、可稽核的量測方法",
    "本計畫以「汽車測速」為主要目標,機車為次要;素材涵蓋路口 CCTV 與車載行車紀錄器",
  ], { size: 14.5, gap: 12 });

  const goals = [
    ["自動化", "從影片直接輸出每台車的速度與距離,含成果影片、逐軌 CSV 與俯視軌跡圖"],
    ["可稽核", "校正標線、追蹤軌跡、時間軸全部燒錄在影片與資料檔,逐幀可回查"],
    ["誠實不確定度", "每個速度附 ±95% 信賴區間;量不到就標 no-lock / far-range,絕不硬給數字"],
  ];
  goals.forEach((g, i) => {
    const y = 1.32 + i * 1.5;
    card(s, 7.15, y, 5.55, 1.34);
    circleNum(s, 7.42, y + 0.28, String(i + 1), AMBER, "FFFFFF", 0.36);
    s.addText(g[0], {
      x: 7.98, y: y + 0.16, w: 4.5, h: 0.4, fontFace: F, fontSize: 15.5, bold: true, color: NAVY, margin: 0,
    });
    s.addText(g[1], {
      x: 7.98, y: y + 0.56, w: 4.55, h: 0.7, fontFace: F, fontSize: 12, color: MUT, margin: 0, valign: "top",
    });
  });

  const stats = [
    ["2 條", "量測管線(CCTV/行車紀錄器)"],
    ["16+ 案", "人工真值/GPS 交叉驗證(含 8 汽車案批量)"],
    ["+0.5%", "CCTV vs 人工交比法(前鎮案)"],
    ["1.37", "8 汽車案批量 MAE km/h(23 可信段)"],
  ];
  stats.forEach((st, i) => {
    const x = 0.62 + i * 3.12;
    s.addText(st[0], {
      x: x, y: 6.02, w: 2.9, h: 0.52, fontFace: F, fontSize: 24, bold: true, color: AMBER_TXT, margin: 0,
    });
    s.addText(st[1], {
      x: x, y: 6.56, w: 2.95, h: 0.4, fontFace: F, fontSize: 11, color: MUT, margin: 0, valign: "top",
    });
  });
  s.addNotes("動機與三大設計原則:自動化、可稽核、誠實。底部是全專案的核心數字。");
})();

/* ---------------- S3 系統總覽 ---------------- */
(function () {
  const s = lightSlide("方法", "系統架構:一個幾何骨架,兩條管線");
  const steps = [
    ["參考幀跑 SHARP", "單張影像單目 3D 重建\n全片只跑一次(CPU 約 90 秒)"],
    ["RANSAC 地面平面", "在點雲中擬合路面\ny = ax + bz + c"],
    ["法定標線尺度錨", "SHARP 尺度不可信(0.88~2.9)\n用台灣法定標線反推 scale"],
    ["像素 → 路面公尺", "任意像素:射線 × 平面求交\n× scale = 路面座標"],
  ];
  const bw = 2.78, gap = 0.32, y0 = 1.42, bh = 1.25;
  steps.forEach((st, i) => {
    const x = 0.62 + i * (bw + gap);
    card(s, x, y0, bw, bh, CARD);
    s.addText(st[0], {
      x: x + 0.16, y: y0 + 0.12, w: bw - 0.32, h: 0.35, fontFace: F, fontSize: 14, bold: true, color: NAVY, margin: 0,
    });
    s.addText(st[1], {
      x: x + 0.16, y: y0 + 0.5, w: bw - 0.32, h: 0.7, fontFace: F, fontSize: 10.8, color: MUT, margin: 0, valign: "top",
    });
    if (i < 3) {
      s.addText("→", {
        x: x + bw - 0.03, y: y0 + 0.38, w: gap + 0.08, h: 0.5, fontFace: F, fontSize: 20, bold: true,
        color: AMBER_TXT, align: "center", valign: "middle", margin: 0,
      });
    }
  });
  s.addText("同一套幾何骨架,分別餵給兩條管線", {
    x: 0.62, y: 2.86, w: 12.1, h: 0.35, fontFace: F, fontSize: 12, color: MUT, align: "center", margin: 0,
  });

  const pipes = [
    ["管線 A|固定 CCTV(路口高視角)", [
      "OSD 時鐘秒跳定時——NVR 串流會謊報 fps,時間軸必須自己量",
      "YOLOv8m-seg 取每台車的接地點 → 平面座標",
      "匈牙利關聯 + 方向/尺寸/物理閘門 → 車輛軌跡",
      "等速擬合 → 速度 ±95% 信賴區間 + 品質旗標",
    ]],
    ["管線 B|行車紀錄器(移動相機)", [
      "平路上地面平面「相對相機」近似不變 → 幾何骨架照用",
      "自車速=虛線週期碼表(唯一信任來源,免 scale/畸變/震動)",
      "他車:接地點 → 跟車距離;絕對速 = 自車速 + d(距離)/dt",
      "每道讀值都有防護鏈把關,無讀值誠實標 no-lock",
    ]],
  ];
  pipes.forEach((pp, i) => {
    const x = 0.62 + i * 6.28;
    card(s, x, 3.35, 6.0, 2.95, "FFFFFF", "C7D2E2");
    s.addText(pp[0], {
      x: x + 0.28, y: 3.56, w: 5.5, h: 0.42, fontFace: F, fontSize: 15.5, bold: true, color: STEEL, margin: 0,
    });
    bullets(s, x + 0.28, 4.12, 5.5, 2.05, pp[1], { size: 12.8, gap: 9 });
  });
  s.addNotes("核心思想:單幀 3D 只提供幾何形狀,尺度由台灣法定標線提供;之後所有量測都是射線與平面的交點。");
})();

/* ---------------- S3b 幾何骨架輸出 ---------------- */
(function () {
  const s = lightSlide("方法", "幾何骨架實錄:一張參考幀 → 3D 點雲 → 地面平面");
  s.addImage({ path: "assets/dc007_ref_frame.jpg", x: 0.62, y: 1.5, w: 5.5, h: 3.09 });
  caption(s, 0.62, 4.66, 5.5, "輸入:整段影片只取一張參考幀(dc007,台86 快速道路)");
  bullets(s, 0.62, 5.25, 5.7, 1.6, [
    "SHARP 單目 3D 重建全片只跑一次(CPU 約 90 秒),之後逐幀量測只做射線×平面求交",
    "固定 FOV 假設 → 形狀可信、尺度不可信:尺度交給下一頁的法定標線錨",
  ], { size: 12.2, gap: 8 });
  s.addImage({ path: "assets/sharp_pointcloud.png", x: 6.85, y: 1.45, w: 5.9, h: 4.91 });
  caption(s, 6.85, 6.42, 5.9,
    "輸出:SHARP 點雲(可辨識路面虛線、紅色目標車、門架與路樹)+ RANSAC 擬合的地面平面(琥珀色,y = ax + bz + c)");
  s.addNotes("每流程一輸出的第一站:左邊是唯一的輸入幀,右邊是實際重建出的點雲與擬合平面。紅色目標車就是 dc007 的危險駕駛車。");
})();

/* ---------------- S4 幾何與校正 ---------------- */
(function () {
  const s = lightSlide("方法", "尺度校正:用台灣法定標線當現場的尺");
  bullets(s, 0.62, 1.5, 6.3, 4.6, [
    "SHARP 採固定視角假設(fx ≈ 0.7955 × 影像寬)→ 尺度天生不可信,實測各裝置 scale 落在 0.88~2.9",
    "解法:台灣法定標線=不用到現場就知道長度的尺——車道虛線 4m/6m、高速公路 4m/8m、路口導引線 0.5m/0.5m(先以 gap/dash 比例做免尺度規格識別)",
    "多鏈剝離:每條虛線各自成為一把獨立的尺;跨鏈互驗得到尺度變異 CV,直接進入速度不確定度",
    "發現:4m 車道線跨鏈一致性約 5%,明顯優於 0.5m 導引線(10~22%)——短標線端點誤差佔比大,能用 4m 線就用",
  ], { size: 13.8, gap: 14 });
  s.addImage({ path: "assets/64000C000013_lane_dash_calibration.png", x: 7.15, y: 1.5, w: 5.55, h: 3.12 });
  caption(s, 7.15, 4.68, 5.55,
    "kh013 校正:SHARP 原始 3D 長度 1.44~1.70 m × scale 2.680 ≈ 法定 4 m(尺度變異 CV 7.4%)");
  card(s, 7.15, 5.3, 5.55, 1.2, AMBER_BG, "F0DFAE");
  s.addText([
    { text: "行車紀錄器例外:", options: { bold: true, color: INK } },
    { text: "貼地視角讓虛線 3D 取樣失效(4 m 會量成 0.3~6.7 m)→ 改用車道寬 3.5 m、同鏡頭相機高度轉移、或 GPS 當錨", options: { color: INK } },
  ], {
    x: 7.38, y: 5.44, w: 5.1, h: 0.95, fontFace: F, fontSize: 11.8, margin: 0, valign: "middle", lineSpacingMultiple: 1.15,
  });
  s.addNotes("尺度是整套幾何的命脈:SHARP 形狀可信、尺度不可信,所以一定要用法定標線反推 scale,而且跨鏈互驗給出 CV。");
})();

/* ---------------- S5 管線 A 流程 ---------------- */
(function () {
  const s = lightSlide("管線 A|CCTV", "固定 CCTV 測速流程");
  const steps = [
    ["OSD 時鐘秒跳定時", "NVR 串流謊報 fps 是常態;以畫面時鐘的秒跳重建真實時間軸(無 OSD 時用實測 fps)"],
    ["接地點量測", "YOLOv8m-seg 取車輛 mask 最低 12% 為接地點 → 射線×平面 → 路面公尺座標"],
    ["追蹤", "匈牙利關聯 + 方向閘 + bbox 尺寸閘 + 物理閘門,串出每台車的軌跡"],
    ["等速擬合 + 品質防護", "淨位移門檻防停等抖動灌水;遠場(>0.3 m/px)自動拒發;速度附 ±95% CI"],
  ];
  steps.forEach((st, i) => {
    const y = 1.5 + i * 1.18;
    circleNum(s, 0.62, y, String(i + 1), STEEL, "FFFFFF", 0.36);
    s.addText(st[0], {
      x: 1.18, y: y - 0.04, w: 5.6, h: 0.4, fontFace: F, fontSize: 15, bold: true, color: NAVY, margin: 0,
    });
    s.addText(st[1], {
      x: 1.18, y: y + 0.36, w: 5.7, h: 0.68, fontFace: F, fontSize: 12, color: MUT, margin: 0, valign: "top",
    });
  });
  s.addImage({ path: "assets/kh013_t25.jpg", x: 7.15, y: 1.5, w: 5.55, h: 3.12 });
  caption(s, 7.15, 4.68, 5.55,
    "成果影片(kh013 夜間):綠=校正標線與法定長度、青=次鏈;車輛標籤含 id/類別/速度;左下 HUD 燒錄 scale、CV 與時間軸");
  card(s, 7.15, 5.3, 5.55, 1.2, CARD);
  s.addText([
    { text: "顯示降級規則:", options: { bold: true, color: INK } },
    { text: "非等速標 ~(區間平均);CI 超過速度一半 → 灰色問號;遠場 → far-range 不給速度", options: { color: INK } },
  ], {
    x: 7.38, y: 5.44, w: 5.1, h: 0.95, fontFace: F, fontSize: 11.8, margin: 0, valign: "middle", lineSpacingMultiple: 1.15,
  });
  s.addNotes("管線 A 四步驟。右圖是實際輸出:所有校正證據都燒在影片上,鑑識人員可直接檢視。");
})();

/* ---------------- S6 v3 追蹤器 ---------------- */
(function () {
  const s = lightSlide("管線 A|CCTV", "v3 追蹤器:解決框跳動與同車重複計數");
  const fixes = [
    ["同幀雙框抑制", "car+truck 對同一台車重複發框(各自成軌=數兩次);重疊>0.65 只留高信心框"],
    ["類別群組關聯", "car/truck/bus 視為同群,類別閃爍不再剪斷軌跡;回報類別=全軌多數決"],
    ["斷軌事後縫合", "偵測中斷讓車輛以新 id 重生;等速外插+尺寸+方向閘縫回(merged_from 可稽核)"],
    ["平行鬼影軌抑制", "同車伴生的平行假軌跡自動壓掉"],
    ["遠場防護鏈", "遠場觀測不進速度擬合、不當縫合端點、關聯閘鎖 4 m——修掉「地平線漫遊」"],
    ["關聯閘門物理化", "速度誤差項+4 m/s² 加速度上限;舊閘門斷檔後會吞下一台車捏造 ~100 km/h"],
  ];
  fixes.forEach((f, i) => {
    const col = i % 2, row = Math.floor(i / 2);
    const x = 0.62 + col * 4.62, y = 1.45 + row * 1.52;
    card(s, x, y, 4.42, 1.38);
    s.addText(f[0], {
      x: x + 0.2, y: y + 0.12, w: 4.05, h: 0.36, fontFace: F, fontSize: 13.5, bold: true, color: STEEL, margin: 0,
    });
    s.addText(f[1], {
      x: x + 0.2, y: y + 0.5, w: 4.05, h: 0.82, fontFace: F, fontSize: 11, color: MUT, margin: 0, valign: "top",
    });
  });
  card(s, 0.62, 6.08, 8.62, 0.72, "EFF6EF", "CDE3CF");
  s.addText([
    { text: "同幀 A/B 重跑驗證:", options: { bold: true, color: GREEN } },
    { text: "配對軌跡速度差 median ≈ 0(kh012 n=113);「消失後重生」可疑對 8 → 4;遠場污染案例 34.1 → 33.9 保住", options: { color: INK } },
  ], {
    x: 0.86, y: 6.16, w: 8.2, h: 0.56, fontFace: F, fontSize: 11.8, margin: 0, valign: "middle",
  });
  s.addImage({ path: "assets/bev_metric.png", x: 9.72, y: 1.45, w: 2.8, h: 5.13 });
  caption(s, 9.72, 6.62, 3.0, "度量俯視圖(1px=5cm):軌跡與速度±CI");
  s.addNotes("v3 是針對使用者回饋(框跳動、重複計數)的六項修正;右側 BEV 圖同時當幾何自我檢查:標線必須落在正確公尺數上。");
})();

/* ---------------- S7 CCTV 驗證 ---------------- */
(function () {
  const s = lightSlide("驗證", "管線 A 驗證:對人工交比法");
  s.addText("+0.5%", {
    x: 0.62, y: 1.35, w: 4.0, h: 0.95, fontFace: F, fontSize: 54, bold: true, color: AMBER_TXT, margin: 0,
  });
  s.addText([
    { text: "前鎮 1130221 案(路口 CCTV):", options: { bold: true, color: INK, breakLine: true } },
    { text: "同窗速度 48.6 vs 人工交比法 48.37 km/h", options: { color: INK } },
  ], {
    x: 4.75, y: 1.42, w: 7.9, h: 0.9, fontFace: F, fontSize: 15, margin: 0, valign: "middle", lineSpacingMultiple: 1.2,
  });
  s.addText("幀對幀互查:人工所選幀號=系統 −1 幀,輪胎接地座標互相吻合;全軌擬合 39.6 km/h=含減速段 → 鑑識結論必須註明取哪一段時間窗",
    { x: 0.62, y: 2.5, w: 12.1, h: 0.6, fontFace: F, fontSize: 12.5, color: MUT, margin: 0, valign: "top" });

  s.addText("海盛 5 案人工對照", {
    x: 0.62, y: 3.35, w: 6.2, h: 0.4, fontFace: F, fontSize: 16, bold: true, color: INK, margin: 0,
  });
  bullets(s, 0.62, 3.85, 6.2, 2.8, [
    "3 案吻合:45.5 / 48.4 / 44.6 km/h",
    "2 案=失效邊界(近地平線遠場、螢幕翻拍摩爾紋)→ 系統自動拒發或標示,不硬給",
    "遠場自動化驗證:1110822 案兩軌靈敏度 0.83 / 0.88 m/px → 自動標 far_field ✓",
    "四台路口 CCTV(kh012/kh013/kh019/hsinchu006)完整成果包已產出",
  ], { size: 13, gap: 10 });

  s.addImage({ path: "assets/qz_t30.jpg", x: 7.15, y: 3.3, w: 5.55, h: 3.12 });
  caption(s, 7.15, 6.5, 5.55, "前鎮 1130221(白天路口):0.5 m 導引線錨、車輛軌跡與即時速度;遠場車誠實標 far-range: no speed");
  s.addNotes("最強的一筆驗證:與人工交比法同窗只差 0.5%,而且幀號、輪胎座標都互相對得上。失效的 2 案正是系統會自動拒發的情境。");
})();

/* ---------------- S8 管線 B 原理 ---------------- */
(function () {
  const s = lightSlide("管線 B|行車紀錄器", "虛線週期碼表:免尺度、免畸變、免震動的自車速");
  bullets(s, 0.62, 1.5, 6.3, 4.3, [
    "相機在動,但平路上地面平面「相對相機」近似不變 → 幾何骨架照用",
    "自車速唯一信任來源=虛線週期碼表:法定虛線以固定週期流過畫面固定列,亮度自相關取週期 T → v = cycle / T",
    "先天免疫:與 scale、鏡頭畸變、車身震動全部無關",
    "他車:接地點 → 跟車距離(逐幀);絕對速 = 自車速 + d(距離)/dt;無自車速時只給距離",
    "光流不給任何速度值(震動/夜間會把 60 km/h 讀成 2)——只用於停止判斷的輔助",
  ], { size: 13.5, gap: 13 });
  s.addImage({ path: "assets/dc006_t45.jpg", x: 7.15, y: 1.5, w: 5.55, h: 3.12 });
  caption(s, 7.15, 4.68, 5.55,
    "國道1號 60 秒片段(dc006):自車視覺碼表 90.0 vs 畫面 GPS 92 km/h;前車逐幀距離+絕對速;>40 m 誠實標 far-range");
  card(s, 7.15, 5.3, 5.55, 1.2, AMBER_BG, "F0DFAE");
  s.addText([
    { text: "實測陷阱:", options: { bold: true, color: INK } },
    { text: "國1、台86 實測虛線週期都是 10 m(非規範值 12 m)→ cycle 一律先用 GPS OSD 反驗,差 20% 可辨", options: { color: INK } },
  ], {
    x: 7.38, y: 5.44, w: 5.1, h: 0.95, fontFace: F, fontSize: 11.8, margin: 0, valign: "middle", lineSpacingMultiple: 1.15,
  });
  s.addNotes("碼表的關鍵洞見:法定虛線本身就是路上印好的量尺,讓它流過固定畫面列,用自相關讀週期,speed 就出來了,完全繞過移動相機的所有麻煩。");
})();

/* ---------------- S8b 碼表訊號實錄 ---------------- */
(function () {
  const s = lightSlide("管線 B|行車紀錄器", "碼表訊號實錄:線位 × 時間條紋圖");
  bullets(s, 0.62, 1.5, 7.4, 3.6, [
    "把「畫面某一列的亮度」沿時間堆疊成圖:橫軸=影像 x、縱軸=幀序(向下)",
    "白色點狀縱列=虛線脈衝列——每個亮點是一根 4 m 虛線流過該列,間距就是週期",
    "縱列筆直=車在道內穩定(駐留平台);緩慢彎曲=道內漂移;大幅掃動=換道 → 線位閘拒發",
    "取樣點就定在駐留平台上(近/中/遠多列),自相關讀出週期 T → 自車速 = 10 m / T",
    "方法論(dc003 教訓):定點前先畫這張圖挑平台,不憑單幀肉眼猜",
  ], { size: 13.5, gap: 12 });
  card(s, 0.62, 5.4, 7.4, 1.3, CARD);
  s.addText([
    { text: "同一張圖也是防護鏈的證據:", options: { bold: true, color: INK } },
    { text: "路口前虛轉實線(脈衝消失)、雙白線波動、減速標線干擾帶都一眼可辨——這些窗就該 no-lock。", options: { color: INK } },
  ], {
    x: 0.88, y: 5.55, w: 6.9, h: 1.0, fontFace: F, fontSize: 12.2, margin: 0, valign: "middle", lineSpacingMultiple: 1.18,
  });
  s.addImage({ path: "assets/strip_c0135.png", x: 8.5, y: 1.45, w: 3.9, h: 5.16 });
  caption(s, 8.5, 6.63, 4.2, "案 01-35 四列條紋圖:f0–f130 駐留平台清楚,之後右漂");
  s.addNotes("這是碼表的『輸出可視化』:把訊號攤開給人看。取樣點怎麼選、閘門為什麼拒發,全部有圖可稽。");
})();

/* ---------------- S9 防護鏈 ---------------- */
(function () {
  const s = lightSlide("管線 B|行車紀錄器", "碼表防護鏈:每一道閘門都是實際失效換來的");
  const gates = [
    ["訊號 std > 2", "停紅燈時的假鎖"],
    ["窗內 ≥2 完整週期", "低速爬行的假峰"],
    ["雙窗 3s/5.1s 一致 12%", "八度錯誤(半速/倍速)"],
    ["峰突出度 ≥ 0.3", "突發訊號寬肩(0.03)vs 真鎖(0.7+)"],
    ["跨列相位檢查", "引擎震動全域同相;真虛線先遠列後近列"],
    ["octave-threshold 0.95", "乾淨巡航時自相關自然衰減 → 系統性翻半速"],
    ["線位穩定閘(x-IQR>50px)", "換道掃過匝道密集短線:82 km/h 被讀成 146"],
    ["sub-octave 修正", "國道貓眼每隔一根 dash=20 m 子結構 → 半速鎖"],
    ["分裂鎖閘", "兩取樣點分歧時取多數決,不平均出幻速"],
    ["光流永不給速度", "夜間/震動把 60 讀成 2:任何裝置都不信"],
  ];
  gates.forEach((g, i) => {
    const col = Math.floor(i / 5), row = i % 5;
    const x = 0.62 + col * 6.28, y = 1.5 + row * 0.92;
    circleNum(s, x, y, String(i + 1), i < 5 ? STEEL : AMBER, "FFFFFF", 0.3);
    s.addText(g[0], {
      x: x + 0.48, y: y - 0.05, w: 5.6, h: 0.34, fontFace: F, fontSize: 13.2, bold: true, color: NAVY, margin: 0,
    });
    s.addText("擋下:" + g[1], {
      x: x + 0.48, y: y + 0.3, w: 5.7, h: 0.5, fontFace: F, fontSize: 11, color: MUT, margin: 0, valign: "top",
    });
  });
  card(s, 0.62, 6.25, 12.08, 0.62, CARD);
  s.addText([
    { text: "全部閘門擋完仍無讀值 → 誠實標 no-lock,只內插 ≤2 秒空隙。", options: { bold: true, color: INK } },
    { text: " 強鎖免雙窗(conf≥0.5 且突出度≥0.5)救回短片減速段。", options: { color: MUT } },
  ], {
    x: 0.9, y: 6.31, w: 11.6, h: 0.5, fontFace: F, fontSize: 12, margin: 0, valign: "middle",
  });
  s.addNotes("每一道閘門背後都有一支實際翻車的影片:假鎖、半速、幻速……。這頁想講的是工程可信度來自失效案例的累積,不是理論。");
})();

/* ---------------- S10 dashcam 驗證 ---------------- */
(function () {
  const s = lightSlide("驗證", "管線 B 驗證:純視覺自車速 vs GPS 與人工真值");
  s.addImage({ path: "assets/ego_vs_gps_validation.png", x: 0.62, y: 1.45, w: 6.35, h: 4.37 });
  caption(s, 0.62, 5.9, 6.35,
    "純視覺碼表(藍線)vs 影片 OSD 燒錄的 GPS(綠點):高速穩定巡航緊貼;市區加減速能跟上動態,無法鎖定處誠實留空");
  const rows = [
    ["002 快速道路", "MAE 1.2 km/h(11/11 檢查點,bias +0.9)"],
    ["dc006 國道 60s", "9 有效檢查點 MAE ≈ 2.1;dc007 台86:MAE ≈ 2.2"],
    ["dc003 超廣角+三度換道", "鎖定段多在 ±4 km/h 內;覆蓋 52% 誠實呈現"],
    ["案18(vs 海盛人工畫格)", "三段 −0.8 / −1.1 / −0.4 km/h;猛加速段誠實 no-lock"],
    ["案78-29(夜間 1296p)", "人工 57.1 / 車上時速表 ≈60 / 本系統 59.2 km/h"],
    ["急煞・換道段", "碼表解析度 ~3 秒 → 誠實 no-lock,不硬給數字"],
  ];
  rows.forEach((r, i) => {
    const y = 1.45 + i * 0.86;
    s.addShape(p.ShapeType.roundRect, {
      x: 7.25, y: y + 0.07, w: 0.12, h: 0.55, rectRadius: 0.06, fill: { color: i < 5 ? GREEN : AMBER }, line: { type: "none" },
    });
    s.addText(r[0], {
      x: 7.52, y: y - 0.02, w: 5.2, h: 0.34, fontFace: F, fontSize: 13, bold: true, color: NAVY, margin: 0,
    });
    s.addText(r[1], {
      x: 7.52, y: y + 0.32, w: 5.25, h: 0.44, fontFace: F, fontSize: 11.5, color: MUT, margin: 0, valign: "top",
    });
  });
  s.addNotes("左圖是最重要的驗證圖:視覺碼表對 GPS。右側彙整所有片段:對 GPS 的 MAE 落在 1~2.4 km/h,對人工畫格法差 1 km/h 級,失效段全部誠實 no-lock。");
})();

/* ---------------- S10b 批量驗證 ---------------- */
(function () {
  const s = lightSlide("驗證", "批量驗證:20251029 汽車 8 案 28 段");
  s.addImage({ path: "assets/error_distribution.png", x: 0.62, y: 1.45, w: 7.6, h: 3.34 });
  caption(s, 0.62, 4.85, 7.6,
    "碼表 vs 人工畫格法逐段誤差(左:各案分布;右:直方圖)。紅圈=GPS 仲裁判定人工真值本身可疑的段");
  const nums = [
    ["1.93", "28 段全體 MAE(km/h)"],
    ["1.37", "剔除可疑真值後 23 段 MAE"],
    ["24/28", "落在 ±3 km/h 內"],
  ];
  nums.forEach((n, i) => {
    const x = 0.62 + i * 2.6;
    s.addText(n[0], { x: x, y: 5.5, w: 2.4, h: 0.55, fontFace: F, fontSize: 26, bold: true, color: AMBER_TXT, margin: 0 });
    s.addText(n[1], { x: x, y: 6.08, w: 2.5, h: 0.5, fontFace: F, fontSize: 10.5, color: MUT, margin: 0, valign: "top" });
  });
  s.addImage({ path: "assets/spot4407.jpg", x: 8.5, y: 1.45, w: 4.25, h: 2.39 });
  caption(s, 8.5, 3.9, 4.25,
    "案 44-07:HUD 讀值 55.8 km/h,同一幀 OSD 燒錄車速 055Km/h——影片內即可三方互證");
  card(s, 8.5, 4.62, 4.25, 2.0, "EFF6EF", "CDE3CF");
  s.addText([
    { text: "GPS OSD 仲裁:", options: { bold: true, color: GREEN, breakLine: true } },
    { text: "5 個大偏差段(01-35 兩段、10-05 兩段、33-23 一段)經畫面 GPS 比對,偏差都在人工端(±1 幀量化、時基誤用);本系統讀值貼 GPS ±2 內。", options: { color: INK } },
  ], {
    x: 8.74, y: 4.76, w: 3.8, h: 1.75, fontFace: F, fontSize: 11.5, margin: 0, valign: "top", lineSpacingMultiple: 1.18,
  });
  s.addNotes("批量驗證核心頁:MAE 1.93 全體 / 1.37 可信段。大偏差段不是系統錯,而是 GPS 證明人工真值有問題——這是鑑識上很有力的敘事。");
})();

/* ---------------- S10c 時基三陷阱 ---------------- */
(function () {
  const s = lightSlide("誠實鑑識", "證物影片的時基陷阱:速度計算前先重建時間軸");
  const traps = [
    ["① 容器 fps 謊報", "案 33-23:容器標 29.97fps 且 pts 完美等距,但 OSD 時鐘 8 秒內有 230 幀 → 真時基 28.75fps。誤信容器=所有速度高 4.2%。"],
    ["② VFR 爆發塞幀", "案 14-16:名義 13fps,實為 10fps 主幀+爆發塞幀。人工用均勻假設 → 發布值高 +30%(51 vs 39);容器 pts 與畫面 GPS 互證後才是真值。"],
    ["③ 剪輯跳接", "案 44-07:f810/811 之間剪掉整整 60 秒(07:25:36→07:26:36,秒位連續、分位才露餡)。人工把 92 秒攤到 952 幀 → 速度 ÷2.9;×2.899 修正後三方吻合(六段 MAE 0.88)。"],
  ];
  traps.forEach((t, i) => {
    const y = 1.5 + i * 1.62;
    card(s, 0.62, y, 8.7, 1.48, i === 2 ? AMBER_BG : CARD, i === 2 ? "F0DFAE" : CARD_LINE);
    s.addText(t[0], {
      x: 0.88, y: y + 0.12, w: 8.2, h: 0.38, fontFace: F, fontSize: 14.5, bold: true, color: STEEL, margin: 0,
    });
    s.addText(t[1], {
      x: 0.88, y: y + 0.52, w: 8.2, h: 0.9, fontFace: F, fontSize: 11.8, color: INK, margin: 0, valign: "top", lineSpacingMultiple: 1.12,
    });
  });
  card(s, 0.62, 6.4, 8.7, 0.62, CARD);
  s.addText([
    { text: "原則:", options: { bold: true, color: INK } },
    { text: "人工的虛線計數(距離)通常沒錯,錯的都是時基——與 CCTV「NVR 謊報 fps → OSD 秒跳定時」同一件事。", options: { color: INK } },
  ], {
    x: 0.88, y: 6.47, w: 8.2, h: 0.5, fontFace: F, fontSize: 12, margin: 0, valign: "middle",
  });
  s.addImage({ path: "assets/c4407_cut.png", x: 9.72, y: 1.5, w: 2.95, h: 5.49 });
  caption(s, 9.72, 7.02, 3.0, "44-07 逐幀時鐘稽核:f805→f811 分鐘直接 25→26");
  s.addNotes("三種陷阱都在這批案例實際出現。右邊是 44-07 的關鍵證據:秒位看起來連續,分位才暴露剪輯。");
})();

/* ---------------- S11 他車測速 demo ---------------- */
(function () {
  const s = lightSlide("成果", "他車測速:白天多車示範(使用者主軸需求)");
  s.addImage({ path: "assets/dc007_t5.jpg", x: 0.62, y: 1.45, w: 5.9, h: 3.32 });
  caption(s, 0.62, 4.83, 5.9,
    "台86 危險駕駛案(dc007):紅車貼右側 13.1 m、~65 km/h;自車視覺碼表 82.8 km/h(畫面下方 GPS 87 為減速中參考)");
  card(s, 0.62, 5.5, 5.9, 1.28, CARD);
  s.addText([
    { text: "絕對速 = 自車速 + d(距離)/dt", options: { bold: true, color: STEEL, breakLine: true } },
    { text: "距離 >40 m(靈敏度 >0.8 m/px)標 far-range 只給距離不給速度", options: { color: MUT } },
  ], {
    x: 0.88, y: 5.62, w: 5.4, h: 1.05, fontFace: F, fontSize: 12.5, margin: 0, valign: "middle", lineSpacingMultiple: 1.2,
  });

  card(s, 6.9, 1.45, 5.8, 2.2, "FFFFFF", "C7D2E2");
  s.addText("dc007|危險駕駛全程重建(11 秒,12 軌)", {
    x: 7.14, y: 1.62, w: 5.35, h: 0.38, fontFace: F, fontSize: 14, bold: true, color: STEEL, margin: 0,
  });
  s.addText("紅色目標車:匝道加速接近 ~100 km/h → 貼自車右側 10 m ~76 → 貼身過近(接地點被引擎蓋遮擋,誠實無量測)→ 切入前方 30 m 再加速逃逸;自車 GPS 對照巡航段 MAE ≈ 2.2", {
    x: 7.14, y: 2.04, w: 5.35, h: 1.5, fontFace: F, fontSize: 12, color: MUT, margin: 0, valign: "top", lineSpacingMultiple: 1.15,
  });
  const two = [
    ["dc006|國道車流", "60 秒內 77 台目標車有絕對速度(62~113 km/h 合理車流分布)"],
    ["dc003|超廣角後視鏡機", "60 條軌跡;自車三度換道 → 碼表覆蓋 52%,低覆蓋誠實呈現"],
  ];
  two.forEach((t, i) => {
    const y = 3.85 + i * 1.5;
    card(s, 6.9, y, 5.8, 1.32, CARD);
    s.addText(t[0], {
      x: 7.14, y: y + 0.13, w: 5.35, h: 0.36, fontFace: F, fontSize: 13.5, bold: true, color: NAVY, margin: 0,
    });
    s.addText(t[1], {
      x: 7.14, y: y + 0.52, w: 5.35, h: 0.7, fontFace: F, fontSize: 12, color: MUT, margin: 0, valign: "top",
    });
  });
  s.addNotes("使用者最新方向:重點是他車測速、影片裡要有多台可量測的車。dc007 是最好的鑑識敘事:危險駕駛紅車全程可重建,貼身段誠實無量測。");
})();

/* ---------------- S12 失效邊界 ---------------- */
(function () {
  const s = lightSlide("誠實鑑識", "已知失效邊界:誠實標示,而不是修掉");
  const fails = [
    ["近地平線遠場", "1 像素=公尺級位移;>0.3 m/px 自動拒發速度"],
    ["螢幕翻拍摩爾紋", "干涉紋污染接地點與標線量測"],
    ["貼地視角虛線 3D", "切線視角深度雜訊:4 m 量成 0.3~6.7 m"],
    ["加減速段(chirp)", "碼表時間解析度 ~3 秒;急煞誠實 no-lock"],
    ["換道期間", "掃過非法定標線;線位閘拒發(曾 82→146 假速)"],
    ["貼身目標車", "接地點低於引擎蓋線,無法取樣(dc007 8~9.3s)"],
    ["LK 光流測速", "震動/夜間把 60 讀成 2:任何裝置都不信"],
    ["超短片(<8s)", "片尾自相關窗截斷,末段無讀值"],
  ];
  fails.forEach((f, i) => {
    const col = i % 4, row = Math.floor(i / 4);
    const x = 0.62 + col * 3.13, y = 1.5 + row * 2.14;
    card(s, x, y, 2.95, 1.98, RED_BG, "EBD3D0");
    circleNum(s, x + 0.22, y + 0.2, "!", RED, "FFFFFF", 0.3);
    s.addText(f[0], {
      x: x + 0.64, y: y + 0.17, w: 2.2, h: 0.62, fontFace: F, fontSize: 12.8, bold: true, color: "8C2B21", margin: 0, valign: "top",
    });
    s.addText(f[1], {
      x: x + 0.22, y: y + 0.88, w: 2.55, h: 1.0, fontFace: F, fontSize: 10.8, color: INK, margin: 0, valign: "top",
    });
  });
  card(s, 0.62, 5.95, 12.08, 0.78, CARD);
  s.addText([
    { text: "誠實標示是計畫要求:", options: { bold: true, color: INK } },
    { text: "每一項都以旗標呈現在影片與 CSV(far-range、no-lock、灰色問號)——法庭證據寧缺勿錯,量不到就說量不到。", options: { color: INK } },
  ], {
    x: 0.9, y: 6.05, w: 11.6, h: 0.6, fontFace: F, fontSize: 12.5, margin: 0, valign: "middle",
  });
  s.addNotes("這頁刻意保留:失效邊界是報告素材,不是要修掉的 bug。系統的可信度來自於知道自己什麼時候不可信。");
})();

/* ---------------- S13 模型選型與品質旗標 ---------------- */
(function () {
  const s = lightSlide("工程決策", "偵測器選型與品質旗標");
  s.addText("五模型偵測器比較(2026-07)", {
    x: 0.62, y: 1.42, w: 6.2, h: 0.4, fontFace: F, fontSize: 16, bold: true, color: INK, margin: 0,
  });
  bullets(s, 0.62, 1.94, 6.25, 3.3, [
    "比較 YOLOv8s/v8m/v8x/11m/11x/12m:端到端速度誤差 v8m −1.6% vs 真值(11x −4.7%)",
    "行車紀錄器自洽測試:模型間差僅 0.40 km/h → 偵測器不是速度誤差的瓶頸",
    "結論:v8m 維持預設",
    "夜間 CCTV 召回率 11x 較佳(0.70/0.76 vs v8m 0.57/0.58)→ 列為夜間案未來選項",
  ], { size: 13.2, gap: 12 });

  s.addText("品質旗標(影片標籤與 CSV 同步)", {
    x: 7.15, y: 1.42, w: 5.6, h: 0.4, fontFace: F, fontSize: 16, bold: true, color: INK, margin: 0,
  });
  const flags = [
    ["ok", GREEN, "等速擬合 RMSE < 1.5 m → 彩色標籤,如 id29 car 34 km/h"],
    ["~ 非等速", AMBER_TXT, "加減速/走走停停 → 標 ~,數字為區間平均"],
    ["far-range", "808A99", "靈敏度 > 0.3 m/px → 灰字 no speed,拒發速度"],
    ["±CI 過大?", "808A99", "CI 超過速度一半 → 灰色問號,BEV 圖不畫"],
  ];
  flags.forEach((fl, i) => {
    const y = 2.0 + i * 0.88;
    s.addShape(p.ShapeType.roundRect, {
      x: 7.15, y: y, w: 1.55, h: 0.5, rectRadius: 0.1, fill: { color: fl[1] }, line: { type: "none" },
    });
    s.addText(fl[0], {
      x: 7.15, y: y, w: 1.55, h: 0.5, fontFace: F, fontSize: 12, bold: true, color: "FFFFFF",
      align: "center", valign: "middle", margin: 0,
    });
    s.addText(fl[2], {
      x: 8.9, y: y - 0.06, w: 3.85, h: 0.72, fontFace: F, fontSize: 11.8, color: INK, margin: 0, valign: "middle",
    });
  });
  card(s, 0.62, 5.75, 12.08, 0.95, CARD);
  s.addText([
    { text: "不確定度公式:", options: { bold: true, color: INK } },
    { text: "speed_ci = 1.96×(等速擬合斜率標準誤) ⊕ 1.96×(速度×尺度CV),平方和開根——幾何校正的不確定度直接進到每個速度數字上。", options: { color: INK } },
  ], {
    x: 0.9, y: 5.88, w: 11.6, h: 0.7, fontFace: F, fontSize: 12.2, margin: 0, valign: "middle",
  });
  s.addNotes("兩個工程決策:偵測器選型有數據支持(v8m 已足夠,瓶頸在幾何不在偵測);品質旗標讓每個數字自帶可信度標示。");
})();

/* ---------------- S14 結論 ---------------- */
(function () {
  const s = p.addSlide();
  s.background = { color: NAVY };
  dashRow(s, 0.64, 0.5, 3, { w: 0.45, gap: 0.28 });
  s.addText("結論與下一步", {
    x: 0.62, y: 0.72, w: 12.0, h: 0.7, fontFace: F, fontSize: 30, bold: true, color: "FFFFFF", margin: 0,
  });
  const concl = [
    ["把影片變成測速儀", "單幀 3D + 台灣法定標線尺度錨:不必到現場丈量,任意監視器/行車紀錄器影片都能重建車速與距離"],
    ["精度已交叉驗證", "CCTV 對人工交比法 +0.5%;行車紀錄器對 GPS MAE 1~2.4 km/h;8 汽車案批量對人工畫格法 28 段 MAE 1.93(可信 23 段 1.37)"],
    ["鑑識可信度來自誠實", "±95% CI、自動拒發、no-lock:系統知道自己什麼時候不可信,失效邊界全部誠實標示"],
  ];
  concl.forEach((c, i) => {
    const y = 1.85 + i * 1.42;
    circleNum(s, 0.66, y + 0.04, String(i + 1), AMBER, NAVY, 0.36);
    s.addText(c[0], {
      x: 1.24, y: y - 0.02, w: 5.6, h: 0.4, fontFace: F, fontSize: 16.5, bold: true, color: AMBER, margin: 0,
    });
    s.addText(c[1], {
      x: 1.24, y: y + 0.42, w: 5.5, h: 0.9, fontFace: F, fontSize: 12.2, color: "C9D4E6", margin: 0, valign: "top", lineSpacingMultiple: 1.15,
    });
  });
  card(s, 7.3, 1.85, 5.4, 4.35, NAVY2, "2C3E63");
  s.addText("下一步", {
    x: 7.58, y: 2.05, w: 4.9, h: 0.42, fontFace: F, fontSize: 16, bold: true, color: "FFFFFF", margin: 0,
  });
  const next = [
    "取得「汽車目標+路人視角」事故素材(WOWtchout 類公開影片/海盛汽車目標案)→ 他車測速實戰",
    "白天 TDX 路口素材重錄與驗證(現有路口素材多為夜間)",
    "期末報告與論文撰寫:流程、校正、批量驗證、時基陷阱、失效邊界素材已齊",
    "程式碼整理與版本封存(v3 追蹤器、碼表防護鏈)",
  ];
  next.forEach((n, i) => {
    const y = 2.62 + i * 0.92;
    s.addShape(p.ShapeType.roundRect, {
      x: 7.6, y: y + 0.06, w: 0.3, h: 0.075, rectRadius: 0.037, fill: { color: AMBER }, line: { type: "none" },
    });
    s.addText(n, {
      x: 8.02, y: y - 0.12, w: 4.5, h: 0.85, fontFace: F, fontSize: 11.8, color: "C9D4E6", margin: 0, valign: "top", lineSpacingMultiple: 1.12,
    });
  });
  s.addText("Vehicle-Distance-Forensics · 大專學生研究計畫 · 2026 年 7 月", {
    x: 0.62, y: 6.9, w: 12.0, h: 0.4, fontFace: F, fontSize: 11.5, color: "8A97AD", margin: 0, valign: "middle",
  });
  footer(s, true, true);
  s.addNotes("收尾:三個結論對應開場的三個目標(自動化、可稽核、誠實);下一步聚焦批量驗證與報告撰寫。");
})();

p.writeFile({ fileName: "out/Vehicle-Distance-Forensics_專案報告_20260712.pptx" }).then((f) => {
  console.log("written:", f);
});
