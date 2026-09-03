// 單一主題簡報:他車的距離與速度,第一次用儀器驗證(2026-09-01)
//
// 風格刻意跟 gen_progress*.js 不同:那些是進度報告,一頁塞滿條列;
// 這份是給使用者自己看懂、也能照著講的版本 —— 一頁一個想法、句子寫成講得出口的口語、
// 表格才是主角。數字全部取自 data/output/comma2k19_radar_eval/README.md。
const PptxGenJS = require("pptxgenjs");

const F = process.env.REPORT_ASSETS || "/home/s11244/tmp/pptx_build/assets";
const INK = "1A1A1A", MUTED = "6B6B6B", ACCENT = "1F4E79", LINE = "DDDDDD", SOFT = "F5F6F8";
const GOOD = "2E6B2E", BAD = "A33A31";
const FONT = "Microsoft JhengHei";

const p = new PptxGenJS();
p.defineLayout({ name: "W16", width: 13.333, height: 7.5 });
p.layout = "W16";

function title(s, text, sub) {
  s.addText(text, { x: 0.9, y: 0.55, w: 11.6, h: 0.7, fontSize: 30, bold: true, color: INK, fontFace: FONT });
  if (sub) s.addText(sub, { x: 0.9, y: 1.28, w: 11.6, h: 0.4, fontSize: 15, color: MUTED, fontFace: FONT });
  s.addShape(p.ShapeType.line, { x: 0.9, y: sub ? 1.78 : 1.42, w: 1.4, h: 0, line: { color: ACCENT, width: 2.5 } });
}
const para = (s, text, o = {}) =>
  s.addText(text, {
    x: o.x ?? 0.9, y: o.y ?? 2.2, w: o.w ?? 11.6, h: o.h ?? 1.0,
    fontSize: o.size ?? 18, color: o.color ?? INK, fontFace: FONT, lineSpacingMultiple: 1.35, valign: "top",
  });
const small = (s, text, y, o = {}) =>
  s.addText(text, { x: o.x ?? 0.9, y, w: o.w ?? 11.6, h: o.h ?? 0.5, fontSize: o.size ?? 13,
                    color: o.color ?? MUTED, fontFace: FONT, italic: o.italic ?? false,
                    lineSpacingMultiple: 1.3 });

// 統一的表格樣式:第一列是標頭,highlight 指定要強調的資料列(0 起算)
function table(s, rows, colW, o = {}) {
  s.addTable(
    rows.map((r, i) => r.map((c, j) => ({
      text: c,
      options: {
        fontSize: i === 0 ? (o.headSize ?? 13.5) : (o.size ?? 15), fontFace: FONT, valign: "middle",
        align: j === 0 ? "left" : "center",
        bold: i === 0 || (o.highlight ?? []).includes(i - 1),
        color: i === 0 ? "FFFFFF" : ((o.rowColor && o.rowColor[i - 1]) || INK),
        fill: i === 0 ? { color: ACCENT } : { color: (o.highlight ?? []).includes(i - 1) ? SOFT : "FFFFFF" },
      },
    }))),
    { x: o.x ?? 0.9, y: o.y ?? 2.15, w: o.w ?? 11.6, colW,
      rowH: o.rowH ?? 0.46, border: { type: "solid", color: LINE, pt: 0.5 }, margin: 0.06 });
}

/* ---------------------------------------------------------------- 1 封面 */
let s = p.addSlide();
s.addShape(p.ShapeType.rect, { x: 0, y: 2.55, w: 13.333, h: 0.06, fill: { color: ACCENT }, line: { color: ACCENT } });
s.addText("別台車量得準不準?", { x: 0.9, y: 1.45, w: 11.6, h: 1.05, fontSize: 40, bold: true, color: INK, fontFace: FONT });
s.addText("第一次拿真正的儀器來對答案", { x: 0.9, y: 2.85, w: 11.6, h: 0.5, fontSize: 20, color: MUTED, fontFace: FONT });
s.addText([
  { text: "結論先講:", options: { bold: true, color: INK } },
  { text: "32 公尺以內,距離差 7%、速度差 3.5 km/h。\n32 公尺以外不能信,而且系統現在還照印,要修。", options: { color: INK } },
], { x: 0.9, y: 3.9, w: 11.0, h: 1.2, fontSize: 19, fontFace: FONT, lineSpacingMultiple: 1.35 });
s.addText("公開資料集 comma2k19 車載原廠雷達　|　3 個路段、908 個配對影格　|　2026-09-01",
  { x: 0.9, y: 6.5, w: 11.6, h: 0.4, fontSize: 13, color: MUTED, fontFace: FONT });

