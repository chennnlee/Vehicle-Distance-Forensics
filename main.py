import argparse
import csv
import shutil
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from core.calibration import apply_scale, compute_scale_factor
from core.depth_engine import DepthEngine
from utils.bevheight import BEVHeightConfig, project_depth_to_bevheight, save_bevheight_preview
from utils.ipm_bev import IPMBEVConfig, PseudoPointCloudBEVConfig, save_ipm_bev, save_pointcloud_bev
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


def parse_two_floats(text: str, label: str) -> tuple[float, float]:
    values = parse_float_list(text)
    if values.size != 2:
        raise ValueError(f"{label} 格式需為 min,max")
    return float(values[0]), float(values[1])


def clamp_bbox(bbox: tuple[int, int, int, int], h: int, w: int) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = bbox
    x1 = max(0, min(x1, w - 1))
    x2 = max(1, min(x2, w))
    y1 = max(0, min(y1, h - 1))
    y2 = max(1, min(y2, h))
    if x2 <= x1 or y2 <= y1:
        raise ValueError("--bbox 無效，需滿足 x2>x1 且 y2>y1")
    return x1, y1, x2, y2


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
    parser.add_argument("--encoder", type=str, default="vitl", choices=["vits", "vitb", "vitl", "vitg"])
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
    parser.add_argument("--auto-scale-gt", type=float, default=None, help="參考物真值距離(公尺)，搭配 --bbox 自動估計每張圖尺度")
    parser.add_argument("--save-simplebev", action="store_true", help="把原始影像轉成鳥瞰圖輸出")
    parser.add_argument("--bev-mode", type=str, default="pcd", choices=["ipm", "height", "pcd"], help="BEV 模式：pcd=偽點雲俯視, ipm=原圖鳥瞰, height=深度高度分層")
    parser.add_argument("--bev-output-dir", type=str, default="", help="BEV 輸出目錄；留空時自動放入本次 run 資料夾")
    parser.add_argument("--bev-x-range", type=str, default="-20,20", help="BEV 左右範圍，格式: min,max，單位公尺")
    parser.add_argument("--bev-z-range", type=str, default="0,60", help="BEV 前方範圍，格式: min,max，單位公尺")
    parser.add_argument("--bev-y-range", type=str, default="-12,12", help="IPM 左右範圍，格式: min,max，單位公尺")
    parser.add_argument("--bev-output-size", type=str, default="800,800", help="IPM 輸出大小，格式: width,height")
    parser.add_argument("--bev-camera-height", type=float, default=1.6, help="相機高度(公尺)，用於 IPM 鳥瞰")
    parser.add_argument("--bev-height-range", type=str, default="-3,5", help="高度範圍，格式: min,max，單位公尺")
    parser.add_argument("--bev-height-bins", type=int, default=8, help="高度分層數量")
    parser.add_argument("--bev-resolution", type=float, default=0.2, help="BEV 每格代表的公尺數")
    parser.add_argument("--bev-fov-deg", type=float, default=90.0, help="投影時假設的水平視角")
    parser.add_argument("--bev-ground-start-ratio", type=float, default=0.45, help="只取影像下半部多少比例後的像素來做 BEV")
    parser.add_argument("--bev-pitch-deg", type=float, default=0.0, help="投影時假設的相機俯仰角，正值代表往下看")
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

    bev_output_dir = None
    if args.save_simplebev:
        default_bev_dir = {
            "ipm": "bev_ipm",
            "height": "bevheight",
            "pcd": "bev_pcd",
        }[args.bev_mode]
        bev_output_dir = Path(args.bev_output_dir) if args.bev_output_dir.strip() else run_dir / default_bev_dir
        if not bev_output_dir.is_absolute():
            bev_output_dir = project_root / bev_output_dir
        bev_output_dir.mkdir(parents=True, exist_ok=True)

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

    if args.save_simplebev and args.model != "metric3d":
        raise ValueError("--save-simplebev 目前只支援 --model metric3d，也就是 Metric3D v2 路線")

    bev_x_range = parse_two_floats(args.bev_x_range, "--bev-x-range")
    bev_z_range = parse_two_floats(args.bev_z_range, "--bev-z-range")
    bev_height_range = parse_two_floats(args.bev_height_range, "--bev-height-range")
    bev_y_range = parse_two_floats(args.bev_y_range, "--bev-y-range")
    bev_output_size_parts = parse_float_list(args.bev_output_size)
    if bev_output_size_parts.size != 2:
        raise ValueError("--bev-output-size 格式需為 width,height")
    bev_output_size = (int(bev_output_size_parts[0]), int(bev_output_size_parts[1]))
    bevheight_config = BEVHeightConfig(
        x_range_m=bev_x_range,
        z_range_m=bev_z_range,
        height_range_m=bev_height_range,
        resolution_m=args.bev_resolution,
        fov_deg=args.bev_fov_deg,
        ground_start_ratio=args.bev_ground_start_ratio,
        pitch_deg=args.bev_pitch_deg,
        num_height_bins=args.bev_height_bins,
    )
    ipm_config = IPMBEVConfig(
        x_range_m=bev_x_range,
        y_range_m=bev_y_range,
        output_size=bev_output_size,
        camera_height_m=args.bev_camera_height,
        pitch_deg=args.bev_pitch_deg,
        fov_deg=args.bev_fov_deg,
        yaw_deg=0.0,
    )
    pointcloud_config = PseudoPointCloudBEVConfig(
        x_range_m=bev_x_range,
        y_range_m=bev_y_range,
        output_size=bev_output_size,
        camera_height_m=args.bev_camera_height,
        pitch_deg=args.bev_pitch_deg,
        fov_deg=args.bev_fov_deg,
        height_range_m=(-20.0, 20.0),
    )

    scale_factor = args.scale_factor
    if args.anchor_pred or args.anchor_gt:
        if not (args.anchor_pred and args.anchor_gt):
            raise ValueError("使用錨點校正時，--anchor-pred 與 --anchor-gt 必須同時提供")
        anchor_pred = parse_float_list(args.anchor_pred)
        anchor_gt = parse_float_list(args.anchor_gt)
        scale_factor = compute_scale_factor(anchor_pred, anchor_gt)

    if args.auto_scale_gt is not None and not args.bbox:
        raise ValueError("使用 --auto-scale-gt 時必須同時提供 --bbox")

    csv_rows: list[dict[str, str | float | int]] = []
    is_batch = image_path.is_dir()

    for image_file in image_files:
        image = cv2.imread(str(image_file))
        if image is None:
            print(f"略過無法讀取影像: {image_file}")
            continue

        depth_raw = engine.infer(image)

        sample_scale_factor = scale_factor
        auto_scale_est = float("nan")
        auto_scale_gt = float("nan")
        auto_scale_enabled = False

        if args.auto_scale_gt is not None:
            h_raw, w_raw = depth_raw.shape
            bbox_raw = parse_bbox(args.bbox)
            x1_raw, y1_raw, x2_raw, y2_raw = clamp_bbox(bbox_raw, h_raw, w_raw)
            ref_roi_raw = depth_raw[y1_raw:y2_raw, x1_raw:x2_raw]
            auto_scale_est = float(np.median(ref_roi_raw))
            if not np.isfinite(auto_scale_est) or auto_scale_est <= 0:
                raise ValueError("參考框估測距離無效，無法自動校正尺度")
            auto_scale_gt = float(args.auto_scale_gt)
            sample_scale_factor = auto_scale_gt / auto_scale_est
            auto_scale_enabled = True

        depth = apply_scale(depth_raw, scale_factor=sample_scale_factor)

        center_y, center_x = depth.shape[0] // 2, depth.shape[1] // 2
        center_depth = float(depth[center_y, center_x])

        roi_median = np.nan
        roi_mean = np.nan
        roi_min = np.nan
        roi_max = np.nan
        bbox_stats_text = ""
        if args.bbox:
            h, w = depth.shape
            bbox = parse_bbox(args.bbox)
            x1, y1, x2, y2 = clamp_bbox(bbox, h, w)

            roi_depth = depth[y1:y2, x1:x2]
            roi_median = float(np.median(roi_depth))
            roi_mean = float(np.mean(roi_depth))
            roi_min = float(np.min(roi_depth))
            roi_max = float(np.max(roi_depth))
            bbox_stats_text = (
                f"目標框: (x1={x1}, y1={y1}, x2={x2}, y2={y2})\n"
                f"框內深度統計 median={roi_median:.6f}, mean={roi_mean:.6f}, min={roi_min:.6f}, max={roi_max:.6f}"
            )
            if auto_scale_enabled:
                bbox_stats_text += (
                    f"\n自動尺度校正: gt={auto_scale_gt:.6f}, est_raw={auto_scale_est:.6f}, s={sample_scale_factor:.6f}"
                )

        bev_output_path = ""
        bev_nonzero_ratio = np.nan
        bev_peak = np.nan
        bev_mean_height = np.nan
        bev_height_bins = np.nan
        bev_ipm_coverage = np.nan
        bev_pcd_coverage = np.nan
        bev_pcd_peak_height = np.nan
        bev_pcd_mean_height = np.nan
        bev_pcd_points = np.nan
        if args.save_simplebev and bev_output_dir is not None:
            if args.bev_mode == "ipm":
                bev_output_path = bev_output_dir / f"{image_file.stem}_bev_ipm.png"
                _, bev_stats = save_ipm_bev(image, bev_output_path, ipm_config)
                bev_ipm_coverage = float(bev_stats["ipm_coverage"])
            elif args.bev_mode == "pcd":
                bev_output_path = bev_output_dir / f"{image_file.stem}_bev_pcd.png"
                _, bev_stats = save_pointcloud_bev(image, depth, bev_output_path, pointcloud_config)
                bev_pcd_coverage = float(bev_stats["pcd_coverage"])
                bev_pcd_peak_height = float(bev_stats["pcd_peak_height_m"])
                bev_pcd_mean_height = float(bev_stats["pcd_mean_height_m"])
                bev_pcd_points = float(bev_stats["pcd_points"])
            else:
                bev_preview, bev_stats = project_depth_to_bevheight(depth, bevheight_config)
                bev_output_path = bev_output_dir / f"{image_file.stem}_bevheight.png"
                save_bevheight_preview(bev_preview, bev_output_path)
                bev_nonzero_ratio = float(bev_stats["bevheight_nonzero_ratio"])
                bev_peak = float(bev_stats["bevheight_peak"])
                bev_mean_height = float(bev_stats["bevheight_mean_height"])
                bev_height_bins = float(bev_stats["bevheight_height_bins"])

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
                "scale_factor": float(sample_scale_factor),
                "center_x": int(center_x),
                "center_y": int(center_y),
                "center_depth": center_depth,
                "roi_median": float(roi_median),
                "roi_mean": float(roi_mean),
                "roi_min": float(roi_min),
                "roi_max": float(roi_max),
                "auto_scale_gt": auto_scale_gt,
                "auto_scale_est_raw": auto_scale_est,
                "auto_scale_enabled": int(auto_scale_enabled),
                "bev_nonzero_ratio": bev_nonzero_ratio,
                "bev_peak": bev_peak,
                "bev_mean_height": bev_mean_height,
                "bev_height_bins": bev_height_bins,
                "bev_ipm_coverage": bev_ipm_coverage,
                "bev_pcd_coverage": bev_pcd_coverage,
                "bev_pcd_peak_height": bev_pcd_peak_height,
                "bev_pcd_mean_height": bev_pcd_mean_height,
                "bev_pcd_points": bev_pcd_points,
                "bev_output": str(bev_output_path),
                "output": str(output_path),
            }
        )

        print(f"影像: {image_file.name}")
        print(f"中心點座標: (x={center_x}, y={center_y})")
        print(f"套用尺度係數: {sample_scale_factor:.6f}")
        print(f"中心點深度值: {center_depth:.6f}")
        if bbox_stats_text:
            print(bbox_stats_text)
        if args.save_simplebev and bev_output_path:
            if args.bev_mode == "ipm":
                print(f"IPM 鳥瞰圖輸出: {bev_output_path} (coverage={bev_ipm_coverage:.6f})")
            elif args.bev_mode == "pcd":
                print(
                    f"偽點雲 BEV 輸出: {bev_output_path} "
                    f"(coverage={bev_pcd_coverage:.6f}, points={bev_pcd_points:.0f}, peak_height={bev_pcd_peak_height:.3f}m, mean_height={bev_pcd_mean_height:.3f}m)"
                )
            else:
                print(
                    f"BEVHeight 輸出: {bev_output_path} "
                    f"(nonzero_ratio={bev_nonzero_ratio:.6f}, peak={bev_peak:.6f}, mean_height={bev_mean_height:.6f}, bins={bev_height_bins:.0f})"
                )
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
                "auto_scale_gt",
                "auto_scale_est_raw",
                "auto_scale_enabled",
                "bev_nonzero_ratio",
                "bev_peak",
                "bev_mean_height",
                "bev_height_bins",
                "bev_ipm_coverage",
                "bev_pcd_coverage",
                "bev_pcd_peak_height",
                "bev_pcd_mean_height",
                "bev_pcd_points",
                "bev_output",
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
