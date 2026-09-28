#!/usr/bin/env bash
# The whole marking-only calibration for Argoverse 1, from the downloaded tar to the table
# that compares A against each log's factory calibration.
#
#   bash tools/run_av1_marking.sh
#
# Rows and band are fixed before any log is looked at, from the screen in
# tools/marking_method_screen.py: at A = h*fy ~ 2290 and a horizon near row 610, rows
# 760-1060 sit at 15.4 m down to 5.1 m, the 13-row band covers 1.24 m at the far row
# against a 3.05 m MUTCD dash, and the widest pair is 30 frames of travel at 30 Hz.
set -eu
cd "$(dirname "$0")/.."
P=${VDF_PY:-python3}
ROWS=${ROWS:-760,860,960,1060}
BAND=${BAND:-740,1080}
OUT=${OUT:-data/output/av1_marking}
mkdir -p "$OUT"

$P tools/av1_fetch.py --tar "${TAR:-tracking_val_v1.1.tar.gz}" --extract
$P tools/av1_select.py --out-list "$OUT/logs.txt" --out-csv "$OUT/windows.csv" | tail -40

while IFS=, read -r log frames vmed straight t0 t1 vwin; do
  [ "$log" = "log" ] && continue
  grep -qx "$log" "$OUT/logs.txt" || continue
  $P tools/av1_prepare.py --log "data/input/av1/$log" --t0 "$t0" --t1 "$t1" | sed 's/^/  /'
done < "$OUT/windows.csv"

$P tools/av2_marking_calib.py --logs-file "$OUT/logs.txt" --av2-root data/input/av1 \
   --rows "$ROWS" --band "$BAND" --out "$OUT/calib.json"
echo AV1_MARKING_DONE