/* -------------------------------------------------- 2 以前的檢查是作弊的 */
s = p.addSlide();
title(s, "先講一件不好意思的事", "我們以前用來說「他車量得準」的那個檢查,其實是自己驗自己");

s.addShape(p.ShapeType.roundRect, { x: 0.9, y: 2.15, w: 11.6, h: 1.0,
  fill: { color: SOFT }, line: { color: LINE }, rectRadius: 0.08 });
s.addText("程式算前車速度的方式  =  自己的車速  +  距離變化率",
  { x: 0.9, y: 2.32, w: 11.6, h: 0.65, fontSize: 22, bold: true, align: "center", color: ACCENT, fontFace: FONT });

para(s, "所以「跟車跟得穩的時候,前車速度跟自己車速差不多」這件事,是這條公式本來就保證的 —— " +
        "不管幾何有沒有算錯,它都會成立。等於考卷自己改自己,考幾分都沒有意義。",
     { y: 3.45, h: 1.0 });
para(s, "自己的車速倒是驗過很多次了(人工畫格法、GPS、CAN、公開資料集都對過)。" +
        "但「別台車」的距離和速度,一直沒有任何外部的東西可以對。",
     { y: 4.5, h: 0.9 });
small(s, "這一輪要做的,就是把這個洞補起來。", 5.6, { size: 16, italic: true });

/* ------------------------------------------------------ 3 借一把獨立的尺 */
s = p.addSlide();
title(s, "去借一把獨立的尺", "找一份「車上有裝雷達」的公開行車資料");

table(s, [
  ["要量的東西", "我們的方法", "雷達的方法"],
  ["前車有多遠", "攝影機看輪胎著地的位置,用地面幾何換算", "打電波出去,量它跑回來要多久"],
  ["自己的車速", "看地上虛線流過畫面的節奏算出來", "車上輪速感測器(CAN)"],
  ["前車的實際速度", "自己車速 + 距離變化率", "輪速 + 雷達測到的速度差"],
], [3.0, 4.4, 4.2], { size: 15.5, rowH: 0.72 });

para(s, "兩邊完全沒有共用任何東西:不同感測器、不同物理原理、連自己車速的來源都不一樣。" +
        "所以我們的幾何要是算錯了,雷達一定看得出來。",
     { y: 4.9, h: 0.9 });
small(s, "資料集沒有說明雷達那幾個欄位是什麼意思。驗證的方法很簡單:靜止的路邊物體,雷達測到的速度差剛好等於「負的自己車速」 —— " +
         "這個關係一成立,欄位的意思就確定了。", 5.9, { h: 0.8 });

/* ---------------------------------------------------- 4 怎麼比才不會作弊 */
s = p.addSlide();
title(s, "比的時候,不能自己挑");

para(s, "最容易騙自己的地方是「哪一台配哪一台」。所以規則訂成這樣:",
     { y: 2.05, h: 0.5, size: 17 });
const rules = [
  ["兩邊各自用自己的數字", "說「我車道正前方那台移動的車是誰」,誰都不准參考對方"],
  ["再拿左右位置來檢查", "兩邊獨立量到的橫向位置要對得上,對不上就丟掉"],
  ["一台配一台", "不允許兩條軌跡同時宣稱同一台車"],
];
rules.forEach(([a, b], i) => {
  const y = 2.6 + i * 0.85;
  s.addText(`${i + 1}`, { x: 0.9, y, w: 0.5, h: 0.5, fontSize: 20, bold: true, color: ACCENT, fontFace: FONT });
  s.addText(a, { x: 1.45, y, w: 3.9, h: 0.5, fontSize: 17, bold: true, color: INK, fontFace: FONT });
  s.addText(b, { x: 5.4, y, w: 7.1, h: 0.5, fontSize: 16, color: MUTED, fontFace: FONT });
});

s.addShape(p.ShapeType.roundRect, { x: 0.9, y: 5.3, w: 11.6, h: 1.35,
  fill: { color: "FFF6F5" }, line: { color: "E8C9C5" }, rectRadius: 0.08 });
s.addText([
  { text: "第 3 條是踩到才加的。  ", options: { bold: true, color: BAD } },
  { text: "第一版只寫「取最近的那台」,結果同一個地方有兩條軌跡都說自己配到那台雷達目標," +
          "一條說距離差 0.94 倍、另一條說 1.15 倍 —— 但現場只可能有一台車。", options: { color: INK } },
], { x: 1.15, y: 5.5, w: 11.1, h: 1.0, fontSize: 15, fontFace: FONT, lineSpacingMultiple: 1.3 });

