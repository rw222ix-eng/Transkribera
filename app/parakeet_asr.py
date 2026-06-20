"""English transcription via NVIDIA Parakeet (onnx-asr / ONNX Runtime).

A second ASR backend alongside faster-whisper. faster-whisper (CTranslate2) cannot
run Parakeet at all — it is a different architecture — so this module wraps
``onnx-asr``: it decodes media to 16 kHz mono PCM with ffmpeg, and because onnx-asr
does not chunk long audio, it transcribes in overlapping windows, offsets the
per-token timestamps, keeps each window's tokens between the overlap midpoints
(so adjacent windows meet with no duplicate/dropped tokens), and groups tokens
into subtitle-sized cues.

Loaded only inside the isolated transcribe-cli subprocess (like WhisperModel), so
its heavy native deps never touch the GUI process.
"""
from __future__ import annotations
import subprocess
from typing import Callable

import numpy as np

from app.transcriber import Segment

SAMPLE_RATE = 16000
CHUNK_SEC = 30.0      # window length fed to onnx-asr at once
OVERLAP_SEC = 2.0     # adjacent windows overlap; merged at the midpoint
MAX_SEG_SEC = 12.0    # force a cue break past this length
SEG_GAP_SEC = 0.8     # a silence gap this long starts a new cue


def decode_audio(path, sr: int = SAMPLE_RATE) -> np.ndarray:
    """Decode any media file to mono float32 PCM at `sr` via ffmpeg."""
    proc = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(sr),
         "-f", "s16le", "-"], capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError("ffmpeg-avkodning misslyckades: "
                           + proc.stderr.decode("utf-8", "replace")[:300])
    return np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float32) / 32768.0


def chunk_starts(audio_dur: float, chunk: float = CHUNK_SEC,
                 overlap: float = OVERLAP_SEC) -> list[float]:
    if audio_dur <= chunk:
        return [0.0]
    step = chunk - overlap
    starts, c = [], 0.0
    while c < audio_dur:
        starts.append(c)
        c += step
    return starts


def group_segments(tokens: list[str], times: list[float], audio_end: float) -> list[Segment]:
    """Group token-level (token, start-time) pairs into subtitle-sized cues:
    break on sentence end, max length, or a silence gap."""
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


def _providers(device: str) -> list:
    """ONNX Runtime providers: CUDA first on GPU, always CPU as fallback."""
    import onnxruntime as ort
    avail = set(ort.get_available_providers())
    order = (["CUDAExecutionProvider", "CPUExecutionProvider"]
             if device == "cuda" else ["CPUExecutionProvider"])
    chosen = [p for p in order if p in avail] or ["CPUExecutionProvider"]
    return [(p, {}) for p in chosen]


def transcribe(audio, model_dir, runtime_id: str, device: str = "cpu",
               log_cb: Callable[[str], None] | None = None,
               progress_cb: Callable[[int], None] | None = None) -> list[Segment]:
    """Transcribe `audio` with a local Parakeet ONNX model. Returns Segments."""
    from app.gpu_dll import ensure_cuda_dll_path
    ensure_cuda_dll_path()                       # CUDA provider DLLs on Windows
    import onnx_asr

    if log_cb:
        log_cb("Avkodar ljud till 16 kHz mono ...")
    wav = decode_audio(audio)
    audio_dur = len(wav) / SAMPLE_RATE
    if audio_dur <= 0:
        raise RuntimeError("Tom eller oläsbar ljudfil")

    if log_cb:
        log_cb("Laddar Parakeet (onnx-asr) ...")
    model = onnx_asr.load_model(
        runtime_id, path=str(model_dir), providers=_providers(device)).with_timestamps()

    starts = chunk_starts(audio_dur)
    n = len(starts)
    tokens: list[str] = []
    times: list[float] = []
    for ci, c_start in enumerate(starts):
        c_end = min(audio_dur, c_start + CHUNK_SEC)
        lo, hi = int(c_start * SAMPLE_RATE), int(c_end * SAMPLE_RATE)
        res = model.recognize(wav[lo:hi], sample_rate=SAMPLE_RATE)
        toks = list(getattr(res, "tokens", []) or [])
        tms = [c_start + float(t) for t in (getattr(res, "timestamps", []) or [])]
        # Keep only this window's tokens between the overlap midpoints.
        keep_lo = c_start + (OVERLAP_SEC / 2 if ci > 0 else 0.0)
        keep_hi = c_end - (OVERLAP_SEC / 2 if ci < n - 1 else 0.0)
        for tok, t in zip(toks, tms):
            if keep_lo <= t < keep_hi:
                tokens.append(tok)
                times.append(t)
        if progress_cb:
            progress_cb(min(99, int(c_end / audio_dur * 100)))

    return group_segments(tokens, times, audio_dur)
