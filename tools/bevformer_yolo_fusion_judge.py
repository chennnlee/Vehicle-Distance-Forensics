from __future__ import annotations

import argparse
import csv
import json
import pickle
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO


@dataclass
class Det2D:
    xyxy: np.ndarray
    score: float
    label: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fuse BEVFormer results with YOLO overlays and generate frame-level judgment stats."
    )
    parser.add_argument(
        "--frames-dir",
        type=str,
        required=True,
        help="Folder containing input frames (jpg/png).",
    )
    parser.add_argument(
        "--bev-results-pkl",
        type=str,
        required=True,
        help="BEVFormer test output pickle path.",
    )
    parser.add_argument(
        "--infos-pkl",
        type=str,
        required=True,
        help="Temporal infos pickle aligned with BEVFormer results.",
    )
    parser.add_argument(
        "--out-dir",
        type=str,
        required=True,
        help="Output directory for fused overlays and reports.",
    )
    parser.add_argument(
        "--yolo-model",
        type=str,
        default="checkpoints/yolov8m.pt",
        help="Ultralytics YOLO model name or local path.",
    )
    parser.add_argument(
        "--yolo-conf",
        type=float,
        default=0.25,
        help="YOLO confidence threshold.",
    )
    parser.add_argument(
        "--bev-score-thr",
        type=float,
        default=0.20,
        help="BEVFormer score threshold before projection.",
    )
    parser.add_argument(
        "--match-iou-thr",
        type=float,
        default=0.20,
        help="IoU threshold used to match YOLO and BEV projected boxes.",
    )
    parser.add_argument(
        "--classes",
        type=str,
        default="2,3,5,7",
        help="COCO class ids to keep from YOLO, comma separated. Default: vehicle classes car,motorcycle,bus,truck.",
    )
    return parser.parse_args()


def list_frames(frames_dir: Path) -> list[Path]:
    exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    return sorted([p for p in frames_dir.iterdir() if p.suffix.lower() in exts])


def build_lidar2img(cam_info: dict) -> np.ndarray:
    lidar2cam_r = np.linalg.inv(cam_info["sensor2lidar_rotation"])
    lidar2cam_t = cam_info["sensor2lidar_translation"] @ lidar2cam_r.T

    lidar2cam_rt = np.eye(4, dtype=np.float32)
    lidar2cam_rt[:3, :3] = lidar2cam_r.T
    lidar2cam_rt[3, :3] = -lidar2cam_t

    intrinsic = cam_info["cam_intrinsic"]
    viewpad = np.eye(4, dtype=np.float32)
    viewpad[: intrinsic.shape[0], : intrinsic.shape[1]] = intrinsic
    return viewpad @ lidar2cam_rt.T


def project_bev_boxes_to_2d(result: dict, cam_info: dict, h: int, w: int, score_thr: float) -> list[Det2D]:
    if "pts_bbox" in result:
        pts_bbox = result["pts_bbox"]
        scores = pts_bbox["scores_3d"].detach().cpu().numpy()
        labels = pts_bbox["labels_3d"].detach().cpu().numpy()
        corners_3d = pts_bbox["boxes_3d"].corners.detach().cpu().numpy()
    else:
        scores = np.asarray(result["scores_3d"], dtype=np.float32)
        labels = np.asarray(result["labels_3d"], dtype=np.int64)
        corners_3d = np.asarray(result["corners_3d"], dtype=np.float32)

    keep = np.where(scores >= score_thr)[0]
    detections: list[Det2D] = []
    if keep.size == 0:
        return detections

    lidar2img = build_lidar2img(cam_info)

    for idx in keep:
        corners = corners_3d[idx]  # (8, 3)
        corners_h = np.concatenate([corners, np.ones((8, 1), dtype=np.float32)], axis=1)
        proj = corners_h @ lidar2img.T
        z = proj[:, 2]

        valid = z > 1e-3
        if valid.sum() < 4:
            continue

        pts2d = proj[valid, :2] / z[valid, None]
        x1, y1 = pts2d.min(axis=0)
        x2, y2 = pts2d.max(axis=0)

        x1 = float(np.clip(x1, 0, w - 1))
        y1 = float(np.clip(y1, 0, h - 1))
        x2 = float(np.clip(x2, 0, w - 1))
        y2 = float(np.clip(y2, 0, h - 1))

        if x2 <= x1 or y2 <= y1:
            continue

        detections.append(
            Det2D(
                xyxy=np.array([x1, y1, x2, y2], dtype=np.float32),
                score=float(scores[idx]),
                label=int(labels[idx]),
            )
        )
    return detections


def yolo_to_dets(result, keep_classes: set[int]) -> list[Det2D]:
    detections: list[Det2D] = []
    if result.boxes is None:
        return detections

    xyxy = result.boxes.xyxy.detach().cpu().numpy()
    conf = result.boxes.conf.detach().cpu().numpy()
    cls = result.boxes.cls.detach().cpu().numpy().astype(np.int64)

    for box, score, label in zip(xyxy, conf, cls):
        if int(label) not in keep_classes:
            continue
        detections.append(Det2D(xyxy=box.astype(np.float32), score=float(score), label=int(label)))
    return detections


def iou_xyxy(a: np.ndarray, b: np.ndarray) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b

    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)

    iw = max(0.0, ix2 - ix1)
    ih = max(0.0, iy2 - iy1)
    inter = iw * ih

    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter

    if union <= 0:
        return 0.0
    return float(inter / union)


