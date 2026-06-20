"""The internal audio-grounded correction model (Gemma 3n E4B).

Gemma 3n E4B accepts native AUDIO input and runs via transformers on the GPU. It
is a FIXED INTERNAL engine for the second, audio-grounded correction pass — NOT a
user-selectable model, so it is deliberately absent from models_catalog.

⚠️ UNVERIFIED: this path was rebuilt against the real model (the original PR #3
pointed at a non-existent "gemma-4-E4B-it"). `google/gemma-3n-E4B-it` is a GATED
HuggingFace model — accept the license and set HF_TOKEN before downloading. The
transformers inference in audio_correct_cli has NOT been run on a GPU yet.

Downloaded into models/ at runtime (the weights are far too large to bundle).
"""
from __future__ import annotations
import threading
import time
from pathlib import Path
from typing import Callable

from huggingface_hub import snapshot_download

AUDIO_MODEL_ID = "google/gemma-3n-E4B-it"   # GATED; native audio; transformers + GPU
AUDIO_MODEL_DOWNLOAD_MB = 16500


def audio_model_dir(models_root: Path) -> Path:
    return models_root / AUDIO_MODEL_ID.replace("/", "__")


def is_audio_model_installed(models_root: Path) -> bool:
    d = audio_model_dir(models_root)
    # Sharded checkpoints use an index file; single-file ones a plain safetensors.
    has_weights = (d / "model.safetensors").exists() or (d / "model.safetensors.index.json").exists()
    return has_weights and (d / "config.json").exists()


def download_audio_model(models_root: Path,
                         log_cb: Callable[[str], None] | None = None,
                         progress_cb: Callable[[int], None] | None = None) -> Path:
    """Download the Gemma 3n E4B weights into models/ (polls folder size for
    progress, since snapshot_download exposes no hook). Requires HF license
    acceptance + token for this gated model."""
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
        raise RuntimeError("Nedladdning ofullständig: ljudmodellen (vikter/config saknas). "
                           "OBS: Gemma 3n är gated — acceptera licensen och sätt HF_TOKEN.")
    if progress_cb is not None:
        progress_cb(100)
    return target
