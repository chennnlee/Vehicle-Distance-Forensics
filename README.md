# Vehicle-Distance-Forensics

本專案目前定位為「單眼深度估測與距離統計」工具，保留以下能力：

- 單模型推論（Depth Anything V2 / UniDepth V2 / Metric3D）
- 支援單張影像或資料夾批次
- 支援 bbox 區域深度統計
- 支援 anchor / 參考物真值的尺度校正
- 輸出深度可視化圖與 CSV 統計

## BEV 流程調整

本 repo 已移除內建 BEV 與 ground-first 白線流程。

如需 BEV 功能，建議使用新版 OpenMMLab 堆疊（PyTorch 2.x）：

- https://github.com/open-mmlab/mmdetection3d

若你仍要跑原始 BEVFormer（舊版依賴）：

- https://github.com/fundamentalvision/BEVFormer

本 repo 提供橋接執行器 `bevformer_runner.py`，可切換新舊後端：

### 一鍵預設

如果你要先跑本 repo 內的 legacy BEVFormer，建議直接用 preset：

```bash
python bevformer_runner.py \
  --preset legacy-bevformer-base \
  --checkpoint ckpts/bevformer_base.pth
```

較省顯存的版本：

```bash
python bevformer_runner.py \
  --preset legacy-bevformer-tiny \
  --checkpoint ckpts/bevformer_tiny.pth
```

> 注意：checkpoint 檔案名稱可依你實際下載的位置替換。

如果你目前只是想先把 BEVFormer 在這個 workspace 內跑通，先用 nuScenes mini smoke test 會比較快：

```bash
bash tools/BEVFormer/prepare_nuscenes_mini.sh
python bevformer_runner.py \
  --preset legacy-bevformer-mini-smoke \
  --checkpoint /path/to/bevformer_tiny_epoch_24.pth \
  --show-dir data/output/bev_vis/mini-smoke
```

`legacy-bevformer-mini-smoke` uses a tiny config. For meaningful predictions, use a matching tiny checkpoint. The base checkpoint already in `checkpoints/` is still useful for boot smoke tests, but weight-mismatch warnings are expected.

```bash
# 方案 3（建議）：新版 mmdetection3d 後端
# 先在 tools/mmdetection3d 放入官方專案
python bevformer_runner.py \
  --stack modern-mmdet3d \
  --mode test \
  --config projects/TPVFormer/configs/tpvformer_8xb1-2x_nus-seg.py \
  --checkpoint checkpoints/model.pth \
  --show-dir data/output/bev_vis
```

```bash
# 相容模式：舊版官方 BEVFormer
python bevformer_runner.py \
  --stack legacy-bevformer \
  --bevformer-root tools/BEVFormer \
  --mode test \
  --config projects/configs/bevformer/bevformer_base.py \
  --checkpoint ckpts/bevformer_base.pth
```

> 注意：BEVFormer 需要對應資料集格式（如 nuScenes）與相機幾何資訊，
> 不是單張圖片 homography 轉換流程。
> 目前 `bevformer_runner.py` 也會在缺少 `nuscenes_infos_temporal_*.pkl` 時直接提示你先準備 mini 或 full nuScenes 資料。

## SHARP 點雲轉鳥瞰圖

如果你先用 SHARP 產生 3D Gaussian 的 `.ply` 輸出，這個 workspace 現在可以直接把它轉成鳥瞰圖。
SHARP 的輸出使用 OpenCV 座標慣例：`x=向右`、`y=向下`、`z=向前`，我們會把它 rasterize 成真正的 2D BEV density map，不再是點雲散點圖。
轉換時會把 `y=向下` 搭配 `--camera-height` 轉成近似地面高度，預設只保留近地面的點，避免天空、建物立面、招牌等 3DGS 中心被一起壓進鳥瞰圖造成變形與模糊。

如果你想肉眼直接和原圖比對，可以再加上 `--reference-image`。
現在改成分開輸出，不再合成左右 compare：會多一張原圖副本與一張 BEV 圖，檔名分別是 `*_reference.*` 與 `*_bev.png`。
如果你用的是 PLY 輸入，輸出也會附上一份原始 PLY 副本，檔名是 `*.ply`，這樣每張照片都會同時有原始 PLY 和 BEV。

```bash
python tools/sharp_to_bev.py \
  --input data/output/sharp_gaussians \
  --out-dir data/output/sharp_bev \
  --reference-image data/input/cctv_keyframes/043.jpg \
  --x-range 0,40 \
  --y-range=-12,12 \
  --output-size 800,800 \
  --camera-height 1.6 \
  --height-range=-0.8,2.5 \
  --blur-kernel 1
```

