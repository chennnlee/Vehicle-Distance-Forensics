# BEVFormer Legacy Environment Setup Guide

## ✅ Status: Environment Ready

The `bevformer_legacy` conda environment has been successfully set up with all required dependencies for running BEVFormer with legacy mmdetection3d (v0.17.1).

## Environment Details

- **Environment Name**: `bevformer_legacy`
- **Python**: 3.8
- **PyTorch**: 1.9.1 + cu111 (CUDA 11.1)
- **Key Dependencies**:
  - mmcv-full: 1.4.0
  - mmdet: 2.14.0
  - mmsegmentation: 0.14.1
  - mmdet3d: 0.17.1 (imported from workspace, not compiled)
- **GPU Support**: NVIDIA GeForce RTX 4050 Laptop (✓ CUDA available)

## Quick Start

### 1. Create the Environment (First Time)

Run the automated setup script:

```bash
bash tools/BEVFormer/setup_bevformer_env.sh
```

This will create the `bevformer_legacy` environment with all dependencies.

### 2. Use BEVFormer

**Option A: Using bevformer_runner.py (Recommended)**

```bash
conda activate bevformer_legacy
python bevformer_runner.py \
    --preset legacy-bevformer-base \
    --mode test \
    --checkpoint checkpoints/bevformer_r101_dcn_24ep.pth \
    --show-dir data/output/bev_vis/test
```

The runner automatically sets up PYTHONPATH for mmdet3d and BEVFormer.

**Option B: Manual Setup**

```bash
conda activate bevformer_legacy

# Set PYTHONPATH to include mmdet3d and BEVFormer
export PYTHONPATH=/home/s11244/code/114/Vehicle-Distance-Forensics/tools/mmdetection3d:$PYTHONPATH
export PYTHONPATH=/home/s11244/code/114/Vehicle-Distance-Forensics/tools/BEVFormer:$PYTHONPATH

# Navigate to BEVFormer directory
cd tools/BEVFormer

# Run test.py or train.py
python tools/test.py projects/configs/bevformer/bevformer_base.py \
    ../../checkpoints/bevformer_r101_dcn_24ep.pth \
    --show-dir ../../data/output/bev_vis/test
```

## Available Presets

### `legacy-bevformer-base`

Default base BEVFormer model for testing.

```bash
python bevformer_runner.py --preset legacy-bevformer-base --mode test --checkpoint checkpoints/bevformer_r101_dcn_24ep.pth
```

### `legacy-bevformer-tiny`

Lightweight BEVFormer model for testing.

```bash
python bevformer_runner.py --preset legacy-bevformer-tiny --mode test --checkpoint checkpoints/bevformer_tiny_epoch_24.pth
```

### `legacy-bevformer-mini-smoke`

Local nuScenes mini smoke-test preset. This is the fastest way to confirm the legacy BEVFormer stack can boot in this workspace.

```bash
bash tools/BEVFormer/prepare_nuscenes_mini.sh

python bevformer_runner.py \
    --preset legacy-bevformer-mini-smoke \
    --mode test \
    --checkpoint /path/to/bevformer_tiny_epoch_24.pth \
    --show-dir data/output/bev_vis/mini-smoke
```

Use a checkpoint that matches `bevformer_tiny` for meaningful results. If you only have `checkpoints/bevformer_r101_dcn_24ep.pth`, you can still use it for smoke testing the pipeline, but weight-mismatch warnings are expected.

## Verify Setup

To verify the environment is correctly set up:

```bash
conda activate bevformer_legacy
python << 'EOF'
import sys
sys.path.insert(0, 'tools/mmdetection3d')
sys.path.insert(0, 'tools/BEVFormer')

print("Checking imports:")
for mod in ['torch', 'mmcv', 'mmdet', 'mmdet3d']:
    try:
        m = __import__(mod)
        v = getattr(m, '__version__', 'OK')
        print(f"  ✓ {mod} {v}")
    except Exception as e:
        print(f"  ✗ {mod} - {e}")

import torch
print(f"\nCUDA available: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"Device: {torch.cuda.get_device_name(0)}")
EOF
```

## Important Notes

### DO NOT Use Other Environments

- **VisionVelocity**: Has broken mmcv import errors
- **bevformer** (old): Uses mmcv 2.x which is incompatible with legacy BEVFormer (Config import fails)

### mmdet3d CUDA Ops

mmdet3d CUDA extensions are **not compiled** due to GCC version incompatibility with CUDA 11.1 (system has GCC 11.4, CUDA 11.1 only supports up to GCC 10). However, this is **not critical for inference** - PyTorch's native CUDA kernels handle the necessary operations.

If you need CUDA ops later, either:
1. Use GCC 10 (via conda)
2. Upgrade to a newer CUDA toolkit
3. Use the modern-mmdet3d stack instead

### Prerequisites for BEVFormer

Before running BEVFormer training/evaluation:

1. **nuScenes Dataset**: Download and place at `data/nuscenes/`
2. **Temporal PKL Files**: Generate using BEVFormer's data preparation script
3. **Pretrained Backbone**: Download and place in `checkpoints/`

