"""Registration pipeline/PREREG_comma2k19_chunk8.md §3.1, item by item, from the shared scorer's output.
Written and committed before the batch's truth exists; the reading of the scores is fixed here, not after seeing them.

  ~/anaconda3/envs/VisionVelocity/bin/python pipeline/judge/chunk8.py --bench <shared repo> \
      --results <score --out folder of the sealed v2> --segments <segments root used by the scorer> \
      --v2own <predictions/A_depth_odometer/v2own> --out <folder>

Numbers use the formulas behind the registration's development values (pairs with a distance, truth in (lo, hi];
relative speed on truth <= 30 m with a reading; ego per one-second bin, coverage = bins with a reading / all bins;
found = pairs / truth in scope), on the groups of segment.json (primary = day ca_highway + unknown).
Items are judged on unrounded numbers; the tables show them rounded.
Before anything is judged:
  - the results must be the sealed v2, scored as a blind batch with the registered config, by a scorer without
    local changes (or --allow-scorer-changes, stated in the output); the seal, the batch list and every segment.json must match the pushed seal;
  - the pooled numbers here must equal the scorer's own (distance, relative speed, found rate, 582, offsets).
Two readings go through the scorer's own per-segment function (mddbench.score.score_segment) with the sealed config:
  - every item again with the config's matching sensitivity column (582) for the whole batch;
  - v2own (item 7), which the scorer only takes with a seal; its files are first checked against
    pipeline/seals/v2own_comma2k19_chunk8.json as pushed in b6dddc7, and its truth must be built after that.
The same function on v2 must give back the scorer's pairs.csv and ego_bins.csv, or nothing is judged.
Also reported, not judged: the distance items under the config's other truth offsets, per drive, and the D9 spot-check
of the label table (d9_chunk8.csv, sample from d9_sample_chunk8.py): the segments where the checker's labels differ,
and the groups with the checker's labels on the sampled segments.
This file sits outside pipeline/*.py, so the code hash of the predictions (pipeline/batch.py code_sha256) is unchanged.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
OWN_LIST = REPO / "pipeline" / "seals" / "v2own_comma2k19_chunk8.json"
OWN_COMMIT = "b6dddc7"
CONFIG_SHA256 = "effc445a14e400b649823b90f066ccb2f8e2ea32e763576d486ac5e7a70da4cf"
SEAL_NAME = "A_depth_odometer_v2_comma2k19_chunk8.json"
SEAL_SHA256 = "fb37af3b724ce69dd6c786967daf9b5c1a00f3b7c7dc76e55ea2ae3541fa54af"
BATCH = "splits/batches/comma2k19_chunk8.txt"
PRIMARY = "primary_day_highway_unknown"
GROUPS = {PRIMARY: lambda r, l: l == "day" and r in ("ca_highway", "unknown"),
          "day_ca_local": lambda r, l: l == "day" and r == "ca_local",
          "night": lambda r, l: l == "night", "all": lambda r, l: True}
COUNTS = {PRIMARY: 126, "day_ca_local": 43, "night": 39, "all": 208}  # registration §2
ROADS, LIGHTS = {"ca_highway", "ca_local", "unknown"}, {"day", "night"}
TITLES = {PRIMARY: "主要組(白天高速公路 + 判不出來)", "day_ca_local": "白天一般道路", "night": "夜間", "all": "全部"}
NAMES = {"ca_highway": "高速公路", "ca_local": "一般道路", "unknown": "判不出來", "day": "白天", "night": "夜間"}
D9 = HERE / "d9_chunk8.csv"
DIST_ITEMS = ("1a", "1b", "2a", "2b", "3a", "3b", "7", "8", "9")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args: str) -> str | None:
    r = subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def utc(iso: str) -> str:
    """git's %cI in the format of the truth's built_utc."""
    return datetime.fromisoformat(iso).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _rnd(nd: bool):
    return (lambda x, k: round(x, k)) if nd else (lambda x, k: x)


def dist_numbers(p: pd.DataFrame, nd: bool = True) -> dict:
    R = _rnd(nd)
    q = p[p.d_pred.notna()]
    out = {}
    for key, lo, hi in (("near", 0, 30), ("d10_20", 10, 20), ("d20_30", 20, 30), ("mid", 30, 60), ("far", 60, 100)):
        r = q[(q.d_truth > lo) & (q.d_truth <= hi)]
        e = (r.d_pred - r.d_truth) / r.d_truth * 100
        out[key] = {"n": int(len(r)), "med_abs_pct": R(float(np.median(np.abs(e))), 2) if len(r) else None,
                    "bias_pct": R(float(np.median(e)), 2) if len(r) else None,
                    "med_abs_m": R(float(np.median(np.abs(r.d_pred - r.d_truth))), 2) if len(r) else None,
                    "gross_pct": R(100 * float((np.abs(e) > 25).mean()), 2) if len(r) else None}
    n = p[(p.d_truth <= 30) & p.rel_pred.notna() & p.rel_truth.notna()]
    if len(n) > 2:
        out["rel_near"] = {"n": int(len(n)), "mae": R(float((n.rel_pred - n.rel_truth).abs().mean()), 3),
                           "corr": R(float(np.corrcoef(n.rel_truth, n.rel_pred)[0, 1]), 3),
                           "slope": R(float(np.polyfit(n.rel_truth, n.rel_pred, 1)[0]), 3),
                           "guess0": R(float(n.rel_truth.abs().mean()), 3)}
    return out


def ego_numbers(b: pd.DataFrame, nd: bool = True) -> dict:
    R = _rnd(nd)
    h = b[b.pred.notna() & b.truth.notna()]
    return {"seconds": int(len(b)), "coverage_pct": R(100 * len(h) / len(b), 1) if len(b) else None,
            "mae": R(float((h.pred - h.truth).abs().mean()), 3) if len(h) else None,
            "within3_pct": R(100 * float(((h.pred - h.truth).abs() <= 3).mean()), 1) if len(h) else None}


def group_numbers(P: pd.DataFrame, EB: pd.DataFrame, rows: pd.DataFrame, labels: dict, nd: bool = True) -> dict:
    out = {}
    for g, pick in GROUPS.items():
        segs = [s for s, (r, l) in labels.items() if pick(r, l)]
        rec = {"segments": len(segs), "drives": len({s.rsplit("_", 1)[0] for s in segs}),
               **dist_numbers(P[P.segment_id.isin(segs)], nd), "ego": ego_numbers(EB[EB.segment_id.isin(segs)], nd)}
        f = rows[rows.segment_id.isin(segs)] if len(rows) else rows
        n = f.truth_in_scope.sum() if len(f) else 0
        rec["found_pct"] = _rnd(nd)(100 * f.n_pairs.sum() / n, 2) if n else None
        out[g] = rec
    return out


def rescore(S, F, cfg: dict, pred_root: Path, truth_root: Path, segments_root: Path, ids: list[str]):
    """mddbench.score.score() without its access checks (done by the caller): pairs, ego bins, per-segment counts,
    and the segments the scorer would count as missing, invalid or refused (no pairs, empty ego bins)."""
    pairs, bins, rows = [], [], []
    status = {"missing": [], "invalid": {}, "refused": {}}
    for sid in ids:
        seg = F.read_segment(segments_root / sid)
        cluster = S._cluster_of(seg, cfg["bootstrap_cluster"])
        _, tego, tobj = F.read_truth(truth_root / sid)
        pdir = pred_root / sid
        if not pdir.is_dir():
            status["missing"].append(sid)
            bins.append(S._empty_bins(sid, cluster, tego, seg, cfg))
            continue
        errors, _ = F.validate_prediction(pdir, seg)
        if errors:
            status["invalid"][sid] = errors
            bins.append(S._empty_bins(sid, cluster, tego, seg, cfg))
            continue
        meta, ego, obj = F.read_prediction(pdir)
        if meta["status"] == "refused":
            status["refused"][sid] = meta.get("reason", "")
            bins.append(S._empty_bins(sid, cluster, tego, seg, cfg))
            continue
        r = S.score_segment(sid, cluster, seg, ego, obj, tego, tobj, cfg)
        pairs += r["pairs"]
        bins.append(r["ego_bins"])
        rows.append({"segment_id": sid, "n_pairs": len(r["pairs"]), "truth_in_scope": r["truth_in_scope"]})
    return (pd.DataFrame(pairs, columns=S.PAIR_COLS), pd.concat(bins, ignore_index=True),
            pd.DataFrame(rows, columns=["segment_id", "n_pairs", "truth_in_scope"]), status)


def read_d9(labels: dict) -> pd.DataFrame:
    d9 = pd.read_csv(D9, dtype=str, keep_default_na=False)
    if d9.segment_id.duplicated().any() or not set(d9.segment_id) <= set(labels) \
            or any(labels[r.segment_id] != (r.table_road, r.table_light) for r in d9.itertuples()) \
            or not set(d9.checker_road) <= ROADS or not set(d9.checker_light) <= LIGHTS:
        raise SystemExit(f"refused: {D9.name} does not match the label table of the batch")
    return d9


def spot_check(P: pd.DataFrame, EB: pd.DataFrame, rows: pd.DataFrame, labels: dict, d9: pd.DataFrame) -> dict:
    """D9 (descriptive): the segments whose spot-check labels differ, and the groups with the checker's labels."""
    diff = d9[(d9.checker_road != d9.table_road) | (d9.checker_light != d9.table_light)]
    segs = []
    for r in diff.itertuples():
        dn, e = dist_numbers(P[P.segment_id == r.segment_id]), ego_numbers(EB[EB.segment_id == r.segment_id])
        segs.append({"n": int(r.n), "segment_id": r.segment_id, "table": [r.table_road, r.table_light],
                     "checker": [r.checker_road, r.checker_light], "near_n": dn["near"]["n"],
                     "near_med_abs_pct": dn["near"]["med_abs_pct"], "mid_n": dn["mid"]["n"],
                     "mid_med_abs_pct": dn["mid"]["med_abs_pct"], "ego": e})
    ids = set(diff.segment_id)
    relabeled = {**labels, **{r.segment_id: (r.checker_road, r.checker_light) for r in d9.itertuples()}}
    return {"file": D9.relative_to(REPO).as_posix(), "sha256": sha(D9), "sampled": len(d9), "differ": len(diff),
            "segments": segs, "differing_pooled": {**dist_numbers(P[P.segment_id.isin(ids)]),
                                                   "ego": ego_numbers(EB[EB.segment_id.isin(ids)])},
            "groups_checker_labels": group_numbers(P, EB, rows, relabeled)}


