from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path


PRESETS: dict[str, dict[str, str]] = {
    "legacy-bevformer-base": {
        "stack": "legacy-bevformer",
        "bevformer_root": "tools/BEVFormer",
        "config": "projects/configs/bevformer/bevformer_base.py",
        "show_dir": "",
        "work_dir": "data/output/bev_runs/legacy-bevformer-base",
    },
    "legacy-bevformer-tiny": {
        "stack": "legacy-bevformer",
        "bevformer_root": "tools/BEVFormer",
        "config": "projects/configs/bevformer/bevformer_tiny.py",
        "show_dir": "",
        "work_dir": "data/output/bev_runs/legacy-bevformer-tiny",
    },
    "legacy-bevformer-mini-smoke": {
        "stack": "legacy-bevformer",
        "bevformer_root": "tools/BEVFormer",
        "config": "projects/configs/bevformer/bevformer_tiny_mini.py",
        "show_dir": "data/output/bev_vis/legacy-bevformer-mini-smoke",
        "work_dir": "data/output/bev_runs/legacy-bevformer-mini-smoke",
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run legacy BEVFormer or modern MMDetection3D tools from this repository."
    )
    parser.add_argument(
        "--preset",
        type=str,
        default="",
        choices=["", *PRESETS.keys()],
        help="Apply a named BEVFormer preset for common local setups.",
    )
    parser.add_argument(
        "--stack",
        type=str,
        default="modern-mmdet3d",
        choices=["legacy-bevformer", "modern-mmdet3d"],
        help="Execution backend stack.",
    )
    parser.add_argument(
        "--bevformer-root",
        type=str,
        default="tools/BEVFormer",
        help="Backend repository root path. Legacy default: tools/BEVFormer.",
    )
    parser.add_argument(
        "--mode",
        type=str,
        default="test",
        choices=["test", "train"],
        help="Execution mode mapped to BEVFormer tools/test.py or tools/train.py.",
    )
    parser.add_argument(
        "--config",
        type=str,
        default="",
        help="Config file path, relative to BEVFormer root or absolute path.",
    )
    parser.add_argument(
        "--checkpoint",
        type=str,
        default="",
        help="Checkpoint path for test mode.",
    )
    parser.add_argument(
        "--out",
        type=str,
        default="",
        help="Output result file in pickle format for test mode.",
    )
    parser.add_argument(
        "--eval",
        nargs="+",
        default=[],
        help="Evaluation metrics passed to BEVFormer test.py.",
    )
    parser.add_argument(
        "--format-only",
        action="store_true",
        help="Format output results without evaluation.",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Show results while running test mode.",
    )
    parser.add_argument(
        "--work-dir",
        type=str,
        default="",
        help="Work directory for logs and outputs.",
    )
    parser.add_argument(
        "--show-dir",
        type=str,
        default="",
        help="Visualization output directory for test mode.",
    )
    parser.add_argument(
        "--task",
        type=str,
        default="",
        choices=["", "mono_det", "multi-view_det", "lidar_det", "lidar_seg", "multi-modality_det"],
        help="Visualization task type (required by modern mmdet3d when --show-dir is used).",
    )
    parser.add_argument(
        "--amp",
        action="store_true",
        help="Enable AMP for train mode on modern-mmdet3d stack.",
    )
    parser.add_argument(
        "--launcher",
        type=str,
        default="none",
        choices=["none", "pytorch", "slurm", "mpi"],
        help="Job launcher passed to BEVFormer test.py or train.py.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=0,
        help="Random seed passed to BEVFormer test.py.",
    )
    parser.add_argument(
        "--deterministic",
        action="store_true",
        help="Enable deterministic CUDNN options for test mode.",
    )
    parser.add_argument(
        "--fuse-conv-bn",
        action="store_true",
        help="Fuse conv and bn layers before testing.",
    )
    parser.add_argument(
        "--gpu-collect",
        action="store_true",
        help="Use GPU collection in distributed test mode.",
    )
    parser.add_argument(
        "--tmpdir",
        type=str,
        default="",
        help="Temporary directory used for result collection.",
    )
    parser.add_argument(
        "--extra-args",
        type=str,
        default="",
        help="Extra raw args appended to BEVFormer command.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print command without executing.",
    )
    return parser.parse_args()


def resolve_path(bevformer_root: Path, path_text: str, required: bool) -> Path:
    path = Path(path_text)
    if not path.is_absolute():
        path = bevformer_root / path
    path = path.resolve()
    if required and not path.exists():
        raise FileNotFoundError(f"找不到檔案: {path}")
    return path


def resolve_path_with_fallback(
    backend_root: Path, project_root: Path, path_text: str, required: bool
) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        resolved = path.resolve()
    else:
        backend_candidate = (backend_root / path).resolve()
        project_candidate = (project_root / path).resolve()
        if not required:
            resolved = project_candidate
        elif project_candidate.exists():
            resolved = project_candidate
        else:
            resolved = backend_candidate
    if required and not resolved.exists():
        raise FileNotFoundError(f"找不到檔案: {resolved}")
    return resolved


def backend_is_usable(backend_root: Path) -> bool:
    return (backend_root / "tools" / "test.py").exists() and (
        backend_root / "tools" / "train.py"
    ).exists()


def config_exists(backend_root: Path, config_text: str) -> bool:
    config_path = Path(config_text)
    if config_path.is_absolute():
        return config_path.exists()
    return (backend_root / config_path).exists()


def infer_legacy_dataset_requirements(config_path: Path, mode: str) -> tuple[bool, bool, list[Path]]:
    try:
        config_text = config_path.read_text(encoding="utf-8")
    except OSError:
        config_text = ""

    config_name = config_path.name.lower()
    uses_nuscenes_temporal = (
        "nuscenes_infos_temporal_" in config_text
        or "customnuscenesdataset" in config_text.lower()
        or config_name.startswith("bevformer_")
    )
    wants_mini = "v1.0-mini" in config_text or config_name.endswith("_mini.py")

    required_files: list[Path] = []
    if uses_nuscenes_temporal:
        data_root = Path("data/nuscenes")
        required_files.append(data_root / "nuscenes_infos_temporal_val.pkl")
        if mode == "train":
            required_files.append(data_root / "nuscenes_infos_temporal_train.pkl")

    return uses_nuscenes_temporal, wants_mini, required_files


def ensure_legacy_dataset_ready(
    args: argparse.Namespace, project_root: Path, config_path: Path
) -> None:
    uses_nuscenes_temporal, wants_mini, required_files = infer_legacy_dataset_requirements(
        config_path, args.mode
    )
    if not uses_nuscenes_temporal:
        return

    missing_files = [project_root / path for path in required_files if not (project_root / path).exists()]
    if not missing_files:
        return

    mini_tar = project_root / "data" / "v1.0-mini.tgz"
    mini_script = project_root / "tools" / "BEVFormer" / "prepare_nuscenes_mini.sh"

    lines = [
        "缺少 BEVFormer 所需的 nuScenes temporal 標註檔：",
        *[f"  - {path}" for path in missing_files],
        "",
    ]

    if wants_mini:
        if mini_tar.exists():
            lines.extend(
                [
                    f"已偵測到 nuScenes mini 壓縮檔：{mini_tar}",
                    "請先執行以下準備腳本，再重新執行 BEVFormer：",
                    f"  bash {mini_script.relative_to(project_root)}",
                ]
            )
        else:
            lines.extend(
                [
                    "目前使用的是 nuScenes mini smoke config，但本機找不到 data/v1.0-mini.tgz。",
                    "請先放入 nuScenes mini 壓縮檔，或改成完整 nuScenes trainval 資料。",
                ]
            )
    else:
        lines.extend(
            [
                "你目前使用的是完整 nuScenes 設定，需先準備 data/nuscenes 與 temporal pkl。",
            ]
        )
        if mini_tar.exists():
            lines.extend(
                [
                    "",
                    "若你只是想先確認流程可跑通，可改用 mini smoke preset：",
                    "  python bevformer_runner.py --preset legacy-bevformer-mini-smoke --mode test --checkpoint /path/to/bevformer_tiny_epoch_24.pth --show-dir data/output/bev_vis/mini-smoke",
                    f"  bash {mini_script.relative_to(project_root)}",
                ]
            )
        else:
            lines.extend(
                [
                    "請先下載完整 nuScenes 與 can_bus，然後執行 BEVFormer 的 create_data.py 產生 temporal pkl。",
                ]
            )

    raise FileNotFoundError("\n".join(lines))


def apply_preset_defaults(args: argparse.Namespace) -> None:
    if not args.preset:
        return

    preset = PRESETS[args.preset]
    args.stack = preset.get("stack", args.stack)
    if not args.bevformer_root.strip() or args.bevformer_root == "tools/BEVFormer":
        args.bevformer_root = preset.get("bevformer_root", args.bevformer_root)
    if not args.config.strip():
        args.config = preset.get("config", args.config)
    if not args.show_dir.strip():
        args.show_dir = preset.get("show_dir", args.show_dir)
    if not args.work_dir.strip():
        args.work_dir = preset.get("work_dir", args.work_dir)
    if not args.mode.strip():
        args.mode = "test"


def build_command(
    args: argparse.Namespace, backend_root: Path, project_root: Path
) -> list[str]:
    python_bin = sys.executable
    if not args.config.strip():
        raise ValueError("必須提供 --config，或使用 --preset 先套用預設設定")
    config_path = resolve_path(backend_root, args.config, required=True)

    train_script = str((backend_root / "tools" / "train.py").resolve())
    test_script = str((backend_root / "tools" / "test.py").resolve())

    if args.mode == "test":
        if not args.checkpoint.strip():
            raise ValueError("test 模式必須提供 --checkpoint")
        if not (args.out.strip() or args.eval or args.format_only or args.show or args.show_dir.strip()):
            raise ValueError(
                'test 模式至少要指定 --out、--eval、--format-only、--show 或 --show-dir 其中一項'
            )
        checkpoint_path = resolve_path_with_fallback(
            backend_root, project_root, args.checkpoint, required=True
        )
        command = [
            python_bin,
            test_script,
            str(config_path),
            str(checkpoint_path),
        ]
        if args.show_dir.strip():
            command.extend(
                [
                    "--show-dir",
                    str(
                        resolve_path_with_fallback(
                            backend_root, project_root, args.show_dir, required=False
                        )
                    ),
                ]
            )
            if args.stack == "modern-mmdet3d":
                task = args.task or "multi-view_det"
                command.extend(["--task", task])
        if args.out.strip():
            command.extend(["--out", str(resolve_path_with_fallback(backend_root, project_root, args.out, required=False))])
        if args.eval:
            command.extend(["--eval", *args.eval])
        if args.format_only:
            command.append("--format-only")
        if args.show:
            command.append("--show")
        if args.fuse_conv_bn:
            command.append("--fuse-conv-bn")
        if args.gpu_collect:
            command.append("--gpu-collect")
        if args.tmpdir.strip():
            command.extend(["--tmpdir", str(resolve_path_with_fallback(backend_root, project_root, args.tmpdir, required=False))])
        if args.launcher != "none":
            command.extend(["--launcher", args.launcher])
        if args.seed is not None:
            command.extend(["--seed", str(args.seed)])
        if args.deterministic:
            command.append("--deterministic")
    else:
        command = [python_bin, train_script, str(config_path)]
        if args.stack == "modern-mmdet3d" and args.amp:
            command.append("--amp")
        if args.launcher != "none":
            command.extend(["--launcher", args.launcher])

    # legacy BEVFormer test.py does not accept --work-dir.
    if args.work_dir.strip() and (args.mode == "train" or args.stack == "modern-mmdet3d"):
        command.extend(
            [
                "--work-dir",
                str(
                    resolve_path_with_fallback(
                        backend_root, project_root, args.work_dir, required=False
                    )
                ),
            ]
        )

    if args.extra_args.strip():
        command.extend(shlex.split(args.extra_args))
    return command


def main() -> None:
    args = parse_args()
    apply_preset_defaults(args)
    project_root = Path(__file__).resolve().parent

    backend_root_arg = args.bevformer_root
    if args.stack == "modern-mmdet3d" and backend_root_arg == "tools/BEVFormer":
        backend_root_arg = "tools/mmdetection3d"

    backend_root = Path(backend_root_arg)
    if not backend_root.is_absolute():
        backend_root = project_root / backend_root
    backend_root = backend_root.resolve()

    legacy_root = (project_root / "tools" / "BEVFormer").resolve()
    modern_root = (project_root / "tools" / "mmdetection3d").resolve()

    if args.stack == "modern-mmdet3d" and not backend_is_usable(modern_root):
        if backend_is_usable(legacy_root):
            print("偵測到 modern-mmdet3d 尚未就緒，改用 legacy-bevformer 後端。")
            args.stack = "legacy-bevformer"
            backend_root = legacy_root
        else:
            backend_root = modern_root

    if args.stack == "legacy-bevformer" and not backend_is_usable(legacy_root):
        if backend_is_usable(modern_root):
            print("偵測到 legacy-bevformer 尚未就緒，改用 modern-mmdet3d 後端。")
            args.stack = "modern-mmdet3d"
            backend_root = modern_root

    if args.stack == "modern-mmdet3d" and not config_exists(modern_root, args.config):
        if config_exists(legacy_root, args.config):
            print("偵測到 config 位於 legacy BEVFormer，改用 legacy-bevformer 後端。")
            args.stack = "legacy-bevformer"
            backend_root = legacy_root

    if args.stack == "legacy-bevformer" and not config_exists(legacy_root, args.config):
        if config_exists(modern_root, args.config):
            print("偵測到 config 位於 modern mmdetection3d，改用 modern-mmdet3d 後端。")
            args.stack = "modern-mmdet3d"
            backend_root = modern_root

    if not backend_root.exists():
        if args.stack == "legacy-bevformer":
            raise FileNotFoundError(
                "找不到 BEVFormer 目錄。請先在 tools/BEVFormer 安裝官方專案: "
                "https://github.com/fundamentalvision/BEVFormer"
            )
        raise FileNotFoundError(
            "找不到 mmdetection3d 目錄。請先在 tools/mmdetection3d 安裝官方專案: "
            "https://github.com/open-mmlab/mmdetection3d"
        )

    if not backend_is_usable(backend_root):
        if args.stack == "legacy-bevformer":
            raise FileNotFoundError(
                "BEVFormer 目錄存在，但缺少 tools/test.py 或 tools/train.py。"
            )
        raise FileNotFoundError(
            "mmdetection3d 目錄存在，但缺少 tools/test.py 或 tools/train.py。"
        )

    config_path = resolve_path(backend_root, args.config, required=True)
    if args.stack == "legacy-bevformer":
        ensure_legacy_dataset_ready(args, project_root, config_path)

    command = build_command(args, backend_root, project_root)
    run_cwd = project_root if args.stack == "legacy-bevformer" else backend_root
    print("執行後端:", args.stack)
    print("執行目錄:", run_cwd)
    print("執行指令:", " ".join(shlex.quote(part) for part in command))

    if args.dry_run:
        return

    # Set up environment for legacy-bevformer stack
    env = None
    if args.stack == "legacy-bevformer":
        import os
        env = os.environ.copy()
        mmdet3d_path = str(project_root / "tools" / "mmdetection3d")
        bevformer_path = str(backend_root)
        current_pythonpath = env.get("PYTHONPATH", "")
        new_pythonpath = f"{mmdet3d_path}:{bevformer_path}"
        if current_pythonpath:
            new_pythonpath = f"{new_pythonpath}:{current_pythonpath}"
        env["PYTHONPATH"] = new_pythonpath
        env.setdefault("MPLCONFIGDIR", tempfile.mkdtemp(prefix="bevformer-mpl-"))
        print(f"設置 PYTHONPATH: {new_pythonpath}")

    subprocess.run(command, cwd=str(run_cwd), check=True, env=env)


if __name__ == "__main__":
    main()
