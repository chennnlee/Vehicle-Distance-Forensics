"""Export a comma2k19 segment's factory radar onto the video frame timebase.

`processed_log/CAN/radar` is the car's own DSU radar: seven columns, of which
the first three are longitudinal distance (m), lateral distance (m) and relative
speed (m/s), and the sixth is the CAN address 0x210-0x21F identifying which of
16 reusable track slots the return came from. The semantics are not documented
in the dataset, but they verify themselves: stationary roadside objects come
back at exactly minus the CAN wheel speed.

Two details matter for making it usable as ground truth:

  * A slot only appears in the scans where it currently holds a target, so
    "take the radar scan nearest this frame" shreds one continuous track into
    fragments. Each slot therefore gets its own series and is sampled per frame
    with a one-frame nearest-neighbour tolerance -- no interpolation, so a slot
    that genuinely drops out stays dropped out.
  * The absolute speed of the target is written out too, as ego CAN speed plus
    the relative speed, because that is the quantity pipeline B reports.
"""
import argparse, io, zipfile, csv, numpy as np

ap = argparse.ArgumentParser()
ap.add_argument('--zip', required=True)
ap.add_argument('--segment', required=True, help="'<route>|<n>'")
ap.add_argument('--out', required=True)
ap.add_argument('--tol-s', type=float, default=0.05)
a = ap.parse_args()

route, num = a.segment.rsplit('|', 1)
z = zipfile.ZipFile(a.zip)
chunk = z.namelist()[0].split('/')[0]
base = f'{chunk}/{route}/{num}'
rd = lambda k: np.load(io.BytesIO(z.read(f'{base}/{k}')), allow_pickle=False)

ft = rd('global_pose/frame_times')
rt, rv = rd('processed_log/CAN/radar/t'), rd('processed_log/CAN/radar/value')
st, sv = rd('processed_log/CAN/speed/t'), rd('processed_log/CAN/speed/value').reshape(-1)
o = np.argsort(st)
ego_f = np.interp(ft, st[o], sv[o])
t0 = ft[0]

rows = []
for slot in np.unique(rv[:, 5]):
    k = rv[:, 5] == slot
    ts, vals = rt[k], rv[k]
    o2 = np.argsort(ts); ts, vals = ts[o2], vals[o2]
    idx = np.searchsorted(ts, ft)
    for i, tf in enumerate(ft):
        cand = [j for j in (idx[i] - 1, idx[i]) if 0 <= j < len(ts)]
        if not cand:
            continue
        j = min(cand, key=lambda j: abs(ts[j] - tf))
        if abs(ts[j] - tf) > a.tol_s:
            continue
        d, lat, vrel = vals[j, 0], vals[j, 1], vals[j, 2]
        rows.append([i, tf - t0, int(slot), d, lat, vrel, ego_f[i] * 3.6, (ego_f[i] + vrel) * 3.6])

rows.sort(key=lambda r: (r[0], r[2]))
with open(a.out, 'w', newline='', encoding='utf-8') as fh:
    w = csv.writer(fh)
    w.writerow(['frame_idx', 't_s', 'slot', 'radar_range_m', 'radar_lat_m',
                'radar_rel_ms', 'can_ego_kmh', 'radar_abs_kmh'])
    for r in rows:
        w.writerow([r[0], f'{r[1]:.4f}', r[2], f'{r[3]:.2f}', f'{r[4]:.2f}',
                    f'{r[5]:.3f}', f'{r[6]:.3f}', f'{r[7]:.3f}'])
print(f'{a.out}: {len(rows)} returns, {len(set(r[0] for r in rows))}/{len(ft)} frames covered')
