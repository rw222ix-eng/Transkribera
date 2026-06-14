"""Download YouTube media with yt-dlp at best quality (refactor of ladda_ner.py)."""
from __future__ import annotations
import os
import subprocess
from pathlib import Path
from typing import Callable


def _ensure_deno_on_path() -> None:
    deno_root = Path.home() / "AppData/Local/Microsoft/WinGet/Packages"
    for d in deno_root.glob("DenoLand.Deno_*"):
        os.environ["PATH"] = str(d) + os.pathsep + os.environ.get("PATH", "")
        break


def build_ytdlp_command(url: str, cookies_file: Path | None, output_dir: Path,
                        fmt: str | None = None) -> list[str]:
    cmd = ["yt-dlp"]
    if cookies_file and cookies_file.exists():
        cmd += ["--cookies", str(cookies_file)]
    cmd += ["-f", fmt or "bv*+ba/b"]
    cmd += ["--merge-output-format", "mkv"]
    cmd += ["-o", str(output_dir / "%(title)s.%(ext)s")]
    cmd += ["--no-playlist", url]
    return cmd


def download(url: str, output_dir: Path, cookies_file: Path | None = None,
             fmt: str | None = None,
             log_cb: Callable[[str], None] | None = None) -> Path:
    """Download `url`, return the path to the newest media file in output_dir."""
    _ensure_deno_on_path()
    output_dir.mkdir(parents=True, exist_ok=True)
    cmd = build_ytdlp_command(url, cookies_file, output_dir, fmt)
    if log_cb:
        log_cb("Kör: " + " ".join(cmd))
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace")
    assert proc.stdout is not None
    for line in proc.stdout:
        if log_cb:
            log_cb(line.rstrip())
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"yt-dlp avslutades med kod {proc.returncode}")

    media = []
    for ext in ("*.mkv", "*.mp4", "*.webm", "*.m4a", "*.mp3"):
        media.extend(output_dir.glob(ext))
    if not media:
        raise RuntimeError("Ingen nedladdad fil hittades")
    return max(media, key=lambda f: f.stat().st_mtime)
