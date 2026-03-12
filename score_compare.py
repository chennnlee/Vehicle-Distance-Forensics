import argparse
import csv
from pathlib import Path

import numpy as np


def get_latest_run_dir(project_root: Path) -> Path:
    latest_file = project_root / "data" / "output" / "latest_run.txt"
    if not latest_file.exists():
        raise FileNotFoundError("找不到 latest_run.txt，請先執行 compare_models.py")

    run_dir = Path(latest_file.read_text(encoding="utf-8").strip())
    if not run_dir.exists():
        raise FileNotFoundError(f"latest_run.txt 指向不存在路徑: {run_dir}")
    return run_dir


def to_float(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def metric_candidates(model_prefix: str, prefer_bev_roi: bool) -> list[str]:
    candidates = []
    if prefer_bev_roi:
        candidates.append(f"{model_prefix}_bev_roi_median_distance_m")
    candidates.extend(
        [
            f"{model_prefix}_bev_center_distance_m",
            f"{model_prefix}_roi_median",
            f"{model_prefix}_center_depth",
        ]
    )
    return candidates


def finite_array(values: list[float]) -> np.ndarray:
    arr = np.asarray(values, dtype=np.float64)
    return arr[np.isfinite(arr)]


def pick_metric_column_and_values(
    model_prefix: str,
    rows: list[dict[str, str]],
    columns: set[str],
    prefer_bev_roi: bool,
) -> tuple[str, np.ndarray]:
    available = [name for name in metric_candidates(model_prefix, prefer_bev_roi) if name in columns]
    if not available:
        raise KeyError(f"找不到可用欄位: {model_prefix}")

    for col in available:
        vals = finite_array([to_float(r.get(col, "")) for r in rows])
        if vals.size > 0:
            return col, vals

    # 全部欄位都存在但皆為 NaN，回傳第一個欄位與空陣列
    return available[0], np.asarray([], dtype=np.float64)


def main() -> None:
    parser = argparse.ArgumentParser(description="Score model comparison by accuracy, consistency, and stability.")
    parser.add_argument("--merged-csv", type=str, default="", help="留空時讀取 latest run 的 compare/merged_compare.csv")
    parser.add_argument("--gt-distance", type=float, default=None, help="若提供，計算對真值距離的準確性分數")
    parser.add_argument("--prefer-bev-roi", action="store_true", help="優先使用 bev_roi_median_distance_m 欄位作為評分依據")
    parser.add_argument("--output-csv", type=str, default="", help="留空時輸出到 latest run 的 compare/score_summary.csv")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent
    latest_run = get_latest_run_dir(project_root)

    if args.merged_csv.strip():
        merged_csv = Path(args.merged_csv)
        if not merged_csv.is_absolute():
            merged_csv = project_root / merged_csv
    else:
        merged_csv = latest_run / "compare" / "merged_compare.csv"

    if not merged_csv.exists():
        raise FileNotFoundError(f"找不到 merged CSV: {merged_csv}")

    if args.output_csv.strip():
        output_csv = Path(args.output_csv)
        if not output_csv.is_absolute():
            output_csv = project_root / output_csv
    else:
        output_csv = latest_run / "compare" / "score_summary.csv"
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    with open(merged_csv, "r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        raise ValueError("merged CSV 無資料列")

    columns = set(rows[0].keys())
    model_prefixes = ["da", "ud", "m3"]
    metric_cols: dict[str, str] = {}
    metrics: dict[str, np.ndarray] = {}
    for m in model_prefixes:
        col, vals = pick_metric_column_and_values(m, rows, columns, args.prefer_bev_roi)
        metric_cols[m] = col
        metrics[m] = vals

    valid_models = [m for m in model_prefixes if metrics[m].size > 0]
    if not valid_models:
        raise ValueError("沒有可用數值欄位可評分")

    all_values = np.concatenate([metrics[m] for m in valid_models])
    ref_scale = float(np.nanmedian(all_values)) if np.isfinite(all_values).any() else 1.0
    if args.gt_distance is not None and args.gt_distance > 0:
        ref_scale = float(args.gt_distance)
    ref_scale = max(ref_scale, 1e-6)

    # Consistency: mean pairwise absolute difference on chosen metric.
    pair_diffs: list[float] = []
    for r in rows:
        vals = []
        for m in valid_models:
            v = to_float(r.get(metric_cols[m], ""))
            if np.isfinite(v):
                vals.append(v)
        if len(vals) < 2:
            continue
        for i in range(len(vals)):
            for j in range(i + 1, len(vals)):
                pair_diffs.append(abs(vals[i] - vals[j]))
    consistency_abs = float(np.mean(pair_diffs)) if pair_diffs else float("nan")
    consistency_score = float(max(0.0, 100.0 * (1.0 - (consistency_abs / ref_scale)))) if np.isfinite(consistency_abs) else float("nan")

    summary_rows: list[dict[str, str]] = []
    for m in valid_models:
        vals = metrics[m]
        mean_val = float(np.mean(vals))
        std_val = float(np.std(vals))

        # Accuracy: needs gt-distance
        if args.gt_distance is not None and args.gt_distance > 0:
            mape = float(np.mean(np.abs(vals - args.gt_distance) / args.gt_distance))
            accuracy_score = float(max(0.0, 100.0 * (1.0 - mape)))
            mae = float(np.mean(np.abs(vals - args.gt_distance)))
        else:
            mape = float("nan")
            accuracy_score = float("nan")
            mae = float("nan")

        # Stability: lower coefficient of variation is better.
        if vals.size >= 2 and abs(mean_val) > 1e-9:
            cv = std_val / abs(mean_val)
            stability_score = float(max(0.0, 100.0 * (1.0 - cv)))
        elif vals.size == 1:
            cv = 0.0
            stability_score = 100.0
        else:
            cv = float("nan")
            stability_score = float("nan")

        # Overall: average of available scores.
        score_list = [s for s in [accuracy_score, consistency_score, stability_score] if np.isfinite(s)]
        overall = float(np.mean(score_list)) if score_list else float("nan")

        summary_rows.append(
            {
                "model": m,
                "metric_column": metric_cols[m],
                "count": str(vals.size),
                "mean_distance": f"{mean_val:.6f}",
                "std_distance": f"{std_val:.6f}",
                "mae_to_gt": f"{mae:.6f}" if np.isfinite(mae) else "",
                "mape_to_gt": f"{mape:.6f}" if np.isfinite(mape) else "",
                "accuracy_score_100": f"{accuracy_score:.2f}" if np.isfinite(accuracy_score) else "",
                "consistency_abs_diff": f"{consistency_abs:.6f}" if np.isfinite(consistency_abs) else "",
                "consistency_score_100": f"{consistency_score:.2f}" if np.isfinite(consistency_score) else "",
                "stability_cv": f"{cv:.6f}" if np.isfinite(cv) else "",
                "stability_score_100": f"{stability_score:.2f}" if np.isfinite(stability_score) else "",
                "overall_score_100": f"{overall:.2f}" if np.isfinite(overall) else "",
            }
        )

    summary_rows.sort(key=lambda r: float(r["overall_score_100"]) if r["overall_score_100"] else -1.0, reverse=True)

    fieldnames = [
        "model",
        "metric_column",
        "count",
        "mean_distance",
        "std_distance",
        "mae_to_gt",
        "mape_to_gt",
        "accuracy_score_100",
        "consistency_abs_diff",
        "consistency_score_100",
        "stability_cv",
        "stability_score_100",
        "overall_score_100",
    ]
    with open(output_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(summary_rows)

    print(f"Merged CSV: {merged_csv}")
    print(f"Score CSV : {output_csv}")
    print("Ranking:")
    for i, row in enumerate(summary_rows, start=1):
        print(
            f"{i}. {row['model']} | overall={row['overall_score_100']} | "
            f"acc={row['accuracy_score_100'] or 'NA'} | "
            f"cons={row['consistency_score_100'] or 'NA'} | "
            f"stab={row['stability_score_100'] or 'NA'}"
        )


if __name__ == "__main__":
    main()
