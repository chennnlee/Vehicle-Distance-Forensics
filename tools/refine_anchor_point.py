from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


def refine_point(gray: np.ndarray, point: tuple[float, float], window: int) -> tuple[np.ndarray, bool]:
    # cornerSubPix needs a rough corner-like feature near the initial guess.
    # We seed it with the initial point itself and let it walk to the nearest
    # true corner within `window`, which is the standard technique for
    # upgrading an approximate manual click into a precise pixel location
    # instead of trusting the click coordinates directly.
    pts = np.array([[point]], dtype=np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_MAX_ITER, 60, 0.001)
    try:
        refined = cv2.cornerSubPix(gray, pts, (window, window), (-1, -1), criteria)
        result = refined[0][0]
        moved = float(np.hypot(result[0] - point[0], result[1] - point[1]))
        # cornerSubPix can drift far away if the neighborhood has no clear
        # corner (e.g. a flat/blurry patch); treat a large jump as failure
        # rather than silently trusting a point that likely snapped to the
        # wrong feature.
        ok = bool(moved <= window * 1.5 and np.isfinite(result).all())
        return result, ok
    except cv2.error:
        return np.array(point, dtype=np.float32), False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Refine a rough manually-estimated anchor point pair to sub-pixel corner locations."
    )
    parser.add_argument("--image", required=True, help="Input image path.")
    parser.add_argument("--pt1", required=True, help="Rough pixel coords x,y for anchor point 1.")
    parser.add_argument("--pt2", required=True, help="Rough pixel coords x,y for anchor point 2.")
    parser.add_argument("--window", type=int, default=8, help="Half-size of the search window in pixels.")
    parser.add_argument("--out-debug", default="", help="Optional path to save a before/after debug visualization.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    image_path = Path(args.image)
    if not image_path.is_absolute():
        image_path = PROJECT_ROOT / image_path
    image = cv2.imread(str(image_path))
    if image is None:
        raise RuntimeError(f"Unable to read image: {image_path}")
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    p1_raw = tuple(float(v) for v in args.pt1.split(","))
    p2_raw = tuple(float(v) for v in args.pt2.split(","))

    p1_refined, ok1 = refine_point(gray, p1_raw, args.window)
    p2_refined, ok2 = refine_point(gray, p2_raw, args.window)

    result = {
        "image": str(image_path),
        "pt1_input": list(p1_raw),
        "pt1_refined": p1_refined.tolist(),
        "pt1_ok": ok1,
        "pt2_input": list(p2_raw),
        "pt2_refined": p2_refined.tolist(),
        "pt2_ok": ok2,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if args.out_debug:
        canvas = image.copy()
        for raw, refined, color in [(p1_raw, p1_refined, (0, 165, 255)), (p2_raw, p2_refined, (0, 165, 255))]:
            cv2.drawMarker(canvas, (int(raw[0]), int(raw[1])), (0, 0, 255), cv2.MARKER_CROSS, 10, 1)
            cv2.drawMarker(canvas, (int(refined[0]), int(refined[1])), (0, 255, 0), cv2.MARKER_TILTED_CROSS, 10, 2)
        min_x = int(min(p1_raw[0], p2_raw[0], p1_refined[0], p2_refined[0])) - 40
        max_x = int(max(p1_raw[0], p2_raw[0], p1_refined[0], p2_refined[0])) + 40
        min_y = int(min(p1_raw[1], p2_raw[1], p1_refined[1], p2_refined[1])) - 40
        max_y = int(max(p1_raw[1], p2_raw[1], p1_refined[1], p2_refined[1])) + 40
        min_x, min_y = max(0, min_x), max(0, min_y)
        crop = canvas[min_y:max_y, min_x:max_x]
        crop = cv2.resize(crop, (crop.shape[1] * 6, crop.shape[0] * 6), interpolation=cv2.INTER_NEAREST)
        out_path = Path(args.out_debug)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(out_path), crop)


if __name__ == "__main__":
    main()
