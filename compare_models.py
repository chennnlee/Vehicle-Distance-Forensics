import argparse
import csv
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def run_main(project_root: Path, args_list: list[str]) -> None:
    command = [sys.executable, "main.py", *args_list]
    subprocess.run(command, cwd=project_root, check=True)


def read_csv_rows(csv_path: Path) -> list[dict[str, str]]:
    with open(csv_path, "r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def write_csv_rows(csv_path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def create_run_dir(project_root: Path, run_name: str) -> Path:
    runs_root = project_root / "data" / "output" / "runs"
    runs_root.mkdir(parents=True, exist_ok=True)
    if run_name.strip():
        run_dir = runs_root / run_name.strip()
    else:
        run_dir = runs_root / datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)

    latest_file = project_root / "data" / "output" / "latest_run.txt"
    latest_file.parent.mkdir(parents=True, exist_ok=True)
    latest_file.write_text(str(run_dir), encoding="utf-8")
    return run_dir


def prune_old_runs(project_root: Path, keep_runs: int) -> None:
    if keep_runs <= 0:
        return
    runs_root = project_root / "data" / "output" / "runs"
    if not runs_root.exists():
        return
    run_dirs = [p for p in runs_root.iterdir() if p.is_dir()]
    run_dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    for old_dir in run_dirs[keep_runs:]:
        shutil.rmtree(old_dir, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run DA-V2, UniDepth-V2, Metric3D and export merged comparison CSV.")
    parser.add_argument("--img-path", type=str, default="data/input", help="Single image path or image directory")
    parser.add_argument("--bbox", type=str, default="", help="ROI bbox: x1,y1,x2,y2")
    parser.add_argument("--input-size", type=int, default=518)
    parser.add_argument("--encoder", type=str, default="vits", choices=["vits", "vitb", "vitl", "vitg"])
    parser.add_argument("--unidepth-backbone", type=str, default="vits14", choices=["vits14", "vitb14", "vitl14"])
    parser.add_argument("--metric3d-variant", type=str, default="vit_large", choices=["vit_small", "vit_large", "vit_giant2"])
    parser.add_argument("--scale-factor", type=float, default=1.0)
    parser.add_argument("--anchor-pred", type=str, default="")
    parser.add_argument("--anchor-gt", type=str, default="")
    parser.add_argument("--run-name", type=str, default="", help="run 資料夾名稱；留空自動時間戳")
    parser.add_argument("--keep-runs", type=int, default=10, help="最多保留最近 N 個 run")
    parser.add_argument("--out-dir", type=str, default="", help="比較輸出目錄；留空時使用本次 run/compare")
    parser.add_argument("--merged-csv", type=str, default="", help="合併 CSV 路徑；留空時使用本次 run/compare")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent
    run_dir = create_run_dir(project_root, args.run_name)

    if args.out_dir.strip():
        out_dir = Path(args.out_dir)
        if not out_dir.is_absolute():
            out_dir = project_root / out_dir
    else:
        out_dir = run_dir / "compare"
    out_dir.mkdir(parents=True, exist_ok=True)

    da_csv = out_dir / "depth_stats_da2.csv"
    ud_csv = out_dir / "depth_stats_ud2.csv"
    m3_csv = out_dir / "depth_stats_metric3d.csv"

    common = [
        "--img-path",
        args.img_path,
        "--bbox",
        args.bbox,
        "--input-size",
        str(args.input_size),
        "--scale-factor",
        str(args.scale_factor),
        "--anchor-pred",
        args.anchor_pred,
        "--anchor-gt",
        args.anchor_gt,
    ]

    run_main(
        project_root,
        [
            "--model",
            "depth_anything_v2",
            "--encoder",
            args.encoder,
            "--run-dir",
            str(run_dir),
            "--no-update-latest",
            "--out-path",
            str(out_dir / "da2"),
            "--csv-path",
            str(da_csv),
            *common,
        ],
    )

    run_main(
        project_root,
        [
            "--model",
            "unidepth_v2",
            "--unidepth-backbone",
            args.unidepth_backbone,
            "--run-dir",
            str(run_dir),
            "--no-update-latest",
            "--out-path",
            str(out_dir / "ud2"),
            "--csv-path",
            str(ud_csv),
            *common,
        ],
    )

    run_main(
        project_root,
        [
            "--model",
            "metric3d",
            "--metric3d-variant",
            args.metric3d_variant,
            "--run-dir",
            str(run_dir),
            "--no-update-latest",
            "--out-path",
            str(out_dir / "metric3d"),
            "--csv-path",
            str(m3_csv),
            *common,
        ],
    )

    da_rows = read_csv_rows(da_csv)
    ud_rows = read_csv_rows(ud_csv)
    m3_rows = read_csv_rows(m3_csv)
    ud_by_image = {row["image"]: row for row in ud_rows}
    m3_by_image = {row["image"]: row for row in m3_rows}

    merged_rows: list[dict[str, str]] = []
    for da in da_rows:
        image = da["image"]
        ud = ud_by_image.get(image)
        m3 = m3_by_image.get(image)
        if ud is None or m3 is None:
            continue

        da_center = float(da["center_depth"])
        ud_center = float(ud["center_depth"])
        m3_center = float(m3["center_depth"])
        da_roi = da["roi_median"]
        ud_roi = ud["roi_median"]
        m3_roi = m3["roi_median"]

        merged_rows.append(
            {
                "image": image,
                "scale_factor": da["scale_factor"],
                "da_center_depth": da["center_depth"],
                "ud_center_depth": ud["center_depth"],
                "m3_center_depth": m3["center_depth"],
                "da_ud_abs_diff": f"{abs(da_center - ud_center):.6f}",
                "da_m3_abs_diff": f"{abs(da_center - m3_center):.6f}",
                "ud_m3_abs_diff": f"{abs(ud_center - m3_center):.6f}",
                "da_roi_median": da_roi,
                "ud_roi_median": ud_roi,
                "m3_roi_median": m3_roi,
                "da_output": da["output"],
                "ud_output": ud["output"],
                "m3_output": m3["output"],
            }
        )

    if args.merged_csv.strip():
        merged_csv = Path(args.merged_csv)
        if not merged_csv.is_absolute():
            merged_csv = project_root / merged_csv
    else:
        merged_csv = out_dir / "merged_compare.csv"

    fieldnames = [
        "image",
        "scale_factor",
        "da_center_depth",
        "ud_center_depth",
        "m3_center_depth",
        "da_ud_abs_diff",
        "da_m3_abs_diff",
        "ud_m3_abs_diff",
        "da_roi_median",
        "ud_roi_median",
        "m3_roi_median",
        "da_output",
        "ud_output",
        "m3_output",
    ]
    write_csv_rows(merged_csv, merged_rows, fieldnames)

    print(f"DA2 CSV: {da_csv}")
    print(f"UD2 CSV: {ud_csv}")
    print(f"M3  CSV: {m3_csv}")
    print(f"Merged CSV: {merged_csv}")
    print(f"Merged rows: {len(merged_rows)}")
    print(f"本次 run 目錄: {run_dir}")

    latest_file = project_root / "data" / "output" / "latest_run.txt"
    latest_file.parent.mkdir(parents=True, exist_ok=True)
    latest_file.write_text(str(run_dir), encoding="utf-8")

    latest_summary = project_root / "data" / "output" / "summary_latest.csv"
    latest_summary.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(merged_csv, latest_summary)

    prune_old_runs(project_root, args.keep_runs)


if __name__ == "__main__":
    main()
