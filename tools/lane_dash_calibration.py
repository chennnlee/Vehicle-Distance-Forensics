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

from utils.pointcloud_io import load_point_cloud_points


# Taiwan legal dashed-marking specs (道路交通標誌標線號誌設置規則).
# gap/dash ratio is scale-invariant, so it identifies the marking TYPE from
# raw (uncalibrated) SHARP measurements before any absolute scale is known.
MARKING_SPECS = {
    "lane_line_4m": {"dash_m": 4.0, "gap_m": 6.0, "note": "車道線/行車分向線 4m/6m"},
    "guide_line_50cm": {"dash_m": 0.5, "gap_m": 0.5, "note": "路口行車導引線/左彎待轉區線 50cm/50cm"},
}


@dataclass
class DashSegment:
    label: int
    area: int
    tip_near: np.ndarray  # pixel coords, larger y (closer to camera)
    tip_far: np.ndarray   # pixel coords, smaller y
    length_px: float


def detect_dash_chain(
    gray: np.ndarray,
    roi_xyxy: tuple[int, int, int, int],
    local_contrast: int,
    min_area: int,
    max_area: int,
    min_elongation: float,
    collinear_tol_px: float,
) -> list[DashSegment]:
    """Find elongated bright dashes collinear with the largest one inside the ROI.

    Straight lane lines project to straight image lines, so collinearity with
    the biggest (nearest, most reliable) dash is a geometric criterion for
    "same lane line" that doesn't rely on eyeballing.
    """
    x1, y1, x2, y2 = roi_xyxy
    # Local-contrast mask instead of a global threshold: dashes inside tree
    # shadows are darker than sunlit asphalt elsewhere, so "brighter than the
    # local road background" is the property that survives mixed lighting.
    blur = cv2.GaussianBlur(gray, (51, 51), 0)
    diff = cv2.subtract(gray, blur)
    roi_mask = np.zeros_like(gray)
    roi_mask[y1:y2, x1:x2] = 1
    mask = ((diff > local_contrast) & (roi_mask > 0)).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 5)))

    num, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    segments: list[DashSegment] = []
    for i in range(1, num):
        _, _, _, _, area = stats[i]
        if area < min_area or area > max_area:
            continue
        ys, xs = np.where(labels == i)
        pts = np.column_stack([xs, ys]).astype(np.float32)
        mean = pts.mean(axis=0)
        cov = np.cov((pts - mean).T)
        evals, evecs = np.linalg.eigh(cov)
        if evals[1] / max(1e-6, evals[0]) < min_elongation:
            continue
        axis = evecs[:, 1]
        proj = (pts - mean) @ axis
        p_a = mean + axis * proj.min()
        p_b = mean + axis * proj.max()
        tip_near, tip_far = (p_a, p_b) if p_a[1] >= p_b[1] else (p_b, p_a)
        segments.append(
            DashSegment(
                label=i,
                area=int(area),
                tip_near=tip_near,
                tip_far=tip_far,
                length_px=float(proj.max() - proj.min()),
            )
        )

    if not segments:
        return []

    def build_chain(seed: DashSegment) -> list[DashSegment]:
        d = seed.tip_far - seed.tip_near
        seed_dir = d / max(1e-8, np.linalg.norm(d))
        normal = np.array([-d[1], d[0]], dtype=np.float32)
        normal /= max(1e-8, np.linalg.norm(normal))
        c0 = -float(normal @ seed.tip_near)
        chain = []
        for s in segments:
            sd = s.tip_far - s.tip_near
            sd = sd / max(1e-8, np.linalg.norm(sd))
            # Same lane line means both collinear AND locally parallel to the
            # seed's direction; crosswalk stripes intersecting the line are
            # collinear-ish at their centroid but roughly perpendicular, so
            # the parallelism test rejects them without any absolute
            # orientation assumption (lane lines may recede at any angle).
            if abs(float(seed_dir @ sd)) < np.cos(np.deg2rad(30)):
                continue
            if abs(float(normal @ s.tip_near) + c0) < collinear_tol_px and abs(
                float(normal @ s.tip_far) + c0
            ) < collinear_tol_px:
                chain.append(s)
        chain.sort(key=lambda s: -float(s.tip_near[1]))  # near (large y) -> far
        return chain

    # The largest component is not always on the lane line of interest (it can
    # be a crosswalk stripe); try the top candidates as seeds and keep the
    # longest resulting chain.
    seeds = sorted(segments, key=lambda s: -s.area)[:8]
    best_chain: list[DashSegment] = []
    for seed in seeds:
        chain = build_chain(seed)
        if len(chain) > len(best_chain) or (
            len(chain) == len(best_chain)
            and chain
            and best_chain
            and sum(c.area for c in chain) > sum(c.area for c in best_chain)
        ):
            best_chain = chain
    return best_chain


