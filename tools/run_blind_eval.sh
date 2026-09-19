#!/usr/bin/env bash
# Blind re-evaluation of the depth benchmark. Resumable: a model/segment whose
# output CSV already exists is skipped, so an interrupted run (WSL shutdown,
# laptop sleep) is continued by simply invoking this again.
#
#   bash tools/run_blind_eval.sh
#
# Three passes, all scored later against radar but none using radar as input:
#   unf_*        the UNFILTERED pairing set -- no row is dropped using the truth's value
#   anchor_*     depth read at road points whose distance comes from the lane markings
#                (Method C geometry), which is what supplies the scale constant k
#   body_pred_*  depth read at each paired car's body centre instead of its ground
#                contact (docs sections 14 and 19); targets from body_centre_targets.py
set -u
cd "$(dirname "$0")/.."
P=${VDF_PY:-~/venvs/depthbench/bin/python}
OUT=data/output/depth_benchmark

# Frames live in /tmp while a session is running, but /tmp does not survive a WSL
# restart. A copy is kept under data/input/_frames_cache/ (gitignored); prefer
# whichever is present so going home does not cost a re-decode.
if [ -d /tmp/c2k19 ]; then FR=/tmp/c2k19
elif [ -d data/input/_frames_cache/c2k19 ]; then FR=data/input/_frames_cache/c2k19
else echo "找不到影格:先重抽(見 docs/DEPTH_MODEL_BENCHMARK.md)"; exit 1; fi
echo "frames: $FR"
SEGS="b0c9d2329ad1606b_2018-07-30--13-44-30_10 b0c9d2329ad1606b_2018-08-15--09-01-03_21"
MODELS="metric3d_v2 unidepth_v2 da3_metric depth_anything_v2_vits depth_pro"

run () {  # $1=prefix $2=targets-prefix
  for T in $SEGS; do
    for M in $MODELS; do
      o="$OUT/$1_${T}__${M}.csv"
      if [ -s "$o" ]; then echo "  skip $1 $T $M"; continue; fi
      echo "  run  $1 $T $M"
      $P tools/depth_model_benchmark.py run --model "$M" \
         --frames "$FR/$T/frames" --frame-glob "{frame}.jpg" \
         --targets "$OUT/$2_$T.csv" --out "$o" 2>&1 | grep -E "^wrote" | sed 's/^/     /'
    done
  done
}

echo "=== pass 1/3: unfiltered pairing set ==="; run unf    targets
echo "=== pass 2/3: marking-derived road anchors ==="; run anchor roadanchor
for T in $SEGS; do
  [ -s "$OUT/body_$T.csv" ] || $P tools/body_centre_targets.py --frames-root "$FR" \
     --segments "$T" --out-dir "$OUT" 2>&1 | grep -E "rows recovered|^wrote" | sed 's/^/     /'
done
echo "=== pass 3/3: body centre ==="; run body_pred body
echo "BLIND_EVAL_DONE"
