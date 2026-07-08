from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from utils.ipm_bev import IPMBEVConfig, save_ipm_bev


def parse_pair(text: str, label: str) -> tuple[float, float]:
    parts = [p.strip() for p in text.split(",") if p.strip()]
    if len(parts) != 2:
        raise ValueError(f"{label} must use min,max")
    return float(parts[0]), float(parts[1])


def parse_size(text: str) -> tuple[int, int]:
    parts = [p.strip() for p in text.split(",") if p.strip()]
    if len(parts) != 2:
        raise ValueError("--output-size must use width,height")
    return int(parts[0]), int(parts[1])


def parse_points(text: str, label: str) -> np.ndarray:
    points = []
    for pair in text.split(";"):
        pair = pair.strip()
        if not pair:
            continue
        values = [p.strip() for p in pair.split(",") if p.strip()]
        if len(values) != 2:
            raise ValueError(f"{label} must use x,y;x,y;...")
        points.append((float(values[0]), float(values[1])))
    if len(points) < 4:
        raise ValueError(f"{label} needs at least 4 points")
    return np.asarray(points, dtype=np.float32)


def order_quad_points(points: np.ndarray) -> np.ndarray:
    if points.shape != (4, 2):
        raise ValueError("interactive homography requires exactly 4 points")

    ordered = np.empty((4, 2), dtype=np.float32)
    point_sums = points.sum(axis=1)
    point_diffs = np.diff(points, axis=1).reshape(-1)

    ordered[0] = points[np.argmin(point_sums)]
    ordered[2] = points[np.argmax(point_sums)]
    ordered[1] = points[np.argmin(point_diffs)]
    ordered[3] = points[np.argmax(point_diffs)]
    return ordered


def quad_area(points: np.ndarray) -> float:
    ordered = order_quad_points(points)
    x = ordered[:, 0]
    y = ordered[:, 1]
    return float(0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))


def compute_warp_output_size(points: np.ndarray, minimum_size: int = 64) -> tuple[int, int]:
    ordered = order_quad_points(points)
    width_a = float(np.linalg.norm(ordered[2] - ordered[3]))
    width_b = float(np.linalg.norm(ordered[1] - ordered[0]))
    height_a = float(np.linalg.norm(ordered[1] - ordered[2]))
    height_b = float(np.linalg.norm(ordered[0] - ordered[3]))
    width = max(minimum_size, int(round(max(width_a, width_b))))
    height = max(minimum_size, int(round(max(height_a, height_b))))
    return width, height


def draw_point_selection_overlay(image: np.ndarray, points: np.ndarray, status_text: str, help_text: str) -> np.ndarray:
    canvas = image.copy()
    h, w = canvas.shape[:2]

    if points.size:
        ordered_indices = np.arange(1, len(points) + 1, dtype=np.int32)
        if len(points) >= 2:
            polyline = np.asarray(points, dtype=np.int32).reshape(-1, 1, 2)
            cv2.polylines(canvas, [polyline], False, (0, 255, 255), 2, cv2.LINE_AA)
        for idx, (x, y) in zip(ordered_indices, points):
            center = (int(round(x)), int(round(y)))
            cv2.circle(canvas, center, 8, (255, 255, 255), 2, cv2.LINE_AA)
            cv2.circle(canvas, center, 5, (0, 0, 255), -1, cv2.LINE_AA)
            cv2.putText(
                canvas,
                str(int(idx)),
                (center[0] + 10, center[1] - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 0, 0),
                4,
                cv2.LINE_AA,
            )
            cv2.putText(
                canvas,
                str(int(idx)),
                (center[0] + 10, center[1] - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 255),
                2,
                cv2.LINE_AA,
            )

    banner_h = 112
    banner = canvas.copy()
    cv2.rectangle(banner, (0, 0), (w - 1, banner_h), (0, 0, 0), -1)
    canvas = cv2.addWeighted(banner, 0.55, canvas, 0.45, 0)

    y = 28
    for line in [help_text, status_text]:
        for subline in line.split("\n"):
            cv2.putText(canvas, subline, (16, y), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (255, 255, 255), 2, cv2.LINE_AA)
            y += 28
        y += 6

    footer = f"selected={len(points)}/4"
    cv2.putText(canvas, footer, (16, h - 18), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (0, 0, 0), 4, cv2.LINE_AA)
    cv2.putText(canvas, footer, (16, h - 18), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (255, 255, 255), 2, cv2.LINE_AA)
    return canvas


