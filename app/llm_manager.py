"""Download and locate the local GGUF LLM used by the bundled llama.cpp server.

Mirrors app/whisper_manager.py: a single locked model, downloaded into models/
at runtime (the ~15 GB GGUF is far too large to bundle in the exe), progress
reported by polling the target folder size (huggingface_hub exposes no hook).
"""
from __future__ import annotations
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from huggingface_hub import hf_hub_download


@dataclass(frozen=True)
class GGUFModelSpec:
    repo_id: str       # HF repo, e.g. "Qwen/Qwen3-14B-GGUF"
    filename: str      # GGUF file within the repo, e.g. "Qwen3-14B-Q8_0.gguf"
    label: str
    download_mb: int


# Locked active model — values from the Phase 0 spike
# (docs/superpowers/notes/2026-06-19-llamacpp-spike.md).
# Phase 3 may swap this after the Swedish benchmark.
ACTIVE_LLM = GGUFModelSpec(
    repo_id="Qwen/Qwen3-14B-GGUF",
    filename="Qwen3-14B-Q8_0.gguf",
    label="Qwen3 14B (Q8_0)",
    download_mb=14971,
)


def model_dir_for(spec: GGUFModelSpec, models_root: Path) -> Path:
    return models_root / "llm" / spec.repo_id.replace("/", "__")


def model_path_for(spec: GGUFModelSpec, models_root: Path) -> Path:
    return model_dir_for(spec, models_root) / spec.filename


def is_installed(spec: GGUFModelSpec, models_root: Path) -> bool:
    return model_path_for(spec, models_root).exists()


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


def download_gguf(spec: GGUFModelSpec, models_root: Path,
                  log_cb: Callable[[str], None] | None = None,
                  progress_cb: Callable[[int], None] | None = None) -> Path:
    target = model_dir_for(spec, models_root)
    target.mkdir(parents=True, exist_ok=True)
    if log_cb:
        log_cb(f"Laddar ner {spec.filename} ...")

    stop = {"v": False}
    if progress_cb is not None:
        total = spec.download_mb * 1024 * 1024

        def monitor():
            while not stop["v"]:
                progress_cb(max(0, min(int(_dir_size(target) / total * 100), 99)))
                time.sleep(0.5)
        threading.Thread(target=monitor, daemon=True).start()

    try:
        hf_hub_download(repo_id=spec.repo_id, filename=spec.filename,
                        local_dir=str(target))
    finally:
        stop["v"] = True

    if not is_installed(spec, models_root):
        raise RuntimeError(f"Nedladdning ofullständig: {spec.filename} saknas")
    if progress_cb is not None:
        progress_cb(100)
    return model_path_for(spec, models_root)
