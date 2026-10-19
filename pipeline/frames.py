"""Block 1: video -> numbered JPEG frames with a pinned decoder (decoder versions change the frames bit for bit)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path


def ffmpeg_path() -> str:
    return os.environ.get("FFMPEG") or shutil.which("ffmpeg") or "ffmpeg"


def probe_fps(video: Path) -> float:
    """Average frame rate from ffprobe next to the chosen ffmpeg."""
    probe = str(Path(ffmpeg_path()).with_name("ffprobe")) if os.environ.get("FFMPEG") else "ffprobe"
    out = subprocess.run([probe, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=avg_frame_rate",
                          "-of", "json", str(video)], capture_output=True, text=True, check=True)
    num, den = json.loads(out.stdout)["streams"][0]["avg_frame_rate"].split("/")
    return float(num) / float(den)


def decode(video: Path, out_dir: Path) -> list[Path]:
    """All frames as f%05d.jpg (%05d keeps sorted() in time order past 9,999 frames)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    if not any(out_dir.glob("*.jpg")):
        subprocess.run([ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-y", "-i", str(video), "-vsync", "0",
                        "-qscale:v", "2", str(out_dir / "f%05d.jpg")], check=True)
    return sorted(out_dir.glob("*.jpg"))