def sample_3d(
    points_xyz: np.ndarray, u: np.ndarray, v: np.ndarray, px: float, py: float, radius: float
) -> tuple[np.ndarray | None, int]:
    d2 = (u - px) ** 2 + (v - py) ** 2
    near = d2 <= radius * radius
    n = int(np.nansum(near))
    if n < 5:
        return None, n
    return np.median(points_xyz[near], axis=0), n


def fit_ground_plane_raw(
    points_xyz: np.ndarray,
    u: np.ndarray,
    v: np.ndarray,
    roi_xyxy: tuple[int, int, int, int],
    iterations: int = 240,
) -> dict[str, float] | None:
    """RANSAC-fit y = a*x + b*z + c on points projecting into the ROI.

    Thresholds are proportional to scene depth because SHARP's raw unit scale
    varies per camera (the fixed-FOV assumption); a fixed metric threshold
    would be wrong on cameras where raw units are 2-3x off.
    """
    x1, y1, x2, y2 = roi_xyxy
    cand = (
        np.isfinite(u)
        & (u >= x1) & (u < x2) & (v >= y1) & (v < y2)
        & np.isfinite(points_xyz).all(axis=1)
    )
    sample = points_xyz[cand]
    if sample.shape[0] < 200:
        return None
    if sample.shape[0] > 60000:
        rng0 = np.random.default_rng(7)
        sample = sample[rng0.choice(sample.shape[0], 60000, replace=False)]

    med_depth = float(np.median(sample[:, 2]))
    thr = 0.012 * med_depth
    rng = np.random.default_rng(114)
    best_inliers = None
    best_count = 0
    for _ in range(iterations):
        idx = rng.choice(sample.shape[0], size=3, replace=False)
        pts = sample[idx]
        design = np.column_stack([pts[:, 0], pts[:, 2], np.ones(3)])
        try:
            coeff, *_ = np.linalg.lstsq(design, pts[:, 1], rcond=None)
        except np.linalg.LinAlgError:
            continue
        res = np.abs(sample[:, 1] - (coeff[0] * sample[:, 0] + coeff[1] * sample[:, 2] + coeff[2]))
        inl = res <= thr
        cnt = int(inl.sum())
        if cnt > best_count:
            best_count, best_inliers = cnt, inl
    if best_inliers is None or best_count < 100:
        return None
    pts = sample[best_inliers]
    design = np.column_stack([pts[:, 0], pts[:, 2], np.ones(pts.shape[0])])
    coeff, *_ = np.linalg.lstsq(design, pts[:, 1], rcond=None)
    res = np.abs(pts[:, 1] - design @ coeff)
    return {
        "a": float(coeff[0]),
        "b": float(coeff[1]),
        "c": float(coeff[2]),
        "residual_median": float(np.median(res)),
        "median_depth": med_depth,
        "inlier_ratio": float(best_count / sample.shape[0]),
    }