def pick_quad_points_interactively(image: np.ndarray, window_name: str = "Homography picker") -> np.ndarray:
    if image is None or image.ndim != 3:
        raise ValueError("image must be an HxWx3 BGR image")

    help_text = (
        "Left click: add point | Right click: undo last | C: clear all\n"
        "Enter/Space: finish after 4 points | Q / Esc: cancel\n"
        "Pick 4 coplanar corners. The order will be normalized for homography."
    )

    points: list[tuple[float, float]] = []
    status_text = "Click four corners on the same ground plane."

    def refresh_status(message: str) -> None:
        nonlocal status_text
        status_text = message

    def on_mouse(event, x, y, flags, userdata):
        nonlocal points
        if event == cv2.EVENT_LBUTTONDOWN:
            if len(points) >= 4:
                refresh_status("Already have 4 points. Press Enter/Space to confirm or C to clear.")
                return
            points.append((float(x), float(y)))
            refresh_status(f"Added point {len(points)}/4 at ({x}, {y}).")
        elif event == cv2.EVENT_RBUTTONDOWN:
            if points:
                removed = points.pop()
                refresh_status(f"Removed last point at ({int(round(removed[0]))}, {int(round(removed[1]))}).")

    try:
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        cv2.setMouseCallback(window_name, on_mouse)
    except cv2.error as exc:
        raise RuntimeError("OpenCV GUI is unavailable in this environment. Use --mode points instead.") from exc

    try:
        while True:
            frame = draw_point_selection_overlay(image, np.asarray(points, dtype=np.float32), status_text, help_text)
            cv2.imshow(window_name, frame)
            key = cv2.waitKey(30) & 0xFF

            if key in (27, ord("q")):
                raise RuntimeError("interactive homography selection was cancelled")
            if key in (ord("c"), ord("C")):
                points.clear()
                refresh_status("Cleared all points. Click four new corners.")
            elif key in (8, 127):
                if points:
                    points.pop()
                    refresh_status(f"Removed last point. {len(points)}/4 remaining.")
            elif key in (13, 10, 32):
                if len(points) == 4:
                    break
                refresh_status("Need exactly 4 points before confirming.")
    finally:
        cv2.destroyWindow(window_name)

    return np.asarray(points, dtype=np.float32)


def save_point_selection_preview(image: np.ndarray, points: np.ndarray, output_path: Path, title: str) -> None:
    preview = draw_point_selection_overlay(image, points, title, "Selected points preview")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), preview)


def collect_images(image_path: Path, ext: str) -> list[Path]:
    if image_path.is_file():
        return [image_path]
    if image_path.is_dir():
        allowed = {f".{ext.lower().lstrip('.')}"}
        if ext == "*":
            allowed = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
        return sorted(p for p in image_path.rglob("*") if p.suffix.lower() in allowed)
    raise FileNotFoundError(f"Image path not found: {image_path}")


def apply_limit(items: list[Path], limit: int) -> list[Path]:
    if limit <= 0:
        return items
    return items[:limit]


def write_report(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def save_monolayout_topview(tv, output_path: Path) -> tuple[dict[str, float], np.ndarray, np.ndarray]:
    tv_np = tv.squeeze().detach().cpu().numpy()
    if tv_np.ndim != 3 or tv_np.shape[0] < 2:
        raise ValueError(f"Unexpected MonoLayout output shape: {tv_np.shape}")

    prob = tv_np[1].astype(np.float32)
    mask = (tv_np[1] > tv_np[0]).astype(np.uint8) * 255
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), mask)
    stats = {
        "occupancy_ratio": float(np.count_nonzero(mask) / mask.size),
        "mean_foreground_probability": float(np.mean(prob)),
        "max_foreground_probability": float(np.max(prob)),
    }
    return stats, mask, prob