如果你習慣用空白分隔參數，也可以直接寫成 `--y-range -12,12`；腳本現在會自動幫你轉成可解析的形式。

如果你只有單一 `.ply` 檔，也可以直接把 `--input` 指向該檔案。輸出會包含：

- `data/output/sharp_bev/*_bev.png`
- `data/output/sharp_bev/report.json`

若 BEV 已經產生，但想讓標線更容易看，可以再跑影像後處理。這一步只做視覺增強，不會新增可靠的幾何量測資訊：

```bash
python tools/enhance_bev_image.py \
  --input data/output/sharp_bev \
  --out-dir data/output/sharp_bev_enhanced \
  --close-kernel 5 \
  --inpaint-radius 2 \
  --clahe-clip 2.2 \
  --sharpen 0.55
```

## SHARP + YOLO 車距量測

如果你的目標不是只看 BEV，而是要量車輛距離，可以直接把 SHARP 的 `.ply` 和原圖丟給 YOLO 量測工具。
這支工具不假設 PLY 路面一定平貼在固定 `y` 值；預設會從投影到影像下半部的點自動擬合地面平面 `y = a*x + b*z + c`，再用相對地面高度過濾車輛 bbox 裡的點。
預設座標系是 SHARP/OpenCV 慣例：`x=向右`、`y=向下`、`z=向前`。如果你的 PLY 是 y 軸向上的座標系，請加上 `--y-axis-convention opengl-y-up`。

單張影像：

```bash
python tools/sharp_yolo_distance.py \
  --image data/input/cctv_keyframes/043.jpg \
  --pointcloud data/output/sharp_gaussians/043.ply \
  --out-dir data/output/sharp_yolo_distance \
  --yolo-model yolov8m.pt \
  --y-axis-convention opencv-y-down \
  --ground-mode auto \
  --bbox-vertical-slice 0.55
```

若 PLY 內含 SHARP 輸出的 `intrinsic` / `image_size` metadata，工具會優先使用 PLY 內參；缺少 metadata 時才使用 `--fov-deg` 作為 fallback。
若已用標線、車牌或軸距算出尺度校正係數，可加上 `--pointcloud-scale`。

資料夾批次時，影像與 PLY 會用相同檔名 stem 配對，例如 `043.jpg` 對 `043.ply`：

```bash
python tools/sharp_yolo_distance.py \
  --image data/input/cctv_keyframes \
  --pointcloud data/output/sharp_gaussians \
  --out-dir data/output/sharp_yolo_distance \
  --yolo-model yolov8m.pt \
  --fov-deg 70 \
  --y-axis-convention opencv-y-down \
  --ground-mode auto
```

主要輸出：

- `data/output/sharp_yolo_distance/sharp_yolo_distances.csv`
- `data/output/sharp_yolo_distance/sharp_yolo_distance_summary.json`
- `data/output/sharp_yolo_distance/overlays/*_sharp_yolo_distance.png`

CSV 會包含每個 YOLO 車輛框的 `distance_p10_m`、`distance_median_m`、`point_count`、`height_median_m` 與狀態欄位。
建議優先看 `distance_p10_m`，它通常比最小值穩定，又比 median 更接近車輛前緣。
若 `distance_iqr_m` 過大，狀態會標成 `unstable_depth_iqr`，代表 bbox 內點雲分布太散，不適合直接採信。

## 環境安裝

```bash
cd Vehicle-Distance-Forensics
pip install -r requirements.txt
```

## 權重準備

此 repo 不包含大型權重，請自行下載並放置於 `checkpoints/`（或相容路徑）。

## 常用指令

### 1) 最短推論

```bash
python main.py --img-path data/input/sample.jpg
```

### 2) 指定模型

```bash
# Depth Anything V2
python main.py --model depth_anything_v2 --encoder vits --img-path data/input/sample.jpg

# UniDepth V2
python main.py --model unidepth_v2 --unidepth-backbone vits14 --img-path data/input/sample.jpg

# Metric3D
python main.py --model metric3d --metric3d-variant vit_large --img-path data/input/sample.jpg
```

### 3) bbox + 自動尺度校正

```bash
python main.py \
  --model depth_anything_v2 \
  --img-path data/input/sample.jpg \
  --bbox 800,500,1200,900 \
  --auto-scale-gt 10.0
```

## 輸出說明

每次執行會在 `data/output/runs/` 建立 run 目錄，主要輸出：

- 深度可視化圖（`depth_vis.png` 或批次檔名）
- `depth_stats.csv`

`depth_stats.csv` 欄位：

