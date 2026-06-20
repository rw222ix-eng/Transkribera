"""English transcription via NVIDIA Parakeet (onnx-asr / ONNX Runtime).

A second ASR backend alongside faster-whisper. faster-whisper (CTranslate2) cannot
run Parakeet at all — it is a different architecture — so this module wraps
``onnx-asr``: it decodes the media to 16 kHz mono WAV with ffmpeg (Whisper read media
directly via PyAV; onnx-asr wants a plain waveform), runs the Parakeet TDT model, and
returns timestamped ``Segment``s grouped into subtitle-friendly cues.

Loaded only inside the isolated transcribe-cli subprocess (like WhisperModel), so its
heavy native deps never touch the GUI process.
"""
from __future__ import annotations
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

from app.transcriber import Segment

SEGMENT_GAP = 0.8    # a silence gap (s) longer than this starts a new subtitle cue
MAX_SEG_WORDS = 14   # cap cue length so subtitle lines stay readable


def _decode_to_wav(audio) -> str:
    """ffmpeg -> 16 kHz mono PCM WAV. Returns the temp path (caller deletes it)."""
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(audio), "-ac", "1", "-ar", "16000", "-f", "wav", tmp.name],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    return tmp.name


def _probe_duration(audio) -> float:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "quiet", "-of", "csv=p=0", "-show_entries",
             "format=duration", str(audio)],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, check=True)
        return float(out.stdout.strip() or 0)
    except (subprocess.SubprocessError, ValueError):
        return 0.0


def _providers(device: str) -> list[str]:
    """ONNX Runtime providers: CUDA first on GPU, always CPU as fallback."""
    import onnxruntime as ort
    avail = set(ort.get_available_providers())
    order = (["CUDAExecutionProvider", "CPUExecutionProvider"]
             if device == "cuda" else ["CPUExecutionProvider"])
    return [p for p in order if p in avail] or ["CPUExecutionProvider"]


def _word_tuples(res, fallback_duration: float) -> list[tuple]:
    """Normalise onnx-asr's result into [(start, end, word)].

    Different onnx-asr versions expose word timestamps as tuples or dicts; if none
    are present we degrade to a single cue spanning the whole clip (still usable
    TXT, coarse SRT/VTT)."""
    ts = getattr(res, "timestamps", None) or getattr(res, "words", None)
    tuples: list[tuple] = []
    for item in (ts or []):
        if isinstance(item, dict):
            start = item.get("start"); end = item.get("end")
            word = item.get("word", item.get("token", ""))
        else:  # (start, end, word) tuple/list
            start, end, word = item[0], item[1], item[2]
        if start is None or end is None:
            continue
        tuples.append((float(start), float(end), str(word)))
    if tuples:
        return tuples
    text = res if isinstance(res, str) else (getattr(res, "text", None) or str(res))
    return [(0.0, float(fallback_duration), str(text).strip())]


def _flush(words) -> Segment:
    text = " ".join(w[2] for w in words).strip()
    for a, b in ((" ,", ","), (" .", "."), (" ?", "?"), (" !", "!")):
        text = text.replace(a, b)
    return Segment(words[0][0], words[-1][1], text)


def group_segments(words) -> list[Segment]:
    """Group (start, end, word) tuples into cues on long pauses or word count."""
    segs: list[Segment] = []
    cur: list = []
    for w in words:
        if cur and (w[0] - cur[-1][1] > SEGMENT_GAP or len(cur) >= MAX_SEG_WORDS):
            segs.append(_flush(cur))
            cur = []
        cur.append(w)
    if cur:
        segs.append(_flush(cur))
    return segs


def transcribe(audio, model_dir, runtime_id: str, device: str = "cpu",
               log_cb: Callable[[str], None] | None = None) -> list[Segment]:
    """Transcribe `audio` with a local Parakeet ONNX model. Returns Segments."""
    import onnx_asr
    if log_cb:
        log_cb("Avkodar ljud (16 kHz mono) ...")
    wav = _decode_to_wav(audio)
    duration = _probe_duration(audio)
    try:
        if log_cb:
            log_cb("Laddar Parakeet (onnx-asr) ...")
        model = onnx_asr.load_model(runtime_id, path=str(model_dir),
                                    providers=_providers(device))
        try:
            res = model.recognize(wav, timestamps=True)
        except TypeError:                      # older onnx-asr: no timestamps kwarg
            res = model.recognize(wav)
    finally:
        try:
            Path(wav).unlink()
        except OSError:
            pass
    return group_segments(_word_tuples(res, duration))
