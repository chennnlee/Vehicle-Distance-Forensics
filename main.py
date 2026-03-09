import argparse
import csv
import shutil
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from core.calibration import apply_scale, compute_scale_factor
from core.depth_engine import DepthEngine
from core.geometry import CameraIntrinsics, depth_to_point_cloud, to_bev
from utils.visualizer import save_depth_colormap


def parse_bbox(bbox_text: str) -> tuple[int, int, int, int]:
    parts = [p.strip() for p in bbox_text.split(",")]
    if len(parts) != 4:
        raise ValueError("--bbox 格式需為 x1,y1,x2,y2")
    x1, y1, x2, y2 = (int(v) for v in parts)
    return x1, y1, x2, y2


def parse_float_list(text: str) -> np.ndarray:
    parts = [p.strip() for p in text.split(",") if p.strip()]
    if not parts:
        raise ValueError("清單不可為空")
    return np.asarray([float(v) for v in parts], dtype=np.float32)


def collect_images(image_path: Path) -> list[Path]:
    if image_path.is_file():
        return [image_path]

    if image_path.is_dir():
        exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
        return sorted([p for p in image_path.rglob("*") if p.suffix.lower() in exts])

    return []


def create_run_dir(project_root: Path, run_name: str, run_dir_arg: str, update_latest: bool) -> Path:
    runs_root = project_root / "data" / "output" / "runs"
    runs_root.mkdir(parents=True, exist_ok=True)

    if run_dir_arg.strip():
        run_dir = Path(run_dir_arg)
        if not run_dir.is_absolute():
            run_dir = project_root / run_dir
    elif run_name.strip():
        run_dir = runs_root / run_name.strip()
    else:
        run_dir = runs_root / datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)

    if update_latest:
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
    parser = argparse.ArgumentParser(description="Vehicle Distance Forensics MVP")
    parser.add_argument("--model", type=str, default="depth_anything_v2", choices=["depth_anything_v2", "unidepth_v2", "metric3d"])
    parser.add_argument("--img-path", type=str, default="data/input/sample.jpg")
    parser.add_argument("--encoder", type=str, default="vits", choices=["vits", "vitb", "vitl", "vitg"])
    parser.add_argument("--unidepth-backbone", type=str, default="vits14", choices=["vits14", "vitb14", "vitl14"])
    parser.add_argument("--metric3d-variant", type=str, default="vit_large", choices=["vit_small", "vit_large", "vit_giant2"])
    parser.add_argument("--input-size", type=int, default=518)
    parser.add_argument("--out-path", type=str, default="", help="輸出圖路徑；留空時自動放入本次 run 資料夾")
    parser.add_argument("--csv-path", type=str, default="", help="CSV 路徑；留空時自動放入本次 run 資料夾")
    parser.add_argument("--run-name", type=str, default="", help="run 資料夾名稱；留空自動用時間戳")
    parser.add_argument("--run-dir", type=str, default="", help="直接指定 run 目錄路徑")
    parser.add_argument("--keep-runs", type=int, default=10, help="最多保留最近 N 個 run 資料夾")
    parser.add_argument("--no-update-latest", action="store_true", help="不更新 latest_run.txt")
    parser.add_argument("--bbox", type=str, default="", help="目標框，格式: x1,y1,x2,y2")
    parser.add_argument("--scale-factor", type=float, default=1.0, help="固定尺度係數")
    parser.add_argument("--anchor-pred", type=str, default="", help="預測錨點距離清單，例: 0.52,0.81")
    parser.add_argument("--anchor-gt", type=str, default="", help="真實錨點距離清單，例: 5.0,8.0")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent
    image_path = Path(args.img_path)
    if not image_path.is_absolute():
        image_path = project_root / image_path

    run_dir = create_run_dir(project_root, args.run_name, args.run_dir, not args.no_update_latest)

    if args.out_path.strip():
        output_path_arg = Path(args.out_path)
        if not output_path_arg.is_absolute():
            output_path_arg = project_root / output_path_arg
    else:
        output_path_arg = run_dir / ("images" if image_path.is_dir() else "depth_vis.png")

    if args.csv_path.strip():
        csv_path = Path(args.csv_path)
        if not csv_path.is_absolute():
            csv_path = project_root / csv_path
    else:
        csv_path = run_dir / "depth_stats.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    if not image_path.exists():
        print(f"找不到輸入路徑: {image_path}")
        return

    image_files = collect_images(image_path)
    if not image_files:
        print(f"在此路徑找不到可用影像: {image_path}")
        return

    engine = DepthEngine(project_root / "checkpoints")
    engine.load_model(
        args.model,
        encoder=args.encoder,
        unidepth_backbone=args.unidepth_backbone,
        metric3d_variant=args.metric3d_variant,
        input_size=args.input_size,
    )

    scale_factor = args.scale_factor
    if args.anchor_pred or args.anchor_gt:
        if not (args.anchor_pred and args.anchor_gt):
            raise ValueError("使用錨點校正時，--anchor-pred 與 --anchor-gt 必須同時提供")
        anchor_pred = parse_float_list(args.anchor_pred)
        anchor_gt = parse_float_list(args.anchor_gt)
        scale_factor = compute_scale_factor(anchor_pred, anchor_gt)

    csv_rows: list[dict[str, str | float | int]] = []
    is_batch = image_path.is_dir()

    for image_file in image_files:
        image = cv2.imread(str(image_file))
        if image is None:
            print(f"略過無法讀取影像: {image_file}")
            continue

        depth_raw = engine.infer(image)
        depth = apply_scale(depth_raw, scale_factor=scale_factor)

        center_y, center_x = depth.shape[0] // 2, depth.shape[1] // 2
        center_depth = float(depth[center_y, center_x])

        roi_median = np.nan
        roi_mean = np.nan
        roi_min = np.nan
        roi_max = np.nan
        bbox_stats_text = ""
        if args.bbox:
            x1, y1, x2, y2 = parse_bbox(args.bbox)
            h, w = depth.shape
            x1 = max(0, min(x1, w - 1))
            x2 = max(1, min(x2, w))
            y1 = max(0, min(y1, h - 1))
            y2 = max(1, min(y2, h))
            if x2 <= x1 or y2 <= y1:
                raise ValueError("--bbox 無效，需滿足 x2>x1 且 y2>y1")

            roi_depth = depth[y1:y2, x1:x2]
            roi_median = float(np.median(roi_depth))
            roi_mean = float(np.mean(roi_depth))
            roi_min = float(np.min(roi_depth))
            roi_max = float(np.max(roi_depth))
            bbox_stats_text = (
                f"目標框: (x1={x1}, y1={y1}, x2={x2}, y2={y2})\n"
                f"框內深度統計 median={roi_median:.6f}, mean={roi_mean:.6f}, min={roi_min:.6f}, max={roi_max:.6f}"
            )

        intrinsics = CameraIntrinsics(fx=1000.0, fy=1000.0, cx=image.shape[1] / 2, cy=image.shape[0] / 2)
        points_xyz = depth_to_point_cloud(depth, intrinsics)
        _points_bev = to_bev(points_xyz)

        if is_batch:
            output_path = output_path_arg / f"{image_file.stem}_depth.png"
        else:
            output_path = output_path_arg
        output_path.parent.mkdir(parents=True, exist_ok=True)
        save_depth_colormap(depth, output_path)

        csv_rows.append(
            {
                "image": str(image_file),
                "model": args.model,
                "scale_factor": float(scale_factor),
                "center_x": int(center_x),
                "center_y": int(center_y),
                "center_depth": center_depth,
                "roi_median": float(roi_median),
                "roi_mean": float(roi_mean),
                "roi_min": float(roi_min),
                "roi_max": float(roi_max),
                "output": str(output_path),
            }
        )

        print(f"影像: {image_file.name}")
        print(f"中心點座標: (x={center_x}, y={center_y})")
        print(f"套用尺度係數: {scale_factor:.6f}")
        print(f"中心點深度值: {center_depth:.6f}")
        if bbox_stats_text:
            print(bbox_stats_text)
        print(f"完成推論，已輸出深度圖: {output_path}")

    with open(csv_path, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "image",
                "model",
                "scale_factor",
                "center_x",
                "center_y",
                "center_depth",
                "roi_median",
                "roi_mean",
                "roi_min",
                "roi_max",
                "output",
            ],
        )
        writer.writeheader()
        writer.writerows(csv_rows)
    print(f"已輸出統計 CSV: {csv_path}")
    print(f"本次 run 目錄: {run_dir}")

    prune_old_runs(project_root, args.keep_runs)


if __name__ == "__main__":
    main()
