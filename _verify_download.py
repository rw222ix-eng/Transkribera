"""Reproduce the windowed-frozen download crash on the REAL download path, then
prove the startup guard (in transkribera.py) fixes it. Run in source; the bundled
code in the exe is identical, and we simulate the frozen condition (None streams)."""
import sys
from pathlib import Path

real_out = sys.__stdout__  # keep a handle to report through, regardless of redirection
from app.models_catalog import WHISPER_MODELS
from app import whisper_manager

SPEC = next(s for s in WHISPER_MODELS if s.id == "KBLab/kb-whisper-tiny")  # 75 MB
ROOT = Path("models_verify")

# --- Phase A: simulate windowed frozen (None streams), NO guard -> expect crash ---
sys.stdout = None
sys.stderr = None
try:
    whisper_manager.download_whisper(SPEC, ROOT)
    real_out.write("PHASE_A: no crash (unexpected)\n")
except Exception as e:
    real_out.write(f"PHASE_A reproduced crash: {type(e).__name__}: {e}\n")

# --- Phase B: apply the SAME guard transkribera.py uses, retry -> expect success ---
import os
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

path = whisper_manager.download_whisper(SPEC, ROOT)
ok = whisper_manager.is_installed(SPEC, ROOT)
real_out.write(f"PHASE_B with guard: download OK, is_installed={ok}, path={path}\n")
real_out.flush()
