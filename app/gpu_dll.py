"""Make onnxruntime-gpu's CUDA provider loadable on Windows.

onnxruntime-gpu's CUDA provider DLL (onnxruntime_providers_cuda.dll) depends on
the nvidia-*-cu12 wheels' DLLs (cublasLt64_12.dll, cudnn64_9.dll, ...). Those
live under site-packages/nvidia/*/bin and are NOT on the default DLL search path,
so the CUDA provider silently fails to load and inference falls back to CPU.

os.add_dll_directory() alone is not enough: a manually-loaded DLL's *transitive*
dependencies are resolved with the standard search order, which uses PATH — not
the add_dll_directory user dirs. So we prepend those bin dirs to PATH (and also
register them via add_dll_directory for good measure).

Call ensure_cuda_dll_path() BEFORE importing onnxruntime / onnx_asr.
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

_done = False
_lang_done = False


def english_os_messages() -> None:
    """Force this thread's Win32 error strings to English so libraries that decode
    OS messages as UTF-8 (notably onnxruntime's pybind layer) don't crash with a
    UnicodeDecodeError on a Swedish (cp1252) system message such as
    'Det går inte att hitta den angivna modulen.' / a file-in-use error. Without
    this, a transient error (e.g. antivirus briefly locking a freshly-downloaded
    model file) surfaces as an un-decodable byte string and hard-crashes instead of
    being handled gracefully. Safe no-op off Windows."""
    global _lang_done
    if _lang_done or sys.platform != "win32":
        _lang_done = True
        return
    try:
        import ctypes
        k32 = ctypes.windll.kernel32
        try:
            k32.SetThreadUILanguage(0x0409)  # en-US
        except Exception:
            pass
        try:
            num = ctypes.c_ulong(0)
            k32.SetThreadPreferredUILanguages(
                0x8, ctypes.create_unicode_buffer("en-US\0\0"), ctypes.byref(num))  # MUI_LANGUAGE_NAME
        except Exception:
            pass
    except Exception:
        pass
    _lang_done = True


def ensure_cuda_dll_path() -> list[str]:
    """Idempotently put the nvidia CUDA wheel bin dirs on the DLL search path."""
    global _done
    english_os_messages()
    if _done or sys.platform != "win32":
        _done = True
        return []
    dirs: list[str] = []
    roots: list[str] = []
    try:
        import nvidia
        roots += list(nvidia.__path__)
    except Exception:
        pass
    # Frozen (PyInstaller onedir): the nvidia wheels are collected under _MEIPASS/nvidia.
    if getattr(sys, "frozen", False):
        mei = getattr(sys, "_MEIPASS", None)
        if mei:
            roots.append(str(Path(mei) / "nvidia"))
    for r in roots:
        for b in Path(r).glob("*/bin"):
            if b.is_dir():
                dirs.append(str(b))
    dirs = list(dict.fromkeys(dirs))  # dedupe, preserve order
    if dirs:
        os.environ["PATH"] = os.pathsep.join(dirs) + os.pathsep + os.environ.get("PATH", "")
        if hasattr(os, "add_dll_directory"):
            for d in dirs:
                try:
                    os.add_dll_directory(d)
                except OSError:
                    pass
    _done = True
    return dirs
