# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Transkribera web-UI desktop app (pywebview + uvicorn).

One-folder, windowed. Reuses the heavy-dep collection from Transkribera.spec and
adds the web stack (fastapi/uvicorn), pywebview (+ pythonnet for the EdgeChromium
backend) and the static frontend. PySide6 is excluded — the web build has no Qt UI.

Build:  pyinstaller Transkribera_web.spec
Result: dist/Transkribera_web/Transkribera_web.exe
"""
from PyInstaller.utils.hooks import collect_all, collect_submodules
import importlib.util

datas, binaries, hiddenimports = [], [], []

_PKGS = [
    "torch", "torchvision", "torchaudio", "ctranslate2", "faster_whisper", "av",
    "huggingface_hub", "tokenizers", "safetensors", "onnxruntime", "onnx_asr",
    "transformers", "accelerate",
    "fastapi", "starlette", "uvicorn", "anyio", "h11", "click", "sniffio",
]
for pkg in _PKGS:
    if importlib.util.find_spec(pkg) is None:
        continue
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# onnxruntime-gpu's CUDA provider DLL depends on the nvidia-*-cu12 wheels' DLLs
# (cublasLt64_12.dll, cudnn64_9.dll, ...). Collect those packages so they ship under
# nvidia/<pkg>/bin/, where app.gpu_dll.ensure_cuda_dll_path() puts them on PATH at runtime.
import glob as _glob, os as _os, site as _site
_NV = ["nvidia.cublas", "nvidia.cudnn", "nvidia.cufft", "nvidia.curand",
       "nvidia.cuda_runtime", "nvidia.cuda_nvrtc", "nvidia.nvjitlink"]
for _nvpkg in _NV:
    if importlib.util.find_spec(_nvpkg) is not None:
        d, b, h = collect_all(_nvpkg)
        datas += d
        binaries += b
        hiddenimports += h
# Belt-and-suspenders: add the bin/*.dll explicitly under nvidia/<pkg>/bin.
for _sp in _site.getsitepackages() + [_site.getusersitepackages()]:
    _nvbase = _os.path.join(_sp, "nvidia")
    if _os.path.isdir(_nvbase):
        for _dll in _glob.glob(_os.path.join(_nvbase, "*", "bin", "*.dll")):
            binaries.append((_dll, _os.path.relpath(_os.path.dirname(_dll), _sp)))
        break

# uvicorn picks protocol/loop/lifespan implementations dynamically at runtime.
hiddenimports += collect_submodules("uvicorn")
# transformers lazy-loads model classes (Gemma 4 / multimodal audio); ensure present.
hiddenimports += collect_submodules("transformers.models.gemma4")
hiddenimports += collect_submodules("transformers.models.gemma4_unified")

# Bundle the web frontend where server._static_dir() looks for it when frozen.
datas += [("app/web/static", "app/web/static")]

a = Analysis(
    ["transkribera_web.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "PyQt5", "PyQt6", "PySide6",
              "webview", "pywebview", "pythonnet", "clr", "clr_loader"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Transkribera_web",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Transkribera_web",
)