/* -------------------------------------------------------------- 5 結果 */
s = p.addSlide();
title(s, "結果:近的準,遠的不準", "3 個路段、908 個配對影格");

table(s, [
  ["", "配對幀數", "距離差多少", "前車速度差多少", "最糟的 10%"],
  ["32 公尺以內", "434", "7 %", "3.5 km/h", "6.2"],
  ["32 公尺以外", "474", "20 %(最糟 72%)", "6.5 km/h", "11.9"],
  ["全部合起來", "908", "9.6 %", "5.1 km/h", "7.8"],
], [3.1, 1.9, 2.6, 2.4, 1.6], { highlight: [0], rowColor: [GOOD, BAD, INK], rowH: 0.6 });

para(s, "「32 公尺」不是我事後畫的線 —— 系統本來就會把超過這個距離的目標標成「遠場、不給速度」。" +
        "這次等於順便驗證了那條線畫在對的位置:界線內誤差 7%,界線外 20%。",
     { y: 4.4, h: 1.0 });
small(s, "系統判斷遠近的方式是「畫面上一個像素代表幾公尺」,超過 0.8 公尺就算遠場。" +
         "這台相機大約對應 32 公尺。", 5.5, { h: 0.7 });

/* ------------------------------------------------------------ 6 證據圖 */
s = p.addSlide();
title(s, "把它畫出來");
s.addImage({ path: `${F}/radar_eval.png`, x: 0.75, y: 1.95, w: 11.9, h: 4.45 });
small(s, "左:橫軸是雷達測到的真實距離,縱軸是「雷達 ÷ 我們」。等於 1 就是完全吻合。" +
         "綠色帶是系統自認可信的近場 —— 那裡貼著 1.0,出了綠帶就一路發散。" +
         "右:把幾秒內的數字平均起來,誤差會降到多少。", 6.55, { h: 0.8 });

/* -------------------------------------------------- 7 誤差是從哪來的 */
s = p.addSlide();
title(s, "這 3.5 km/h 是從哪來的", "可以精確拆成兩半,而且兩半必然相加(實測誤差小於 0.11)");

s.addShape(p.ShapeType.roundRect, { x: 0.9, y: 2.15, w: 11.6, h: 0.85,
  fill: { color: SOFT }, line: { color: LINE }, rectRadius: 0.08 });
s.addText("前車速度的誤差  =  (我們的車速 − 真實車速)  +  (我們的距離變化率 − 雷達的)",
  { x: 0.9, y: 2.3, w: 11.6, h: 0.55, fontSize: 19, bold: true, align: "center", color: ACCENT, fontFace: FONT });

const parts = [
  ["自己車速這一項", "1.9 km/h", "虛線碼表算的自車速,跟車上真實輪速的差"],
  ["幾何這一項", "3.3 km/h", "接地點 → 地面幾何 → 距離,這條鏈自己的誤差"],
];
parts.forEach(([a, b, c], i) => {
  const y = 3.4 + i * 1.0;
  s.addShape(p.ShapeType.line, { x: 0.9, y: y + 0.75, w: 11.6, h: 0, line: { color: LINE, width: 1 } });
  s.addText(a, { x: 0.9, y, w: 3.4, h: 0.6, fontSize: 18, bold: true, color: INK, fontFace: FONT });
  s.addText(b, { x: 4.3, y, w: 2.1, h: 0.6, fontSize: 20, bold: true, color: ACCENT, align: "right", fontFace: FONT });
  s.addText(c, { x: 6.6, y: y + 0.05, w: 5.9, h: 0.5, fontSize: 15, color: MUTED, fontFace: FONT });
});
para(s, "兩邊差不多大。也就是說,想讓他車速度更準,光改幾何或光改碼表都只能砍掉一半。",
     { y: 5.6, h: 0.8, size: 17 });

/* -------------------------------------------------------- 8 平均的效果 */
s = p.addSlide();
title(s, "把幾秒內的數字平均,會更準", "但改善有兩個來源,要分開講");

table(s, [
  ["平均幾秒", "樣本數", "誤差 MAE", "同一批影格、不平均的話"],
  ["不平均", "890", "5.1 km/h", "—"],
  ["1 秒", "636", "4.0 km/h", "4.7"],
  ["2 秒", "484", "1.9 km/h", "2.7"],
  ["3 秒", "283", "1.4 km/h", "2.9"],
], [2.4, 2.0, 3.0, 4.2], { highlight: [3], rowH: 0.52 });

