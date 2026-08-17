#!/bin/bash
set -e
cd /home/s11244/tmp/pptx_build/assets
OUT=/home/s11244/code/114/Vehicle-Distance-Forensics/data/output

# new assets for the v2 deck
cp -f /tmp/strip_c0135.png strip_c0135.png
cp -f /tmp/c4407_cut.png c4407_cut.png
cp -f /tmp/spot4407.jpg spot4407.jpg
cp -f "$OUT/dashcam_validation/error_distribution.png" error_distribution.png
ffmpeg -y -loglevel error -ss 0.1 -i "$OUT/dashcam_demo/dc007/original_clip_h264.mp4" -frames:v 1 -qscale:v 2 dc007_ref_frame.jpg

/home/s11244/anaconda3/envs/VisionVelocity/bin/python /home/s11244/tmp/pptx_build/render_ply.py
ls -la strip_c0135.png c4407_cut.png spot4407.jpg error_distribution.png dc007_ref_frame.jpg sharp_pointcloud.png
