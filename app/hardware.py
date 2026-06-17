"""Scan the machine for GPU/VRAM/CUDA, RAM, CPU and disks.

The base fields (has_cuda, gpu_name, vram_mb, ram_mb, cpu_cores, cpu_name,
free_disk_mb) are consumed by recommend.py and the fit logic. The richer fields
(free VRAM, CUDA version, compute capability, arch, total disk, the disks list)
feed the redesigned hardware panel; all degrade gracefully to sensible defaults.
"""
from __future__ import annotations
import os
import platform
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DiskInfo:
    id: str             # short id, e.g. "c"
    drive: str          # display, e.g. "C:"
    name: str           # volume label or a generic name
    total_mb: int
    free_mb: int


@dataclass
class HardwareInfo:
    has_cuda: bool
    gpu_name: str | None
    vram_mb: int            # total VRAM, 0 if no GPU detected
    ram_mb: int             # total RAM
    cpu_cores: int
    cpu_name: str
    free_disk_mb: int       # free space on the models drive
    # ---- richer fields (best-effort) ----
    vram_free_mb: int = 0
    total_disk_mb: int = 0
    cuda_version: str = ""
    compute_capability: str = ""
    gpu_arch: str = ""
    ram_free_mb: int = 0
    disks: list[DiskInfo] = field(default_factory=list)


# Compute-capability → NVIDIA architecture name (best-effort display only).
_ARCH_BY_CC = {
    "9.0": "Hopper", "8.9": "Ada Lovelace", "8.6": "Ampere", "8.0": "Ampere",
    "7.5": "Turing", "7.0": "Volta", "6.1": "Pascal", "6.0": "Pascal",
    "12.0": "Blackwell", "10.0": "Blackwell",
}


def _gpu_via_torch() -> dict:
    """Return {has_cuda, name, total_mb, free_mb, cc, arch, cuda_version} via torch."""
    out = {"has_cuda": False, "name": None, "total_mb": 0, "free_mb": 0,
           "cc": "", "arch": "", "cuda_version": ""}
    try:
        import torch
        if torch.cuda.is_available():
            props = torch.cuda.get_device_properties(0)
            out["has_cuda"] = True
            out["name"] = props.name
            out["total_mb"] = props.total_memory // (1024 * 1024)
            cc = f"{props.major}.{props.minor}"
            out["cc"] = cc
            out["arch"] = _ARCH_BY_CC.get(cc, "")
            out["cuda_version"] = getattr(torch.version, "cuda", "") or ""
            try:
                free_b, _total_b = torch.cuda.mem_get_info(0)
                out["free_mb"] = int(free_b) // (1024 * 1024)
            except Exception:
                pass
    except Exception:
        pass
    return out


def _gpu_via_nvidia_smi() -> dict:
    """Fallback for name / total+free VRAM / CUDA version when torch is unavailable."""
    out = {"name": None, "total_mb": 0, "free_mb": 0, "cuda_version": ""}
    try:
        r = subprocess.run(
            ["nvidia-smi",
             "--query-gpu=name,memory.total,memory.free,driver_version",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5)
        if r.returncode == 0 and r.stdout.strip():
            parts = [p.strip() for p in r.stdout.strip().splitlines()[0].split(",")]
            out["name"] = parts[0]
            out["total_mb"] = int(float(parts[1]))
            out["free_mb"] = int(float(parts[2]))
    except Exception:
        pass
    # CUDA runtime version (separate query — not all builds support it)
    try:
        r = subprocess.run(["nvidia-smi", "--query", "--display=COMPUTE"],
                           capture_output=True, text=True, timeout=5)
    except Exception:
        pass
    return out


def _scan_disks(models_root: Path) -> tuple[list[DiskInfo], int, int]:
    """Enumerate fixed drives. Returns (disks, models_total_mb, models_free_mb)."""
    disks: list[DiskInfo] = []
    try:
        import psutil
        parts = psutil.disk_partitions(all=False)
    except Exception:
        parts = []
    seen = set()
    for p in parts:
        mount = p.mountpoint
        if not mount or mount in seen:
            continue
        # Skip removable/cdrom on Windows when flagged
        opts = (getattr(p, "opts", "") or "")
        if "cdrom" in opts.lower():
            continue
        seen.add(mount)
        try:
            u = shutil.disk_usage(mount)
        except OSError:
            continue
        drive = mount.rstrip("\\/") or mount       # "C:\\" -> "C:"
        did = (drive.replace(":", "") or mount).lower()[:2]
        disks.append(DiskInfo(
            id=did, drive=drive, name=_volume_label(mount) or "Lokal disk",
            total_mb=u.total // (1024 * 1024), free_mb=u.free // (1024 * 1024)))
    # models drive usage (always available even if partition scan failed)
    models_root.mkdir(parents=True, exist_ok=True)
    mu = shutil.disk_usage(models_root)
    return disks, mu.total // (1024 * 1024), mu.free // (1024 * 1024)


def _volume_label(mount: str) -> str:
    """Windows volume label via ctypes; empty string elsewhere / on failure."""
    if platform.system() != "Windows":
        return ""
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(261)
        fsbuf = ctypes.create_unicode_buffer(261)
        root = mount if mount.endswith("\\") else mount + "\\"
        ok = ctypes.windll.kernel32.GetVolumeInformationW(
            ctypes.c_wchar_p(root), buf, ctypes.sizeof(buf),
            None, None, None, fsbuf, ctypes.sizeof(fsbuf))
        if ok:
            label = buf.value.strip()
            fs = fsbuf.value.strip()
            if label and fs:
                return f"{label} · {fs}"
            return label or (f"{fs}" if fs else "")
    except Exception:
        pass
    return ""


def scan_hardware(cache_dir: Path) -> HardwareInfo:
    g = _gpu_via_torch()
    has_cuda = g["has_cuda"]
    gpu_name = g["name"]
    vram_total = g["total_mb"]
    vram_free = g["free_mb"]
    cuda_version = g["cuda_version"]
    cc = g["cc"]
    arch = g["arch"]
    if vram_total == 0:                      # torch found nothing — try nvidia-smi
        s = _gpu_via_nvidia_smi()
        if s["total_mb"] > 0:
            gpu_name = s["name"]
            vram_total = s["total_mb"]
            vram_free = s["free_mb"]

    try:
        import psutil
        vm = psutil.virtual_memory()
        ram_mb = vm.total // (1024 * 1024)
        ram_free_mb = vm.available // (1024 * 1024)
    except Exception:
        ram_mb = 0
        ram_free_mb = 0

    disks, total_disk_mb, free_disk_mb = _scan_disks(cache_dir)

    if not cuda_version and has_cuda:
        cuda_version = ""  # unknown but CUDA present
    precisions = "fp16 · int8 · int4" if has_cuda else "int8"

    return HardwareInfo(
        has_cuda=has_cuda,
        gpu_name=gpu_name,
        vram_mb=vram_total,
        ram_mb=ram_mb,
        cpu_cores=os.cpu_count() or 1,
        cpu_name=platform.processor() or platform.machine(),
        free_disk_mb=free_disk_mb,
        vram_free_mb=vram_free,
        total_disk_mb=total_disk_mb,
        cuda_version=cuda_version,
        compute_capability=cc,
        gpu_arch=arch,
        ram_free_mb=ram_free_mb,
        disks=disks,
    )