def greedy_match(yolo_dets: list[Det2D], bev_dets: list[Det2D], iou_thr: float) -> tuple[list[tuple[int, int, float]], set[int], set[int]]:
    pairs: list[tuple[int, int, float]] = []

    cand: list[tuple[float, int, int]] = []
    for yi, yd in enumerate(yolo_dets):
        for bi, bd in enumerate(bev_dets):
            iou = iou_xyxy(yd.xyxy, bd.xyxy)
            if iou >= iou_thr:
                cand.append((iou, yi, bi))

    cand.sort(reverse=True, key=lambda x: x[0])
    used_y, used_b = set(), set()
    for iou, yi, bi in cand:
        if yi in used_y or bi in used_b:
            continue
        used_y.add(yi)
        used_b.add(bi)
        pairs.append((yi, bi, iou))

    y_only = set(range(len(yolo_dets))) - used_y
    b_only = set(range(len(bev_dets))) - used_b
    return pairs, y_only, b_only


def draw_box(img: np.ndarray, det: Det2D, color: tuple[int, int, int], label_text: str) -> None:
    x1, y1, x2, y2 = det.xyxy.astype(np.int32)
    cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
    cv2.putText(img, label_text, (x1, max(18, y1 - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)


def main() -> None:
    args = parse_args()

    frames_dir = Path(args.frames_dir)
    bev_results_pkl = Path(args.bev_results_pkl)
    infos_pkl = Path(args.infos_pkl)
    out_dir = Path(args.out_dir)

    out_img_dir = out_dir / "frames"
    out_img_dir.mkdir(parents=True, exist_ok=True)

    keep_classes = {int(x.strip()) for x in args.classes.split(",") if x.strip()}

    with bev_results_pkl.open("rb") as f:
        bev_results = pickle.load(f)
    with infos_pkl.open("rb") as f:
        infos = pickle.load(f)["infos"]

    frames = list_frames(frames_dir)

    n = min(len(frames), len(bev_results), len(infos))
    if n == 0:
        raise RuntimeError("No usable samples found.")

    model = YOLO(args.yolo_model)

    rows: list[dict[str, str | int | float]] = []
    total_yolo = total_bev = total_match = total_y_only = total_b_only = 0

    for i in range(n):
        frame = frames[i]
        info = infos[i]
        cam_info = info["cams"]["CAM_FRONT"]

        img = cv2.imread(str(frame))
        if img is None:
            continue
        h, w = img.shape[:2]

        yolo_res = model.predict(source=str(frame), conf=args.yolo_conf, verbose=False)[0]
        yolo_dets = yolo_to_dets(yolo_res, keep_classes)
        bev_dets = project_bev_boxes_to_2d(bev_results[i], cam_info, h, w, args.bev_score_thr)

        matches, y_only, b_only = greedy_match(yolo_dets, bev_dets, args.match_iou_thr)

        canvas = img.copy()

        for yi, yd in enumerate(yolo_dets):
            color = (0, 255, 0) if yi not in y_only else (0, 0, 255)
            txt = f"YOLO {yd.score:.2f}"
            draw_box(canvas, yd, color, txt)

        for bi, bd in enumerate(bev_dets):
            color = (255, 255, 0) if bi not in b_only else (255, 0, 0)
            txt = f"BEV {bd.score:.2f}"
            draw_box(canvas, bd, color, txt)

        status = "ok"
        if len(y_only) > 0:
            status = "bev_miss"

        summary_line = (
            f"frame={i:04d} YOLO={len(yolo_dets)} BEV_proj={len(bev_dets)} "
            f"match={len(matches)} y_only={len(y_only)} b_only={len(b_only)} status={status}"
        )
        cv2.putText(canvas, summary_line, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (255, 255, 255), 2, cv2.LINE_AA)

        out_img = out_img_dir / f"{i:04d}_{frame.stem}_fusion.png"
        cv2.imwrite(str(out_img), canvas)

        rows.append(
            {
                "frame_index": i,
                "frame_name": frame.name,
                "yolo_count": len(yolo_dets),
                "bev_projected_count": len(bev_dets),
                "matched_count": len(matches),
                "yolo_only_count": len(y_only),
                "bev_only_count": len(b_only),
                "status": status,
            }
        )

        total_yolo += len(yolo_dets)
        total_bev += len(bev_dets)
        total_match += len(matches)
        total_y_only += len(y_only)
        total_b_only += len(b_only)

    csv_path = out_dir / "fusion_judgment.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "frame_index",
                "frame_name",
                "yolo_count",
                "bev_projected_count",
                "matched_count",
                "yolo_only_count",
                "bev_only_count",
                "status",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    overall = {
        "frames_used": len(rows),
        "yolo_total": total_yolo,
        "bev_projected_total": total_bev,
        "matched_total": total_match,
        "yolo_only_total": total_y_only,
        "bev_only_total": total_b_only,
        "match_iou_thr": args.match_iou_thr,
        "yolo_conf": args.yolo_conf,
        "bev_score_thr": args.bev_score_thr,
        "yolo_classes": sorted(list(keep_classes)),
    }
    json_path = out_dir / "fusion_summary.json"
    json_path.write_text(json.dumps(overall, indent=2), encoding="utf-8")

    print(f"saved_frames={len(rows)}")
    print(f"frame_dir={out_img_dir.resolve()}")
    print(f"csv={csv_path.resolve()}")
    print(f"summary={json_path.resolve()}")


if __name__ == "__main__":
    main()
