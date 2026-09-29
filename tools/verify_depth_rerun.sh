#!/usr/bin/env bash
# Re-run the depth models from the frames and compare against the archived predictions.
#
# The benchmark numbers in docs/DEPTH_MODEL_BENCHMARK.md are computed from prediction CSVs
# written in September 2026. Re-running the ANALYSIS re-reads those CSVs, so it proves the
# analysis is deterministic and nothing about the inference. This script closes that gap:
# it runs the five backends again over the same frames and target pixels, into a separate
# directory, and diffs.
#
#   bash tools/verify_depth_rerun.sh [out-dir]        # default data/output/depth_rerun
#
# Resumable: a model/segment whose output already exists is skipped, so an interrupted run
# continues by invoking it again. The log is written inside the repo on purpose -- /tmp
# does not survive a WSL restart, and a previous attempt at
# this check was lost that way.
set -u
cd "$(dirname "$0")/.."
P=${VDF_PY:-~/venvs/depthbench/bin/python}
OUT=data/output/depth_benchmark
NEW=${1:-data/output/depth_rerun}
LOG=depth_rerun.log
mkdir -p "$NEW"

if [ -d /tmp/c2k19 ]; then FR=/tmp/c2k19
elif [ -d data/input/_frames_cache/c2k19 ]; then FR=data/input/_frames_cache/c2k19
else echo "找不到影格:見 docs/DEPTH_MODEL_BENCHMARK.md §12.5"; exit 1; fi

[ -f "$HOME/miniconda3/lib/libstdc++.so.6" ] && export LD_PRELOAD=$HOME/miniconda3/lib/libstdc++.so.6
SEGS="b0c9d2329ad1606b_2018-07-30--13-44-30_10 b0c9d2329ad1606b_2018-08-15--09-01-03_21"
MODELS="metric3d_v2 da3_metric unidepth_v2 depth_anything_v2_vits depth_pro"

{
echo "frames: $FR   out: $NEW   started: $(date -Is)"
for T in $SEGS; do
  for M in $MODELS; do
    o="$NEW/unf_${T}__${M}.csv"
    [ -s "$o" ] && { echo "skip $M $T"; continue; }
    echo "=== $M  $T  $(date +%H:%M:%S) ==="
    $P tools/depth_model_benchmark.py run --model "$M" \
       --frames "$FR/$T/frames" --frame-glob "{frame}.jpg" \
       --targets "$OUT/targets_$T.csv" --out "$o" 2>&1 | tail -2
  done
done

echo
echo "=== 與封存的 unf_* 比對 ==="
$P - "$OUT" "$NEW" <<'PY'
import csv, sys, glob, os
import numpy as np
old_d, new_d = sys.argv[1], sys.argv[2]
def col(p, c):
    with open(p, newline="", encoding="utf-8") as f:
        return np.array([float(r[c]) for r in csv.DictReader(f)])
print(f"{'檔':<62}{'n':>6}{'逐位元':>8}{'max|Δ|':>12}{'max 相對':>11}")
for n in sorted(os.path.basename(p) for p in glob.glob(f"{new_d}/unf_*.csv")):
    a, b = f"{old_d}/{n}", f"{new_d}/{n}"
    if not os.path.exists(a):
        print(f"{n[:60]:<62}{'':>6}{'封存缺':>8}"); continue
    x, y = col(a, "pred"), col(b, "pred")
    if len(x) != len(y):
        print(f"{n[:60]:<62}{len(y):>6}{'列數不同':>8}"); continue
    same = open(a,'rb').read() == open(b,'rb').read()
    d = np.abs(x - y)
    print(f"{n[:60]:<62}{len(y):>6}{'✅' if same else '✗':>8}"
          f"{d.max():>12.3e}{(d/np.maximum(np.abs(x),1e-9)).max()*100:>10.4f}%")
PY
echo "VERIFY_DONE $(date -Is)"
} >> "$LOG" 2>&1
