from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}


def collect_images(input_path: Path) -> list[Path]:
    if input_path.is_file():
        return [input_path]
    if input_path.is_dir():
        return sorted(
            path
            for path in input_path.rglob("*")
            if path.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS and path.name.endswith("_bev.png")
        )
    raise FileNotFoundError(f"Input path not found: {input_path}")


def enhance_bev_image(
    image_bgr: np.ndarray,
    black_threshold: int,
    close_kernel: int,
    inpaint_radius: float,
    clahe_clip: float,
    sharpen_amount: float,
) -> tuple[np.ndarray, dict[str, float]]:
    if image_bgr is None or image_bgr.ndim != 3:
        raise ValueError("image_bgr must be an HxWx3 image")

    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    valid_mask = gray > int(black_threshold)

    enhanced = image_bgr.copy()
    hole_pixels = 0
    if np.any(valid_mask) and close_kernel > 1:
        kernel_size = max(3, int(close_kernel) | 1)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
        closed_mask = cv2.morphologyEx(valid_mask.astype(np.uint8) * 255, cv2.MORPH_CLOSE, kernel) > 0
        hole_mask = closed_mask & ~valid_mask
        hole_pixels = int(np.count_nonzero(hole_mask))
        if hole_pixels > 0 and inpaint_radius > 0:
            enhanced = cv2.inpaint(enhanced, (hole_mask.astype(np.uint8) * 255), float(inpaint_radius), cv2.INPAINT_TELEA)
        valid_mask = closed_mask

    if np.any(valid_mask):
        denoised = cv2.bilateralFilter(enhanced, 5, 45, 45)
        enhanced[valid_mask] = denoised[valid_mask]

        lab = cv2.cvtColor(enhanced, cv2.COLOR_BGR2LAB)
        l_channel, a_channel, b_channel = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=max(0.1, float(clahe_clip)), tileGridSize=(8, 8))
        l_enhanced = clahe.apply(l_channel)
        lab_enhanced = cv2.merge((l_enhanced, a_channel, b_channel))
        contrast = cv2.cvtColor(lab_enhanced, cv2.COLOR_LAB2BGR)
        enhanced[valid_mask] = contrast[valid_mask]

        if sharpen_amount > 0:
            blurred = cv2.GaussianBlur(enhanced, (0, 0), 1.1)
            sharpened = cv2.addWeighted(enhanced, 1.0 + float(sharpen_amount), blurred, -float(sharpen_amount), 0)
            enhanced[valid_mask] = sharpened[valid_mask]

    enhanced[~valid_mask] = 0
    return enhanced, {
        "valid_ratio_before": float(np.count_nonzero(gray > int(black_threshold)) / gray.size),
        "valid_ratio_after": float(np.count_nonzero(valid_mask) / valid_mask.size),
        "hole_pixels_inpainted": float(hole_pixels),
    }


def write_report(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Enhance generated BEV images without rerunning SHARP.")
    parser.add_argument("--input", required=True, help="Input BEV image or folder containing *_bev.png files.")
    parser.add_argument("--out-dir", required=True, help="Output folder for enhanced images and report.json.")
    parser.add_argument("--black-threshold", type=int, default=4, help="Pixels darker than this are treated as no-data.")
    parser.add_argument("--close-kernel", type=int, default=5, help="Morphological close kernel for small holes; 1 disables.")
    parser.add_argument("--inpaint-radius", type=float, default=2.0, help="Radius for filling small no-data holes inside valid regions.")
    parser.add_argument("--clahe-clip", type=float, default=2.2, help="Local contrast enhancement strength.")
    parser.add_argument("--sharpen", type=float, default=0.55, help="Unsharp-mask strength; 0 disables.")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.is_absolute():
        input_path = PROJECT_ROOT / input_path
    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = PROJECT_ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    files = collect_images(input_path)
    if not files:
        raise FileNotFoundError(f"No BEV images found under: {input_path}")

    outputs: list[dict[str, object]] = []
    for image_path in files:
        try:
            image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
            if image is None:
                raise ValueError("OpenCV could not read image")
            enhanced, stats = enhance_bev_image(
                image,
                black_threshold=args.black_threshold,
                close_kernel=args.close_kernel,
                inpaint_radius=args.inpaint_radius,
                clahe_clip=args.clahe_clip,
                sharpen_amount=args.sharpen,
            )
            output_path = out_dir / f"{image_path.stem}_enhanced.png"
            cv2.imwrite(str(output_path), enhanced)
            outputs.append({
                "input": str(image_path),
                "output": str(output_path),
                "status": "ok",
                **stats,
            })
        except Exception as exc:
            outputs.append({
                "input": str(image_path),
                "status": "error",
                "error": str(exc),
            })

    report = {
        "input": str(input_path),
        "output_dir": str(out_dir),
        "mode": "enhance_bev_image",
        "config": {
            "black_threshold": int(args.black_threshold),
            "close_kernel": int(args.close_kernel),
            "inpaint_radius": float(args.inpaint_radius),
            "clahe_clip": float(args.clahe_clip),
            "sharpen": float(args.sharpen),
        },
        "outputs": outputs,
    }
    write_report(out_dir / "report.json", report)
    print(f"Wrote enhanced BEV report to {out_dir / 'report.json'}")


if __name__ == "__main__":
    sys.exit(main())
