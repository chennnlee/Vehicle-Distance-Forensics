from pathlib import Path
import json
import sys
from typing import Literal, Optional

import numpy as np
import torch


MODEL_CONFIGS = {
    "vits": {"encoder": "vits", "features": 64, "out_channels": [48, 96, 192, 384]},
    "vitb": {"encoder": "vitb", "features": 128, "out_channels": [96, 192, 384, 768]},
    "vitl": {"encoder": "vitl", "features": 256, "out_channels": [256, 512, 1024, 1024]},
    "vitg": {"encoder": "vitg", "features": 384, "out_channels": [1536, 1536, 1536, 1536]},
}


class DepthEngine:
    """整合多種深度模型（UniDepth / Depth Anything V2）的推論入口。"""

    def __init__(self, checkpoints_dir: str | Path = "checkpoints") -> None:
        self.checkpoints_dir = Path(checkpoints_dir)
        self.active_model: Optional[Literal["unidepth_v2", "depth_anything_v2"]] = None
        self.depth_anything_encoder: str = "vits"
        self.unidepth_backbone: str = "vits14"
        self.model = None
        self.input_size = 518
        self.device = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
        self.project_root = Path(__file__).resolve().parents[1]

    def _ensure_internal_depth_anything_importable(self) -> None:
        depth_anything_repo = self.project_root / "depth_models" / "Depth-Anything-V2"
        if not depth_anything_repo.exists():
            raise FileNotFoundError(f"找不到內建模型路徑: {depth_anything_repo}")

        repo_path = str(depth_anything_repo)
        if repo_path not in sys.path:
            sys.path.insert(0, repo_path)

    def _resolve_checkpoint_path(self, encoder: str) -> Path:
        candidates = [
            self.checkpoints_dir / f"depth_anything_v2_{encoder}.pth",
            self.project_root / "depth_models" / "Depth-Anything-V2" / "checkpoints" / f"depth_anything_v2_{encoder}.pth",
        ]

        for checkpoint_path in candidates:
            if checkpoint_path.exists():
                return checkpoint_path

        joined = "\n".join(str(path) for path in candidates)
        raise FileNotFoundError(f"找不到權重，請確認以下路徑之一存在：\n{joined}")

    def _ensure_internal_unidepth_importable(self) -> None:
        unidepth_repo = self.project_root / "depth_models" / "UniDepth"
        if not unidepth_repo.exists():
            raise FileNotFoundError(f"找不到內建模型路徑: {unidepth_repo}")

        repo_path = str(unidepth_repo)
        if repo_path not in sys.path:
            sys.path.insert(0, repo_path)

    def _resolve_unidepth_checkpoint_path(self, backbone: str) -> Path | None:
        candidates = [
            self.checkpoints_dir / f"unidepth_v2_{backbone}.pth",
            self.checkpoints_dir / "unidepth_v2.pth",
        ]

        for checkpoint_path in candidates:
            if checkpoint_path.exists():
                return checkpoint_path
        return None

    def _load_unidepth_v2(self, backbone: Literal["vits14", "vitb14", "vitl14"]) -> None:
        self._ensure_internal_unidepth_importable()
        from unidepth.models import UniDepthV2

        checkpoint_path = self._resolve_unidepth_checkpoint_path(backbone)
        self.unidepth_backbone = backbone

        if checkpoint_path is not None:
            config_path = self.project_root / "depth_models" / "UniDepth" / "configs" / f"config_v2_{backbone}.json"
            if not config_path.exists():
                raise FileNotFoundError(f"找不到 UniDepth 設定檔: {config_path}")

            with open(config_path, "r", encoding="utf-8") as file:
                config = json.load(file)

            model = UniDepthV2(config)
            model.load_pretrained(str(checkpoint_path))
        else:
            hf_repo_id = f"lpiccinelli/unidepth-v2-{backbone}"
            model = UniDepthV2.from_pretrained(hf_repo_id)

        self.model = model.to(self.device).eval()

    def load_model(
        self,
        model_name: Literal["unidepth_v2", "depth_anything_v2"],
        encoder: Literal["vits", "vitb", "vitl", "vitg"] = "vits",
        unidepth_backbone: Literal["vits14", "vitb14", "vitl14"] = "vits14",
        input_size: int = 518,
    ) -> None:
        """載入指定模型。"""
        self.active_model = model_name
        self.input_size = input_size

        if model_name == "unidepth_v2":
            self._load_unidepth_v2(unidepth_backbone)
            return

        self._ensure_internal_depth_anything_importable()
        from depth_anything_v2.dpt import DepthAnythingV2

        checkpoint_path = self._resolve_checkpoint_path(encoder)
        self.depth_anything_encoder = encoder

        model = DepthAnythingV2(**MODEL_CONFIGS[encoder])
        model.load_state_dict(torch.load(checkpoint_path, map_location="cpu"))
        self.model = model.to(self.device).eval()

    def infer(self, image_bgr: np.ndarray) -> np.ndarray:
        """輸入 BGR 影像，回傳 HxW 的深度圖（float32）。"""
        if self.active_model is None:
            raise RuntimeError("尚未載入模型，請先呼叫 load_model().")
        if self.model is None:
            raise RuntimeError("模型尚未載入完成。")

        if image_bgr is None or image_bgr.ndim != 3:
            raise ValueError("image_bgr 必須是 HxWx3 的影像陣列")

        if self.active_model == "depth_anything_v2":
            depth = self.model.infer_image(image_bgr, self.input_size)
            return depth.astype(np.float32)

        if self.active_model == "unidepth_v2":
            image_rgb = image_bgr[:, :, ::-1].copy()
            rgb_tensor = torch.from_numpy(image_rgb).permute(2, 0, 1)
            predictions = self.model.infer(rgb_tensor)
            depth_tensor = predictions["depth"]
            depth = depth_tensor[0, 0].detach().float().cpu().numpy()
            return depth.astype(np.float32)

        raise RuntimeError(f"不支援的模型: {self.active_model}")