See `tools/BEVFormer/docs/prepare_dataset.md` for details.

### nuScenes Mini Smoke Test

If you only want to verify the pipeline locally, you can use `data/v1.0-mini.tgz` instead of the full trainval split:

```bash
bash tools/BEVFormer/prepare_nuscenes_mini.sh
```

This extracts `data/v1.0-mini.tgz` into `data/nuscenes/` and generates `nuscenes_infos_temporal_{train,val}.pkl`.

If `data/can_bus/` is not present, the local BEVFormer converter now falls back to zeroed CAN bus features so the mini smoke test can still run. This is suitable for environment validation, not for final benchmark-quality evaluation.

### CCTV Data + Depth Anything V2 Augmentation

For CCTV frames without full nuScenes calibration, this workspace can create a BEVFormer-readable temporal PKL with pseudo intrinsics/extrinsics, then augment each camera record with Depth Anything V2 outputs.

This is the practical pipeline that is already wired up in this repo:
- Depth Anything V2 writes per-frame pseudo-depth `.npy` files.
- BEVFormer still runs on the temporal infos / camera images as usual.
- The depth maps are then used for a separate pseudo-BEV renderer or for downstream custom fusion.

If you want the reference-style two-panel output like `sample_063_cam_front_summary.png`, render the BEVFormer `results.pkl` with `tools/BEVFormer/visualize_result_sample.py`.

1. Build the base CCTV temporal PKL:

```bash
python tools/BEVFormer/tools/build_cctv_default_infos.py \
    --image-dir data/input/cctv_keyframes \
    --output-root data/nuscenes \
    --fov-deg 90 \
    --camera-height-m 6.0 \
    --fps 2.0
```

2. Add Depth Anything V2 pseudo-depth fields:

```bash
python tools/BEVFormer/tools/augment_infos_with_depth_anything.py \
    --infos-pkl data/nuscenes/nuscenes_infos_temporal_val.pkl \
    --out-pkl data/nuscenes/nuscenes_infos_temporal_val_depth_anything.pkl \
    --depth-output-dir data/output/depth_anything_bevformer/cctv_keyframes \
    --encoder vitl \
    --save-vis
```

The augmented PKL adds these fields under `info["cams"]["CAM_FRONT"]`:

- `depth_path`
- `depth_anything_v2_path`
- `depth_vis_path`
- `depth_model`
- `depth_encoder`
- `depth_input_size`
- `depth_scale_factor`
- `depth_stats`

Important limitation: Depth Anything V2 can provide pseudo-depth, but it cannot recover real camera extrinsics, ego motion, or CAN bus values by itself. The default CCTV PKL still uses assumed FOV/camera height and zero ego motion. The current BEVFormer test/inference path does not ingest the depth fields automatically; to make depth influence the detector, you must modify the model/dataset forward path. For a real fusion prototype, start from `tools/BEVFormer/projects/configs/bevformerv2/*.py` and `tools/BEVFormer/projects/mmdet3d_plugin/bevformer/detectors/bevformerV2.py`.

## Troubleshooting

### Import Errors

If you get import errors for mmdet3d:

```bash
# Make sure PYTHONPATH includes workspace paths
export PYTHONPATH=/home/s11244/code/114/Vehicle-Distance-Forensics/tools/mmdetection3d:$PYTHONPATH
export PYTHONPATH=/home/s11244/code/114/Vehicle-Distance-Forensics/tools/BEVFormer:$PYTHONPATH
```

Or use `bevformer_runner.py` which handles this automatically.

### Missing `nuscenes_infos_temporal_*.pkl`

If `bevformer_runner.py` reports missing temporal PKL files:

```bash
bash tools/BEVFormer/prepare_nuscenes_mini.sh
```

Or prepare the full nuScenes dataset and run:

```bash
python tools/BEVFormer/tools/create_data.py nuscenes \
    --root-path data/nuscenes \
    --out-dir data/nuscenes \
    --extra-tag nuscenes \
    --version v1.0 \
    --canbus data
```

### CUDA Memory Errors

BEVFormer is memory-intensive. Try using a smaller model or reducing batch size:

```bash
python bevformer_runner.py --preset legacy-bevformer-tiny ...
```

### Configuration Import Errors

If you see "Config not found" errors, make sure you're using the `bevformer_legacy` environment, not the `bevformer` environment.

## Environment Path References

- **Repository Root**: `/home/s11244/code/114/Vehicle-Distance-Forensics/`
- **BEVFormer Source**: `tools/BEVFormer/`
- **mmdet3d Source**: `tools/mmdetection3d/` (v0.17.1 tag)
- **Checkpoints**: `checkpoints/`
- **Output**: `data/output/`

## Next Steps

1. ✅ Environment setup complete
2. ⬜ Download nuScenes dataset (if needed)
3. ⬜ Generate temporal PKL indices
4. ⬜ Run BEVFormer inference or training

For detailed BEVFormer usage, see `tools/BEVFormer/README.md` and `tools/BEVFormer/docs/`.
