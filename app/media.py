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


ACCENT = "#3B5BDB"
WEB_VIDEO_EXTS = {".mp4", ".m4v", ".mov", ".webm"}
VIDEO_EXTS = {".mp4", ".mkv", ".mov", ".webm", ".avi", ".m4v"}
AUDIO_EXTS = {".mp3", ".m4a", ".wav", ".aac", ".ogg", ".oga", ".opus", ".flac"}


def _run(cmd: list[str], cwd: str):
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    return proc.returncode, (proc.stderr or "")


def build_thumbnail_cmd(media_name: str, out_name: str, kind: str,
                        seek: float = 1.0) -> list[str]:
    if kind == "video":
        return ["ffmpeg", "-y", "-ss", str(seek), "-i", media_name,
                "-frames:v", "1", "-vf", "scale=640:-2", out_name]
    return ["ffmpeg", "-y", "-i", media_name, "-filter_complex",
            f"showwavespic=s=640x200:colors={ACCENT}", out_name]


def make_thumbnail(media: Path) -> Path | None:
    """Skapa (eller återanvänd cachad) miniatyr bredvid median: en bildruta för
    video, en vågform för ljud. Returnerar sökvägen eller None om ffmpeg saknas/
    misslyckas. Kör med cwd=mappen och endast filnamn (slipper Windows-escaping)."""
    media = Path(media)
    if not media.exists() or shutil.which("ffmpeg") is None:
        return None
    ext = media.suffix.lower()
    kind = "video" if ext in VIDEO_EXTS else "audio"
    out = media.with_name(media.stem + (".thumb.jpg" if kind == "video" else ".thumb.png"))
    try:
        if out.exists() and out.stat().st_mtime >= media.stat().st_mtime:
            return out
    except OSError:
        pass
    seek = 1.0
    if kind == "video":
        dur = probe_duration(media)
        if dur and dur > 0:
            seek = max(1.0, dur * 0.1)
    cmd = build_thumbnail_cmd(media.name, out.name, kind, seek)
    rc, _err = _run(cmd, str(media.parent))
    return out if rc == 0 and out.exists() else None