def save_probability_heatmap(prob: np.ndarray, output_path: Path) -> None:
    prob_u8 = np.clip(prob * 255.0, 0, 255).astype(np.uint8)
    heatmap = cv2.applyColorMap(prob_u8, cv2.COLORMAP_TURBO)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), heatmap)


def save_monolayout_panel(
    image_path: Path,
    mask: np.ndarray,
    prob: np.ndarray,
    output_path: Path,
    panel_height: int = 320,
) -> None:
    image = cv2.imread(str(image_path))
    if image is None:
        return

    def fit_height(img: np.ndarray) -> np.ndarray:
        h, w = img.shape[:2]
        target_w = max(1, int(round(w * panel_height / max(1, h))))
        return cv2.resize(img, (target_w, panel_height), interpolation=cv2.INTER_AREA)

    original = fit_height(image)
    mask_bgr = fit_height(cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR))
    prob_u8 = np.clip(prob * 255.0, 0, 255).astype(np.uint8)
    heatmap = fit_height(cv2.applyColorMap(prob_u8, cv2.COLORMAP_TURBO))
    panel = np.hstack([original, mask_bgr, heatmap])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), panel)


def require_monolayout_weights(model_path: Path, layout_type: str) -> list[Path]:
    required = [model_path / "encoder.pth"]
    if layout_type == "both":
        required.extend([model_path / "static_decoder.pth", model_path / "dynamic_decoder.pth"])
    else:
        required.append(model_path / "decoder.pth")
    return [p for p in required if not p.exists()]


