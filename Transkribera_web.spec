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
    "torch", "ctranslate2", "faster_whisper", "av",
    "huggingface_hub", "tokenizers", "onnxruntime",
    "fastapi", "starlette", "uvicorn", "anyio", "h11", "click", "sniffio",
    "webview", "clr_loader", "pythonnet",
]
for pkg in _PKGS:
    if importlib.util.find_spec(pkg) is None:
        continue
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# uvicorn picks protocol/loop/lifespan implementations dynamically at runtime.
hiddenimports += collect_submodules("uvicorn")
hiddenimports += ["clr"]

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
    excludes=["tkinter", "matplotlib", "PyQt5", "PyQt6", "PySide6"],
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
    console=False,
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
