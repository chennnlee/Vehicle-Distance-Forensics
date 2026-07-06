from __future__ import annotations

import argparse
import csv
import json
import pickle
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Replace BEVFormer object detection with YOLOv8 on frames listed in infos pkl."
    )
    parser.add_argument("--infos-pkl", type=str, required=True, help="Temporal infos pickle path.")
    parser.add_argument("--out-pkl", type=str, required=True, help="Output pickle for YOLO detections.")
    parser.add_argument("--overlay-dir", type=str, required=True, help="Output directory for YOLO overlay frames.")
    parser.add_argument("--summary-json", type=str, default="", help="Optional summary json path.")
    parser.add_argument("--summary-csv", type=str, default="", help="Optional frame summary csv path.")
    parser.add_argument("--yolo-model", type=str, default="checkpoints/yolov8m.pt", help="YOLOv8 model name or path.")
    parser.add_argument("--conf", type=float, default=0.25, help="YOLO confidence threshold.")
    parser.add_argument("--iou", type=float, default=0.45, help="YOLO NMS IoU threshold.")
    parser.add_argument(
        "--classes",
        type=str,
        default="2,3,5,7",
        help="COCO class IDs to keep, comma separated. Default keeps vehicle classes.",
    )
    return parser.parse_args()


def load_infos(infos_pkl: Path) -> list[dict]:
    with infos_pkl.open("rb") as f:
        data = pickle.load(f)
    if isinstance(data, dict) and "infos" in data:
        return data["infos"]
    raise ValueError("Invalid infos pkl format: expected dict with key 'infos'.")


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def draw_filtered_overlay(img_bgr: np.ndarray, boxes: np.ndarray, scores: np.ndarray, labels: np.ndarray) -> np.ndarray:
    canvas = img_bgr.copy()
    for box, score, label in zip(boxes, scores, labels):
        x1, y1, x2, y2 = box.astype(np.int32)
        cv2.rectangle(canvas, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(
            canvas,
            f"cls={int(label)} {float(score):.2f}",
            (x1, max(20, y1 - 4)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 255, 0),
            2,
            cv2.LINE_AA,
        )
    return canvas


def main() -> None:
    args = parse_args()

    infos_pkl = Path(args.infos_pkl)
    out_pkl = Path(args.out_pkl)
    overlay_dir = Path(args.overlay_dir)
    summary_json = Path(args.summary_json) if args.summary_json else out_pkl.with_suffix(".summary.json")
    summary_csv = Path(args.summary_csv) if args.summary_csv else out_pkl.with_suffix(".summary.csv")

    ensure_parent(out_pkl)
    ensure_parent(summary_json)
    ensure_parent(summary_csv)
    overlay_dir.mkdir(parents=True, exist_ok=True)

    keep_classes = {int(x.strip()) for x in args.classes.split(",") if x.strip()}
    infos = load_infos(infos_pkl)
    model = YOLO(args.yolo_model)

    rows: list[dict[str, int | str]] = []
    yolo_results: list[dict] = []

    total_det = 0
    valid_frames = 0
    missing_frames = 0

    for idx, info in enumerate(infos):
        cam = info.get("cams", {}).get("CAM_FRONT")
        if cam is None:
            rows.append({"frame_index": idx, "frame": "<no_cam_front>", "det_count": 0, "status": "missing_cam"})
            continue

        frame_path = Path(cam["data_path"])
        if not frame_path.exists():
            rows.append({"frame_index": idx, "frame": str(frame_path), "det_count": 0, "status": "missing_frame"})
            missing_frames += 1
            continue

        img = cv2.imread(str(frame_path))
        if img is None:
            rows.append({"frame_index": idx, "frame": str(frame_path), "det_count": 0, "status": "unreadable_frame"})
            missing_frames += 1
            continue

        pred = model.predict(source=str(frame_path), conf=args.conf, iou=args.iou, verbose=False)[0]

        if pred.boxes is None or len(pred.boxes) == 0:
            boxes = np.empty((0, 4), dtype=np.float32)
            scores = np.empty((0,), dtype=np.float32)
            labels = np.empty((0,), dtype=np.int64)
        else:
            all_boxes = pred.boxes.xyxy.detach().cpu().numpy().astype(np.float32)
            all_scores = pred.boxes.conf.detach().cpu().numpy().astype(np.float32)
            all_labels = pred.boxes.cls.detach().cpu().numpy().astype(np.int64)
            keep_mask = np.array([int(c) in keep_classes for c in all_labels], dtype=bool)
            boxes = all_boxes[keep_mask]
            scores = all_scores[keep_mask]
            labels = all_labels[keep_mask]

        overlay = draw_filtered_overlay(img, boxes, scores, labels)
        overlay_path = overlay_dir / f"{idx:04d}_{frame_path.stem}_yolo_overlay.png"
        cv2.imwrite(str(overlay_path), overlay)

        yolo_results.append(
            {
                "frame_index": idx,
                "token": info.get("token", ""),
                "frame_path": str(frame_path),
                "boxes_xyxy": boxes,
                "scores": scores,
                "labels": labels,
            }
        )

        det_count = int(len(scores))
        rows.append(
            {
                "frame_index": idx,
                "frame": frame_path.name,
                "det_count": det_count,
                "status": "ok",
            }
        )
        total_det += det_count
        valid_frames += 1

    with out_pkl.open("wb") as f:
        pickle.dump(yolo_results, f)

    with summary_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["frame_index", "frame", "det_count", "status"])
        writer.writeheader()
        writer.writerows(rows)

    summary = {
        "frames_total": len(infos),
        "frames_valid": valid_frames,
        "frames_missing": missing_frames,
        "detections_total": total_det,
        "detections_per_valid_frame": (float(total_det) / float(valid_frames)) if valid_frames else 0.0,
        "yolo_model": args.yolo_model,
        "conf": args.conf,
        "iou": args.iou,
        "classes": sorted(list(keep_classes)),
        "out_pkl": str(out_pkl.resolve()),
        "overlay_dir": str(overlay_dir.resolve()),
        "summary_csv": str(summary_csv.resolve()),
    }
    summary_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"saved_yolo_pkl={out_pkl.resolve()}")
    print(f"saved_overlay_dir={overlay_dir.resolve()}")
    print(f"saved_summary_json={summary_json.resolve()}")
    print(f"saved_summary_csv={summary_csv.resolve()}")


if __name__ == "__main__":
    main()
