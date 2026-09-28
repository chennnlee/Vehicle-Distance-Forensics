#!/usr/bin/env bash
# Keep looking for striped fast road, one Argoverse 1 training split at a time.
#
# The validation split refused all four of its clean logs, and one frame from each said why:
# no legal periodic dash is painted on those streets. That is a property of the material, not
# of the camera, so the answer is more road rather than another dataset. The splits are taken
# smallest first, so the first verdict arrives in about twenty minutes rather than ninety.
#
# Restartable: downloads skip chunks already on disk, extraction skips files already written,
# and a log that already has a result is not measured again.
#
#   bash tools/run_av1_train.sh [tar ...]
set -u
cd "$(dirname "$0")/.."
exec >> av1_train.log 2>&1
TARS=${@:-"tracking_train4_v1.1.tar.gz tracking_train1_v1.1.tar.gz tracking_train3_v1.1.tar.gz tracking_train2_v1.1.tar.gz"}
DESK=$(ls -d /mnt/c/Users/*/OneDrive/Desktop 2>/dev/null | head -1)

for TAR in $TARS; do
  SPLIT=$(echo "$TAR" | sed 's/tracking_//; s/_v1.1.tar.gz//')
  echo "════════ $TAR  start $(date '+%F %T') ════════"
  python3 tools/av1_fetch.py --tar "$TAR" --workers 8 --extract || { echo "fetch failed"; continue; }

  python3 tools/av1_select.py --min-speed 8 --max-yaw-rate 3 --min-seconds 8 \
      --out-list tools/av1_all_logs.txt --out-csv data/output/av1_marking/windows.csv || continue

  # Only the logs that have no result yet; everything else keeps the number it already has.
  python3 - "$SPLIT" <<'PY'
import json, pathlib, sys
root = pathlib.Path("data/output/av1_marking")
done = set()
for f in root.glob("calib*.json"):
    try:
        d = json.loads(f.read_text())
    except Exception:
        continue
    if isinstance(d, list):
        done |= {r.get("log") for r in d if isinstance(r, dict)}
sel = [l.strip() for l in open("tools/av1_all_logs.txt") if l.strip()]
new = [l for l in sel if l not in done]
pathlib.Path("tools/av1_new_logs.txt").write_text("\n".join(new) + ("\n" if new else ""))
print(f"selected {len(sel)} logs in total, {len(new)} of them new")
PY
  [ -s tools/av1_new_logs.txt ] || { echo "no new qualifying logs in $SPLIT"; continue; }

  python3 tools/av1_marking_run.py --logs-file tools/av1_new_logs.txt \
      --windows data/output/av1_marking/windows.csv \
      --seed-rows 822,912,1008 --band 700,1100 --dash-m 3.05 --cycle-set 12.19,14.63 \
      --out "data/output/av1_marking/calib_${SPLIT}.json"

  # One frame per new log, so condition (4) -- is a dash even painted? -- can be checked by eye
  # without opening the dataset. This is the cheap procedure section 6.7 prescribes.
  python3 - "$SPLIT" <<'PY'
import csv, glob, pathlib, sys
import cv2, numpy as np
split = sys.argv[1]
logs = [l.strip() for l in open("tools/av1_new_logs.txt") if l.strip()]
tiles = []
for lg in logs[:12]:
    fs = sorted(glob.glob(f"data/input/av1/{lg}/pinhole/*.jpg"))
    if not fs:
        continue
    im = cv2.imread(fs[len(fs) // 2])
    h, w = im.shape[:2]
    for y in (772, 822, 912, 1008):
        cv2.line(im, (0, y), (w, y), (0, 0, 255), 2)
    cv2.putText(im, lg[:8], (30, 120), cv2.FONT_HERSHEY_SIMPLEX, 3, (0, 255, 255), 6)
    tiles.append(cv2.resize(im, (w // 4, h // 4)))
if tiles:
    while len(tiles) % 3:
        tiles.append(np.zeros_like(tiles[0]))
    rows = [np.hstack(tiles[i:i + 3]) for i in range(0, len(tiles), 3)]
    out = pathlib.Path(f"data/output/av1_marking/frames_{split}.jpg")
    cv2.imwrite(str(out), np.vstack(rows))
    print(f"wrote {out}")
PY

  SUM=$(python3 - "$SPLIT" <<'PY'
import json, pathlib, sys
split = sys.argv[1]
p = pathlib.Path(f"data/output/av1_marking/calib_{split}.json")
if not p.exists():
    print("no result file"); raise SystemExit
d = json.loads(p.read_text())
ok = [r for r in d if r.get("status") == "ok"]
print(f"{split}: {len(ok)}/{len(d)} new logs produced an answer")
for r in ok:
    f = pathlib.Path("data/input/av1") / r["log"] / "factory_reference.json"
    fa = json.loads(f.read_text())["A_factory"] if f.exists() else float("nan")
    print(f"  {r['log'][:8]}  A {r['A_marking']:6.0f}  factory {fa:6.0f}  "
          f"ratio {r['A_marking']/fa:5.3f}  spread {r['spread']*100:4.1f}%")
for r in d:
    if r.get("status") != "ok":
        print(f"  {r['log'][:8]}  refused: {r.get('status')}")
PY
)
  echo "$SUM"
  [ -n "$DESK" ] && printf 'Argoverse 1 %s 跑完 %s\n\n%s\n\n影像: data/output/av1_marking/frames_%s.jpg\n' \
      "$SPLIT" "$(date '+%F %T')" "$SUM" "$SPLIT" > "$DESK/AV1_${SPLIT}_結果.txt"
  powershell.exe -NoProfile -Command "Add-Type -AssemblyName System.Windows.Forms; \$n=New-Object System.Windows.Forms.NotifyIcon; \$n.Icon=[System.Drawing.SystemIcons]::Information; \$n.Visible=\$true; \$n.ShowBalloonTip(30000,'AV1 $SPLIT','桌面有結果','Info'); Start-Sleep -Seconds 10" 2>/dev/null || true
  echo "════════ $TAR  done $(date '+%F %T') ════════"
done
echo "all splits finished $(date '+%F %T')"
