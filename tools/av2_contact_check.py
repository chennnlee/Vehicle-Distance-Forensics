#!/usr/bin/env python3
"""Is a distance bias in the pixel we pick, or in the geometry that turns it into metres?

`av2_eval.py` scores metres against metres, which cannot tell the two apart: a contact
point a few px too high and a scale constant a few percent too large move the answer the
same way.  This projects each matched cuboid's nearest ground corner back into the image
and compares that row with the mask's lowest point -- the same comparison in pixels, where
only the detector's choice of contact point can be wrong.

On the four AV2 logs the gap is +2.0 / -5.8 / -4.1 / (see output) px, i.e. a few px, which
is what ruled the contact point out as the cause of the 11-19% distance errors on two of
them.  Run it after av2_eval.py; it needs that log's annotations.feather, so it is a
diagnostic and never part of the measurement.

Usage:
  python3 tools/av2_contact_check.py
"""
import sys, json, numpy as np, pandas as pd
sys.path.insert(0, "tools")
from av2_eval import SE3, corners, iou
for tag, L in [("c865c156","c865c156-0f26-411c-a16c-be985333f675"),
               ("cf5aaa11","cf5aaa11-4f92-3377-a7a2-861f305023eb"),
               ("dc9077b9","dc9077b9-2fe0-3d18-9b97-8067ff090874")]:
    root=f"data/input/av2/{L}"
    meta=json.load(open(f"{root}/pinhole_meta.json"))
    e=json.load(open(f"data/output/av2_depth/eval_{L}.json"))
    rows=pd.read_csv(f"data/output/av2_depth/eval_{L}_rows.csv")
    tg=pd.read_csv(f"data/output/av2_depth/targets_{L}.csv")[["frame_idx","px","x0","y0","x1","y1"]]
    rows=rows.merge(tg,on=["frame_idx","px"],how="left")
    ann=pd.read_feather(f"{root}/annotations.feather")
    ann=ann[ann.category=="REGULAR_VEHICLE"]
    poses=pd.read_feather(f"{root}/city_SE3_egovehicle.feather").drop_duplicates("timestamp_ns").sort_values("timestamp_ns")
    pt=poses.timestamp_ns.values
    ex=pd.read_feather(f"{root}/calibration/egovehicle_SE3_sensor.feather")
    ex=ex[ex.sensor_name=="ring_front_center"].iloc[0]
    camT=np.linalg.inv(SE3((ex.qw,ex.qx,ex.qy,ex.qz),(ex.tx_m,ex.ty_m,ex.tz_m)))
    K=np.array([[meta["fx"],0,meta["cx"]],[0,meta["fy"],meta["cy"]],[0,0,1]])
    fr=pd.read_csv(f"{root}/pinhole_frames.csv"); ts_of=dict(zip(fr.frame_idx,fr.timestamp_ns))
    def pose(ts):
        r=poses.iloc[int(np.argmin(np.abs(pt-ts)))]
        return SE3((r.qw,r.qx,r.qy,r.qz),(r.tx_m,r.ty_m,r.tz_m))
    ats_all=np.unique(ann.timestamp_ns.values)
    d_py=[]; d_z=[]
    for _,t in rows.iterrows():
        ts=ts_of[t.frame_idx]; ats=int(ats_all[np.argmin(np.abs(ats_all-ts))])
        T=camT@np.linalg.inv(pose(ts))@pose(ats)
        best=None;bi=0
        for _,a in ann[ann.timestamp_ns==ats].iterrows():
            C=corners(a); Ch=(T@np.c_[C,np.ones(8)].T).T[:,:3]
            if (Ch[:,2]<=.5).any(): continue
            uv=(K@Ch.T).T; uv=uv[:,:2]/uv[:,2:3]
            v=iou([t.x0,t.y0,t.x1,t.y1],[uv[:,0].min(),uv[:,1].min(),uv[:,0].max(),uv[:,1].max()])
            if v>bi: bi, best = v, (C, Ch, uv)
        if best is None or bi<0.5: continue
        C,Ch,uv=best
        Ce=(np.linalg.inv(pose(ts))@pose(ats)@np.c_[C,np.ones(8)].T).T[:,:3]
        bottom=Ce[:,2]<Ce[:,2].mean()                     # the 4 corners on the road
        near=np.argmin(Ce[bottom,0])                       # nearest of those
        py_gt=uv[bottom][near,1]
        d_py.append(t.py_max-py_gt); d_z.append(Ce[bottom][near,2])
    d_py=np.array(d_py); d_z=np.array(d_z)
    print(f"{tag}  n={len(d_py):3d}   mask lowest row - cuboid ground corner row: "
          f"median {np.median(d_py):+6.2f} px  (IQR {np.percentile(d_py,25):+.1f}..{np.percentile(d_py,75):+.1f})"
          f"   cuboid bottom height above ego z=0: median {np.median(d_z):+.3f} m")
