"""Transcription core: data model, output formatters, and the faster-whisper runner."""
from __future__ import annotations
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Segment:
    start: float
    end: float
    text: str


def _hms(seconds: float) -> tuple[int, int, int, int]:
    total_ms = round(seconds * 1000)
    hours, rem = divmod(total_ms, 3600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return hours, minutes, secs, ms


def format_timestamp_srt(seconds: float) -> str:
    h, m, s, ms = _hms(seconds)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def format_timestamp_vtt(seconds: float) -> str:
    h, m, s, ms = _hms(seconds)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def segments_to_srt(segments: list[Segment]) -> str:
    parts = []
    for i, seg in enumerate(segments, start=1):
        parts.append(
            f"{i}\n{format_timestamp_srt(seg.start)} --> "
            f"{format_timestamp_srt(seg.end)}\n{seg.text.strip()}\n\n"
        )
    return "".join(parts)


def segments_to_vtt(segments: list[Segment]) -> str:
    parts = ["WEBVTT\n\n"]
    for seg in segments:
        parts.append(
            f"{format_timestamp_vtt(seg.start)} --> "
            f"{format_timestamp_vtt(seg.end)}\n{seg.text.strip()}\n\n"
        )
    return "".join(parts)


def segments_to_txt(segments: list[Segment]) -> str:
    return "".join(seg.text.strip() + "\n" for seg in segments)


WRITERS = {
    "srt": (segments_to_srt, ".srt"),
    "vtt": (segments_to_vtt, ".vtt"),
    "txt": (segments_to_txt, ".txt"),
}


def write_outputs(segments: list[Segment], base_path: Path, formats: list[str]) -> list[Path]:
    written = []
    for fmt in formats:
        render, ext = WRITERS[fmt]
        out = base_path.with_suffix(ext)
        out.write_text(render(segments), encoding="utf-8")
        written.append(out)
    return written


# NOTE: transcription deliberately does NOT run in-process. The CTranslate2
# WhisperModel destructor can abort the process on Windows/CUDA when deallocated
# mid-program, so the model is loaded only inside the isolated subprocess
# `app.transcribe_cli`, launched via the argv built below.
def build_transcribe_cmd(audio: Path, model_dir: str, device: str, compute_type: str,
                         language: str, out_base: Path, formats: list[str]) -> list[str]:
    """Build the argv to run one transcription in an isolated subprocess.

    Frozen (PyInstaller): re-invoke our own exe with the `transcribe-cli` subcommand,
    since `-m app.transcribe_cli` does not exist in a frozen build. Source runs use
    the normal module form.
    """
    if getattr(sys, "frozen", False):
        head = [sys.executable, "transcribe-cli"]
    else:
        head = [sys.executable, "-m", "app.transcribe_cli"]
    return head + [
        "--audio", str(audio),
        "--model-dir", model_dir,
        "--device", device,
        "--compute-type", compute_type,
        "--language", language or "",
        "--out-base", str(out_base),
        "--formats", ",".join(formats),
    ]
