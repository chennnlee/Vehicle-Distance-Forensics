#!/usr/bin/env bash
# Depth readings for the AV2 logs whose marking calibration passed. Resumable: a log/model
# whose CSV exists is skipped, so an interrupted run continues by invoking this again.
#
#   bash tools/run_av2_depth.sh <log id> [<log id> ...]
#
# The models are fed the project's DEFAULT focal length, never Argoverse's published one --
# the marking constant absorbs the difference (docs/TERRY_RESEARCH_RECORD.md table 5-4), and
# feeding the factory value would put calibration data inside the measurement.
set -u
cd "$(dirname "$0")/.."
P=${VDF_PY:-~/venvs/depthbench/bin/python}
OUT=data/output/av2_depth
MODELS=${MODELS:-"metric3d_v2 da3_metric"}
for L in "$@"; do
  [ -s "$OUT/targets_$L.csv" ] || $P tools/av2_targets.py --log "data/input/av2/$L" \
      --calib data/output/av2_marking/calib.json --out "$OUT/targets_$L.csv"
  for M in $MODELS; do
    o="$OUT/pred_${L}__${M}.csv"
    if [ -s "$o" ]; then echo "  skip $L $M"; continue; fi
    echo "== $L $M"
    $P tools/depth_model_benchmark.py run --model "$M" \
       --frames "data/input/av2/$L/pinhole" --frame-glob "{frame}.jpg" \
       --targets "$OUT/targets_$L.csv" --out "$o" 2>&1 | grep -E "^wrote"
  done
done
echo AV2_DEPTH_DONE
