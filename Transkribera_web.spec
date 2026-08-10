# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Transkribera web-UI desktop app (pywebview + uvicorn).

One-folder, windowed. Reuses the heavy-dep collection from Transkribera.spec and
adds the web stack (fastapi/uvicorn), pywebview (+ pythonnet for the EdgeChromium
backend) and the static frontend. PySide6 is excluded — the web build has no Qt UI.

Inget byggsteg krävs för frontenden: app/web/ui serveras som den ligger.

Build:  pyinstaller Transkribera_web.spec
Result: dist/Transkribera_web/Transkribera_web.exe
"""
from PyInstaller.utils.hooks import collect_all, collect_submodules
import importlib.util
import os as _os

datas, binaries, hiddenimports = [], [], []

_PKGS = [
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

# Frontenden. Den är versionshanterad och behöver inget byggsteg — den serveras
# precis som den ligger — men den måste med i paketet, annars svarar "/" med
# 503-texten i server.index() i det frysta bygget. Kollas explicit: PyInstaller
# 6.x kraschar annars hela bygget med ett kryptiskt "ERROR: Unable to find ...
# when adding binary and data files" i stället för att säga vad som fattas.
if not _os.path.isdir("app/web/ui"):
    raise SystemExit("app/web/ui saknas — frontenden finns inte i utcheckningen.")
datas += [("app/web/ui", "app/web/ui")]

# Bundlad appdata (centralt innehåll m.m.) där course_data.data_dir() letar
# när appen är fryst (Fas 3).
datas += [("app/data", "app/data")]

# LaTeX-mallarna för provgeneratorn (Fas 4) + Tectonic-motorn med förseedad
# paketcache (offline-kompilering; se exam_pdf.engine_dir).
datas += [("app/templates", "app/templates")]
if _os.path.isdir("bin/tectonic"):
    datas += [("bin/tectonic", "bin/tectonic")]

# llama.cpp-servern buntades här förr (680 MB binär + CUDA-DLL:er). Den är borta
# med den lokala språkmodellen: allt språkmodellsarbete går via Claude Code, som
# körs som ett eget kommando på datorn och inte ska ligga i vår exe.

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
    icon="assets/transkribera.ico",
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
