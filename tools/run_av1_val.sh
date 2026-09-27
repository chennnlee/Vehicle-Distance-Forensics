#!/usr/bin/env bash
# Finish the Argoverse 1 validation run unattended, with every parameter fixed before it starts.
#
# Restartable by design: the download skips chunks already on disk, the extraction skips files
# already written, and av1_prepare skips frames already rectified. If the machine sleeps (WSL
# freezes with it), run this again and it picks up where it stopped.
#
# It does NOT touch the ground truth. av1_fetch excludes per_sweep_annotations_amodal unless
# asked for it, so the cuboids stay inside the tar until predictions have been sealed.
set -u
cd "$(dirname "$0")/.."
exec >> av1_overnight.log 2>&1
echo "=== run_av1_val start $(date '+%F %T') ==="

# Do not fight a download already in flight for the same chunks.
for pid in $(pgrep -f "av1_fetch.py --tar tracking_val" || true); do
  [ "$pid" = "$$" ] && continue
  echo "waiting for the running fetch (pid $pid)"
  while kill -0 "$pid" 2>/dev/null; do sleep 60; done
done

python3 tools/av1_fetch.py --tar tracking_val_v1.1.tar.gz --workers 8 --extract || exit 1

# The selection rule, declared in advance and identical to the one AV2 used.
python3 tools/av1_select.py --min-speed 8 --max-yaw-rate 3 --min-seconds 8 \
    --out-list tools/av1_val_logs.txt --out-csv data/output/av1_marking/windows.csv || exit 1

# The measurement. Rows seed from image geometry and extend by the provisional A; the factory
# constant is withheld by av1_prepare --hide-factory, which av1_marking_run passes.
python3 tools/av1_marking_run.py --logs-file tools/av1_val_logs.txt \
    --windows data/output/av1_marking/windows.csv \
    --seed-rows 822,912,1008 --band 700,1100 --dash-m 3.05 --cycle-set 12.19,14.63 \
    --out data/output/av1_marking/calib.json
echo "=== run_av1_val done $(date '+%F %T') ==="

SUM=$(python3 - <<'PY'
import json, pathlib
p = pathlib.Path("data/output/av1_marking/calib.json")
if not p.exists():
    print("calib.json missing -- see av1_overnight.log"); raise SystemExit
d = json.loads(p.read_text())
ok = [r for r in d if r.get("status") == "ok"]
print(f"{len(ok)}/{len(d)} logs produced an answer (factory value still withheld)")
for r in ok:
    print(f"  {r['log'][:8]}  A {r['A_marking']:6.0f}  spread {r['spread']*100:4.1f}%  {r['pass']}")
for r in d:
    if r.get("status") != "ok":
        print(f"  {r['log'][:8]}  refused: {r.get('status')}")
PY
)
echo "$SUM"

DESK=$(ls -d /mnt/c/Users/*/OneDrive/Desktop 2>/dev/null | head -1)
[ -n "$DESK" ] && printf 'Argoverse 1 validation run finished %s\n\n%s\n\nNext: open the Claude Code conversation in Vehicle-Distance-Forensics.\nLog: av1_overnight.log\n' "$(date '+%F %T')" "$SUM" > "$DESK/AV1_跑完了.txt"
powershell.exe -NoProfile -Command "Add-Type -AssemblyName System.Windows.Forms; \$n=New-Object System.Windows.Forms.NotifyIcon; \$n.Icon=[System.Drawing.SystemIcons]::Information; \$n.Visible=\$true; \$n.ShowBalloonTip(30000,'Vehicle-Distance-Forensics','AV1 跑完了 - 桌面有結果','Info'); Start-Sleep -Seconds 15" 2>/dev/null || true
