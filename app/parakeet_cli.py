"""Run ONE Parakeet (onnx-asr, GPU) transcription in an isolated process.

Mirrors app.transcribe_cli's stdout protocol so app.web.server streams it
identically:
  LOG <text> | PROGRESS <int> | FILE <path> | SEG <start> <end> <text> | DONE

Parakeet TDT 0.6B v3 is an NVIDIA NeMo transducer run via onnx-asr on the CUDA
execution provider (GPU). onnx-asr does not chunk long audio, so we decode the
input to 16 kHz mono and transcribe it in overlapping windows, offset the
per-token timestamps, and group tokens into subtitle-sized segments. Like
transcribe_cli we os._exit(0) at the end to skip any native teardown.
"""
from __future__ import annotations
import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

from app.gpu_dll import ensure_cuda_dll_path
from app.transcriber import Segment, write_outputs, clean_caption_segments

SAMPLE_RATE = 16000
CHUNK_SEC = 30.0          # window length fed to onnx-asr at once
OVERLAP_SEC = 2.0         # adjacent windows overlap; merged at the midpoint
MAX_SEG_SEC = 12.0        # force a segment break past this length
SEG_GAP_SEC = 0.8         # a silence gap this long starts a new segment
MODEL_NAME = "nemo-parakeet-tdt-0.6b-v3"


def _log(msg: str) -> None:
    print(f"LOG {msg}", flush=True)


def decode_audio(path: str, sr: int = SAMPLE_RATE) -> np.ndarray:
    """Decode any media file to mono float32 PCM at `sr` via ffmpeg."""
    proc = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", str(sr), "-f", "s16le", "-"],
        capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError("ffmpeg-avkodning misslyckades: "
                           + proc.stderr.decode("utf-8", "replace")[:300])
    return np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float32) / 32768.0


def _chunk_starts(audio_dur: float) -> list[float]:
    if audio_dur <= CHUNK_SEC:
        return [0.0]
    step = CHUNK_SEC - OVERLAP_SEC
    starts, c = [], 0.0
    while c < audio_dur:
        starts.append(c)
        c += step
    return starts


def _tokens_to_segments(tokens: list[str], times: list[float], audio_end: float) -> list[Segment]:
    """Group token-level (token, start-time) pairs into subtitle-sized segments."""
    segs: list[Segment] = []
    cur: list[str] = []
    start = None

    def end_of(i: int) -> float:
        return times[i + 1] if i + 1 < len(times) else audio_end

    for i, (tok, t) in enumerate(zip(tokens, times)):
        if start is None:
            start = t
        cur.append(tok)
        text = "".join(cur).strip()
        dur = end_of(i) - start
        gap = (times[i + 1] - t) if i + 1 < len(times) else 0.0
        ends_sentence = text.endswith((".", "!", "?", "…"))
        if (ends_sentence and dur >= 1.0) or dur >= MAX_SEG_SEC or gap >= SEG_GAP_SEC:
            if text:
                segs.append(Segment(start, end_of(i), text))
            cur, start = [], None
    if cur:
        text = "".join(cur).strip()
        if text:
            segs.append(Segment(start, audio_end, text))
    return segs


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--audio", required=True)
    p.add_argument("--model-dir", required=True)
    p.add_argument("--language", default="")  # Parakeet v3 is multilingual; auto
    p.add_argument("--out-base", required=True)
    p.add_argument("--formats", required=True)
    args = p.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    ensure_cuda_dll_path()
    import onnx_asr
    import onnxruntime as ort
    ort.set_default_logger_severity(3)  # errors only — keep the stdout protocol clean
    try:
        ort.preload_dlls()  # robustly load CUDA 12.x / cuDNN 9.x DLLs (onnxruntime-gpu)
    except Exception:
        pass

    _log("Avkodar ljud till 16 kHz mono...")
    wav = decode_audio(args.audio)
    audio_dur = len(wav) / SAMPLE_RATE
    if audio_dur <= 0:
        raise RuntimeError("Tom eller olasbar ljudfil")

    providers = [("CUDAExecutionProvider", {}), ("CPUExecutionProvider", {})]
    _log("Laddar Parakeet-modell pa GPU...")
    # Retry once: a freshly-downloaded model file can be briefly locked (e.g. by
    # antivirus), which would otherwise fail the very first load.
    model = None
    for _attempt in range(2):
        try:
            model = onnx_asr.load_model(MODEL_NAME, path=args.model_dir,
                                        providers=providers).with_timestamps()
            break
        except Exception as e:
            if _attempt == 0:
                _log("Modell-laddning misslyckades (" + type(e).__name__ + "), forsoker igen om 2 s...")
                time.sleep(2)
            else:
                raise

    starts = _chunk_starts(audio_dur)
    n = len(starts)
    tokens: list[str] = []
    times: list[float] = []
    for ci, c_start in enumerate(starts):
        c_end = min(audio_dur, c_start + CHUNK_SEC)
        lo, hi = int(c_start * SAMPLE_RATE), int(c_end * SAMPLE_RATE)
        res = model.recognize(wav[lo:hi], sample_rate=SAMPLE_RATE)
        toks = list(getattr(res, "tokens", []) or [])
        tms = [c_start + float(t) for t in (getattr(res, "timestamps", []) or [])]
        # Keep only this window's tokens between the overlap midpoints so adjacent
        # windows meet cleanly with no duplicate or dropped tokens.
        keep_lo = c_start + (OVERLAP_SEC / 2 if ci > 0 else 0.0)
        keep_hi = c_end - (OVERLAP_SEC / 2 if ci < n - 1 else 0.0)
        for tok, t in zip(toks, tms):
            if keep_lo <= t < keep_hi:
                tokens.append(tok)
                times.append(t)
        print(f"PROGRESS {min(99, int(c_end / audio_dur * 100))}", flush=True)
    print("PROGRESS 100", flush=True)

    segs = _tokens_to_segments(tokens, times, audio_dur)
    segs = clean_caption_segments(segs)
    for s in segs:
        print(f"SEG {s.start} {s.end} {s.text}", flush=True)

    formats = [f for f in args.formats.split(",") if f]
    for w in write_outputs(segs, Path(args.out_base), formats):
        print(f"FILE {w}", flush=True)
    print("DONE", flush=True)

    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)  # skip native teardown


if __name__ == "__main__":
    main()