def judge_state(first_truth: str) -> dict:
    """Whether this file, as it runs, is the committed and pushed one, and committed before the first truth."""
    rel = Path(__file__).resolve().relative_to(REPO).as_posix()
    head = git("rev-parse", f"HEAD:{rel}")
    same = head is not None and head == git("hash-object", rel)
    last = git("log", "-1", "--format=%H %cI", "--", rel) if same else None
    commit, when = last.split() if last else (None, None)
    when = utc(when) if when else None
    pushed = commit is not None and git("merge-base", "--is-ancestor", commit, "origin/main") is not None
    return {"file": rel, "sha256": sha(Path(__file__)), "committed_as_run": same, "commit": commit,
            "commit_utc": when, "pushed": pushed, "first_truth_utc": first_truth,
            "before_truth": bool(same and pushed and when and when < first_truth)}


def check_own(pred_root: Path, built: dict, ids: list[str], bench: Path) -> dict:
    """v2own must be the files of the hash list pushed in OWN_COMMIT, and the truth must be built after that."""
    rel = OWN_LIST.relative_to(REPO).as_posix()
    blob = git("hash-object", rel) if OWN_LIST.is_file() else None
    if blob is None or git("rev-parse", f"{OWN_COMMIT}:{rel}") != blob:
        raise SystemExit(f"refused: the v2own hash list is not the one committed in {OWN_COMMIT}")
    if git("merge-base", "--is-ancestor", OWN_COMMIT, "origin/main") is None:
        raise SystemExit(f"refused: {OWN_COMMIT} (the v2own hash list) is not on origin/main")
    committed = utc(git("log", "-1", "--format=%cI", OWN_COMMIT))
    lst = json.loads(OWN_LIST.read_text(encoding="utf-8"))
    if (lst.get("method"), lst.get("version")) != ("A_depth_odometer", "v2own") or sorted(lst["segments"]) != sorted(ids):
        raise SystemExit("refused: the v2own hash list is not for this method, version and batch")
    if lst.get("batch_sha256") != sha(bench / BATCH) or (lst.get("same_inference_as") or {}).get("seal_sha256") != SEAL_SHA256:
        raise SystemExit("refused: the v2own hash list names another batch list or another v2 seal")
    gone = [s for s in ids if not (pred_root / s).is_dir()]
    if gone:
        raise SystemExit(f"refused: no v2own folder for {len(gone)} segments, e.g. {gone[0]}")
    found = {f"{p.parent.name}/{p.name}" for sid in ids for p in (pred_root / sid).iterdir() if p.is_file()}
    if found != set(lst["files"]):
        raise SystemExit(f"refused: v2own files differ from the list ({len(found ^ set(lst['files']))} paths)")
    bad = [k for k, v in lst["files"].items() if sha(pred_root / k) != v]
    if bad:
        raise SystemExit(f"refused: {len(bad)} v2own files changed since the list, e.g. {bad[0]}")
    anchor = max(lst["written_utc"], committed)
    early = [s for s in ids if not built[s] > anchor]
    if early:
        raise SystemExit(f"refused: truth of {early[0]} ({built[early[0]] or '?'}) is not newer than the v2own list ({anchor})")
    return {"list": rel, "list_sha256": sha(OWN_LIST), "commit": OWN_COMMIT, "commit_utc": committed,
            "written_utc": lst["written_utc"], "files": len(found)}


