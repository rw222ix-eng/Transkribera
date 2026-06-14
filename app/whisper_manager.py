"""Download and detect locally-installed faster-whisper models."""
from __future__ import annotations
from pathlib import Path
from typing import Callable

from huggingface_hub import snapshot_download

from app.models_catalog import WhisperModelSpec, WHISPER_MODELS


def model_dir_for(spec: WhisperModelSpec, models_root: Path) -> Path:
    safe = spec.id.replace("/", "__")
    return models_root / safe


def is_installed(spec: WhisperModelSpec, models_root: Path) -> bool:
    return (model_dir_for(spec, models_root) / "model.bin").exists()


def download_whisper(spec: WhisperModelSpec, models_root: Path,
                     log_cb: Callable[[str], None] | None = None) -> Path:
    target = model_dir_for(spec, models_root)
    if log_cb:
        log_cb(f"Laddar ner {spec.id} ...")
    snapshot_download(repo_id=spec.id, local_dir=str(target))
    if not is_installed(spec, models_root):
        raise RuntimeError(f"Nedladdning ofullständig: {spec.id} (model.bin saknas)")
    return target


def installed_specs(models_root: Path) -> list[WhisperModelSpec]:
    return [s for s in WHISPER_MODELS if is_installed(s, models_root)]
