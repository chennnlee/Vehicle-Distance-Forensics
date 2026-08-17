#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Render dc007_ref SHARP point cloud + RANSAC ground plane for the deck."""
import sys
sys.path.insert(0, '/home/s11244/code/114/Vehicle-Distance-Forensics')
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from utils.pointcloud_io import load_point_cloud_points

pts, cols, _meta = load_point_cloud_points(
    '/home/s11244/code/114/Vehicle-Distance-Forensics/data/output/sharp_gaussians/dc007_ref.ply')
print('points:', pts.shape, 'colors:', None if cols is None else cols.shape)

# keep the road-scene volume only (sky/far billboard kills the perspective)
m = (pts[:, 2] > 0.8) & (pts[:, 2] < 60.0) & (np.abs(pts[:, 0]) < 28.0)
pts, cols = pts[m], (cols[m] if cols is not None else None)
if len(pts) > 260000:
    idx = np.random.RandomState(0).choice(len(pts), 260000, replace=False)
    pts = pts[idx]
    cols = cols[idx] if cols is not None else None

# simple RANSAC: y = a*x + b*z + c (camera coords, y down)
rng = np.random.RandomState(1)
best = None
depth = pts[:, 2]
thr = 0.015 * np.median(depth)
for _ in range(300):
    i = rng.choice(len(pts), 3, replace=False)
    P = pts[i]
    A = np.column_stack([P[:, 0], P[:, 2], np.ones(3)])
    try:
        coef = np.linalg.solve(A, P[:, 1])
    except np.linalg.LinAlgError:
        continue
    resid = np.abs(pts[:, 0] * coef[0] + pts[:, 2] * coef[1] + coef[2] - pts[:, 1])
    inl = (resid < thr * (0.3 + pts[:, 2] / np.median(depth))).sum()
    if best is None or inl > best[1]:
        best = (coef, inl)
coef = best[0]
print('plane y = %.4f x + %.4f z + %.4f  inliers %d/%d' % (coef[0], coef[1], coef[2], best[1], len(pts)))

# drop points far below the fitted ground (mirror/noise) and too high above
resid_all = pts[:, 0] * coef[0] + pts[:, 2] * coef[1] + coef[2] - pts[:, 1]  # + above ground
keep = (resid_all > -0.6) & (resid_all < 9.0)
pts, cols = pts[keep], (cols[keep] if cols is not None else None)

fig = plt.figure(figsize=(10.8, 6.4), dpi=150)
ax = fig.add_subplot(111, projection='3d')
c = np.clip(cols / 255.0, 0, 1) if cols is not None else 'gray'
ax.scatter(pts[:, 0], pts[:, 2], -pts[:, 1], s=0.5, c=c, linewidths=0, rasterized=True)
resid2 = pts[:, 0] * coef[0] + pts[:, 2] * coef[1] + coef[2] - pts[:, 1]
road = pts[np.abs(resid2) < 0.35]
xr = np.linspace(np.percentile(road[:, 0], 3), np.percentile(road[:, 0], 97), 12)
zr = np.linspace(np.percentile(road[:, 2], 1), np.percentile(road[:, 2], 99), 12)
X, Z = np.meshgrid(xr, zr)
Y = coef[0] * X + coef[1] * Z + coef[2]
ax.plot_surface(X, Z, -Y, alpha=0.20, color='#F5A800', edgecolor='none')
ax.set_xlim(pts[:, 0].min(), pts[:, 0].max())
ax.set_ylim(pts[:, 2].min(), pts[:, 2].max())
ax.set_zlim((-pts[:, 1]).min(), (-pts[:, 1]).max())
ax.view_init(elev=30, azim=-100)
ax.set_box_aspect((1.7, 2.8, 0.6))
ax.set_axis_off()
ax.set_position([-0.35, -0.42, 1.7, 1.84])
tmp_path = '/tmp/sharp_pc_raw.png'
fig.savefig(tmp_path, facecolor='white', dpi=200)
from PIL import Image, ImageChops
im = Image.open(tmp_path).convert('RGB')
bg = Image.new('RGB', im.size, (255, 255, 255))
bbox = ImageChops.difference(im, bg).getbbox()
if bbox:
    pad = 14
    bbox = (max(0, bbox[0]-pad), max(0, bbox[1]-pad),
            min(im.width, bbox[2]+pad), min(im.height, bbox[3]+pad))
    im = im.crop(bbox)
im.save('/home/s11244/tmp/pptx_build/assets/sharp_pointcloud.png')
print('saved sharp_pointcloud.png', im.size)
