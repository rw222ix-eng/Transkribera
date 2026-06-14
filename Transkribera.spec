# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Transkribera (one-folder, windowed).

Collects the heavy ML deps so their bundled native DLLs (CUDA/cuDNN via ctranslate2,
PyAV's ffmpeg libs, torch) travel with the app. Build:  pyinstaller Transkribera.spec
Result: dist/Transkribera/Transkribera.exe
"""
from PyInstaller.utils.hooks import collect_all
import importlib.util

datas, binaries, hiddenimports = [], [], []

# Only collect packages that are actually importable, so an absent optional dep
# (e.g. onnxruntime) doesn't break the build.
_HEAVY = [
    "torch", "ctranslate2", "faster_whisper", "av",
    "huggingface_hub", "tokenizers", "onnxruntime",
]
for pkg in _HEAVY:
    if importlib.util.find_spec(pkg) is None:
        continue
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    ["transkribera.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "PyQt5", "PyQt6"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Transkribera",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # windowed — no console pops up for the GUI
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
    name="Transkribera",
)
