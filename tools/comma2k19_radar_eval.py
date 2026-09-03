"""Validate the *target* measurements of pipeline B against comma2k19's factory radar.

Everything this project has published about other vehicles -- following distance
and absolute speed -- rests on geometry that has never been checked against an
instrument. The one self-check that existed, "when following steadily the
target's absolute speed should equal ego speed", is algebraically circular: the
pipeline computes abs = (ego + d(range)/dt) * 3.6, so |abs - ego| IS |rel| * 3.6,
and filtering for steady following filters for small |rel|. It cannot fail.

comma2k19 breaks the circle. Every segment carries the car's own DSU radar on
`processed_log/CAN/radar` -- longitudinal distance, lateral distance and relative
speed for up to 16 tracked objects -- alongside CAN wheel speed. That is an
independent chain for the same quantities:

    ours   ground point -> ground plane -> range ;  abs = ego_odometer + d(range)/dt
    radar  time of flight -> range      ;           abs = ego_CAN      + v_rel

No shared component: different sensor, different physics, different ego-speed
source. A scale error in our geometry has nowhere to hide.

Three things this report is careful about.

ASSOCIATION IS FORCED, NOT CHOSEN. Only frames where EACH side sees exactly one
in-lane moving object are used, so the pairing is the only one available rather
than the one that agrees best; lateral position, measured independently on each
side, is then required to agree as a check on that pairing. Taking "the nearest
in-lane object" whenever several exist looked equivalent and was not: on segment
21 two of our tracks competed for the same radar slot and returned range ratios
of 0.94 and 1.15 for what had to be one car. The moving-object gate is not
cosmetic either -- an in-lane radar return at 0 km/h is a gantry or a sign, and
the camera has no vehicle there at all.

THE ERROR IS DECOMPOSED, NOT JUST TOTALLED. Target absolute speed error splits
exactly into an ego term and a geometry term,

    abs_ours - abs_radar = (ego_ours - ego_CAN) + 3.6 * (rel_ours - rel_radar),

so a bad dash-cycle constant cannot be mistaken for a bad ground plane. The range
comparison is decomposed the same way: because range = A/(y - y_h) on both sides
with the same pixel row, 1/d_radar is an AFFINE function of 1/d_ours whose slope
is the scale ratio A_ours/A_radar and whose intercept carries the horizon offset.
That separates a focal-length error (uniform, slope) from a pitch error (grows
with distance, intercept) -- the exact question left open in CLAUDE.md.

CLOCKS ARE NOT ASSUMED ALIGNED. Radar and video run on different clocks and the
odometer answers with a ~3 s window, so the report sweeps a lag and prints
boxcar-averaged errors alongside the instantaneous ones, and always states the
zero-lag number too.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ranges", required=True, help="ranges.csv from dashcam_range_speed.py")
    ap.add_argument("--ego-speed", required=True, help="ego_speed.csv from the same run")
    ap.add_argument("--tracks", default="",
                    help="tracks.json from the same run; enables the geometry solve, "
                         "which needs the ground point's pixel row.")
    ap.add_argument("--radar", required=True, help="radar.csv from comma2k19_radar_export.py")
    ap.add_argument("--gt", required=True, help="gt_both.csv (CAN + pose ego speed)")
    ap.add_argument("--lane-half-width-m", type=float, default=1.8,
                    help="Lateral gate defining 'in my lane', applied to BOTH sides.")
    ap.add_argument("--max-range-m", type=float, default=90.0)
    ap.add_argument("--min-target-kmh", type=float, default=15.0,
                    help="Radar returns slower than this are roadside furniture, not vehicles.")
    ap.add_argument("--dedup-m", type=float, default=1.0,
                    help="Radar returns closer than this in range and lateral are one object.")
    ap.add_argument("--min-pair-frames", type=int, default=20,
                    help="Shortest track<->object pairing worth accepting.")
    ap.add_argument("--max-dlat-m", type=float, default=1.5,
                    help="Lateral disagreement above which the pair is not the same object.")
    ap.add_argument("--a-ours", type=float, default=0.0,
                    help="A = h*f of our geometry, for the printed comparison.")
    ap.add_argument("--y-h-ours", type=float, default=0.0,
                    help="Horizon row of our geometry, for the printed comparison.")
    ap.add_argument("--lag-max-s", type=float, default=2.0)
    ap.add_argument("--avg-windows-s", default="0,1,3",
                    help="Boxcar widths for the averaged comparison; 0 means instantaneous.")
    ap.add_argument("--label", default="")
    ap.add_argument("--out-json", default="")
    ap.add_argument("--dump-csv", default="",
                    help="Per-frame paired rows, so segments can be pooled without re-running.")
    return ap.parse_args()


def read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def num(row: dict, key: str) -> float:
    v = row.get(key, "")
    return float(v) if v not in ("", None) else float("nan")


def radar_lead(rows, half_w, max_r, dedup, min_kmh):
    """Nearest in-lane moving radar object per frame, after merging duplicate slots."""
    by_frame = defaultdict(list)
    for r in rows:
        d, lat, ab = num(r, "radar_range_m"), num(r, "radar_lat_m"), num(r, "radar_abs_kmh")
        if abs(lat) <= half_w and 0 < d <= max_r and ab >= min_kmh:
            by_frame[int(r["frame_idx"])].append(
                (d, lat, num(r, "radar_rel_ms"), ab, int(r["slot"])))
    lead = {}
    for fi, items in by_frame.items():
        items.sort()
        merged = []
        for it in items:
            if any(abs(it[0] - m[0]) < dedup and abs(it[1] - m[1]) < dedup for m in merged):
                continue
            merged.append(it)
        d, lat, rel, ab, slot = merged[0]
        lead[fi] = {"range_m": d, "lat_m": lat, "rel_ms": rel, "abs_kmh": ab,
                    "slot": slot, "n_inlane": len(merged)}

    # The DSU reuses slot numbers and reports one car on two slots at once, so the
    # slot id is not an object id: following it fragments a single 30 s lead into
    # sub-second pieces. Link the merged leads by continuity of range and lateral
    # instead, and use that as the radar-side object identity.
    obj, nxt, prev = {}, 0, None
    for fi in sorted(lead):
        cur = lead[fi]
        if (prev is not None and fi - prev[0] <= 2
                and abs(cur["range_m"] - prev[1]["range_m"]) < 2.5
                and abs(cur["lat_m"] - prev[1]["lat_m"]) < 1.2):
            cur["obj"] = prev[1]["obj"]
        else:
            nxt += 1
            cur["obj"] = nxt
        prev = (fi, cur)
    return lead


def ours_lead(rows, half_w, max_r):
    """Nearest in-lane measured target per frame, by the same rule."""
    by_frame = defaultdict(list)
    for r in rows:
        d, lat = num(r, "range_m"), num(r, "lat_m")
        if abs(lat) <= half_w and 0 < d <= max_r:
            by_frame[int(r["frame_idx"])].append(r)
    lead = {}
    for fi, items in by_frame.items():
        r = min(items, key=lambda q: num(q, "range_m"))
        lead[fi] = {"range_m": num(r, "range_m"), "lat_m": num(r, "lat_m"),
                    "rel_ms": num(r, "rel_ms"), "abs_kmh": num(r, "abs_kmh"),
                    "sens": num(r, "sens_m_per_px"), "track_id": int(r["track_id"]),
                    "t_s": num(r, "t_s"), "n_inlane": len(items)}
    return lead


def boxcar(x: np.ndarray, n: int, runs: list[np.ndarray] | None = None) -> np.ndarray:
    """Centred moving average, never crossing a run boundary.

    Averaging is what makes a lag-tolerant comparison possible, but a window laid
    across the whole series will happily average the tail of one car with the head
    of the next. That is not a smoothed measurement of anything; on segment 21 it
    made the 3 s p90 worse than the instantaneous one. So the window is confined
    to runs of frames that are contiguous and belong to the same pairing.
    """
    if n <= 1:
        return x.copy()
    out = np.full_like(x, np.nan)
    for idx in (runs if runs is not None else [np.arange(len(x))]):
        if len(idx) < n:          # a run shorter than the window has no centred average
            continue
        seg = x[idx]
        ok = np.isfinite(seg).astype(float)
        v = np.where(np.isfinite(seg), seg, 0.0)
        k = np.ones(n)
        ssum, c = np.convolve(v, k, "same"), np.convolve(ok, k, "same")
        avg = np.where(c > 0, ssum / np.maximum(c, 1e-9), np.nan)
        out[idx] = np.where(c >= 0.6 * n, avg, np.nan)
    return out


def stats(err: np.ndarray) -> dict:
    e = err[np.isfinite(err)]
    if e.size == 0:
        return {"n": 0, "bias": float("nan"), "mae": float("nan"),
                "p50": float("nan"), "p90": float("nan")}
    return {"n": int(e.size), "bias": float(np.mean(e)), "mae": float(np.mean(np.abs(e))),
            "p50": float(np.median(np.abs(e))), "p90": float(np.percentile(np.abs(e), 90))}


def shift(x: np.ndarray, lag: int) -> np.ndarray:
    """x delayed by `lag` frames (positive = our series happens later)."""
    out = np.full_like(x, np.nan)
    if lag == 0:
        return x.copy()
    if lag > 0:
        out[lag:] = x[:-lag]
    else:
        out[:lag] = x[-lag:]
    return out


def main() -> None:
    a = parse_args()
    ours = ours_lead(read_csv(Path(a.ranges)), a.lane_half_width_m, a.max_range_m)
    radar = radar_lead(read_csv(Path(a.radar)), a.lane_half_width_m, a.max_range_m,
                       a.dedup_m, a.min_target_kmh)
    ego_map = {int(r["frame_idx"]): num(r, "ego_visual_kmh")
               for r in read_csv(Path(a.ego_speed))}
    gt = read_csv(Path(a.gt))
    can_map = {i: num(r, "can_kmh") for i, r in enumerate(gt)}

    common = sorted(set(ours) & set(radar))
    if not common:
        raise SystemExit("no frame has a lead on both sides")
    ok_lat = [i for i in common if abs(ours[i]["lat_m"] - radar[i]["lat_m"]) <= a.max_dlat_m]
    # One-to-one on (our track, radar object). Both directions matter: without it
    # two of our tracks claimed the same radar object on segment 21 and returned
    # range ratios of 0.94 and 1.15 for what could only be one car.
    votes = Counter((ours[i]["track_id"], radar[i]["obj"]) for i in ok_lat)
    taken_t, taken_o, accept = set(), set(), set()
    for (t, o), n in votes.most_common():
        if t in taken_t or o in taken_o or n < a.min_pair_frames:
            continue
        taken_t.add(t); taken_o.add(o); accept.add((t, o))
    frames = [i for i in ok_lat if (ours[i]["track_id"], radar[i]["obj"]) in accept]

    print(f"\n=== {a.label or Path(a.ranges).parent.name} ===")
    print(f"frames: in-lane object on both sides {len(common)} -> lateral agreement "
          f"{len(ok_lat)} -> one-to-one track<->object pairing keeps {len(frames)} "
          f"in {len(accept)} pairs")
    if len(frames) < 30:
        raise SystemExit("too few paired frames to say anything")

    fi = np.array(frames)
    g = lambda src, k: np.array([src[i][k] for i in frames], dtype=float)
    r_ours, r_rad = g(ours, "range_m"), g(radar, "range_m")
    lat_ours, lat_rad = g(ours, "lat_m"), g(radar, "lat_m")
    v_ours, v_rad = g(ours, "abs_kmh"), g(radar, "abs_kmh")
    rel_ours, rel_rad = g(ours, "rel_ms"), g(radar, "rel_ms")
    sens, t_s = g(ours, "sens"), g(ours, "t_s")
    py_row = None
    if a.tracks:
        tj = json.loads(Path(a.tracks).read_text(encoding="utf-8"))["tracks"]
        py_map = {(int(k), o["frame"]): o["py"] for k, t in tj.items() for o in t["obs"]}
        got = [py_map.get((ours[i]["track_id"], i)) for i in frames]
        if all(v is not None for v in got):
            py_row = np.array(got, dtype=float)
        else:
            print(f"warn: {sum(v is None for v in got)} frames missing a ground point row; "
                  f"geometry solve skipped")
    ego_ours = np.array([ego_map.get(i, np.nan) for i in frames])
    ego_can = np.array([can_map.get(i, np.nan) for i in frames])
    fps = 1.0 / float(np.median(np.diff(t_s))) if len(t_s) > 2 else 20.0

    res = {"label": a.label, "n_frames": len(frames), "fps": fps}

    # ---------------------------------------------------------------- range
    ratio = r_rad / r_ours
    res["range"] = {"bias_m": float(np.mean(r_ours - r_rad)),
                    "mae_m": float(np.mean(np.abs(r_ours - r_rad))),
                    "ratio_median": float(np.median(ratio)),
                    "radar_min_m": float(r_rad.min()), "radar_max_m": float(r_rad.max())}
    print(f"\n-- range --  radar spans {r_rad.min():.1f}-{r_rad.max():.1f} m")
    print(f"   ours - radar : bias {np.mean(r_ours - r_rad):+.2f} m   "
          f"MAE {np.mean(np.abs(r_ours - r_rad)):.2f} m")
    print(f"   radar / ours : median {np.median(ratio):.3f}   "
          f"IQR {np.percentile(ratio,25):.3f}-{np.percentile(ratio,75):.3f}")
    print(f"{'band (m)':>12s} {'n':>5s} {'ours':>7s} {'radar':>7s} {'ratio':>7s}")
    bands = []
    for lo, hi in zip([0, 10, 15, 20, 30, 45], [10, 15, 20, 30, 45, 90]):
        m = (r_rad >= lo) & (r_rad < hi)
        if m.sum() < 5:
            continue
        bands.append({"lo": lo, "hi": hi, "n": int(m.sum()),
                      "ours": float(np.median(r_ours[m])), "radar": float(np.median(r_rad[m])),
                      "ratio": float(np.median(ratio[m]))})
        print(f"{f'{lo}-{hi}':>12s} {m.sum():5d} {np.median(r_ours[m]):7.2f} "
              f"{np.median(r_rad[m]):7.2f} {np.median(ratio[m]):7.3f}")
    res["range"]["bands"] = bands

    # Solve the camera's forward-distance model from radar range and the ground
    # point's PIXEL ROW: d_radar + delta = A / (py - y_h). Nothing of ours enters
    # except py, so this is an external measurement of our own geometry rather
    # than a comparison of two guesses. delta is the radar-to-camera mounting
    # offset (radar on the bumper, camera on the screen); it is additive and would
    # otherwise be absorbed into A, so it is carried as a nuisance parameter.
    # Residuals are taken in pixels because that is where the noise lives.
    if py_row is not None:
        from scipy.optimize import least_squares

        def solve(fix_yh=None, free_delta=True):
            def resid(p):
                A = p[0]
                yh = fix_yh if fix_yh is not None else p[1]
                dl = p[-1] if free_delta else 0.0
                return (yh + A / np.maximum(r_rad + dl, 0.5)) - py_row
            x0 = [1200.0] + ([float(py_row.min()) - 20] if fix_yh is None else []) \
                          + ([1.0] if free_delta else [])
            lo = [200.0] + ([200.0] if fix_yh is None else []) + ([-3.0] if free_delta else [])
            hi = [6000.0] + ([float(py_row.min()) - 2] if fix_yh is None else []) \
                          + ([5.0] if free_delta else [])
            sol = least_squares(resid, x0, bounds=(lo, hi))
            A = float(sol.x[0])
            yh = float(fix_yh if fix_yh is not None else sol.x[1])
            dl = float(sol.x[-1]) if free_delta else 0.0
            r = resid(sol.x)
            return A, yh, dl, float(np.sqrt(np.mean(r ** 2)))

        # If only our horizon was supplied, our own A follows from the same pixels,
        # which keeps the two sides on identical data.
        if a.y_h_ours > 0 and a.a_ours <= 0:
            a.a_ours = float(np.median(r_ours * (py_row - a.y_h_ours)))
        A_r, yh_r, dl_r, rms_r = solve()
        print(f"\n-- geometry solved from radar + ground-point row --")
        print(f"{'model':38s} {'A=h*f':>7s} {'y_h':>7s} {'bumper':>7s} {'rms px':>7s}")
        print(f"{'free A, y_h, bumper offset':38s} {A_r:7.0f} {yh_r:7.1f} {dl_r:+7.2f} {rms_r:7.2f}")
        res["geometry"] = {"A_radar": A_r, "y_h_radar": yh_r,
                           "bumper_offset_m": dl_r, "rms_px": rms_r}
        if a.y_h_ours > 0:
            A_f, yh_f, dl_f, rms_f = solve(fix_yh=a.y_h_ours)
            print(f"{'y_h forced to ours (%.1f)' % a.y_h_ours:38s} {A_f:7.0f} {yh_f:7.1f} "
                  f"{dl_f:+7.2f} {rms_f:7.2f}")
            res["geometry"]["forced_to_ours"] = {"A": A_f, "bumper_offset_m": dl_f, "rms_px": rms_f}
            # A horizon that only fits by demanding an impossible mounting offset is
            # rejected by the data, not merely different from ours.
            print(f"   forcing our horizon costs {rms_f - rms_r:+.2f} px of residual and "
                  f"needs a {dl_f:+.2f} m bumper offset")
        if a.a_ours > 0:
            print(f"   ours: A {a.a_ours:.0f} ({a.a_ours / A_r:.3f}x radar), "
                  f"y_h {a.y_h_ours:.1f} ({a.y_h_ours - yh_r:+.1f} px vs radar)")
            res["geometry"].update({"A_ours": a.a_ours, "y_h_ours": a.y_h_ours,
                                    "A_ratio": a.a_ours / A_r})

    # ---------------------------------------------------------------- speed
    d_ego = ego_ours - ego_can
    d_rel = 3.6 * (rel_ours - rel_rad)
    d_abs = v_ours - v_rad
    print(f"\n-- target absolute speed --  radar spans {v_rad.min():.1f}-{v_rad.max():.1f} km/h")
    print(f"   error decomposition (they must sum, and do to "
          f"{np.nanmax(np.abs(d_abs - (d_ego + d_rel))):.3f} km/h):")
    for tag, e in (("ego term  (odometer vs CAN)", d_ego),
                   ("geom term (3.6 * d rel)   ", d_rel),
                   ("total     (abs vs radar)  ", d_abs)):
        s = stats(e)
        print(f"     {tag}: bias {s['bias']:+7.2f}  MAE {s['mae']:6.2f}  p90 {s['p90']:6.2f}")
        res.setdefault("speed_terms", {})[tag.split()[0]] = s

    # Contiguous stretches of one pairing: the only spans over which averaging,
    # or a lag, means anything.
    runs, cur = [], [0]
    for j in range(1, len(fi)):
        same = (ours[frames[j]]["track_id"] == ours[frames[j - 1]]["track_id"]
                and radar[frames[j]]["obj"] == radar[frames[j - 1]]["obj"]
                and fi[j] - fi[j - 1] <= 2)
        if same:
            cur.append(j)
        else:
            runs.append(np.array(cur)); cur = [j]
    runs.append(np.array(cur))
    long_runs = [r for r in runs if len(r) >= 20]
    print(f"\n   {len(runs)} contiguous single-pairing runs "
          f"({len(long_runs)} of them >=1 s), longest {max(len(r) for r in runs)} frames")
    res["runs"] = {"n": len(runs), "longest": int(max(len(r) for r in runs))}

    # The end-to-end number uses our own ego speed; the geometry-only number swaps
    # in CAN so that a bad dash-cycle constant cannot be charged to the ground plane.
    v_geom = ego_can + 3.6 * rel_ours
    print(f"\n   averaging window (a 3 s window is what the odometer itself uses):")
    print(f"{'window':>8s} {'n':>5s} {'end-to-end MAE':>15s} {'bias':>8s} "
          f"{'geometry-only MAE':>18s} {'bias':>8s}")
    for w in [float(v) for v in a.avg_windows_s.split(",")]:
        n = max(1, int(round(w * fps)))
        se = stats(boxcar(v_ours, n, runs) - boxcar(v_rad, n, runs))
        sg = stats(boxcar(v_geom, n, runs) - boxcar(v_rad, n, runs))
        res.setdefault("speed_avg", {})[f"{w:g}s"] = {"end_to_end": se, "geometry_only": sg}
        print(f"{(f'{w:g}s' if w else 'inst'):>8s} {se['n']:5d} {se['mae']:15.2f} "
              f"{se['bias']:+8.2f} {sg['mae']:18.2f} {sg['bias']:+8.2f}")

    lag_max = int(round(a.lag_max_s * fps))

    def shift_in_runs(x, L):
        out = np.full_like(x, np.nan)
        for idx in runs:
            out[idx] = shift(x[idx], L)
        return out

    curve = [(L, stats(shift_in_runs(v_ours, L) - v_rad)["mae"])
             for L in range(-lag_max, lag_max + 1)]
    curve = [(L, m) for L, m in curve if np.isfinite(m)]
    bestL, bestM = min(curve, key=lambda z: z[1])
    zero = dict(curve).get(0, float("nan"))
    # A lag is only believable if it is also consistent across segments and does not
    # sit at the edge of the search. On nearly-constant speeds the sweep can always
    # shave the MAE by sliding one slowly-wandering error onto another, so the
    # verdict here is deliberately weak and the caller is expected to compare signs.
    edge = abs(bestL) >= lag_max - 1
    print(f"   lag sweep: best {bestL:+d} frames ({bestL/fps:+.2f} s) MAE {bestM:.2f}; "
          f"zero lag MAE {zero:.2f}"
          + ("  -> at the edge of the search, treat as unresolved" if edge
             else "  -> improves by %.0f%%, check the sign against other segments"
                  % (100 * (1 - bestM / zero)) if bestM < 0.9 * zero
             else "  -> no meaningful delay"))
    res["lag"] = {"best_frames": int(bestL), "best_s": bestL / fps,
                  "best_mae": float(bestM), "zero_mae": float(zero),
                  "curve": [[int(L), float(m)] for L, m in curve]}

    # ------------------------------------------- does our own far-range flag work?
    print(f"\n-- against the pipeline's own sensitivity flag --")
    for tag, m in (("near sens<=0.8", sens <= 0.8), ("far  sens> 0.8", sens > 0.8)):
        if m.sum() < 5:
            continue
        s = stats(np.where(m, d_abs, np.nan))
        print(f"   {tag}: n={s['n']:5d}  speed MAE {s['mae']:6.2f}  "
              f"range ratio {np.median(ratio[m]):.3f}")
        res.setdefault("by_sens", {})[tag.split()[0]] = {
            "speed": s, "range_ratio": float(np.median(ratio[m]))}

    if a.dump_csv:
        Path(a.dump_csv).parent.mkdir(parents=True, exist_ok=True)
        with open(a.dump_csv, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["frame_idx", "t_s", "track_id", "radar_obj", "run",
                        "range_ours_m", "range_radar_m", "py",
                        "lat_ours_m", "lat_radar_m", "rel_ours_ms", "rel_radar_ms",
                        "abs_ours_kmh", "abs_radar_kmh", "ego_ours_kmh", "ego_can_kmh",
                        "sens_m_per_px"])
            run_of = {int(j): k for k, idx in enumerate(runs) for j in idx}
            for k, i in enumerate(frames):
                w.writerow([i, f"{t_s[k]:.3f}", ours[i]["track_id"], radar[i]["obj"],
                            run_of.get(k, -1),
                            f"{r_ours[k]:.2f}", f"{r_rad[k]:.2f}",
                            "" if py_row is None else f"{py_row[k]:.2f}",
                            f"{lat_ours[k]:.2f}", f"{lat_rad[k]:.2f}",
                            f"{rel_ours[k]:.3f}", f"{rel_rad[k]:.3f}",
                            f"{v_ours[k]:.2f}", f"{v_rad[k]:.2f}",
                            f"{ego_ours[k]:.2f}", f"{ego_can[k]:.2f}",
                            f"{sens[k]:.3f}"])
        print(f"wrote {a.dump_csv}")

    if a.out_json:
        Path(a.out_json).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out_json).write_text(json.dumps(res, indent=2), encoding="utf-8")
        print(f"\nwrote {a.out_json}")


if __name__ == "__main__":
    main()