def items(R: dict, outputs: dict) -> list[dict]:
    """R: unrounded group numbers for {"v2": ..., "v2own": ... or None}. Judged on R, shown rounded."""
    def get(*ks):
        d = R
        for k in ks:
            d = None if d is None else d.get(k)
        return d

    def div(a, b):
        return None if a is None or not b else a / b
    v2near = get("v2", PRIMARY, "near", "med_abs_pct")
    spec = [
        ("1a", "主要組 30 m 內中位誤差 ≤ 5.5%", get("v2", PRIMARY, "near", "med_abs_pct"), lambda v: v <= 5.5, "4.5", "%", 2),
        ("1b", "主要組 30 m 內中位偏差在 ±4% 內", get("v2", PRIMARY, "near", "bias_pct"), lambda v: abs(v) <= 4, "+2.1", "%", 2),
        ("2a", "主要組 10–20 m 中位誤差 ≤ 0.9 m", get("v2", PRIMARY, "d10_20", "med_abs_m"), lambda v: v <= 0.9, "0.72", "m", 2),
        ("2b", "主要組 20–30 m 中位誤差 ≤ 1.4 m", get("v2", PRIMARY, "d20_30", "med_abs_m"), lambda v: v <= 1.4, "1.10", "m", 2),
        ("3a", "主要組 30–60 m 中位誤差 ≤ 9%", get("v2", PRIMARY, "mid", "med_abs_pct"), lambda v: v <= 9, "6.7", "%", 2),
        ("3b", "主要組 60–100 m 中位誤差 ≤ 11%", get("v2", PRIMARY, "far", "med_abs_pct"), lambda v: v <= 11, "8.3", "%", 2),
        ("4a", "主要組相對速度(30 m 內)MAE ≤ 2.4 km/h", get("v2", PRIMARY, "rel_near", "mae"), lambda v: v <= 2.4,
         "1.88", "km/h", 3),
        ("4b", "主要組相對速度 MAE 不到「全猜 0」的一半",
         div(get("v2", PRIMARY, "rel_near", "mae"), get("v2", PRIMARY, "rel_near", "guess0")), lambda v: v < 0.5,
         "0.23(1.88 / 8.07)", "倍", 3),
        ("5a", "主要組本車速度每秒 MAE ≤ 4.0 km/h", get("v2", PRIMARY, "ego", "mae"), lambda v: v <= 4.0, "3.14", "km/h", 3),
        ("5b", "主要組本車速度秒數覆蓋率 ≥ 85%", get("v2", PRIMARY, "ego", "coverage_pct"), lambda v: v >= 85, "94", "%", 1),
        ("6a", "主要組找到率 ≥ 45%", get("v2", PRIMARY, "found_pct"), lambda v: v >= 45, "57", "%", 2),
        ("6b", "208 段全部有輸出、沒有拒發", outputs["with_output"], lambda v: v == 208 and not outputs["refused"],
         "202/202", "段", 0),
        ("7", "v2own 主要組 30 m 內誤差比 v2 大", None if v2near is None else get("v2own", PRIMARY, "near", "med_abs_pct"),
         lambda v: v > v2near, "6.6 對 4.5", "%", 2),
        ("8", "白天一般道路 30 m 內中位誤差 ≤ 6.5%", get("v2", "day_ca_local", "near", "med_abs_pct"), lambda v: v <= 6.5,
         "5.1", "%", 2),
        ("9", "夜間 30 m 內中位誤差 ≤ 12%", get("v2", "night", "near", "med_abs_pct"), lambda v: v <= 12, "8.3", "%", 2),
    ]
    return [{"item": no, "text": text, "value": None if v is None else round(v, nd), "unit": unit,
             "met": None if v is None else bool(ok(v)), "dev": dev} for no, text, v, ok, dev, unit, nd in spec]


