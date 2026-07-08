from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# Taiwan regulation plate sizes (width_mm, height_mm) -> (width/height ratio, length_m)
# Source: 交通部公路局 號牌型式 (380x160 for cars, 260x140 for standard motorcycles).
PLATE_SPECS = {
    "car": {"width_m": 0.380, "height_m": 0.160},
    "motorcycle": {"width_m": 0.260, "height_m": 0.140},
}


@dataclass(frozen=True)
class PlateCandidate:
    box: np.ndarray  # (4, 2) corner points, ordered
    score: float
    aspect_ratio: float


def order_corners(pts: np.ndarray) -> np.ndarray:
    # Returns corners ordered as top-left, top-right, bottom-right, bottom-left
    # based on centroid angle, robust to the arbitrary order cv2.boxPoints gives.
    center = pts.mean(axis=0)
    angles = np.arctan2(pts[:, 1] - center[1], pts[:, 0] - center[0])
    order = np.argsort(angles)
    pts = pts[order]
    # Rotate so index 0 is the top-left-most (smallest x+y)
    start = int(np.argmin(pts.sum(axis=1)))
    return np.roll(pts, -start, axis=0)


def find_plate_candidates(
    crop_bgr: np.ndarray,
    expected_ratio: float,
    ratio_tolerance: float,
    min_area_frac: float,
    max_area_frac: float,
) -> list[PlateCandidate]:
    h, w = crop_bgr.shape[:2]
    crop_area = float(h * w)
    gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.bilateralFilter(gray, 7, 40, 40)

    # Plate borders + characters produce strong local edges; blackhat highlights
    # dark text/frame details against the plate's lighter background regardless
    # of overall scene brightness, which a single global threshold would miss.
    rect_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (13, 5))
    blackhat = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, rect_kernel)
    grad = cv2.Sobel(blackhat, cv2.CV_32F, 1, 0, ksize=3)
    grad = np.absolute(grad)
    grad = cv2.normalize(grad, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    grad = cv2.GaussianBlur(grad, (5, 5), 0)
    _, thresh = cv2.threshold(grad, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (21, 7)))
    thresh = cv2.erode(thresh, None, iterations=1)
    thresh = cv2.dilate(thresh, None, iterations=1)

    contours, _ = cv2.findContours(thresh, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    candidates: list[PlateCandidate] = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        area_frac = area / crop_area
        if area_frac < min_area_frac or area_frac > max_area_frac:
            continue
        rect = cv2.minAreaRect(cnt)
        (rw, rh) = rect[1]
        if rw < 1 or rh < 1:
            continue
        long_side, short_side = max(rw, rh), min(rw, rh)
        ratio = long_side / short_side
        if abs(ratio - expected_ratio) > ratio_tolerance:
            continue
        rect_area = rw * rh
        rectangularity = area / max(1.0, rect_area)  # how filled-in vs. a sparse/irregular blob
        if rectangularity < 0.5:
            continue
        ratio_error = abs(ratio - expected_ratio) / expected_ratio
        score = rectangularity * (1.0 - min(1.0, ratio_error))
        box = cv2.boxPoints(rect)
        candidates.append(PlateCandidate(box=order_corners(box), score=float(score), aspect_ratio=float(ratio)))

    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates


def anchor_points_from_box(box: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    # box is ordered top-left, top-right, bottom-right, bottom-left.
    # The physical plate WIDTH runs along the top/bottom edges; use the
    # midpoints of the left and right edges so the anchor line follows the
    # plate's actual (possibly tilted) orientation instead of assuming
    # horizontal, which matters for off-axis viewing angles.
    tl, tr, br, bl = box
    left_mid = (tl + bl) / 2.0
    right_mid = (tr + br) / 2.0
    return left_mid, right_mid


def draw_debug(crop_bgr: np.ndarray, candidates: list[PlateCandidate], chosen_idx: int, out_path: Path) -> None:
    canvas = crop_bgr.copy()
    for i, cand in enumerate(candidates[:5]):
        color = (0, 255, 0) if i == chosen_idx else (0, 165, 255)
        thickness = 2 if i == chosen_idx else 1
        cv2.drawContours(canvas, [cand.box.astype(np.int32)], -1, color, thickness)
        if i == chosen_idx:
            p1, p2 = anchor_points_from_box(cand.box)
            cv2.circle(canvas, tuple(p1.astype(np.int32)), 4, (0, 0, 255), -1)
            cv2.circle(canvas, tuple(p2.astype(np.int32)), 4, (0, 0, 255), -1)
            cv2.line(canvas, tuple(p1.astype(np.int32)), tuple(p2.astype(np.int32)), (0, 0, 255), 1)
    scale = max(1, 400 // max(1, canvas.shape[0]))
    if scale > 1:
        canvas = cv2.resize(canvas, (canvas.shape[1] * scale, canvas.shape[0] * scale), interpolation=cv2.INTER_NEAREST)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_path), canvas)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Auto-detect a license plate rectangle inside a vehicle bbox for calibration anchor points."
    )
    parser.add_argument("--image", required=True, help="Input image path.")
    parser.add_argument("--bbox", required=True, help="Vehicle bbox x1,y1,x2,y2 in image pixel coordinates.")
    parser.add_argument("--plate-type", choices=sorted(PLATE_SPECS), default="car", help="Regulation plate size to match against.")
    parser.add_argument("--ratio-tolerance", type=float, default=0.35, help="Allowed absolute deviation from the expected width/height ratio.")
    parser.add_argument("--min-area-frac", type=float, default=0.002, help="Minimum plate contour area as a fraction of the bbox crop area.")
    parser.add_argument("--max-area-frac", type=float, default=0.35, help="Maximum plate contour area as a fraction of the bbox crop area.")
    parser.add_argument("--out-debug", default="", help="Optional path to save a debug visualization image.")
    parser.add_argument("--bbox-padding-frac", type=float, default=0.08, help="Expand the bbox by this fraction before searching, in case the plate sits near the box edge.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    image_path = Path(args.image)
    if not image_path.is_absolute():
        image_path = PROJECT_ROOT / image_path
    image = cv2.imread(str(image_path))
    if image is None:
        raise RuntimeError(f"Unable to read image: {image_path}")
    img_h, img_w = image.shape[:2]

    x1, y1, x2, y2 = [float(v) for v in args.bbox.split(",")]
    pad_x = (x2 - x1) * args.bbox_padding_frac
    pad_y = (y2 - y1) * args.bbox_padding_frac
    cx1 = int(max(0, x1 - pad_x))
    cy1 = int(max(0, y1 - pad_y))
    cx2 = int(min(img_w, x2 + pad_x))
    cy2 = int(min(img_h, y2 + pad_y))
    crop = image[cy1:cy2, cx1:cx2]

    spec = PLATE_SPECS[args.plate_type]
    expected_ratio = spec["width_m"] / spec["height_m"]
    candidates = find_plate_candidates(
        crop,
        expected_ratio=expected_ratio,
        ratio_tolerance=args.ratio_tolerance,
        min_area_frac=args.min_area_frac,
        max_area_frac=args.max_area_frac,
    )

    result: dict[str, object] = {
        "image": str(image_path),
        "bbox": [x1, y1, x2, y2],
        "plate_type": args.plate_type,
        "expected_aspect_ratio": expected_ratio,
        "anchor_length_m": spec["width_m"],
        "candidate_count": len(candidates),
        "found": False,
    }

    if candidates:
        best = candidates[0]
        p1_local, p2_local = anchor_points_from_box(best.box)
        offset = np.array([cx1, cy1], dtype=np.float32)
        p1_global = p1_local + offset
        p2_global = p2_local + offset
        result.update(
            {
                "found": True,
                "score": best.score,
                "measured_aspect_ratio": best.aspect_ratio,
                "corners_image_coords": (best.box + offset).tolist(),
                "anchor_pt1": p1_global.tolist(),
                "anchor_pt2": p2_global.tolist(),
            }
        )
        if args.out_debug:
            draw_debug(crop, candidates, chosen_idx=0, out_path=Path(args.out_debug))

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
