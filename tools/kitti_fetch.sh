#!/usr/bin/env bash
# KITTI raw drives used for the cross-camera attempt (docs/TERRY_RESEARCH_RECORD.md 6.5).
# unzip is not installed here; extract with python -c "import zipfile,glob;[zipfile.ZipFile(z).extractall('.') for z in glob.glob('*.zip')]"
cd /home/terry/Vehicle-Distance-Forensics/data/input/kitti
B=https://s3.eu-central-1.amazonaws.com/avg-kitti/raw_data
for D in 2011_09_26_drive_0015 2011_09_26_drive_0027 2011_09_26_drive_0032; do
  [ -d "${D}_sync" ] || { curl -sL -o ${D}_sync.zip $B/$D/${D}_sync.zip && unzip -q -o ${D}_sync.zip && rm ${D}_sync.zip; }
  [ -f "${D}_tracklets.zip" ] || curl -sL -o ${D}_tracklets.zip $B/$D/${D}_tracklets.zip
  unzip -q -o ${D}_tracklets.zip 2>/dev/null
  echo "done $D"
done
curl -sL -o calib.zip https://s3.eu-central-1.amazonaws.com/avg-kitti/raw_data/2011_09_26_calib.zip && unzip -q -o calib.zip && echo "calib ok"
echo KITTI_DONE