def shifted(P: pd.DataFrame, sens: dict, k: int) -> pd.DataFrame:
    """Scenario k of the config's truth offsets: only the truth distance moves (as the scorer's offset_sensitivity)."""
    off = {c: float(v[k]) for c, v in sens.items() if not c.startswith("_")}
    d = P.d_truth - P.truth_offset_m + P.car.astype(str).map(off)
    if d[P.d_pred.notna()].isna().any():
        raise SystemExit("refused: a car of the pairs has no truth offset scenario")
    return P.assign(d_truth=d)


def per_drive(P: pd.DataFrame, labels: dict) -> list[dict]:
    """Primary group, per drive and leaving one drive out (descriptive)."""
    segs = [s for s, (r, l) in labels.items() if GROUPS[PRIMARY](r, l)]
    q = P[P.segment_id.isin(segs) & P.d_pred.notna()].assign(drive=lambda x: x.segment_id.str.rsplit("_", n=1).str[0])
    out = []
    for dv in sorted({s.rsplit("_", 1)[0] for s in segs}):
        one, rest = dist_numbers(q[q.drive == dv]), dist_numbers(q[q.drive != dv])
        out.append({"drive": dv, "segments": sum(s.rsplit("_", 1)[0] == dv for s in segs),
                    "near_n": one["near"]["n"], "near_med_abs_pct": one["near"]["med_abs_pct"],
                    "mid_n": one["mid"]["n"], "mid_med_abs_pct": one["mid"]["med_abs_pct"],
                    "without_near_med_abs_pct": rest["near"]["med_abs_pct"],
                    "without_mid_med_abs_pct": rest["mid"]["med_abs_pct"]})
    return out


