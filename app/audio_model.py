"""The internal audio-grounded correction model.

Gemma 4 E4B has native audio input and runs via transformers on the GPU. It is a
FIXED INTERNAL engine for the second, audio-grounded correction pass — NOT a
user-selectable model, so it is deliberately absent from models_catalog. The
text correction/analysis model (gemma4:26b-a4b-it-qat via Ollama) does not take
audio and is unaffected.

Like the Whisper/Parakeet models it is downloaded into models/ at runtime (the
~16 GB weights are far too large to bundle in the exe).
"""
from __future__ import annotations
import threading
import time
from pathlib import Path
from typing import Callable

from huggingface_hub import snapshot_download

AUDIO_MODEL_ID = "google/gemma-4-E4B-it"   # not gated; native audio; transformers + GPU
AUDIO_MODEL_DOWNLOAD_MB = 16500


def audio_model_dir(models_root: Path) -> Path:
    return models_root / AUDIO_MODEL_ID.replace("/", "__")


def is_audio_model_installed(models_root: Path) -> bool:
    d = audio_model_dir(models_root)
    return (d / "model.safetensors").exists() and (d / "config.json").exists()


def download_audio_model(models_root: Path,
                         log_cb: Callable[[str], None] | None = None,
                         progress_cb: Callable[[int], None] | None = None) -> Path:
    """Download the Gemma 4 E4B weights into models/ (polls folder size for progress,
    since snapshot_download exposes no hook)."""
    target = audio_model_dir(models_root)
    if log_cb:
        log_cb(f"Laddar ner ljudmodell {AUDIO_MODEL_ID} ...")

    stop = {"v": False}
    if progress_cb is not None:
        total = AUDIO_MODEL_DOWNLOAD_MB * 1024 * 1024

        def monitor():
            while not stop["v"]:
                got = 0
                try:
                    for p in target.rglob("*"):
                        try:
                            if p.is_file():
                                got += p.stat().st_size
                        except OSError:
                            pass
                except OSError:
                    pass
                progress_cb(max(0, min(int(got / total * 100), 99)))
                time.sleep(0.5)
        threading.Thread(target=monitor, daemon=True).start()

    try:
        snapshot_download(repo_id=AUDIO_MODEL_ID, local_dir=str(target))
    finally:
        stop["v"] = True

    if not is_audio_model_installed(models_root):
        raise RuntimeError("Nedladdning ofullstandig: ljudmodellen (model.safetensors saknas)")
    if progress_cb is not None:
        progress_cb(100)
    return target
