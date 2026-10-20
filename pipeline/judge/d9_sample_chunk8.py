"""D9 spot-check sample of comma2k19_chunk8 labels (written before any frame is extracted).
Rule: cells = (road_class, light) of the label table; within a cell, order segments by
sha256("d9-chunk8-20261020|" + segment_id) and take the first k. Night and unknown cells are oversampled."""
import csv, hashlib, json, sys
from pathlib import Path
LAB = Path.home() / "code/114/monocular-driving-distance/benchmark/splits/batches/comma2k19_chunk8_labels.csv"
K = {("ca_highway", "day"): 12, ("ca_highway", "night"): 6, ("ca_local", "day"): 10,
     ("ca_local", "night"): 3, ("unknown", "day"): 6, ("unknown", "night"): 3}
rows = list(csv.DictReader(open(LAB, encoding="utf-8")))
key = lambda s: hashlib.sha256(("d9-chunk8-20261020|" + s).encode()).hexdigest()
out = []
for cell, k in K.items():
    segs = sorted((r for r in rows if (r["road_class"], r["light"]) == cell), key=lambda r: key(r["segment_id"]))
    out += [dict(r, cell_n=len(segs)) for r in segs[:k]]
out.sort(key=lambda r: key(r["segment_id"]))          # page order mixes the cells
Path("sample.json").write_text(json.dumps({"labels_file_sha256": hashlib.sha256(LAB.read_bytes()).hexdigest(),
                                           "rule": __doc__, "k": {f"{a}/{b}": v for (a, b), v in K.items()},
                                           "segments": out}, indent=1), encoding="utf-8")
print(len(out), len({r['segment_id'].rsplit('_', 1)[0] for r in out}), "routes")