- `image`, `model`, `scale_factor`
- `center_x`, `center_y`, `center_depth`
- `roi_median`, `roi_mean`, `roi_min`, `roi_max`
- `auto_scale_gt`, `auto_scale_est_raw`, `auto_scale_enabled`
- `output`

## 備註

- 若使用 `--auto-scale-gt`，必須同時提供 `--bbox`。
- 若輸入為資料夾，會對所有影像逐張輸出與記錄。

## 台灣道路影像 BEV demo

如果你的目標是「自己在圖上點幾個角點，直接變成鳥瞰圖」，現在優先使用互動選點模式。這個流程適合先把影像做成可看的 bird's-eye view；如果你要的是公尺尺度，下面的 metric homography 模式仍然保留。

第一步先用互動模式直接選 4 個同一平面上的角點：

```bash
python tools/monolayout_demo.py \
  --mode warp \
  --image-path data/input/cctv_keyframes/043.jpg \
  --out-dir data/output/taiwan_road_bev_demo
```

操作方式：

- 左鍵點 4 個角點
- 右鍵可復原上一點
- `Enter` 或 `Space` 完成並輸出鳥瞰圖
- `C` 可清空重選

輸出：

- `data/output/taiwan_road_bev_demo/interactive_homography/*_birdseye.png`
- `data/output/taiwan_road_bev_demo/interactive_homography/*_picked_points.png`
- `data/output/taiwan_road_bev_demo/report.json`

如果你想先做一張帶 pixel 座標的選點圖，再慢慢校正，也可以先產生 grid sheet：

```bash
python tools/monolayout_demo.py \
  --mode pick-sheet \
  --image-path data/input/cctv_keyframes/043.jpg \
  --out-dir data/output/taiwan_road_bev_demo \
  --grid-step-px 80
```

輸出：

- `data/output/taiwan_road_bev_demo/pick_sheets/*_pick_sheet.png`
- `data/output/taiwan_road_bev_demo/report.json`

如果你要的是「真實公尺尺度」的 BEV，第二步再用 metric homography，從同一個路面平面選至少 4 個標線角點，並填入對應的真實公尺座標。座標約定為 `X=向右公尺`、`Y=向前公尺`：

```bash
python tools/monolayout_demo.py \
  --mode points \
  --image-path data/input/cctv_keyframes/043.jpg \
  --out-dir data/output/taiwan_road_bev_demo \
  --src-points '380,650;650,650;585,500;450,500' \
  --dst-points-m '0,0;4,0;4,8;0,8' \
  --meters-per-pixel 0.025 \
  --margin-m 1.0
```

`--src-points` 是影像上的 pixel 點；`--dst-points-m` 是同一批點在地面上的公尺座標。上面數字只是格式範例，實際要換成從選點圖讀到的標線角點與台灣標線規範/現地量測尺寸。

輸出：

- `data/output/taiwan_road_bev_demo/metric_homography/*_metric_bev.png`
- `data/output/taiwan_road_bev_demo/metric_homography/*_metric_bev_grid.png`
- `data/output/taiwan_road_bev_demo/report.json`

如果只是想快速看畫面方向，也可以跑近似 IPM preview：

```bash
python tools/monolayout_demo.py \
  --mode ipm \
  --image-path data/input/cctv_keyframes/085.jpg \
  --out-dir data/output/monolayout_demo \
  --pitch-deg 20 \
  --fov-deg 90
```

IPM preview 不使用標線實際尺寸，只適合初步檢查：

- `data/output/monolayout_demo/ipm_preview/*_ipm_preview.png`
- `data/output/monolayout_demo/report.json`

如果已經有本機 MonoLayout checkout 與 pretrained model 目錄，仍可跑 MonoLayout layout prediction：

```bash
python tools/monolayout_demo.py \
  --mode monolayout \
  --image-path data/input/cctv_keyframes/043.jpg \
  --out-dir data/output/monolayout_demo \
  --monolayout-root tools/monolayout \
  --model-path checkpoints/monolayout/kitti_odometry_static \
  --type static
```

`--model-path` 需包含 `encoder.pth` 與 `decoder.pth`；若 `--type both`，則需包含 `encoder.pth`、`static_decoder.pth`、`dynamic_decoder.pth`。

## 官方 SimpleBEV 現況

本 workspace 已放入官方 SimpleBEV repo 到 [tools/SimpleBEV](tools/SimpleBEV)，但目前公開內容只有 README，沒有實際訓練/推論程式碼，也沒有公開 checkpoint。

如果你之後拿到完整的官方專案或權重，我可以再幫你把它接成獨立 backend。
