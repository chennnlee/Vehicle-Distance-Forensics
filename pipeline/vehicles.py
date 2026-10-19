"""Block 3: vehicles per frame with a stable id: YOLOv8m-seg detections tracked by BoT-SORT in image coordinates
(no road plane needed). Boxes whose bottom reaches the hood row are the own car's reflection and are dropped."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

VEHICLE_CLASSES = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}      # as tools/dashcam_range_speed.py


def track(frames: list[Path], weights: Path, hood_row: int, conf: float = 0.3) -> tuple[pd.DataFrame, int]:
    """Boxes per frame with track ids, and how many times the tracker had to be restarted."""
    import numpy as np
    from ultralytics import YOLO

    model = YOLO(str(weights))
    rows, restarts, offset = [], 0, 0
    for i, f in enumerate(frames):
        kw = dict(source=str(f), persist=True, conf=conf, classes=list(VEHICLE_CLASSES), tracker="botsort.yaml", verbose=False)
        try:
            r = model.track(**kw)[0]
        except np.linalg.LinAlgError:
            # BoT-SORT's Kalman update can fail numerically on a degenerate box; restart the tracker at this frame and
            # keep later ids distinct from earlier ones (the tracks on both sides of the restart are not joined)
            restarts += 1
            offset += 100000
            model.predictor.trackers[0].reset()
            r = model.track(**kw)[0]
        if r.boxes is None or r.boxes.id is None:
            continue
        for (x1, y1, x2, y2), tid, cls, cf in zip(r.boxes.xyxy.cpu().numpy(), r.boxes.id.cpu().numpy().astype(int),
                                                  r.boxes.cls.cpu().numpy().astype(int), r.boxes.conf.cpu().numpy()):
            if y2 >= hood_row - 2:
                continue
            rows.append([i, str(int(tid) + offset), round(float(x1), 1), round(float(y1), 1), round(float(x2), 1),
                         round(float(y2), 1), VEHICLE_CLASSES[int(cls)], round(float(cf), 3)])
    return pd.DataFrame(rows, columns=["frame_idx", "track_id", "x0", "y0", "x1", "y1", "cls", "conf"]), restarts
