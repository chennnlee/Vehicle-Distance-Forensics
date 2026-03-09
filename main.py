import argparse
from pathlib import Path

import cv2

from core.calibration import apply_scale
from core.depth_engine import DepthEngine
from core.geometry import CameraIntrinsics, depth_to_point_cloud, to_bev
from utils.visualizer import save_depth_colormap


def main() -> None:
    parser = argparse.ArgumentParser(description="Vehicle Distance Forensics MVP")
    parser.add_argument("--model", type=str, default="depth_anything_v2", choices=["depth_anything_v2", "unidepth_v2"])
    parser.add_argument("--img-path", type=str, default="data/input/sample.jpg")
    parser.add_argument("--encoder", type=str, default="vits", choices=["vits", "vitb", "vitl", "vitg"])
    parser.add_argument("--unidepth-backbone", type=str, default="vits14", choices=["vits14", "vitb14", "vitl14"])
    parser.add_argument("--input-size", type=int, default=518)
    parser.add_argument("--out-path", type=str, default="data/output/depth_vis.png")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent
    image_path = Path(args.img_path)
    if not image_path.is_absolute():
        image_path = project_root / image_path

    output_path = Path(args.out_path)
    if not output_path.is_absolute():
        output_path = project_root / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not image_path.exists():
        print(f"請先放一張測試圖到: {image_path}")
        return

    image = cv2.imread(str(image_path))
    if image is None:
        print("讀取影像失敗，請確認檔案格式。")
        return

    engine = DepthEngine(project_root / "checkpoints")
    engine.load_model(
        args.model,
        encoder=args.encoder,
        unidepth_backbone=args.unidepth_backbone,
        input_size=args.input_size,
    )

    depth = engine.infer(image)
    depth = apply_scale(depth, scale_factor=1.0)

    intrinsics = CameraIntrinsics(fx=1000.0, fy=1000.0, cx=image.shape[1] / 2, cy=image.shape[0] / 2)
    points_xyz = depth_to_point_cloud(depth, intrinsics)
    _points_bev = to_bev(points_xyz)

    save_depth_colormap(depth, output_path)

    print(f"完成推論，已輸出深度圖: {output_path}")


if __name__ == "__main__":
    main()
