#!/bin/bash
set -e
cd ~/tmp/pptx_build

# node smoke test
node -e 'const g=require("pptxgenjs"); const p=new g(); console.log("pptxgenjs OK, version:", p.version || "unknown")'

OUT=~/code/114/Vehicle-Distance-Forensics/data/output
cd assets

# fix qz overlay (was clobbered by kh013's)
cp -f "$OUT/cctv_validation/qz1130221/speed_overlay.png" qz_speed_overlay.png
cp -f "$OUT/cctv_validation/qz1130221/bev_metric.png" qz_bev_metric.png

# extract candidate frames from annotated videos
ffmpeg -y -loglevel error -ss 12 -i "$OUT/report_final/kh013/speed_realtime_h264.mp4" -frames:v 1 -qscale:v 2 kh013_t12.jpg
ffmpeg -y -loglevel error -ss 25 -i "$OUT/report_final/kh013/speed_realtime_h264.mp4" -frames:v 1 -qscale:v 2 kh013_t25.jpg
ffmpeg -y -loglevel error -ss 40 -i "$OUT/report_final/kh013/speed_realtime_h264.mp4" -frames:v 1 -qscale:v 2 kh013_t40.jpg

ffmpeg -y -loglevel error -ss 2.0 -i "$OUT/dashcam_demo/dc007/range_speed_h264.mp4" -frames:v 1 -qscale:v 2 dc007_t2.jpg
ffmpeg -y -loglevel error -ss 5.0 -i "$OUT/dashcam_demo/dc007/range_speed_h264.mp4" -frames:v 1 -qscale:v 2 dc007_t5.jpg
ffmpeg -y -loglevel error -ss 9.8 -i "$OUT/dashcam_demo/dc007/range_speed_h264.mp4" -frames:v 1 -qscale:v 2 dc007_t98.jpg

ffmpeg -y -loglevel error -ss 25 -i "$OUT/dashcam_demo/dc006/range_speed_h264.mp4" -frames:v 1 -qscale:v 2 dc006_t25.jpg
ffmpeg -y -loglevel error -ss 45 -i "$OUT/dashcam_demo/dc006/range_speed_h264.mp4" -frames:v 1 -qscale:v 2 dc006_t45.jpg

ffmpeg -y -loglevel error -ss 30 -i "$OUT/cctv_validation/qz1130221/speed_realtime_h264.mp4" -frames:v 1 -qscale:v 2 qz_t30.jpg

# downscale big PNGs for slide use is not needed; just report sizes
for f in *.png *.jpg; do
  identify_size=$(python3 -c "from PIL import Image; im=Image.open('$f'); print(f'{im.width}x{im.height}')" 2>/dev/null || echo "?")
  echo "$f  $identify_size"
done