s.addShape(p.ShapeType.roundRect, { x: 0.9, y: 5.1, w: 11.6, h: 1.5,
  fill: { color: "F4F8F4" }, line: { color: "CBDCCB" }, rectRadius: 0.08 });
s.addText([
  { text: "5.1 → 1.4 這個進步,只有一半是平均的功勞。", options: { bold: true, color: GOOD } },
  { text: "\n最右邊那欄是關鍵:同一批影格如果不平均是 2.9,平均後才 1.4 —— 平均本身把誤差砍一半。" +
          "\n另一半(5.1 → 2.9)是因為「能撐滿 3 秒的片段,本來就是比較好量的片段」。報告時兩者要分開說。",
    options: { color: INK } },
], { x: 1.15, y: 5.28, w: 11.1, h: 1.2, fontSize: 15, fontFace: FONT, lineSpacingMultiple: 1.3 });

/* ------------------------------------------------------------ 9 延遲 */
s = p.addSlide();
title(s, "有沒有反應慢半拍?", "沒有");

para(s, "本來擔心攝影機這條鏈會比雷達慢一點,所以前後掃了 2 秒找最合的位置。三段各自的答案是:",
     { y: 2.05, h: 0.6, size: 17 });
const lags = [["路段 1", "+1.95 秒"], ["路段 2", "−1.60 秒"], ["路段 3", "+2.00 秒"]];
lags.forEach(([a, b], i) => {
  const x = 0.9 + i * 3.95;
  s.addShape(p.ShapeType.roundRect, { x, y: 2.8, w: 3.5, h: 1.5, fill: { color: "FFFFFF" }, line: { color: LINE }, rectRadius: 0.08 });
  s.addText(a, { x, y: 3.0, w: 3.5, h: 0.35, fontSize: 15, align: "center", color: MUTED, fontFace: FONT });
  s.addText(b, { x, y: 3.4, w: 3.5, h: 0.7, fontSize: 30, bold: true, align: "center",
                 color: i === 1 ? BAD : ACCENT, fontFace: FONT });
});
para(s, "一個往前、一個往後,而且有兩個剛好卡在搜尋範圍的邊界。真的有延遲的話,三段應該指同一個方向。",
     { y: 4.6, h: 0.8 });
para(s, "所以那個「看起來變準」只是硬湊出來的 —— 速度本來就變化很小,把兩條各自慢慢飄的誤差對齊," +
        "數字當然會變好看。結論:不要做延遲補償。",
     { y: 5.45, h: 0.9 });

/* ------------------------------------------------ 10 順便結掉一個懸案 */
s = p.addSlide();
title(s, "順便解決一個懸了兩週的問題", "「距離要乘以 0.76~0.90 修正」,那個倍數到底對不對");

para(s, "8 月時發現系統算的距離偏長,用地上虛線推出每台相機的修正倍數。但之後用「已知尺寸的東西」" +
        "去量,得到 0.71 / 0.89 / 0.93 三個不一樣的答案,所以一直只能寫「方向確定、幅度未定」。",
     { y: 2.05, h: 1.0, size: 17 });

table(s, [
  ["路段", "我們用虛線推的倍數", "雷達實測的倍數", "差多少"],
  ["路段 1", "1.031", "0.995", "+3.6 %"],
  ["路段 2", "0.919", "0.934", "−1.6 %"],
  ["路段 3", "品質檢查沒過,不給答案", "(沒有近場資料)", "—"],
], [2.6, 4.2, 3.0, 1.8], { y: 3.25, highlight: [0, 1], rowH: 0.5 });

para(s, "差 1.6% 到 3.6%,而且都落在這個量測自己的誤差範圍內。方法沒問題。" +
        "另外第三段被系統自己的品質檢查擋下來了 —— 那道關卡也是有效的。",
     { y: 5.15, h: 0.9, size: 17 });
small(s, "但要講清楚適用範圍:驗證的是「這個量法不會系統性騙人」(準到大約 ±4%),不是台灣那五支影片的個別倍數 —— " +
         "這台相機需要的修正接近 1.0,沒測試到 0.76 那種大幅修正的情形。", 6.15, { h: 0.8 });

/* -------------------------------------------------- 11 抓到一個要修的 */
s = p.addSlide();
title(s, "順便抓到一個要修的地方");

s.addShape(p.ShapeType.roundRect, { x: 0.9, y: 2.15, w: 11.6, h: 1.55,
  fill: { color: "FFF6F5" }, line: { color: "E8C9C5" }, rectRadius: 0.08 });
