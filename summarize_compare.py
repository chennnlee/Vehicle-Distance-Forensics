import argparse
import csv
import shutil
from pathlib import Path


def to_float(row: dict[str, str], key: str) -> float:
    value = row.get(key, "")
    try:
        return float(value)
    except ValueError:
        return float("nan")


def pick_diff(row: dict[str, str]) -> float:
    if "da_ud_abs_diff" in row:
        return to_float(row, "da_ud_abs_diff")
    return to_float(row, "center_depth_abs_diff")


def get_latest_run_dir(project_root: Path) -> Path:
    latest_file = project_root / "data" / "output" / "latest_run.txt"
    if not latest_file.exists():
        raise FileNotFoundError("找不到 latest_run.txt，請先執行 main.py 或 compare_models.py")

    run_dir = Path(latest_file.read_text(encoding="utf-8").strip())
    if not run_dir.exists():
        raise FileNotFoundError(f"latest_run.txt 指向不存在路徑: {run_dir}")
    return run_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize merged model comparison CSV.")
    parser.add_argument("--merged-csv", type=str, default="", help="留空時讀取 latest run 的 compare/merged_compare.csv")
    parser.add_argument("--report-path", type=str, default="", help="留空時輸出到 latest run 的 compare/summary_report.txt")
    parser.add_argument("--markdown-path", type=str, default="", help="留空時輸出到 latest run 的 compare/summary_report.md")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent
    latest_run = get_latest_run_dir(project_root)

    if args.merged_csv.strip():
        merged_csv = Path(args.merged_csv)
        if not merged_csv.is_absolute():
            merged_csv = project_root / merged_csv
    else:
        merged_csv = latest_run / "compare" / "merged_compare.csv"

    if args.report_path.strip():
        report_path = Path(args.report_path)
        if not report_path.is_absolute():
            report_path = project_root / report_path
    else:
        report_path = latest_run / "compare" / "summary_report.txt"
    report_path.parent.mkdir(parents=True, exist_ok=True)

    if args.markdown_path.strip():
        markdown_path = Path(args.markdown_path)
        if not markdown_path.is_absolute():
            markdown_path = project_root / markdown_path
    else:
        markdown_path = latest_run / "compare" / "summary_report.md"
    markdown_path.parent.mkdir(parents=True, exist_ok=True)

    if not merged_csv.exists():
        raise FileNotFoundError(f"找不到比較 CSV: {merged_csv}")

    with open(merged_csv, "r", encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))

    if not rows:
        report_text = "沒有可分析的資料列，請先執行 compare_models.py 產生 merged CSV。\n"
        report_path.write_text(report_text, encoding="utf-8")
        markdown_path.write_text("# 比較摘要\n\n沒有可分析的資料列。\n", encoding="utf-8")
        print(report_text.strip())
        print(f"報告已輸出: {report_path}")
        print(f"Markdown 已輸出: {markdown_path}")
        return

    abs_diffs = [pick_diff(row) for row in rows]
    da_centers = [to_float(row, "da_center_depth") for row in rows]
    ud_centers = [to_float(row, "ud_center_depth") for row in rows]
    has_m3 = "m3_center_depth" in rows[0]
    m3_centers = [to_float(row, "m3_center_depth") for row in rows] if has_m3 else []

    mean_abs_diff = sum(abs_diffs) / len(abs_diffs)
    min_abs_diff = min(abs_diffs)
    max_abs_diff = max(abs_diffs)

    # 這裡只做深度量值比較，不代表絕對精度優劣。
    da_lower_count = sum(1 for da, ud in zip(da_centers, ud_centers) if da < ud)
    ud_lower_count = len(rows) - da_lower_count

    lines = [
        "Vehicle-Distance-Forensics 比較摘要",
        "================================",
        f"資料筆數: {len(rows)}",
        f"中心深度絕對差 平均值: {mean_abs_diff:.6f}",
        f"中心深度絕對差 最小值: {min_abs_diff:.6f}",
        f"中心深度絕對差 最大值: {max_abs_diff:.6f}",
        "",
        "中心深度大小關係（僅供尺度觀察）",
        f"- DA2 < UD2 次數: {da_lower_count}",
        f"- UD2 <= DA2 次數: {ud_lower_count}",
        "",
        "逐筆結果",
    ]

    if has_m3:
        da_m3 = [to_float(row, "da_m3_abs_diff") for row in rows]
        ud_m3 = [to_float(row, "ud_m3_abs_diff") for row in rows]
        lines.extend(
            [
                "",
                f"DA2-M3 絕對差平均值: {sum(da_m3) / len(da_m3):.6f}",
                f"UD2-M3 絕對差平均值: {sum(ud_m3) / len(ud_m3):.6f}",
            ]
        )

    for idx, row in enumerate(rows, start=1):
        if has_m3:
            lines.append(
                f"{idx}. image={row['image']} | da_center={row['da_center_depth']} | "
                f"ud_center={row['ud_center_depth']} | m3_center={row['m3_center_depth']} | "
                f"da_ud={row['da_ud_abs_diff']} | da_m3={row['da_m3_abs_diff']} | ud_m3={row['ud_m3_abs_diff']}"
            )
        else:
            lines.append(
                f"{idx}. image={row['image']} | da_center={row['da_center_depth']} | "
                f"ud_center={row['ud_center_depth']} | abs_diff={row['center_depth_abs_diff']}"
            )

    report_text = "\n".join(lines) + "\n"
    report_path.write_text(report_text, encoding="utf-8")

    md_lines = [
        "# Vehicle-Distance-Forensics 比較摘要",
        "",
        f"- 資料筆數: {len(rows)}",
        f"- 中心深度絕對差平均值: {mean_abs_diff:.6f}",
        f"- 中心深度絕對差最小值: {min_abs_diff:.6f}",
        f"- 中心深度絕對差最大值: {max_abs_diff:.6f}",
        "",
        "## 中心深度大小關係（僅供尺度觀察）",
        f"- DA2 < UD2 次數: {da_lower_count}",
        f"- UD2 <= DA2 次數: {ud_lower_count}",
    ]

    if has_m3:
        da_m3 = [to_float(row, "da_m3_abs_diff") for row in rows]
        ud_m3 = [to_float(row, "ud_m3_abs_diff") for row in rows]
        md_lines.extend(
            [
                f"- DA2-M3 絕對差平均值: {sum(da_m3) / len(da_m3):.6f}",
                f"- UD2-M3 絕對差平均值: {sum(ud_m3) / len(ud_m3):.6f}",
            ]
        )

    md_lines.extend(
        [
            "",
            "## 逐筆結果",
            "",
        ]
    )

    if has_m3:
        md_lines.extend(
            [
                "| # | image | da_center | ud_center | m3_center | da_ud | da_m3 | ud_m3 |",
                "|---|---|---:|---:|---:|---:|---:|---:|",
            ]
        )
    else:
        md_lines.extend(
            [
                "| # | image | da_center | ud_center | abs_diff |",
                "|---|---|---:|---:|---:|",
            ]
        )

    for idx, row in enumerate(rows, start=1):
        if has_m3:
            md_lines.append(
                f"| {idx} | {row['image']} | {row['da_center_depth']} | {row['ud_center_depth']} | {row['m3_center_depth']} | {row['da_ud_abs_diff']} | {row['da_m3_abs_diff']} | {row['ud_m3_abs_diff']} |"
            )
        else:
            md_lines.append(
                f"| {idx} | {row['image']} | {row['da_center_depth']} | {row['ud_center_depth']} | {row['center_depth_abs_diff']} |"
            )

    markdown_text = "\n".join(md_lines) + "\n"
    markdown_path.write_text(markdown_text, encoding="utf-8")
    print(f"報告已輸出: {report_path}")
    print(f"Markdown 已輸出: {markdown_path}")

    latest_txt = project_root / "data" / "output" / "summary_latest.txt"
    latest_md = project_root / "data" / "output" / "summary_latest.md"
    latest_txt.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(report_path, latest_txt)
    shutil.copy2(markdown_path, latest_md)
    print(f"Latest 摘要（txt）: {latest_txt}")
    print(f"Latest 摘要（md）: {latest_md}")


if __name__ == "__main__":
    main()
