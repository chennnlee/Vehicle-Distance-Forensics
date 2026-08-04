"""Project nuScenes 3D annotations into 2D boxes and write YOLO-format labels.

Why this exists: the professor's action item "資料集若有 bounding box 可以微調
object detector". nuScenes ships 3D cuboids in the global frame, not 2D boxes,
so the boxes have to be transformed global -> ego -> camera and projected. The
class ids written out are COCO ids, not nuScenes ids, so a fine-tuned model
stays drop-in compatible with `dashcam_range_speed.py` / `cctv_speed_estimation.py`,
which filter COCO 2/3/5/7 and group them as 4w/2w.

Note on the mapping: construction vehicles and trailers are folded into COCO
`truck`. A stock COCO detector already reports them that way, and both pipelines
put car/bus/truck in the same size group, so the fold does not change any
downstream logic -- it only stops those vehicles from becoming unlabelled
background, which would actively teach the model to miss them.

This does NOT make nuScenes a speed benchmark: its ego speed (measured from
ego_pose) is a median 18 km/h with nothing above 60, so the dash-cycle odometer
has no legal dash cycle to lock onto. See docs/PUBLIC_DATASET_BENCHMARK_PLAN.md.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

# nuScenes category -> COCO class id used by both pipelines
CATEGORY_TO_COCO = {
    "vehicle.car": 2,
    "vehicle.motorcycle": 3,
    "vehicle.bus.bendy": 5,
    "vehicle.bus.rigid": 5,
    "vehicle.truck": 7,
    "vehicle.construction": 7,
    "vehicle.trailer": 7,
    "vehicle.emergency.ambulance": 7,
    "vehicle.emergency.police": 2,
}
COCO_NAMES = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataroot", required=True, help="nuScenes root (contains samples/ and the metadata dir).")
    ap.add_argument("--version", default="v1.0-mini", help="Metadata directory name.")
    ap.add_argument("--cameras", default="CAM_FRONT",
                    help="Comma-separated channels. Default CAM_FRONT: the pipelines are forward-facing.")
    ap.add_argument("--min-visibility", type=int, default=2,
                    help="Drop annotations below this nuScenes visibility level (1=v0-40 .. 4=v80-100). "
                         "Heavily occluded cuboids project to boxes the detector cannot be asked to reproduce.")
    ap.add_argument("--min-box-px", type=float, default=12.0, help="Drop 2D boxes smaller than this on either side.")
    ap.add_argument("--min-lidar-pts", type=int, default=1,
                    help="Drop annotations with fewer lidar returns; 0 keeps everything.")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--draw", type=int, default=6, help="How many verification images to render.")
    return ap.parse_args()


def quat_to_rot(q: list[float]) -> np.ndarray:
    """nuScenes stores rotations as [w, x, y, z]."""
    w, x, y, z = q
    n = w * w + x * x + y * y + z * z
    if n < 1e-12:
        return np.eye(3)
    s = 2.0 / n
    return np.array([
        [1 - s * (y * y + z * z), s * (x * y - z * w), s * (x * z + y * w)],
        [s * (x * y + z * w), 1 - s * (x * x + z * z), s * (y * z - x * w)],
        [s * (x * z - y * w), s * (y * z + x * w), 1 - s * (x * x + y * y)],
    ])


def corners_3d(translation, size, rotation) -> np.ndarray:
    """8 cuboid corners in the global frame. nuScenes size is (width, length, height)."""
    w, l, h = size
    x = np.array([1, 1, 1, 1, -1, -1, -1, -1]) * l / 2
    y = np.array([1, -1, -1, 1, 1, -1, -1, 1]) * w / 2
    z = np.array([1, 1, -1, -1, 1, 1, -1, -1]) * h / 2
    return quat_to_rot(rotation) @ np.vstack([x, y, z]) + np.array(translation).reshape(3, 1)


def main() -> None:
    args = parse_args()
    root = Path(args.dataroot)
    meta = root / args.version

    def load(name):
        return json.loads((meta / f"{name}.json").read_text())

    sample_data = load("sample_data")
    ego_pose = {e["token"]: e for e in load("ego_pose")}
    calib = {c["token"]: c for c in load("calibrated_sensor")}
    sensor = {s["token"]: s for s in load("sensor")}
    channel_of = {c["token"]: sensor[c["sensor_token"]]["channel"] for c in calib.values()}
    anns = defaultdict(list)
    for a in load("sample_annotation"):
        anns[a["sample_token"]].append(a)
    instance = {i["token"]: i for i in load("instance")}
    category = {c["token"]: c["name"] for c in load("category")}

    wanted = {c.strip() for c in args.cameras.split(",") if c.strip()}
    out = Path(args.out_dir)
    (out / "labels").mkdir(parents=True, exist_ok=True)
    (out / "images").mkdir(parents=True, exist_ok=True)
    (out / "verify").mkdir(parents=True, exist_ok=True)

    kept = defaultdict(int)
    dropped = defaultdict(int)
    n_img = 0
    drawn = 0
    index_rows = []

    for sd in sample_data:
        if not sd["is_key_frame"] or channel_of.get(sd["calibrated_sensor_token"]) not in wanted:
            continue
        cs = calib[sd["calibrated_sensor_token"]]
        pose = ego_pose[sd["ego_pose_token"]]
        K = np.array(cs["camera_intrinsic"], dtype=float)
        if K.size != 9:
            continue
        R_ec, t_ec = quat_to_rot(cs["rotation"]), np.array(cs["translation"])   # camera -> ego
        R_ge, t_ge = quat_to_rot(pose["rotation"]), np.array(pose["translation"])  # ego -> global
        W, H = sd["width"], sd["height"]

        lines = []
        boxes_for_draw = []
        for a in anns.get(sd["sample_token"], []):
            name = category[instance[a["instance_token"]]["category_token"]]
            cls = CATEGORY_TO_COCO.get(name)
            if cls is None:
                dropped["not_a_vehicle_class"] += 1
                continue
            if int(a["visibility_token"]) < args.min_visibility:
                dropped["low_visibility"] += 1
                continue
            if a["num_lidar_pts"] < args.min_lidar_pts:
                dropped["no_lidar_return"] += 1
                continue

            c = corners_3d(a["translation"], a["size"], a["rotation"])       # global
            c = R_ge.T @ (c - t_ge.reshape(3, 1))                            # -> ego
            c = R_ec.T @ (c - t_ec.reshape(3, 1))                            # -> camera
            if (c[2] <= 0.1).any():
                # Any corner behind the image plane makes the projection wrap
                # around; a partially-behind cuboid cannot be boxed reliably.
                dropped["behind_or_straddling_camera"] += 1
                continue
            uv = K @ c
            uv = uv[:2] / uv[2]
            x1, y1 = uv[0].min(), uv[1].min()
            x2, y2 = uv[0].max(), uv[1].max()
            # Clip to the frame, then require the visible part to still be a box.
            x1c, y1c = max(0.0, x1), max(0.0, y1)
            x2c, y2c = min(W - 1.0, x2), min(H - 1.0, y2)
            if x2c - x1c < args.min_box_px or y2c - y1c < args.min_box_px:
                dropped["outside_or_too_small"] += 1
                continue

            cx, cy = (x1c + x2c) / 2 / W, (y1c + y2c) / 2 / H
            bw, bh = (x2c - x1c) / W, (y2c - y1c) / H
            lines.append(f"{cls} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}")
            boxes_for_draw.append((x1c, y1c, x2c, y2c, cls))
            kept[COCO_NAMES[cls]] += 1

        stem = Path(sd["filename"]).stem
        (out / "labels" / f"{stem}.txt").write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        src = root / sd["filename"]
        link = out / "images" / f"{stem}.jpg"
        if not link.exists():
            try:
                link.symlink_to(src.resolve())
            except OSError:
                link.write_bytes(src.read_bytes())
        index_rows.append({"image": str(link), "n_boxes": len(lines), "sample_token": sd["sample_token"]})
        n_img += 1

        if drawn < args.draw and len(boxes_for_draw) >= 3:
            import cv2
            img = cv2.imread(str(src))
            for x1c, y1c, x2c, y2c, cls in boxes_for_draw:
                cv2.rectangle(img, (int(x1c), int(y1c)), (int(x2c), int(y2c)), (0, 200, 255), 2)
                cv2.putText(img, COCO_NAMES[cls], (int(x1c), max(14, int(y1c) - 5)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 200, 255), 2)
            cv2.imwrite(str(out / "verify" / f"{stem}.jpg"), img)
            drawn += 1

    (out / "index.json").write_text(json.dumps(index_rows, indent=1), encoding="utf-8")
    names = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}
    (out / "dataset.yaml").write_text(
        "# COCO class ids kept so a fine-tuned model stays drop-in for the pipelines\n"
        f"path: {out.resolve()}\ntrain: images\nval: images\n"
        "names:\n" + "".join(f"  {k}: {v}\n" for k, v in names.items()), encoding="utf-8")

    print(f"images written : {n_img}")
    print("boxes kept     : " + ", ".join(f"{k} {v}" for k, v in sorted(kept.items())) +
          f"   (total {sum(kept.values())})")
    print("dropped        : " + ", ".join(f"{k} {v}" for k, v in sorted(dropped.items())))
    print(f"verification images: {drawn} -> {out / 'verify'}")


if __name__ == "__main__":
    main()