def save_pick_sheet(image_path: Path, out_dir: Path, grid_step_px: int) -> dict:
    image = cv2.imread(str(image_path))
    if image is None:
        return {"image": str(image_path), "status": "skipped_unreadable"}

    sheet = image.copy()
    h, w = sheet.shape[:2]
    step = max(25, int(grid_step_px))

    for x in range(0, w, step):
        cv2.line(sheet, (x, 0), (x, h - 1), (0, 255, 255), 1, cv2.LINE_AA)
        cv2.putText(sheet, str(x), (x + 3, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(sheet, str(x), (x + 3, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1, cv2.LINE_AA)
    for y in range(0, h, step):
        cv2.line(sheet, (0, y), (w - 1, y), (0, 255, 255), 1, cv2.LINE_AA)
        cv2.putText(sheet, str(y), (4, y + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(sheet, str(y), (4, y + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1, cv2.LINE_AA)

    output_path = out_dir / "pick_sheets" / f"{image_path.stem}_pick_sheet.png"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), sheet)
    return {
        "image": str(image_path),
        "output": str(output_path),
        "status": "ok",
        "width": int(w),
        "height": int(h),
        "grid_step_px": int(step),
    }


def draw_metric_grid(bev: np.ndarray, meters_per_pixel: float, margin_m: float, bounds_m: dict[str, float]) -> np.ndarray:
    grid = bev.copy()
    h, w = grid.shape[:2]
    step_px = max(1, int(round(1.0 / meters_per_pixel)))
    major_step_px = max(step_px, int(round(5.0 / meters_per_pixel)))

    for x in range(0, w, step_px):
        color = (70, 70, 70) if x % major_step_px else (150, 150, 150)
        cv2.line(grid, (x, 0), (x, h - 1), color, 1, cv2.LINE_AA)
    for y in range(0, h, step_px):
        color = (70, 70, 70) if y % major_step_px else (150, 150, 150)
        cv2.line(grid, (0, y), (w - 1, y), color, 1, cv2.LINE_AA)

    alpha = 0.28
    blended = cv2.addWeighted(grid, alpha, bev, 1.0 - alpha, 0)
    text = (
        f"scale={meters_per_pixel:.3f} m/px, "
        f"x=[{bounds_m['x_min']:.2f},{bounds_m['x_max']:.2f}], "
        f"y=[{bounds_m['y_min']:.2f},{bounds_m['y_max']:.2f}], margin={margin_m:.2f}m"
    )
    cv2.putText(blended, text, (16, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (0, 0, 0), 4, cv2.LINE_AA)
    cv2.putText(blended, text, (16, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (255, 255, 255), 1, cv2.LINE_AA)
    return blended


def metric_points_to_pixels(dst_points_m: np.ndarray, meters_per_pixel: float, margin_m: float) -> tuple[np.ndarray, tuple[int, int], dict[str, float]]:
    x_min = float(np.min(dst_points_m[:, 0]))
    x_max = float(np.max(dst_points_m[:, 0]))
    y_min = float(np.min(dst_points_m[:, 1]))
    y_max = float(np.max(dst_points_m[:, 1]))
    if x_max <= x_min or y_max <= y_min:
        raise ValueError("--dst-points-m must span a non-zero metric area")

    width = int(np.ceil((x_max - x_min + 2.0 * margin_m) / meters_per_pixel))
    height = int(np.ceil((y_max - y_min + 2.0 * margin_m) / meters_per_pixel))
    if width <= 0 or height <= 0:
        raise ValueError("computed BEV output size is invalid")

    dst_px = np.empty_like(dst_points_m, dtype=np.float32)
    dst_px[:, 0] = (dst_points_m[:, 0] - x_min + margin_m) / meters_per_pixel
    dst_px[:, 1] = (y_max + margin_m - dst_points_m[:, 1]) / meters_per_pixel
    bounds = {"x_min": x_min, "x_max": x_max, "y_min": y_min, "y_max": y_max}
    return dst_px, (width, height), bounds


def run_metric_homography(images: Iterable[Path], out_dir: Path, args: argparse.Namespace) -> dict:
    src_points = parse_points(args.src_points, "--src-points")
    dst_points_m = parse_points(args.dst_points_m, "--dst-points-m")
    if src_points.shape != dst_points_m.shape:
        raise ValueError("--src-points and --dst-points-m must contain the same number of points")
    if args.meters_per_pixel <= 0:
        raise ValueError("--meters-per-pixel must be positive")

    dst_points_px, output_size, bounds_m = metric_points_to_pixels(
        dst_points_m,
        args.meters_per_pixel,
        args.margin_m,
    )
    homography, inlier_mask = cv2.findHomography(src_points, dst_points_px, cv2.RANSAC, 3.0)
    if homography is None:
        raise ValueError("Could not estimate homography from the provided points")

    outputs = []
    for image_path in images:
        image = cv2.imread(str(image_path))
        if image is None:
            outputs.append({"image": str(image_path), "status": "skipped_unreadable"})
            continue

        bev = cv2.warpPerspective(
            image,
            homography,
            output_size,
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(0, 0, 0),
        )
        output_path = out_dir / "metric_homography" / f"{image_path.stem}_metric_bev.png"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(output_path), bev)

        grid_path = out_dir / "metric_homography" / f"{image_path.stem}_metric_bev_grid.png"
        grid = draw_metric_grid(bev, args.meters_per_pixel, args.margin_m, bounds_m)
        cv2.imwrite(str(grid_path), grid)
        outputs.append({
            "image": str(image_path),
            "output": str(output_path),
            "grid_output": str(grid_path),
            "status": "ok",
        })

    return {
        "mode": "metric_homography",
        "note": (
            "This mode uses user-provided road-surface point correspondences. "
            "For Taiwan road footage, use measured/legal road marking dimensions "
            "from the same frame whenever possible."
        ),
        "source_points_px": src_points.tolist(),
        "destination_points_m": dst_points_m.tolist(),
        "destination_points_px": dst_points_px.tolist(),
        "meters_per_pixel": float(args.meters_per_pixel),
        "output_size_px": {"width": int(output_size[0]), "height": int(output_size[1])},
        "bounds_m": bounds_m,
        "homography_image_to_bev": homography.tolist(),
        "inlier_mask": inlier_mask.ravel().astype(int).tolist() if inlier_mask is not None else [],
        "outputs": outputs,
    }


def run_interactive_homography(images: Iterable[Path], out_dir: Path, args: argparse.Namespace) -> dict:
    outputs = []

    for image_path in images:
        image = cv2.imread(str(image_path))
        if image is None:
            outputs.append({"image": str(image_path), "status": "skipped_unreadable"})
            continue

        try:
            clicked_points = pick_quad_points_interactively(image, f"Homography picker - {image_path.name}")
        except RuntimeError as exc:
            outputs.append({"image": str(image_path), "status": "cancelled", "reason": str(exc)})
            break

        ordered_points = order_quad_points(clicked_points)

        if args.warp_output_size.strip():
            output_size = parse_size(args.warp_output_size)
        else:
            output_size = compute_warp_output_size(ordered_points)

        out_w, out_h = output_size
        destination_points = np.asarray(
            [
                [0.0, 0.0],
                [float(out_w - 1), 0.0],
                [float(out_w - 1), float(out_h - 1)],
                [0.0, float(out_h - 1)],
            ],
            dtype=np.float32,
        )
        homography = cv2.getPerspectiveTransform(ordered_points, destination_points)
        bev = cv2.warpPerspective(
            image,
            homography,
            output_size,
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(0, 0, 0),
        )

        output_dir = out_dir / "interactive_homography"
        output_path = output_dir / f"{image_path.stem}_birdseye.png"
        points_path = output_dir / f"{image_path.stem}_picked_points.png"
        output_dir.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(output_path), bev)
        save_point_selection_preview(
            image,
            ordered_points,
            points_path,
            "Ordered corners used for homography",
        )

        outputs.append(
            {
                "image": str(image_path),
                "output": str(output_path),
                "points_preview": str(points_path),
                "status": "ok",
                "selected_points_px": clicked_points.tolist(),
                "ordered_points_px": ordered_points.tolist(),
                "destination_points_px": destination_points.tolist(),
                "output_size_px": {"width": int(out_w), "height": int(out_h)},
                "output_size_source": "cli" if args.warp_output_size.strip() else "auto_from_points",
                "homography_image_to_bev": homography.tolist(),
                "selected_quad_area_px2": quad_area(ordered_points),
            }
        )

    return {
        "mode": "interactive_homography",
        "note": (
            "This mode uses four user-picked coplanar points and rectifies them into a bird's-eye view. "
            "It is perspective-correct but not metric unless you supply your own scale convention."
        ),
        "outputs": outputs,
    }


def run_ipm_preview(images: Iterable[Path], out_dir: Path, args: argparse.Namespace) -> dict:
    config = IPMBEVConfig(
        x_range_m=parse_pair(args.x_range, "--x-range"),
        y_range_m=parse_pair(args.y_range, "--y-range"),
        output_size=parse_size(args.output_size),
        camera_height_m=args.camera_height,
        pitch_deg=args.pitch_deg,
        fov_deg=args.fov_deg,
    )

    outputs = []
    for image_path in images:
        image = cv2.imread(str(image_path))
        if image is None:
            outputs.append({"image": str(image_path), "status": "skipped_unreadable"})
            continue
        output_path = out_dir / "ipm_preview" / f"{image_path.stem}_ipm_preview.png"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        _, stats = save_ipm_bev(image, output_path, config)
        outputs.append({
            "image": str(image_path),
            "output": str(output_path),
            "status": "ok",
            **stats,
        })

    return {
        "mode": "ipm_preview",
        "note": (
            "MonoLayout weights were not provided, so this is only a geometric ground-plane "
            "preview. It is useful for checking image orientation and rough BEV framing, "
            "not for MonoLayout semantic occupancy quality."
        ),
        "outputs": outputs,
    }


def run_monolayout(images: Iterable[Path], out_dir: Path, args: argparse.Namespace) -> dict:
    import PIL.Image as pil
    import torch
    from torchvision import transforms

    monolayout_root = Path(args.monolayout_root).expanduser().resolve()
    model_path = Path(args.model_path).expanduser().resolve()
    sys.path.insert(0, str(monolayout_root))
    from monolayout import model  # type: ignore

    device = torch.device(args.device if args.device else ("cuda" if torch.cuda.is_available() else "cpu"))
    encoder_path = model_path / "encoder.pth"
    encoder_dict = torch.load(str(encoder_path), map_location=device, weights_only=False)
    feed_height = int(encoder_dict["height"])
    feed_width = int(encoder_dict["width"])

    encoder = model.Encoder(18, feed_width, feed_height, False)
    filtered_encoder = {k: v for k, v in encoder_dict.items() if k in encoder.state_dict()}
    encoder.load_state_dict(filtered_encoder)
    encoder.to(device).eval()

    decoders = {}
    if args.type == "both":
        for name in ("static", "dynamic"):
            decoder = model.Decoder(encoder.resnet_encoder.num_ch_enc)
            decoder.load_state_dict(torch.load(str(model_path / f"{name}_decoder.pth"), map_location=device, weights_only=False))
            decoders[name] = decoder.to(device).eval()
    else:
        decoder = model.Decoder(encoder.resnet_encoder.num_ch_enc)
        decoder.load_state_dict(torch.load(str(model_path / "decoder.pth"), map_location=device, weights_only=False))
        decoders[args.type] = decoder.to(device).eval()

    outputs = []
    with torch.no_grad():
        for image_path in images:
            input_image = pil.open(image_path).convert("RGB")
            input_image = input_image.resize((feed_width, feed_height), pil.LANCZOS)
            tensor = transforms.ToTensor()(input_image).unsqueeze(0).to(device)
            features = encoder(tensor)

            image_outputs = {"image": str(image_path), "status": "ok", "layouts": []}
            for name, decoder in decoders.items():
                tv = decoder(features, is_training=False)
                output_path = out_dir / "monolayout" / name / f"{image_path.stem}.png"
                stats, mask, prob = save_monolayout_topview(tv, output_path)
                heatmap_path = out_dir / "monolayout" / name / f"{image_path.stem}_prob.png"
                panel_path = out_dir / "monolayout" / name / f"{image_path.stem}_panel.png"
                save_probability_heatmap(prob, heatmap_path)
                save_monolayout_panel(image_path, mask, prob, panel_path)
                image_outputs["layouts"].append({
                    "type": name,
                    "output": str(output_path),
                    "probability_output": str(heatmap_path),
                    "panel_output": str(panel_path),
                    **stats,
                })
            outputs.append(image_outputs)

    return {
        "mode": "monolayout",
        "device": str(device),
        "model_path": str(model_path),
        "monolayout_root": str(monolayout_root),
        "outputs": outputs,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MonoLayout suitability/demo runner")
    parser.add_argument("--image-path", default="data/input/cctv_keyframes/043.jpg")
    parser.add_argument("--out-dir", default="data/output/monolayout_demo")
    parser.add_argument("--ext", default="*", help="Image extension for folder input, or * for common image types")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of images for folder input")
    parser.add_argument("--mode", default="auto", choices=["auto", "pick-sheet", "points", "warp", "ipm", "monolayout"])
    parser.add_argument("--grid-step-px", type=int, default=100, help="Pixel grid spacing for pick-sheet mode")
    parser.add_argument("--src-points", default="", help="Image points as x,y;x,y;x,y;x,y")
    parser.add_argument("--dst-points-m", default="", help="Ground points in meters as x,y;x,y;x,y;x,y. X=right, Y=forward")
    parser.add_argument("--meters-per-pixel", type=float, default=0.02, help="BEV scale for points mode")
    parser.add_argument("--margin-m", type=float, default=1.0, help="Metric BEV margin around destination points")
    parser.add_argument("--warp-output-size", default="", help="Optional output size for interactive warp mode, width,height")
    parser.add_argument("--monolayout-root", default="", help="Path to a local clone of https://github.com/manila95/monolayout")
    parser.add_argument("--model-path", default="", help="Path containing encoder.pth and decoder weights")
    parser.add_argument("--type", default="static", choices=["static", "dynamic", "both"])
    parser.add_argument("--device", default="", help="Optional torch device override, e.g. cpu or cuda")
    parser.add_argument("--x-range", default="0,40")
    parser.add_argument("--y-range", default="-12,12")
    parser.add_argument("--output-size", default="800,800")
    parser.add_argument("--camera-height", type=float, default=1.6)
    parser.add_argument("--pitch-deg", type=float, default=15.0)
    parser.add_argument("--fov-deg", type=float, default=90.0)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    image_path = Path(args.image_path)
    if not image_path.is_absolute():
        image_path = PROJECT_ROOT / image_path
    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = PROJECT_ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    images = apply_limit(collect_images(image_path, args.ext), args.limit)
    report = {
        "approach": {
            "recommended_for_taiwan_road_footage": "metric_homography_from_known_markings",
            "fits_when": "You can identify at least four coplanar road-surface points with known metric coordinates.",
            "weak_when": "The chosen points are not on the same ground plane, are poorly localized, or markings are worn/deformed.",
            "license": "MIT",
        },
        "inputs": {
            "image_path": str(image_path),
            "image_count": len(images),
            "type": args.type,
        },
    }

    if args.mode == "pick-sheet":
        outputs = [save_pick_sheet(image, out_dir, args.grid_step_px) for image in images]
        report["run"] = {
            "mode": "pick_sheet",
            "note": "Use this image to read pixel coordinates for road marking corners, then rerun with --mode points.",
            "outputs": outputs,
        }
    elif args.mode == "warp":
        report["run"] = run_interactive_homography(images, out_dir, args)
    elif args.mode == "points" or (args.src_points and args.dst_points_m):
        if not args.src_points or not args.dst_points_m:
            raise ValueError("--mode points requires --src-points and --dst-points-m")
        report["run"] = run_metric_homography(images, out_dir, args)
    elif args.mode == "ipm":
        report["run"] = run_ipm_preview(images, out_dir, args)
    elif args.mode == "monolayout":
        if not (args.monolayout_root and args.model_path):
            raise ValueError("--mode monolayout requires --monolayout-root and --model-path")
        missing = require_monolayout_weights(Path(args.model_path).expanduser(), args.type)
        if missing:
            raise FileNotFoundError(f"Missing MonoLayout weights: {missing}")
        report["run"] = run_monolayout(images, out_dir, args)
    elif args.monolayout_root and args.model_path:
        missing = require_monolayout_weights(Path(args.model_path).expanduser(), args.type)
        if missing:
            report["run"] = run_ipm_preview(images, out_dir, args)
            report["missing_monolayout_weights"] = [str(p) for p in missing]
        else:
            report["run"] = run_monolayout(images, out_dir, args)
    else:
        report["run"] = run_ipm_preview(images, out_dir, args)
        report["missing_monolayout_setup"] = {
            "monolayout_root": "not provided",
            "model_path": "not provided",
            "expected_weights": (
                "encoder.pth + decoder.pth for static/dynamic, or "
                "encoder.pth + static_decoder.pth + dynamic_decoder.pth for both"
            ),
        }

    report_path = out_dir / "report.json"
    write_report(report_path, report)
    print(f"Demo report: {report_path}")
    for item in report["run"].get("outputs", []):
        if "output" in item:
            print(f"Output: {item['output']}")
        for layout in item.get("layouts", []):
            print(f"Output: {layout['output']}")


if __name__ == "__main__":
    main()
