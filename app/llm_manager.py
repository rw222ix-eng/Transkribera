"""Download and locate the local GGUF LLM used by the bundled llama.cpp server.

Mirrors app/whisper_manager.py: a single locked model, downloaded into models/
at runtime (the ~15 GB GGUF is far too large to bundle in the exe), progress
reported by polling the target folder size (huggingface_hub exposes no hook).
"""
from __future__ import annotations
import shutil
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
    # Vision models need a separate multimodal projector (mmproj) GGUF alongside
    # the weights; llama-server loads it via --mmproj. None for text-only models.
    mmproj_filename: str | None = None

    @property
    def is_vision(self) -> bool:
        return self.mmproj_filename is not None


# Locked text model — values from the Phase 0 spike.
# Phase 3 may swap this after the Swedish benchmark.
ACTIVE_LLM = GGUFModelSpec(
    repo_id="Qwen/Qwen3-14B-GGUF",
    filename="Qwen3-14B-Q8_0.gguf",
    label="Qwen3 14B (Q8_0)",
    download_mb=14971,
)

# Multimodal model for image chat. Gemma 3 4B (vision) is small enough to load
# after the text model is unloaded on the 24 GB card, and ships an mmproj
# projector (SigLIP) in the same repo. llama-server is switched to this model
# on demand whenever the chat carries an image (see gpu_arbiter.ensure_model).
VISION_LLM = GGUFModelSpec(
    repo_id="ggml-org/gemma-3-4b-it-GGUF",
    filename="gemma-3-4b-it-Q4_K_M.gguf",
    label="Gemma 3 4B (vision)",
    download_mb=3341,                       # weights ~2.5 GB + mmproj ~0.85 GB
    mmproj_filename="mmproj-model-f16.gguf",
)

# Every GGUF the app can manage; the text model stays first so it remains the default.
ALL_LLMS: list[GGUFModelSpec] = [ACTIVE_LLM, VISION_LLM]


def spec_by_name(name: str) -> GGUFModelSpec | None:
    """Resolve a GGUF filename (the catalog 'name') to its spec."""
    return next((s for s in ALL_LLMS if s.filename == name), None)


def model_dir_for(spec: GGUFModelSpec, models_root: Path) -> Path:
    return models_root / "llm" / spec.repo_id.replace("/", "__")


def model_path_for(spec: GGUFModelSpec, models_root: Path) -> Path:
    return model_dir_for(spec, models_root) / spec.filename


def mmproj_path_for(spec: GGUFModelSpec, models_root: Path) -> Path | None:
    if not spec.mmproj_filename:
        return None
    return model_dir_for(spec, models_root) / spec.mmproj_filename


def is_installed(spec: GGUFModelSpec, models_root: Path) -> bool:
    if not model_path_for(spec, models_root).exists():
        return False
    mmproj = mmproj_path_for(spec, models_root)
    return mmproj is None or mmproj.exists()


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


def download_gguf(spec: GGUFModelSpec, models_root: Path,
                  log_cb: Callable[[str], None] | None = None,
                  progress_cb: Callable[[int], None] | None = None) -> Path:
    target = model_dir_for(spec, models_root)
    target.mkdir(parents=True, exist_ok=True)
    if log_cb:
        log_cb(f"Laddar ner {spec.filename} ...")

    stop = {"v": False}
    if progress_cb is not None:
        def monitor():
            while not stop["v"]:
                progress_cb(_progress_percent(_dir_size(target), spec.download_mb))
                time.sleep(0.5)
        threading.Thread(target=monitor, daemon=True).start()

    try:
        hf_hub_download(repo_id=spec.repo_id, filename=spec.filename,
                        local_dir=str(target))
        if spec.mmproj_filename:               # vision projector lives in the same repo
            if log_cb:
                log_cb(f"Laddar ner {spec.mmproj_filename} (vision) ...")
            hf_hub_download(repo_id=spec.repo_id, filename=spec.mmproj_filename,
                            local_dir=str(target))
    finally:
        stop["v"] = True

    if not is_installed(spec, models_root):
        raise RuntimeError(f"Nedladdning ofullständig: {spec.filename} saknas")
    if progress_cb is not None:
        progress_cb(100)
    return model_path_for(spec, models_root)


def delete_gguf(spec: GGUFModelSpec, models_root: Path) -> bool:
    """Radera GGUF-modellens katalog (vikter + ev. mmproj) från disk. Returnerar
    True om något togs bort. Vägrar (False) utanför models_root/llm/."""
    root = Path(models_root).resolve()
    target = model_dir_for(spec, models_root).resolve()
    if root not in target.parents:
        return False
    if target.exists():
        shutil.rmtree(target)
        return True
    return False