def agree(name: str, mine, scorer, tol: float = 1.5e-4) -> None:
    """tol covers the scorer's rounding (4 decimals; found % has 2)."""
    if (mine is None) != (scorer is None) or (mine is not None and abs(mine - scorer) > tol):
        raise SystemExit(f"refused: {name} here ({mine}) differs from the scorer's ({scorer})")


def render(res: dict) -> str:
    mark = {True: "達到", False: "沒達到", None: "無法判定(沒有讀值)"}
    pv, js = res["provenance"], res["provenance"]["judge"]
    if js["before_truth"]:
        when = (f"判定程式 commit `{js['commit'][:7]}`({js['commit_utc']})早於現存真值檔最早的建立時間"
                f"({js['first_truth_utc']});執行判定時本機 origin/main 已包含這個 commit。")
    else:
        when = (f"⚠ 跑的判定程式不是早於真值 commit 並推上的版本(與 HEAD 相同:{js['committed_as_run']},"
                f"commit {js['commit']},{js['commit_utc']},origin/main 包含:{js['pushed']};"
                f"現存真值最早 {js['first_truth_utc']})。")
    lines = ["# 第 8 包事前預期逐條判定(方法 A)", "",
             f"依登錄 `pipeline/PREREG_comma2k19_chunk8.md` §3.1;評分設定 sha256 `{pv['config_sha256'][:12]}…`,"
             f"封存 `{pv['seal']}`(`{pv['seal_sha256'][:12]}…`)。{when}", "",
             "| 條目 | 預期 | 開發值 | 第 8 包 | 結果 | 用 582 配對 | 結果 |", "|---|---|---|---|---|---|---|"]
    alt = {r["item"]: r for r in res["items_cx582"]}
    for r in res["items"]:
        a = alt.get(r["item"], {})
        val = "—" if r["value"] is None else f"{r['value']} {r['unit']}"
        lines.append(f"| {r['item']} | {r['text']} | {r['dev']} | {val} | {mark[r['met']]} | "
                     f"{'—' if a.get('value') is None else a['value']} | {mark[a.get('met')]} |")
    met = [r["met"] for r in res["items"]]
    lines += ["", f"達到 {met.count(True)} 條、沒達到 {met.count(False)} 條、無法判定 {met.count(None)} 條(共 {len(met)} 條)。",
              "判定用未四捨五入的數字;表上是四捨五入後的值。", ""]
    if pv["scorer_changes_allowed"]:
        lines += [f"⚠ 評分時評分器有本機改動,以 --allow-scorer-changes 照判:{pv['scorer_uncommitted_changes']}", ""]
    lines += ["10–20 m、20–30 m 的公尺誤差與 60–100 m 只由本程式算(評分器沒有這些格);"
              "30 m 內、30–60 m、相對速度、本車速度、找到率、582 與各偏移的合併數字已和評分器核對相同。", ""]
    if pv["v2own"]:
        lines += [f"第 7 條的 v2own 不經評分器的存取檢查(評分器只收有封存的版本):改核對 Vehicle-Distance-Forensics "
                  f"{pv['v2own']['commit']} 推上的雜湊清單({pv['v2own']['files']} 個檔),真值晚於清單。"
                  "v2own 只進方法 A 自己的紀錄,不是共同成績。", ""]
    s = res["outputs"]
    if s["refused"] or s["missing"] or s["invalid"]:
        lines += [f"拒發 {len(s['refused'])} 段、缺 {len(s['missing'])} 段、格式錯誤 {len(s['invalid'])} 段;"
                  "找到率的分母只含有輸出的段(與評分器相同)。", ""]
    lines += ["## 真值偏移敏感度(描述,不改判定;判定照登錄用第二台車 −0.70 m)", "",
              "| 第二台車偏移 | " + " | ".join(DIST_ITEMS) + " |", "|---" * (len(DIST_ITEMS) + 1) + "|"]
    for sc in res["offset_sensitivity"]:
        by = {r["item"]: r for r in sc["items"]}
        lines.append(f"| {sc['offset_m']:+.2f} m | " + " | ".join(
            "—" if by[i]["value"] is None else f"{by[i]['value']}{'' if by[i]['met'] else ' ✗'}" for i in DIST_ITEMS) + " |")
    lines += ["", "✗ = 在這個偏移下沒達到門檻。", "", "## 主要組逐趟(描述,不判定)", "",
              "| 行程 | 段 | 30 m 內筆數 | 30 m 內 % | 30–60 m 筆數 | 30–60 m % | 去掉這趟 30 m 內 % | 去掉這趟 30–60 m % |",
              "|---|---|---|---|---|---|---|---|"]
    for d in res["per_drive_primary"]:
        lines.append(f"| {d['drive']} | {d['segments']} | {d['near_n']} | {d['near_med_abs_pct']} | {d['mid_n']} | "
                     f"{d['mid_med_abs_pct']} | {d['without_near_med_abs_pct']} | {d['without_mid_med_abs_pct']} |")
    meds = [d["near_med_abs_pct"] for d in res["per_drive_primary"] if d["near_med_abs_pct"] is not None]
    lines += ["", f"逐趟 30 m 內中位誤差的中位數:{round(float(np.median(meds)), 2) if meds else '—'}%"
              f"({len(meds)} 趟有 30 m 內讀值;開發值 5.0%)。", "", "## 各組數字(v2)", ""]
    for g, rec in res["groups"]["v2"].items():
        lines.append(f"- {TITLES[g]}:{rec['segments']} 段、{rec['drives']} 趟;30 m 內 {rec['near']['med_abs_pct']}%"
                     f"(偏差 {rec['near']['bias_pct']}%,{rec['near']['n']} 筆),30–60 m {rec['mid']['med_abs_pct']}%,"
                     f"60–100 m {rec['far']['med_abs_pct']}%;相對速 {(rec.get('rel_near') or {}).get('mae')} km/h"
                     f"(全猜 0 {(rec.get('rel_near') or {}).get('guess0')});本車速 {rec['ego']['mae']} km/h、覆蓋 "
                     f"{rec['ego']['coverage_pct']}%;找到率 {rec['found_pct']}%")
    d = res["spot_check"]
    lines += ["", "## 判定表抽查(D9,描述,不改判定)", "",
              f"抽查 {d['sampled']} 段,抽查者的標籤和判定表不同 {d['differ']} 段(`{d['file']}`)。"
              "各條仍照判定表分組判定;下面是不同的段,以及抽查過的段改用抽查者標籤後的各組數字。", "",
              "| # | 段 | 判定表 | 抽查者 | 30 m 內筆數 | 30 m 內 % | 30–60 m 筆數 | 30–60 m % | 本車速 MAE | 覆蓋 % |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for s in d["segments"]:
        lines.append(f"| {s['n']} | {s['segment_id']} | {'/'.join(NAMES[x] for x in s['table'])} | "
                     f"{'/'.join(NAMES[x] for x in s['checker'])} | {s['near_n']} | {s['near_med_abs_pct']} | {s['mid_n']} | "
                     f"{s['mid_med_abs_pct']} | {s['ego']['mae']} | {s['ego']['coverage_pct']} |")
    dp = d["differing_pooled"]
    lines += ["", f"不同的 {d['differ']} 段合併:30 m 內 {dp['near']['med_abs_pct']}%({dp['near']['n']} 筆),"
              f"30–60 m {dp['mid']['med_abs_pct']}%({dp['mid']['n']} 筆);本車速 {dp['ego']['mae']} km/h、覆蓋 "
              f"{dp['ego']['coverage_pct']}%。", "",
              "| 組 | 段數(判定表 → 抽查者) | 30 m 內 % | 30–60 m % | 60–100 m % | 相對速 km/h | 本車速 km/h | 找到率 % |",
              "|---|---|---|---|---|---|---|---|"]
    for g, rec in d["groups_checker_labels"].items():
        t = res["groups"]["v2"][g]
        lines.append(f"| {TITLES[g]} | {t['segments']} → {rec['segments']} | " + " | ".join(
            f"{a} → {b}" for a, b in ((t["near"]["med_abs_pct"], rec["near"]["med_abs_pct"]),
                                       (t["mid"]["med_abs_pct"], rec["mid"]["med_abs_pct"]),
                                       (t["far"]["med_abs_pct"], rec["far"]["med_abs_pct"]),
                                       ((t.get("rel_near") or {}).get("mae"), (rec.get("rel_near") or {}).get("mae")),
                                       (t["ego"]["mae"], rec["ego"]["mae"]), (t["found_pct"], rec["found_pct"]))) + " |")
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--bench", type=Path, required=True, help="the shared repo (has mddbench/, splits/, seals/)")
    ap.add_argument("--results", type=Path, required=True, help="mddbench score --out folder of the sealed v2")
    ap.add_argument("--segments", type=Path, required=True, help="segments root the scorer read")
    ap.add_argument("--truth", type=Path, help="truth root (default <bench>/data/truth)")
    ap.add_argument("--scorer-cwd", type=Path, help="folder the scorer ran in, for relative paths (default --bench)")
    ap.add_argument("--v2own", type=Path, help="v2own predictions; item 7 is not judged without it")
    ap.add_argument("--allow-scorer-changes", action="store_true",
                    help="judge although the scorer ran with local changes in mddbench/, configs/ or splits/ (stated in the output)")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    sys.path.insert(0, str(a.bench))
    from mddbench import formats as F, score as S  # noqa: E402
    truth = a.truth or a.bench / "data" / "truth"
    ids = (a.bench / BATCH).read_text(encoding="utf-8").split()

    def at_run(x: str) -> Path:
        p = Path(x) if Path(x).is_absolute() else (a.scorer_cwd or a.bench) / x
        if not p.exists():
            raise SystemExit(f"refused: {x} from the scorer's provenance is not at {p} (see --scorer-cwd)")
        return p

    res = json.loads((a.results / "results.json").read_text(encoding="utf-8"))
    prov, segs = res["provenance"], res["segments"]
    if prov["config_sha256"] != CONFIG_SHA256 or prov["seal_sha256"] != SEAL_SHA256 \
            or Path(prov["seal_file"] or "").name != SEAL_NAME:
        raise SystemExit("refused: the results are not the sealed v2 scored with the registered config")
    if sha(a.bench / "seals" / SEAL_NAME) != SEAL_SHA256 or sha(at_run(prov["config_file"])) != CONFIG_SHA256:
        raise SystemExit("refused: the seal or the config in the shared repo changed")
    if prov["overridden"] or segs["listed"] != len(ids) or segs.get("split_status") != {"blind": len(ids)}:
        raise SystemExit("refused: the results override the config, do not list the whole batch, "
                         "or were not scored as a blind batch (so the scorer did not check the seal)")
    changes = (prov.get("benchmark_repo") or {}).get("uncommitted_changes")
    scorer_changed = changes is None or bool([c for c in changes if c.split("/")[0] in ("mddbench", "configs", "splits")])
    if scorer_changed and not a.allow_scorer_changes:
        raise SystemExit(f"refused: the scorer ran with local changes or an unknown state: {changes} "
                         "(--allow-scorer-changes judges anyway and says so)")
    cfg, _ = S.load_config(at_run(prov["config_file"]))
    seal = json.loads((a.bench / "seals" / SEAL_NAME).read_text(encoding="utf-8"))
    if sha(a.bench / BATCH) != seal["batch_sha256"]:
        raise SystemExit("refused: the batch list differs from the sealed one")
    v2_root = at_run(res["predictions"])

    labels = {}
    for s in ids:
        if sha(a.segments / s / "segment.json") != seal["segment_json_sha256"].get(s):
            raise SystemExit(f"refused: segment.json of {s} differs from the sealed one")
        seg = F.read_segment(a.segments / s)
        labels[s] = (seg.get("road_class", "unknown"), seg.get("light", "unknown"))
    odd = [s for s, (r, l) in labels.items() if r not in ROADS or l not in LIGHTS]
    counts = {g: sum(pick(*v) for v in labels.values()) for g, pick in GROUPS.items()}
    if odd or counts != COUNTS:
        raise SystemExit(f"refused: labels are not those of the registration ({counts}, unknown labels {odd[:3]})")
    d9 = read_d9(labels)
    built = {s: F.read_truth(truth / s)[0].get("built_utc", "") for s in ids}

    # round_trip: the exact floats the scorer wrote, so truth shifted onto a bin edge falls where it does in the scorer
    P = pd.read_csv(a.results / "pairs.csv", float_precision="round_trip")
    EB = pd.read_csv(a.results / "ego_bins.csv", float_precision="round_trip")
    rows = pd.DataFrame(res["per_segment"]["rows"])
    outputs = {"with_output": segs["with_output"], "refused": segs["refused"],
               "missing": segs["missing"], "invalid": segs["invalid"]}

    # the per-segment function must reproduce the scorer before it is trusted for the two extra readings
    P2, EB2, _, st2 = rescore(S, F, cfg, v2_root, truth, a.segments, ids)
    cols = ["segment_id", "frame_idx", "truth_id", "d_truth", "d_pred", "rel_truth", "rel_pred"]
    same = len(P2) == len(P) and np.allclose(P2[cols[3:]].to_numpy(float), P[cols[3:]].to_numpy(float),
                                             atol=1e-6, equal_nan=True) \
        and (P2[cols[:3]].astype(str).to_numpy() == P[cols[:3]].astype(str).to_numpy()).all() \
        and len(EB2) == len(EB) and np.allclose(EB2[["pred", "truth"]].to_numpy(float),
                                                EB[["pred", "truth"]].to_numpy(float), atol=1e-6, equal_nan=True) \
        and st2["missing"] == list(outputs["missing"]) and sorted(st2["invalid"]) == sorted(outputs["invalid"]) \
        and sorted(st2["refused"]) == sorted(outputs["refused"])
    if not same:
        raise SystemExit("refused: score_segment does not reproduce the scorer's pairs.csv / ego_bins.csv")

    # the formulas here must give the scorer's own pooled numbers
    near = f"near_le_{cfg['near_max_m']:g}m"
    allr = group_numbers(P, EB, rows, labels, nd=False)["all"]
    agree("near median %", allr["near"]["med_abs_pct"], res["distance"][near].get("median_abs_pct"))
    agree("30-60 m median %", allr["mid"]["med_abs_pct"], res["distance"]["by_truth_distance_m"]["30-60"].get("median_abs_pct"))
    agree("near relative speed MAE", (allr.get("rel_near") or {}).get("mae"), res["relative_speed"]["near"].get("mae"))
    agree("found %", allr["found_pct"], res["detection"]["found_pct"], tol=0.006)
    agree("ego per-second MAE", allr["ego"]["mae"], res["ego_speed"]["per_second"].get("mae"))

    (name582, cx582), = [(v["name"], float(v["cx"])) for v in cfg["matching_sensitivity"]]
    cfg582 = dict(cfg, camera_for_matching={**cfg["camera_for_matching"], "cx": cx582, "cx_by_car": {}, "cx_by_route": {}})
    P582, EB582, rows582, _ = rescore(S, F, cfg582, v2_root, truth, a.segments, ids)
    ms = res["matching_sensitivity"][name582]
    a582 = group_numbers(P582, EB582, rows582, labels, nd=False)["all"]
    agree("582 matched", len(P582), ms["matched"])
    agree("582 near median %", a582["near"]["med_abs_pct"], ms["distance"][near].get("median_abs_pct"))

    sens = cfg["truth_dist_offset_sensitivity_m"]
    n_sc = len(next(v for c, v in sens.items() if not c.startswith("_")))
    for k in range(n_sc):
        agree(f"offset scenario {k} near median %", dist_numbers(shifted(P, sens, k), nd=False)["near"]["med_abs_pct"],
              res["distance_offset_sensitivity"][k][near].get("median_abs_pct"))

    G = {"v2": group_numbers(P, EB, rows, labels), "v2_cx582": group_numbers(P582, EB582, rows582, labels)}
    R = {"v2": group_numbers(P, EB, rows, labels, nd=False), "v2own": None,
         "v2_cx582": group_numbers(P582, EB582, rows582, labels, nd=False), "v2own_cx582": None}
    Po = None
    own_check = None
    if a.v2own:
        own_check = check_own(a.v2own, built, ids, a.bench)
        Po, EBo, rowso, st_o = rescore(S, F, cfg, a.v2own, truth, a.segments, ids)
        Po582, EBo582, rowso582, _ = rescore(S, F, cfg582, a.v2own, truth, a.segments, ids)
        G["v2own"] = group_numbers(Po, EBo, rowso, labels)
        G["v2own_cx582"] = group_numbers(Po582, EBo582, rowso582, labels)
        R["v2own"] = group_numbers(Po, EBo, rowso, labels, nd=False)
        R["v2own_cx582"] = group_numbers(Po582, EBo582, rowso582, labels, nd=False)
        own_check["status"] = st_o

    car2 = next(c for c in sens if not c.startswith("_") and c in set(P.car.astype(str)))
    offsets = []
    for k in range(n_sc):
        Rk = {"v2": group_numbers(shifted(P, sens, k), EB, rows, labels, nd=False),
              "v2own": None if Po is None else group_numbers(shifted(Po, sens, k), EBo, rowso, labels, nd=False)}
        offsets.append({"offset_m": float(sens[car2][k]),
                        "items": [r for r in items(Rk, outputs) if r["item"] in DIST_ITEMS]})

    out = {"provenance": {"config_sha256": prov["config_sha256"], "seal": SEAL_NAME, "seal_sha256": SEAL_SHA256,
                          "results": str(a.results), "results_sha256": sha(a.results / "results.json"),
                          "benchmark_commit": (prov.get("benchmark_repo") or {}).get("commit"),
                          "scorer_uncommitted_changes": changes, "scorer_changes_allowed": scorer_changed,
                          "split_sha256_at_scoring": prov["split_sha256"],
                          "judge": judge_state(min(built.values())),
                          "rescore_reproduces_scorer": True, "pooled_numbers_agree_with_scorer": True,
                          "v2own": own_check},
           "outputs": outputs, "groups": G,
           "items": items({"v2": R["v2"], "v2own": R["v2own"]}, outputs),
           "items_cx582": items({"v2": R["v2_cx582"], "v2own": R["v2own_cx582"]}, outputs),
           "offset_sensitivity": offsets, "per_drive_primary": per_drive(P, labels),
           "spot_check": spot_check(P, EB, rows, labels, d9)}
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "judgement.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    (a.out / "judgement.md").write_text(render(out), encoding="utf-8")
    print(render(out))


if __name__ == "__main__":
    main()
