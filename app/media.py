"""ffmpeg/ffprobe helpers: detect availability and read media duration."""
from __future__ import annotations
import shutil
import subprocess
from pathlib import Path


def parse_duration(ffprobe_output: str) -> float | None:
    for line in ffprobe_output.splitlines():
        if line.startswith("duration="):
            value = line.split("=", 1)[1].strip()
            try:
                return float(value)
            except ValueError:
                return None
    return None


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def probe_duration(path: Path) -> float | None:
    if shutil.which("ffprobe") is None:
        return None
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1", str(path)],
            capture_output=True, text=True, timeout=30,
        )
        return parse_duration(out.stdout)
    except Exception:
        return None
