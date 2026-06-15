"""Download and detect locally-installed faster-whisper models."""
from __future__ import annotations
import threading
import time
from pathlib import Path
from typing import Callable

from huggingface_hub import snapshot_download

from app.models_catalog import WhisperModelSpec, WHISPER_MODELS


def model_dir_for(spec: WhisperModelSpec, models_root: Path) -> Path:
    safe = spec.id.replace("/", "__")
    return models_root / safe


def is_installed(spec: WhisperModelSpec, models_root: Path) -> bool:
    return (model_dir_for(spec, models_root) / "model.bin").exists()


def _dir_size(path: Path) -> int:
    total = 0
    try:
        for p in path.rglob("*"):
            try:
                if p.is_file():
                    total += p.stat().st_size
            except OSError:
                pass
    except OSError:
        pass
    return total


def _progress_percent(downloaded_bytes: int, total_mb: int) -> int:
    """Percent of an expected download, capped at 99 until verified complete."""
    if total_mb <= 0:
        return 0
    total = total_mb * 1024 * 1024
    return max(0, min(int(downloaded_bytes / total * 100), 99))


def download_whisper(spec: WhisperModelSpec, models_root: Path,
                     log_cb: Callable[[str], None] | None = None,
                     progress_cb: Callable[[int], None] | None = None) -> Path:
    """Download a faster-whisper model from HuggingFace.

    ``snapshot_download`` exposes no progress hook (and in the windowed exe its
    tqdm output goes nowhere), so when ``progress_cb`` is given we poll the target
    folder size against the catalog's ``download_mb`` on a background thread — this
    is what makes the progress bar actually move instead of sitting at 0%.
    """
    target = model_dir_for(spec, models_root)
    if log_cb:
        log_cb(f"Laddar ner {spec.id} ...")

    stop = {"v": False}
    if progress_cb is not None:
        def monitor():
            while not stop["v"]:
                progress_cb(_progress_percent(_dir_size(target), spec.download_mb))
                time.sleep(0.5)
        threading.Thread(target=monitor, daemon=True).start()

    try:
        snapshot_download(repo_id=spec.id, local_dir=str(target))
    finally:
        stop["v"] = True

    if not is_installed(spec, models_root):
        raise RuntimeError(f"Nedladdning ofullständig: {spec.id} (model.bin saknas)")
    if progress_cb is not None:
        progress_cb(100)
    return target


def installed_specs(models_root: Path) -> list[WhisperModelSpec]:
    return [s for s in WHISPER_MODELS if is_installed(s, models_root)]
