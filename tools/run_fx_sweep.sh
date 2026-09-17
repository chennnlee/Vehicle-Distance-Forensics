#!/usr/bin/env bash
# What does the focal length a metric model is handed actually buy?
#
# metric3d_v2 and da3_metric both take fx as an input and scale their metres by it.
# Their raw scores in docs/DEPTH_MODEL_BENCHMARK.md were obtained with the default
# fx = 0.7955*width = 926 px (SHARP's 30 mm rule on a 16:9 frame; on this 4:3 camera
# SHARP itself uses 1009 px), which happens to be within 2% of this camera's
# documented 910 px -- so the raw column may be measuring the assumption rather than
# the model. Sweeping fx separates the two. Resumable like the blind run.
set -u
cd "$(dirname "$0")/.."
P=${VDF_PY:-~/venvs/depthbench/bin/python}
OUT=data/output/depth_benchmark
T=b0c9d2329ad1606b_2018-07-30--13-44-30_10
if [ -d /tmp/c2k19 ]; then FR=/tmp/c2k19; else FR=data/input/_frames_cache/c2k19; fi
for spec in "metric3d_v2 650" "metric3d_v2 910" "metric3d_v2 1200" "da3_metric 650" "da3_metric 1200"; do
  set -- $spec; M=$1; FX=$2
  o="$OUT/fx${FX}_${T}__${M}.csv"
  [ -s "$o" ] && { echo "skip $M fx=$FX"; continue; }
  echo "run  $M fx=$FX"
  $P tools/depth_model_benchmark.py run --model "$M" --fx "$FX" \
     --frames "$FR/$T/frames" --frame-glob "{frame}.jpg" \
     --targets "$OUT/paired_$T.csv" --out "$o" 2>&1 | grep -E "^wrote|frames  \(" | tail -1
done
echo FX_SWEEP_DONE