s.addText("遠處的「速度」系統會拒絕給,但遠處的「距離」還是照印在影片上,而且沒有任何警告。",
  { x: 1.15, y: 2.4, w: 11.1, h: 0.6, fontSize: 20, bold: true, color: BAD, fontFace: FONT });
s.addText("而那個距離中位偏 20%,最糟的一筆:我們寫 38 公尺,雷達說 66 公尺。",
  { x: 1.15, y: 3.0, w: 11.1, h: 0.5, fontSize: 18, color: INK, fontFace: FONT });

para(s, "做事故鑑識,把一個可能差七成的數字當成量測值印出來是有風險的 —— 看的人不會知道那格能不能信。",
     { y: 4.0, h: 0.8 });
para(s, "建議的修法很簡單:遠場的距離比照速度,標註成「僅供參考」或直接不印。" +
        "系統本來就已經知道哪些是遠場了,只是沒把這個資訊傳給距離那一欄。",
     { y: 4.85, h: 0.9 });
small(s, "另外還得到一條新的失效邊界:從旁邊擦身而過的車(路邊停的車、切進來的車)," +
         "因為輪胎著地點會沿著車身滑動,速度不可信 —— 只能報距離。", 5.95, { h: 0.8 });

/* -------------------------------------------- 12 整體驗證完成度一覽 */
s = p.addSlide();
title(s, "整個專案現在驗到哪了", "打勾的是有外部真值對過的");

table(s, [
  ["量什麼", "拿什麼當答案", "準到多少", "狀態"],
  ["路口監視器測他車速度", "人工交比法", "+0.5 %", "✔"],
  ["同上,但用公開資料集", "BrnoCompSpeed", "—", "未做(200GB 下載不到)"],
  ["行車紀錄器算自己的車速", "人工畫格法", "0.7 ~ 1.3 km/h", "✔ 最強的一項"],
  ["同上,公開資料集", "comma2k19,兩台車 33 段", "2.2 km/h", "✔"],
  ["行車紀錄器測前車距離", "車載原廠雷達", "7 %(32 m 內)", "✔ 這一輪新增"],
  ["行車紀錄器測前車速度", "車載原廠雷達", "3.5 km/h(32 m 內)", "✔ 這一輪新增"],
  ["偵測器該選哪一個", "五個模型實測比較", "換模型只差 0.4 km/h", "✔ 不是瓶頸"],
  ["用資料集微調偵測器", "nuImages", "—", "未做(教授第 4 點)"],
], [4.0, 3.3, 2.5, 1.8], { size: 13.5, headSize: 13, rowH: 0.42, highlight: [4, 5] });

small(s, "「未做」的兩項都有理由:BrnoCompSpeed 卡在下載與連線,需要學校網路或老師具名索取;" +
         "微調偵測器則是因為實測顯示偵測器只影響 0.4 km/h,而尺度校正影響 2 到 11 km/h,不划算。", 6.15, { h: 0.9 });

/* ------------------------------------------------------------ 13 收尾 */
s = p.addSlide();
title(s, "一句話");
s.addText("以前是「大概準」,現在是「32 公尺內準到 7%,32 公尺外不要用」。",
  { x: 0.9, y: 2.2, w: 11.6, h: 1.5, fontSize: 26, bold: true, color: ACCENT, fontFace: FONT, lineSpacingMultiple: 1.3 });
para(s, "能量的範圍變小了,但範圍內的數字現在有儀器背書。對鑑識用途來說,「知道哪裡不能用」" +
        "跟「知道哪裡很準」一樣重要。",
     { y: 3.75, h: 0.9 });

s.addText("接下來三件事", { x: 0.9, y: 4.6, w: 11.6, h: 0.4, fontSize: 17, bold: true, color: ACCENT, fontFace: FONT });
[["1", "把遠場距離加上警語(這輪唯一直接指出的程式缺陷)"],
 ["2", "請老師協助取得 BrnoCompSpeed,補上路口監視器那條線的公開資料集驗證"],
 ["3", "報告封面的姓名、系所、指導教授、執行期間還要補"]].forEach(([n, t], i) => {
  s.addText(`${n}.  ${t}`, { x: 1.15, y: 5.1 + i * 0.5, w: 11.3, h: 0.45, fontSize: 16, color: INK, fontFace: FONT });
});

p.writeFile({ fileName: "/home/s11244/code/114/Vehicle-Distance-Forensics/data/output/report_slides/他車量測驗證_雷達_20260903.pptx" })
  .then(f => console.log("已寫出", f));
