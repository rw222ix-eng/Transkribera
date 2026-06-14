"""Scan the machine for GPU/VRAM/CUDA, RAM, CPU and free disk."""
from __future__ import annotations
import os
import platform
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class HardwareInfo:
    has_cuda: bool
    gpu_name: str | None
    vram_mb: int        # 0 if no GPU detected
    ram_mb: int
    cpu_cores: int
    cpu_name: str
    free_disk_mb: int


def _gpu_via_torch() -> tuple[bool, str | None, int]:
    try:
        import torch
        if torch.cuda.is_available():
            props = torch.cuda.get_device_properties(0)
            return True, props.name, props.total_memory // (1024 * 1024)
    except Exception:
        pass
    return False, None, 0


def _gpu_via_nvidia_smi() -> tuple[str | None, int]:
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0 and out.stdout.strip():
            name, mem = out.stdout.strip().splitlines()[0].split(",")
            return name.strip(), int(mem.strip())
    except Exception:
        pass
    return None, 0


def scan_hardware(cache_dir: Path) -> HardwareInfo:
    has_cuda, gpu_name, vram_mb = _gpu_via_torch()
    if vram_mb == 0:
        name, mem = _gpu_via_nvidia_smi()
        if mem > 0:
            gpu_name, vram_mb = name, mem  # present but maybe no working CUDA

    try:
        import psutil
        ram_mb = psutil.virtual_memory().total // (1024 * 1024)
    except Exception:
        ram_mb = 0

    cache_dir.mkdir(parents=True, exist_ok=True)
    free_disk_mb = shutil.disk_usage(cache_dir).free // (1024 * 1024)

    return HardwareInfo(
        has_cuda=has_cuda,
        gpu_name=gpu_name,
        vram_mb=vram_mb,
        ram_mb=ram_mb,
        cpu_cores=os.cpu_count() or 1,
        cpu_name=platform.processor() or platform.machine(),
        free_disk_mb=free_disk_mb,
    )