def height_above_plane(p: np.ndarray, gp: dict[str, float]) -> float:
    return abs(float(p[1] - (gp["a"] * p[0] + gp["b"] * p[2] + gp["c"])))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Estimate a SHARP point-cloud scale factor from legally-specified lane dash lengths, "
        "with a cross-depth consistency check (dashes on one lane line share one true length)."
    )
    parser.add_argument("--image", required=True, help="Input image path.")
    parser.add_argument("--pointcloud", required=True, help="Matching SHARP PLY path.")
    parser.add_argument("--out-dir", required=True, help="Output directory for the report JSON and annotated PNG.")
    parser.add_argument("--roi", default="", help="Search region x1,y1,x2,y2. Default: lower 60% of the image.")
    parser.add_argument("--dash-length-m", type=float, default=4.0, help="Legal dash segment length in meters (Taiwan default 4m).")
    parser.add_argument("--spec-gap-ratio", type=float, default=1.5, help="Legal gap/dash ratio used for the plausibility check (6m/4m).")
    parser.add_argument("--local-contrast", type=int, default=20, help="Brightness-above-local-background threshold.")
    parser.add_argument("--min-area", type=int, default=40, help="Minimum dash component area in pixels.")
    parser.add_argument("--max-area", type=int, default=6000, help="Maximum dash component area in pixels.")
    parser.add_argument("--min-elongation", type=float, default=4.0, help="Minimum PCA eigenvalue ratio for a dash.")
    parser.add_argument("--collinear-tol-px", type=float, default=12.0, help="Max distance from the seed line for chain membership.")
    parser.add_argument("--max-length-cv", type=float, default=0.15, help="Flag the result unstable above this dash-length coefficient of variation.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    image_path = Path(args.image)
    cloud_path = Path(args.pointcloud)
    out_dir = Path(args.out_dir)
    if not image_path.is_absolute():
        image_path = PROJECT_ROOT / image_path
    if not cloud_path.is_absolute():
        cloud_path = PROJECT_ROOT / cloud_path
    if not out_dir.is_absolute():
        out_dir = PROJECT_ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    image = cv2.imread(str(image_path))
    if image is None:
        raise RuntimeError(f"Unable to read image: {image_path}")
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    img_h, img_w = gray.shape

    if args.roi:
        x1, y1, x2, y2 = [int(v) for v in args.roi.split(",")]
    else:
        x1, y1, x2, y2 = 0, int(img_h * 0.4), img_w, img_h

    chain = detect_dash_chain(
        gray,
        (x1, y1, x2, y2),
        local_contrast=args.local_contrast,
        min_area=args.min_area,
        max_area=args.max_area,
        min_elongation=args.min_elongation,
        collinear_tol_px=args.collinear_tol_px,
    )

    result: dict[str, object] = {
        "image": str(image_path),
        "pointcloud": str(cloud_path),
        "roi": [x1, y1, x2, y2],
        "dash_length_m": args.dash_length_m,
        "chain_count": len(chain),
        "status": "no_chain",
    }

    if len(chain) < 2:
        (out_dir / "lane_dash_calibration.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print("偵測不到同一條車道線上的 >=2 段虛線;請調整 --roi 或閾值參數。")
        return

    points_xyz, _, metadata = load_point_cloud_points(cloud_path)
    intr = metadata.get("intrinsics") or {}
    fx = float(intr.get("fx", 0.0))
    if fx <= 0:
        raise RuntimeError("PLY metadata has no intrinsics; cannot project points.")
    fy = float(intr.get("fy") or fx)
    cx = float(intr.get("cx", (img_w - 1) * 0.5))
    cy = float(intr.get("cy", (img_h - 1) * 0.5))

    z = points_xyz[:, 2]
    valid = np.isfinite(points_xyz).all(axis=1) & (z > 1e-6)
    u = np.where(valid, fx * (points_xyz[:, 0] / z) + cx, np.nan)
    v = np.where(valid, fy * (points_xyz[:, 1] / z) + cy, np.nan)

    # Road paint lies on the ground plane; railings, poles, and bus-shelter
    # frames -- the main false positives -- sit well above it. Fit the plane
    # from the whole ROI's points, then drop any "dash" whose tips are
    # elevated. This is the strongest available cue because it uses 3D
    # geometry rather than appearance.
    ground = fit_ground_plane_raw(points_xyz, u, v, (x1, y1, x2, y2))
    result["ground_plane"] = ground

    dash_rows = []
    rejected_rows = []
    survivors = []
    lengths = []
    for seg in chain:
        radius = max(3.0, seg.length_px * 0.10)
        p_near, n_near = sample_3d(points_xyz, u, v, *seg.tip_near, radius)
        p_far, n_far = sample_3d(points_xyz, u, v, *seg.tip_far, radius)
        row = {
            "label": seg.label,
            "tip_near_px": seg.tip_near.tolist(),
            "tip_far_px": seg.tip_far.tolist(),
            "length_px": seg.length_px,
            "sample_radius_px": radius,
            "sample_counts": [n_near, n_far],
            "length_3d_raw_m": None,
            "depth_raw_m": None,
            "height_above_ground_raw": None,
        }
        if p_near is None or p_far is None:
            rejected_rows.append({**row, "rejected": "no_3d_samples"})
            continue
        row["length_3d_raw_m"] = float(np.linalg.norm(p_far - p_near))
        row["depth_raw_m"] = float((p_near[2] + p_far[2]) / 2.0)
        if ground is not None:
            h = max(height_above_plane(p_near, ground), height_above_plane(p_far, ground))
            row["height_above_ground_raw"] = h
            h_thr = max(2.5 * ground["residual_median"], 0.02 * ground["median_depth"])
            if h > h_thr:
                rejected_rows.append({**row, "rejected": "off_ground"})
                continue
        dash_rows.append(row)
        survivors.append(seg)
        lengths.append(row["length_3d_raw_m"])

    gaps = []
    for i in range(len(survivors) - 1):
        pa, _ = sample_3d(points_xyz, u, v, *survivors[i].tip_far, 5.0)
        pb, _ = sample_3d(points_xyz, u, v, *survivors[i + 1].tip_near, 5.0)
        if pa is not None and pb is not None:
            gaps.append(float(np.linalg.norm(pb - pa)))

    result["dashes"] = dash_rows
    result["rejected_dashes"] = rejected_rows
    result["gaps_3d_raw_m"] = gaps
    result["chain_count_after_ground_filter"] = len(survivors)

    if len(lengths) < 2:
        off_ground = sum(1 for r in rejected_rows if r.get("rejected") == "off_ground")
        result["status"] = "off_ground_rejected" if off_ground > 0 else "too_few_3d_samples"
    else:
        arr = np.array(lengths)
        median_len = float(np.median(arr))
        cv_val = float(arr.std() / max(1e-9, arr.mean()))
        median_len_px = float(np.median([r["length_px"] for r in dash_rows]))

        # Identify the marking type from the scale-invariant gap/dash ratio,
        # then calibrate against that spec's legal dash length. Never assume
        # the 4m lane-line spec blindly: intersection guide lines are 8x
        # shorter and would produce absurd scale factors if misidentified.
        measured_ratios = [g / median_len for g in gaps]
        spec_id = None
        spec_ratio_err = None
        if measured_ratios:
            # A gap is "explained" by a spec if it matches either the adjacent
            # gap ratio or the one-dash-missing ratio (2*target+1). Choose the
            # spec that explains the most gaps -- a median over ratios would be
            # corrupted by a single hidden/undetected dash in the chain.
            best = None
            for name, spec in MARKING_SPECS.items():
                target = spec["gap_m"] / spec["dash_m"]
                explained = 0
                errs = []
                for ratio in measured_ratios:
                    e_adj = abs(ratio - target) / target
                    e_miss = abs(ratio - (2 * target + 1)) / (2 * target + 1)
                    e = min(e_adj, e_miss)
                    if e < 0.25:
                        explained += 1
                        errs.append(e)
                if explained == 0:
                    continue
                mean_err = float(np.mean(errs))
                key = (explained, -mean_err)
                if best is None or key > best[0]:
                    best = (key, name, mean_err, explained)
            if best is not None and best[3] * 2 >= len(measured_ratios):
                spec_id, spec_ratio_err = best[1], best[2]

        gap_flags = []
        if spec_id is not None:
            spec = MARKING_SPECS[spec_id]
            target = spec["gap_m"] / spec["dash_m"]
            for ratio in measured_ratios:
                if abs(ratio - target) / target < 0.25:
                    gap_flags.append("adjacent_ok")
                elif abs(ratio - (2 * target + 1)) / (2 * target + 1) < 0.25:
                    gap_flags.append("one_dash_missing_ok")
                else:
                    gap_flags.append("ratio_mismatch")
            scale = spec["dash_m"] / median_len

            # Post-calibration ground re-check in REAL meters. The raw-unit
            # pre-filter cannot use an absolute height limit because SHARP's
            # raw scale differs per camera (a railing 1m up measures only
            # 0.15 raw units on a far-off-FOV camera). Once the candidate
            # scale exists, heights convert to meters: paint sits within
            # plane-fit noise (<0.35m), railings/shelter frames start ~0.8m.
            if ground is not None:
                kept, dropped = [], []
                for row in dash_rows:
                    h = row.get("height_above_ground_raw")
                    if h is not None and h * scale > 0.35:
                        dropped.append({**row, "rejected": "off_ground_real_m"})
                    else:
                        kept.append(row)
                if dropped:
                    rejected_rows.extend(dropped)
                    dash_rows = kept
                    lengths = [r["length_3d_raw_m"] for r in dash_rows]
                    result["dashes"] = dash_rows
                    result["rejected_dashes"] = rejected_rows
                    result["chain_count_after_ground_filter"] = len(dash_rows)
                    if len(lengths) >= 2:
                        arr = np.array(lengths)
                        median_len = float(np.median(arr))
                        cv_val = float(arr.std() / max(1e-9, arr.mean()))
                        median_len_px = float(np.median([r["length_px"] for r in dash_rows]))
                        scale = spec["dash_m"] / median_len
                        measured_ratios = [g / median_len for g in gaps]
                    else:
                        spec_id = None
                        scale = None
        else:
            gap_flags = ["no_spec_match"] * len(measured_ratios)
            scale = None

        fully_rejected = (
            scale is None
            and spec_id is None
            and any(r.get("rejected") == "off_ground_real_m" for r in rejected_rows)
        )
        if fully_rejected:
            # The whole chain turned out to be an elevated structure once its
            # implied scale exposed the true heights.
            result.update({"status": "off_ground_rejected", "scale_factor": None})
        else:
            # Confidence gating: all three must hold for a trustworthy anchor.
            # Short markings (guide lines ~50cm) often fail the pixel-length
            # gate: at low resolution tip-sampling error dominates.
            checks = {
                "spec_identified": spec_id is not None,
                "length_cv_ok": cv_val <= args.max_length_cv,
                "pixel_length_ok": median_len_px >= 30.0,
            }
            if all(checks.values()):
                status = "ok"
            elif spec_id is None:
                status = "no_spec_match"
            else:
                status = "low_confidence"

            result.update(
                {
                    "length_median_raw_m": median_len,
                    "length_median_px": median_len_px,
                    "length_cv": cv_val,
                    "identified_spec": spec_id,
                    "identified_spec_note": MARKING_SPECS[spec_id]["note"] if spec_id else None,
                    "spec_ratio_error": spec_ratio_err,
                    "scale_factor": scale,
                    "gap_over_dash_ratios": measured_ratios,
                    "gap_flags": gap_flags,
                    "confidence_checks": checks,
                    "status": status,
                }
            )

    canvas = image.copy()
    scale_for_draw = result.get("scale_factor")
    for row in rejected_rows:
        p1 = np.array(row["tip_near_px"], dtype=int)
        p2 = np.array(row["tip_far_px"], dtype=int)
        cv2.line(canvas, tuple(p1), tuple(p2), (0, 0, 255), 2)
        mid = ((p1 + p2) / 2).astype(int)
        cv2.putText(canvas, row["rejected"], (mid[0] + 8, mid[1]), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
    for row in dash_rows:
        p1 = np.array(row["tip_near_px"], dtype=int)
        p2 = np.array(row["tip_far_px"], dtype=int)
        cv2.line(canvas, tuple(p1), tuple(p2), (0, 255, 0), 3)
        if row["length_3d_raw_m"] is not None:
            mid = ((p1 + p2) / 2).astype(int)
            if scale_for_draw is not None:
                # Show what the dash measures AFTER calibration so it can be
                # compared to the legal length (4m / 0.5m) at a glance.
                text = f"{row['length_3d_raw_m'] * scale_for_draw:.2f}m"
            else:
                text = f"raw {row['length_3d_raw_m']:.2f}"
            cv2.putText(canvas, text, (mid[0] + 10, mid[1]), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 4)
            cv2.putText(canvas, text, (mid[0] + 10, mid[1]), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    header = f"chain={len(chain)} status={result['status']}"
    if result.get("scale_factor") is not None:
        header += f" spec={result.get('identified_spec')} scale={result['scale_factor']:.3f} cv={result['length_cv']:.3f}"
    cv2.putText(canvas, header, (16, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 4)
    cv2.putText(canvas, header, (16, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    annotated = out_dir / f"{image_path.stem}_lane_dash_calibration.png"
    cv2.imwrite(str(annotated), canvas)
    result["annotated"] = str(annotated)

    (out_dir / "lane_dash_calibration.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({k: v for k, v in result.items() if k != "dashes"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
