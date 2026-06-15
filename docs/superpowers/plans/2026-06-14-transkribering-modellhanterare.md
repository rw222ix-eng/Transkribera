# Transkribering + Modellhanterare Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn two standalone scripts into one PySide6 desktop app that transcribes video/audio/YouTube and includes a model manager that scans hardware and recommends/downloads Whisper + Ollama models.

**Architecture:** GUI-independent logic in `app/` (pure functions + thin runtimes), tested without Qt. PySide6 GUI is a thin layer driven by `QThread` workers that stream progress. Whisper via `faster-whisper`, LLM post-processing via the Ollama HTTP API.

**Tech Stack:** Python 3.12, PySide6, faster-whisper (CTranslate2), torch (CUDA), huggingface_hub, psutil, requests, yt-dlp, ffmpeg/ffprobe, pytest.

**Environment note:** Use the existing global interpreter (`python` = 3.12.10) — it already has faster-whisper, torch+cu121, huggingface_hub, psutil, requests, yt-dlp. Only PySide6 and pytest need installing (Task 1).

---

## File Structure

| File | Responsibility |
|------|----------------|
| `app/__init__.py` | Marks package |
| `app/hardware.py` | `HardwareInfo` dataclass + `scan_hardware()` |
| `app/models_catalog.py` | `WhisperModelSpec`, `LLMModelSpec` + static catalogs |
| `app/recommend.py` | `Fit` enum + fit/recommendation logic (pure) |
| `app/transcriber.py` | `Segment`, SRT/VTT/TXT formatters (pure), `write_outputs`, `build_transcribe_cmd` |
| `app/transcribe_cli.py` | Isolated subprocess that loads the model, writes outputs, `os._exit(0)` (avoids CTranslate2 teardown abort) |
| `app/media.py` | ffprobe duration parse (pure) + `probe_duration()`, `ffmpeg_available()` |
| `app/youtube.py` | `build_ytdlp_command()` (pure) + `download()` |
| `app/whisper_manager.py` | model dir / install detection / `download_whisper()` |
| `app/ollama_client.py` | Ollama HTTP API: running/list/pull/generate |
| `app/postprocess.py` | `build_prompt()` (pure) + `run()` |
| `app/workers.py` | `QThread` workers wrapping the runtimes |
| `app/ui/main_window.py` | `QMainWindow` + tabs |
| `app/ui/transcribe_tab.py` | Transcription UI |
| `app/ui/models_tab.py` | Hardware panel + model lists |
| `app/main.py` | Entry point |
| `tests/test_*.py` | pytest suites for pure logic + mocked runtimes |
| `requirements.txt` | Dependencies |

Phases: **1** Setup → **2** Pure logic (hardware/catalog/recommend/formatters/parsers) → **3** Runtimes (whisper_manager/ollama_client/youtube/transcriber/postprocess) → **4** GUI.

---

## Task 1: Project setup

**Files:**
- Create: `requirements.txt`, `app/__init__.py`, `app/ui/__init__.py`, `tests/__init__.py`, `pytest.ini`

- [ ] **Step 1: Create `requirements.txt`**

```text
PySide6>=6.7
faster-whisper>=1.2
torch
huggingface_hub
psutil
requests
yt-dlp
pytest
```

- [ ] **Step 2: Install the missing deps**

Run: `python -m pip install PySide6 pytest`
Expected: installs PySide6 and pytest (the rest are already present).

- [ ] **Step 3: Create empty package markers**

Create `app/__init__.py`, `app/ui/__init__.py`, `tests/__init__.py` (empty files).

- [ ] **Step 4: Create `pytest.ini`**

```ini
[pytest]
testpaths = tests
python_files = test_*.py
```

- [ ] **Step 5: Verify pytest runs (collects nothing yet)**

Run: `python -m pytest -q`
Expected: "no tests ran" (exit code 5) — confirms pytest works.

- [ ] **Step 6: Commit**

```bash
git add requirements.txt app tests pytest.ini
git commit -m "chore: project scaffold and dependencies"
```

---

## Task 2: Models catalog

**Files:**
- Create: `app/models_catalog.py`
- Test: `tests/test_models_catalog.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_models_catalog.py
from app.models_catalog import WHISPER_MODELS, LLM_MODELS, WhisperModelSpec, LLMModelSpec

def test_whisper_catalog_is_well_formed():
    assert len(WHISPER_MODELS) >= 5
    ids = [m.id for m in WHISPER_MODELS]
    assert len(ids) == len(set(ids)), "duplicate Whisper ids"
    for m in WHISPER_MODELS:
        assert isinstance(m, WhisperModelSpec)
        assert m.download_mb > 0
        assert m.vram_int8_mb <= m.vram_fp16_mb
        assert m.rank > 0

def test_llm_catalog_is_well_formed():
    assert len(LLM_MODELS) >= 3
    names = [m.name for m in LLM_MODELS]
    assert len(names) == len(set(names)), "duplicate LLM names"
    for m in LLM_MODELS:
        assert isinstance(m, LLMModelSpec)
        assert m.download_mb > 0 and m.vram_mb > 0 and m.ram_mb > 0

def test_kb_whisper_large_present_for_swedish():
    sv = [m for m in WHISPER_MODELS if m.id == "KBLab/kb-whisper-large"]
    assert sv and sv[0].languages == "sv"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_models_catalog.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.models_catalog'`.

- [ ] **Step 3: Write minimal implementation**

```python
# app/models_catalog.py
"""Static catalog of downloadable models with hardware requirements.

VRAM/RAM/size figures are approximate working estimates used only for the
green/yellow/red fit logic; tune freely as real-world numbers are observed.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class WhisperModelSpec:
    id: str            # HuggingFace repo id (CTranslate2 / faster-whisper format)
    label: str         # display name
    download_mb: int
    vram_fp16_mb: int  # approx VRAM for float16 on GPU
    vram_int8_mb: int  # approx VRAM for int8 on GPU
    languages: str     # "sv", "en", or "multi"
    rank: int          # higher = more accurate (used to pick "best")
    note: str = ""


@dataclass(frozen=True)
class LLMModelSpec:
    name: str          # Ollama model name, e.g. "llama3.1:8b"
    label: str
    download_mb: int
    vram_mb: int       # recommended VRAM to run on GPU
    ram_mb: int        # recommended RAM for CPU fallback
    rank: int          # higher = more capable
    note: str = ""


WHISPER_MODELS: list[WhisperModelSpec] = [
    WhisperModelSpec("Systran/faster-whisper-tiny", "Whisper tiny", 75, 1000, 500, "multi", 1),
    WhisperModelSpec("Systran/faster-whisper-base", "Whisper base", 145, 1200, 600, "multi", 2),
    WhisperModelSpec("Systran/faster-whisper-small", "Whisper small", 480, 2000, 1000, "multi", 3),
    WhisperModelSpec("Systran/faster-whisper-medium", "Whisper medium", 1500, 5000, 2500, "multi", 4),
    WhisperModelSpec("Systran/faster-whisper-large-v3", "Whisper large-v3", 3000, 10000, 5000, "multi", 5),
    WhisperModelSpec("Systran/faster-distil-whisper-large-v3", "Distil large-v3 (snabb)", 1500, 6000, 3000, "multi", 4,
                     "Snabbare, något lägre noggrannhet"),
    WhisperModelSpec("KBLab/kb-whisper-tiny", "KB-Whisper tiny (sv)", 75, 1000, 500, "sv", 3),
    WhisperModelSpec("KBLab/kb-whisper-small", "KB-Whisper small (sv)", 480, 2000, 1000, "sv", 4),
    WhisperModelSpec("KBLab/kb-whisper-medium", "KB-Whisper medium (sv)", 1500, 5000, 2500, "sv", 5),
    WhisperModelSpec("KBLab/kb-whisper-large", "KB-Whisper large (sv)", 3000, 10000, 5000, "sv", 6,
                     "Bäst för svenska"),
]

LLM_MODELS: list[LLMModelSpec] = [
    LLMModelSpec("gemma2:2b", "Gemma 2 (2B)", 1600, 4000, 8000, 1),
    LLMModelSpec("llama3.2:3b", "Llama 3.2 (3B)", 2000, 5000, 8000, 2),
    LLMModelSpec("qwen2.5:7b", "Qwen 2.5 (7B)", 4700, 8000, 16000, 3),
    LLMModelSpec("llama3.1:8b", "Llama 3.1 (8B)", 4900, 8000, 16000, 4),
    LLMModelSpec("qwen2.5:14b", "Qwen 2.5 (14B)", 9000, 16000, 32000, 5),
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_models_catalog.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add app/models_catalog.py tests/test_models_catalog.py
git commit -m "feat: model catalog with hardware requirement metadata"
```

---

## Task 3: Hardware scanning

**Files:**
- Create: `app/hardware.py`
- Test: `tests/test_hardware.py`

`scan_hardware()` touches real hardware, so it is not unit-tested for values. We test the dataclass shape and that a real scan returns sane non-negative numbers (smoke test on this machine).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_hardware.py
from pathlib import Path
from app.hardware import HardwareInfo, scan_hardware

def test_scan_returns_sane_values(tmp_path: Path):
    hw = scan_hardware(tmp_path)
    assert isinstance(hw, HardwareInfo)
    assert hw.ram_mb > 0
    assert hw.cpu_cores >= 1
    assert hw.free_disk_mb > 0
    assert hw.vram_mb >= 0
    if hw.has_cuda:
        assert hw.vram_mb > 0 and hw.gpu_name
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_hardware.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# app/hardware.py
"""Scan the machine for GPU/VRAM/CUDA, RAM, CPU and free disk."""
from __future__ import annotations
import os
import platform
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class HardwareInfo:
    has_cuda: bool
    gpu_name: str | None
    vram_mb: int        # 0 if no GPU detected
    ram_mb: int
    cpu_cores: int
    cpu_name: str
    free_disk_mb: int


def _gpu_via_torch() -> tuple[bool, str | None, int]:
    try:
        import torch
        if torch.cuda.is_available():
            props = torch.cuda.get_device_properties(0)
            return True, props.name, props.total_memory // (1024 * 1024)
    except Exception:
        pass
    return False, None, 0


def _gpu_via_nvidia_smi() -> tuple[str | None, int]:
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0 and out.stdout.strip():
            name, mem = out.stdout.strip().splitlines()[0].split(",")
            return name.strip(), int(mem.strip())
    except Exception:
        pass
    return None, 0


def scan_hardware(cache_dir: Path) -> HardwareInfo:
    has_cuda, gpu_name, vram_mb = _gpu_via_torch()
    if vram_mb == 0:
        name, mem = _gpu_via_nvidia_smi()
        if mem > 0:
            gpu_name, vram_mb = name, mem  # present but maybe no working CUDA

    try:
        import psutil
        ram_mb = psutil.virtual_memory().total // (1024 * 1024)
    except Exception:
        ram_mb = 0

    cache_dir.mkdir(parents=True, exist_ok=True)
    free_disk_mb = shutil.disk_usage(cache_dir).free // (1024 * 1024)

    return HardwareInfo(
        has_cuda=has_cuda,
        gpu_name=gpu_name,
        vram_mb=vram_mb,
        ram_mb=ram_mb,
        cpu_cores=os.cpu_count() or 1,
        cpu_name=platform.processor() or platform.machine(),
        free_disk_mb=free_disk_mb,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_hardware.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/hardware.py tests/test_hardware.py
git commit -m "feat: hardware scanning (GPU/VRAM/RAM/CPU/disk)"
```

---

## Task 4: Recommendation logic

**Files:**
- Create: `app/recommend.py`
- Test: `tests/test_recommend.py`

This is the core algorithm — fully TDD'd against synthetic `HardwareInfo`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_recommend.py
from app.hardware import HardwareInfo
from app.models_catalog import WhisperModelSpec, LLMModelSpec
from app.recommend import (
    Fit, evaluate_whisper, recommend_whisper, evaluate_llm, recommend_llm,
)

def hw(has_cuda=True, vram_mb=12000, ram_mb=32000, free_disk_mb=100000):
    return HardwareInfo(has_cuda, "Test GPU", vram_mb, ram_mb, 8, "CPU", free_disk_mb)

LARGE = WhisperModelSpec("x/large", "L", 3000, 10000, 5000, "multi", 5)
TINY = WhisperModelSpec("x/tiny", "T", 75, 1000, 500, "multi", 1)

def test_green_when_vram_fits_fp16():
    r = evaluate_whisper(LARGE, hw(vram_mb=12000))
    assert r.fit is Fit.GREEN and r.device == "cuda" and r.compute_type == "float16"

def test_yellow_int8_when_only_int8_fits_on_gpu():
    r = evaluate_whisper(LARGE, hw(vram_mb=6500))
    assert r.fit is Fit.YELLOW and r.device == "cuda" and r.compute_type == "int8_float16"

def test_yellow_cpu_when_no_cuda_but_enough_ram():
    r = evaluate_whisper(LARGE, hw(has_cuda=False, vram_mb=0, ram_mb=16000))
    assert r.fit is Fit.YELLOW and r.device == "cpu" and r.compute_type == "int8"

def test_red_when_disk_too_small():
    r = evaluate_whisper(LARGE, hw(free_disk_mb=100))
    assert r.fit is Fit.RED

def test_red_when_nothing_fits():
    r = evaluate_whisper(LARGE, hw(has_cuda=False, vram_mb=0, ram_mb=2000))
    assert r.fit is Fit.RED

def test_recommend_picks_most_accurate_green():
    evals, best = recommend_whisper([TINY, LARGE], hw(vram_mb=12000))
    assert best is LARGE  # higher rank, and green

def test_recommend_falls_back_to_best_yellow_when_no_green():
    evals, best = recommend_whisper([TINY, LARGE], hw(has_cuda=False, vram_mb=0, ram_mb=16000))
    assert best is LARGE  # both yellow on CPU, pick highest rank

GLLM = LLMModelSpec("g:2b", "G", 1600, 4000, 8000, 1)
BLLM = LLMModelSpec("b:8b", "B", 4900, 8000, 16000, 4)

def test_llm_green_on_gpu():
    assert evaluate_llm(BLLM, hw(vram_mb=12000)).fit is Fit.GREEN

def test_llm_yellow_on_cpu_ram():
    assert evaluate_llm(BLLM, hw(has_cuda=False, vram_mb=0, ram_mb=16000)).fit is Fit.YELLOW

def test_llm_red_when_insufficient():
    assert evaluate_llm(BLLM, hw(has_cuda=False, vram_mb=0, ram_mb=4000)).fit is Fit.RED

def test_recommend_llm_picks_best_capable_green():
    evals, best = recommend_llm([GLLM, BLLM], hw(vram_mb=12000))
    assert best is BLLM
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_recommend.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.recommend'`.

- [ ] **Step 3: Write minimal implementation**

```python
# app/recommend.py
"""Map hardware to per-model fit (green/yellow/red) and pick a recommended model."""
from __future__ import annotations
import enum
from dataclasses import dataclass

from app.hardware import HardwareInfo
from app.models_catalog import WhisperModelSpec, LLMModelSpec

GPU_OVERHEAD_MB = 1000   # CUDA context + activations headroom
CPU_OVERHEAD_MB = 2000   # OS + process headroom for CPU inference


class Fit(enum.Enum):
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"


@dataclass
class WhisperRecommendation:
    spec: WhisperModelSpec
    fit: Fit
    device: str          # "cuda" | "cpu"
    compute_type: str    # "float16" | "int8_float16" | "int8"
    reason: str


@dataclass
class LLMRecommendation:
    spec: LLMModelSpec
    fit: Fit
    device: str
    reason: str


def evaluate_whisper(spec: WhisperModelSpec, hw: HardwareInfo) -> WhisperRecommendation:
    if hw.free_disk_mb < spec.download_mb + 200:
        return WhisperRecommendation(spec, Fit.RED, "cpu", "int8",
                                     "För lite ledigt diskutrymme")
    if hw.has_cuda and hw.vram_mb >= spec.vram_fp16_mb + GPU_OVERHEAD_MB:
        return WhisperRecommendation(spec, Fit.GREEN, "cuda", "float16",
                                     "Körs i full precision på GPU")
    if hw.has_cuda and hw.vram_mb >= spec.vram_int8_mb + GPU_OVERHEAD_MB:
        return WhisperRecommendation(spec, Fit.YELLOW, "cuda", "int8_float16",
                                     "Körs på GPU med int8 (knapp VRAM)")
    if hw.ram_mb >= spec.vram_int8_mb + CPU_OVERHEAD_MB:
        return WhisperRecommendation(spec, Fit.YELLOW, "cpu", "int8",
                                     "Körs på CPU (långsamt)")
    return WhisperRecommendation(spec, Fit.RED, "cpu", "int8",
                                 "Otillräcklig VRAM och RAM")


def recommend_whisper(specs: list[WhisperModelSpec], hw: HardwareInfo):
    evals = [evaluate_whisper(s, hw) for s in specs]
    greens = [e for e in evals if e.fit is Fit.GREEN]
    yellows = [e for e in evals if e.fit is Fit.YELLOW]
    pool = greens or yellows
    best = max(pool, key=lambda e: e.spec.rank).spec if pool else None
    return evals, best


def evaluate_llm(spec: LLMModelSpec, hw: HardwareInfo) -> LLMRecommendation:
    if hw.free_disk_mb < spec.download_mb + 200:
        return LLMRecommendation(spec, Fit.RED, "cpu", "För lite ledigt diskutrymme")
    if hw.has_cuda and hw.vram_mb >= spec.vram_mb:
        return LLMRecommendation(spec, Fit.GREEN, "cuda", "Körs på GPU")
    if hw.ram_mb >= spec.ram_mb:
        return LLMRecommendation(spec, Fit.YELLOW, "cpu", "Körs på CPU/delvis (långsammare)")
    return LLMRecommendation(spec, Fit.RED, "cpu", "Otillräcklig VRAM och RAM")


def recommend_llm(specs: list[LLMModelSpec], hw: HardwareInfo):
    evals = [evaluate_llm(s, hw) for s in specs]
    greens = [e for e in evals if e.fit is Fit.GREEN]
    yellows = [e for e in evals if e.fit is Fit.YELLOW]
    pool = greens or yellows
    best = max(pool, key=lambda e: e.spec.rank).spec if pool else None
    return evals, best
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_recommend.py -v`
Expected: PASS (11 tests).

- [ ] **Step 5: Commit**

```bash
git add app/recommend.py tests/test_recommend.py
git commit -m "feat: green/yellow/red fit logic and best-model recommendation"
```

---

## Task 5: Transcript formatters + Segment

**Files:**
- Create: `app/transcriber.py`
- Test: `tests/test_formatters.py`

Formatters are pure and TDD'd. The `transcribe()` runner (faster-whisper) is added in the same file but verified manually in Task 11/integration.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_formatters.py
from app.transcriber import (
    Segment, format_timestamp_srt, format_timestamp_vtt,
    segments_to_srt, segments_to_vtt, segments_to_txt,
)

SEGS = [Segment(0.0, 1.5, "Hej"), Segment(1.5, 3.25, "världen")]

def test_srt_timestamp():
    assert format_timestamp_srt(3661.5) == "01:01:01,500"

def test_vtt_timestamp():
    assert format_timestamp_vtt(3661.5) == "01:01:01.500"

def test_segments_to_srt():
    out = segments_to_srt(SEGS)
    assert out == (
        "1\n00:00:00,000 --> 00:00:01,500\nHej\n\n"
        "2\n00:00:01,500 --> 00:00:03,250\nvärlden\n\n"
    )

def test_segments_to_vtt_has_header():
    out = segments_to_vtt(SEGS)
    assert out.startswith("WEBVTT\n\n")
    assert "00:00:00.000 --> 00:00:01.500\nHej" in out

def test_segments_to_txt_is_plain_lines():
    assert segments_to_txt(SEGS) == "Hej\nvärlden\n"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_formatters.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# app/transcriber.py
"""Transcription core: data model, output formatters, and the faster-whisper runner."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


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


def transcribe(
    audio_path: Path,
    model_dir: str,
    device: str,
    compute_type: str,
    language: str | None,
    progress_cb: Callable[[int], None] | None = None,
    log_cb: Callable[[str], None] | None = None,
) -> list[Segment]:
    """Run faster-whisper. `model_dir` is a local path or HF id; faster-whisper
    decodes the audio track of both video and audio files via PyAV."""
    from faster_whisper import WhisperModel

    if log_cb:
        log_cb(f"Laddar modell ({device}/{compute_type})...")
    model = WhisperModel(model_dir, device=device, compute_type=compute_type)

    segments_iter, info = model.transcribe(str(audio_path), language=language or None)
    duration = getattr(info, "duration", 0) or 0
    out: list[Segment] = []
    for seg in segments_iter:
        out.append(Segment(seg.start, seg.end, seg.text.strip()))
        if progress_cb and duration:
            progress_cb(min(100, int(seg.end / duration * 100)))
    if progress_cb:
        progress_cb(100)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_formatters.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add app/transcriber.py tests/test_formatters.py
git commit -m "feat: Segment model, SRT/VTT/TXT formatters, transcribe runner"
```

---

## Task 6: Media probing

**Files:**
- Create: `app/media.py`
- Test: `tests/test_media.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_media.py
from app.media import parse_duration

def test_parse_duration_reads_value():
    assert parse_duration("duration=123.456\n") == 123.456

def test_parse_duration_missing_returns_none():
    assert parse_duration("codec=h264\n") is None

def test_parse_duration_na_returns_none():
    assert parse_duration("duration=N/A\n") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_media.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# app/media.py
"""ffmpeg/ffprobe helpers: detect availability and read media duration."""
from __future__ import annotations
import shutil
import subprocess
from pathlib import Path


def parse_duration(ffprobe_output: str) -> float | None:
    for line in ffprobe_output.splitlines():
        if line.startswith("duration="):
            value = line.split("=", 1)[1].strip()
            try:
                return float(value)
            except ValueError:
                return None
    return None


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def probe_duration(path: Path) -> float | None:
    if shutil.which("ffprobe") is None:
        return None
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1", str(path)],
            capture_output=True, text=True, timeout=30,
        )
        return parse_duration(out.stdout)
    except Exception:
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_media.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add app/media.py tests/test_media.py
git commit -m "feat: ffprobe duration parsing and ffmpeg availability check"
```

---

## Task 7: YouTube download (refactor ladda_ner.py)

**Files:**
- Create: `app/youtube.py`
- Test: `tests/test_youtube.py`

Reuses the proven logic from `ladda_ner.py` (cookies, Deno PATH, `bv*+ba/b`, mkv merge). Command-building is pure and TDD'd; `download()` runs yt-dlp.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_youtube.py
from pathlib import Path
from app.youtube import build_ytdlp_command

def test_command_includes_url_and_default_format(tmp_path: Path):
    cmd = build_ytdlp_command("https://yt/abc", cookies_file=None, output_dir=tmp_path)
    assert cmd[0] == "yt-dlp"
    assert "https://yt/abc" == cmd[-1]
    assert "bv*+ba/b" in cmd
    assert "mkv" in cmd

def test_command_adds_cookies_when_present(tmp_path: Path):
    cookies = tmp_path / "cookies.txt"
    cookies.write_text("x", encoding="utf-8")
    cmd = build_ytdlp_command("u", cookies_file=cookies, output_dir=tmp_path)
    assert "--cookies" in cmd and str(cookies) in cmd

def test_command_omits_cookies_when_missing(tmp_path: Path):
    cmd = build_ytdlp_command("u", cookies_file=tmp_path / "nope.txt", output_dir=tmp_path)
    assert "--cookies" not in cmd
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_youtube.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# app/youtube.py
"""Download YouTube media with yt-dlp at best quality (refactor of ladda_ner.py)."""
from __future__ import annotations
import os
import subprocess
from pathlib import Path
from typing import Callable


def _ensure_deno_on_path() -> None:
    deno_root = Path.home() / "AppData/Local/Microsoft/WinGet/Packages"
    for d in deno_root.glob("DenoLand.Deno_*"):
        os.environ["PATH"] = str(d) + os.pathsep + os.environ.get("PATH", "")
        break


def build_ytdlp_command(url: str, cookies_file: Path | None, output_dir: Path,
                        fmt: str | None = None) -> list[str]:
    cmd = ["yt-dlp"]
    if cookies_file and cookies_file.exists():
        cmd += ["--cookies", str(cookies_file)]
    cmd += ["-f", fmt or "bv*+ba/b"]
    cmd += ["--merge-output-format", "mkv"]
    cmd += ["-o", str(output_dir / "%(title)s.%(ext)s")]
    cmd += ["--no-playlist", url]
    return cmd


def download(url: str, output_dir: Path, cookies_file: Path | None = None,
             fmt: str | None = None,
             log_cb: Callable[[str], None] | None = None) -> Path:
    """Download `url`, return the path to the newest media file in output_dir."""
    _ensure_deno_on_path()
    output_dir.mkdir(parents=True, exist_ok=True)
    cmd = build_ytdlp_command(url, cookies_file, output_dir, fmt)
    if log_cb:
        log_cb("Kör: " + " ".join(cmd))
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace")
    assert proc.stdout is not None
    for line in proc.stdout:
        if log_cb:
            log_cb(line.rstrip())
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"yt-dlp avslutades med kod {proc.returncode}")

    media = []
    for ext in ("*.mkv", "*.mp4", "*.webm", "*.m4a", "*.mp3"):
        media.extend(output_dir.glob(ext))
    if not media:
        raise RuntimeError("Ingen nedladdad fil hittades")
    return max(media, key=lambda f: f.stat().st_mtime)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_youtube.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add app/youtube.py tests/test_youtube.py
git commit -m "feat: yt-dlp download wrapper with cookie and Deno support"
```

---

## Task 8: Whisper model manager

**Files:**
- Create: `app/whisper_manager.py`
- Test: `tests/test_whisper_manager.py`

Download uses `huggingface_hub.snapshot_download`; tests mock it so no network is hit.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_whisper_manager.py
from pathlib import Path
from app.models_catalog import WhisperModelSpec
from app import whisper_manager as wm

SPEC = WhisperModelSpec("KBLab/kb-whisper-large", "L", 3000, 10000, 5000, "sv", 6)

def test_model_dir_is_under_root(tmp_path: Path):
    d = wm.model_dir_for(SPEC, tmp_path)
    assert d.parent == tmp_path
    assert "kb-whisper-large" in d.name

def test_not_installed_when_no_model_bin(tmp_path: Path):
    assert wm.is_installed(SPEC, tmp_path) is False

def test_installed_when_model_bin_present(tmp_path: Path):
    d = wm.model_dir_for(SPEC, tmp_path)
    d.mkdir(parents=True)
    (d / "model.bin").write_bytes(b"x")
    assert wm.is_installed(SPEC, tmp_path) is True

def test_download_calls_snapshot(monkeypatch, tmp_path: Path):
    called = {}
    def fake_snapshot(repo_id, local_dir, **kw):
        called["repo_id"] = repo_id
        Path(local_dir).mkdir(parents=True, exist_ok=True)
        (Path(local_dir) / "model.bin").write_bytes(b"x")
        return local_dir
    monkeypatch.setattr(wm, "snapshot_download", fake_snapshot)
    path = wm.download_whisper(SPEC, tmp_path)
    assert called["repo_id"] == "KBLab/kb-whisper-large"
    assert wm.is_installed(SPEC, tmp_path)
    assert (path / "model.bin").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_whisper_manager.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# app/whisper_manager.py
"""Download and detect locally-installed faster-whisper models."""
from __future__ import annotations
from pathlib import Path
from typing import Callable

from huggingface_hub import snapshot_download

from app.models_catalog import WhisperModelSpec, WHISPER_MODELS


def model_dir_for(spec: WhisperModelSpec, models_root: Path) -> Path:
    safe = spec.id.replace("/", "__")
    return models_root / safe


def is_installed(spec: WhisperModelSpec, models_root: Path) -> bool:
    return (model_dir_for(spec, models_root) / "model.bin").exists()


def download_whisper(spec: WhisperModelSpec, models_root: Path,
                     log_cb: Callable[[str], None] | None = None) -> Path:
    target = model_dir_for(spec, models_root)
    if log_cb:
        log_cb(f"Laddar ner {spec.id} ...")
    snapshot_download(repo_id=spec.id, local_dir=str(target))
    if not is_installed(spec, models_root):
        raise RuntimeError(f"Nedladdning ofullständig: {spec.id} (model.bin saknas)")
    return target


def installed_specs(models_root: Path) -> list[WhisperModelSpec]:
    return [s for s in WHISPER_MODELS if is_installed(s, models_root)]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_whisper_manager.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add app/whisper_manager.py tests/test_whisper_manager.py
git commit -m "feat: whisper model download and install detection"
```

---

## Task 9: Ollama client

**Files:**
- Create: `app/ollama_client.py`
- Test: `tests/test_ollama_client.py`

All HTTP is via `requests`; tests monkeypatch `requests` calls so no server is needed.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ollama_client.py
import json
from app import ollama_client as oc

class FakeResp:
    def __init__(self, status=200, payload=None, lines=None):
        self.status_code = status
        self._payload = payload
        self._lines = lines or []
    def json(self): return self._payload
    def iter_lines(self):
        for ln in self._lines:
            yield ln.encode("utf-8")
    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("http error")
    def __enter__(self): return self
    def __exit__(self, *a): return False

def test_is_running_true(monkeypatch):
    monkeypatch.setattr(oc.requests, "get", lambda *a, **k: FakeResp(200, {"models": []}))
    assert oc.is_running() is True

def test_is_running_false_on_error(monkeypatch):
    def boom(*a, **k): raise OSError("refused")
    monkeypatch.setattr(oc.requests, "get", boom)
    assert oc.is_running() is False

def test_list_models(monkeypatch):
    payload = {"models": [{"name": "llama3.1:8b"}, {"name": "gemma2:2b"}]}
    monkeypatch.setattr(oc.requests, "get", lambda *a, **k: FakeResp(200, payload))
    assert oc.list_models() == ["llama3.1:8b", "gemma2:2b"]

def test_pull_streams_progress(monkeypatch):
    lines = [
        json.dumps({"status": "pulling", "completed": 50, "total": 100}),
        json.dumps({"status": "success"}),
    ]
    monkeypatch.setattr(oc.requests, "post", lambda *a, **k: FakeResp(200, lines=lines))
    seen = []
    oc.pull("gemma2:2b", progress_cb=lambda pct, status: seen.append((pct, status)))
    assert (50, "pulling") in seen

def test_generate_concatenates_tokens(monkeypatch):
    lines = [
        json.dumps({"response": "Hej "}),
        json.dumps({"response": "där", "done": True}),
    ]
    monkeypatch.setattr(oc.requests, "post", lambda *a, **k: FakeResp(200, lines=lines))
    tokens = []
    text = oc.generate("gemma2:2b", "prompt", token_cb=tokens.append)
    assert text == "Hej där"
    assert tokens == ["Hej ", "där"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ollama_client.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# app/ollama_client.py
"""Minimal client for a local Ollama server (default http://localhost:11434)."""
from __future__ import annotations
import json
from typing import Callable

import requests

BASE_URL = "http://localhost:11434"


def is_running(base_url: str = BASE_URL) -> bool:
    try:
        r = requests.get(f"{base_url}/api/tags", timeout=2)
        return r.status_code == 200
    except Exception:
        return False


def list_models(base_url: str = BASE_URL) -> list[str]:
    r = requests.get(f"{base_url}/api/tags", timeout=5)
    r.raise_for_status()
    return [m["name"] for m in r.json().get("models", [])]


def pull(name: str, progress_cb: Callable[[int, str], None] | None = None,
         base_url: str = BASE_URL) -> None:
    with requests.post(f"{base_url}/api/pull", json={"name": name},
                       stream=True, timeout=None) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if not line:
                continue
            data = json.loads(line)
            status = data.get("status", "")
            total, completed = data.get("total"), data.get("completed")
            if progress_cb:
                pct = int(completed / total * 100) if total and completed else 0
                progress_cb(pct, status)


def generate(model: str, prompt: str,
             token_cb: Callable[[str], None] | None = None,
             base_url: str = BASE_URL) -> str:
    text = []
    with requests.post(f"{base_url}/api/generate",
                       json={"model": model, "prompt": prompt, "stream": True},
                       stream=True, timeout=None) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if not line:
                continue
            data = json.loads(line)
            chunk = data.get("response", "")
            if chunk:
                text.append(chunk)
                if token_cb:
                    token_cb(chunk)
            if data.get("done"):
                break
    return "".join(text)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ollama_client.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add app/ollama_client.py tests/test_ollama_client.py
git commit -m "feat: Ollama client (running/list/pull/generate)"
```

---

## Task 10: LLM post-processing

**Files:**
- Create: `app/postprocess.py`
- Test: `tests/test_postprocess.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_postprocess.py
import pytest
from app import postprocess as pp

def test_operations_exist():
    assert set(pp.OPERATIONS) >= {"summary", "cleanup", "bullets"}

def test_build_prompt_includes_transcript_and_instruction():
    prompt = pp.build_prompt("summary", "Detta är ett transkript.")
    assert "Detta är ett transkript." in prompt
    assert pp.OPERATIONS["summary"] in prompt

def test_build_prompt_rejects_unknown_operation():
    with pytest.raises(KeyError):
        pp.build_prompt("nonexistent", "x")

def test_run_calls_generate(monkeypatch):
    captured = {}
    def fake_generate(model, prompt, token_cb=None, **kw):
        captured["model"] = model
        captured["prompt"] = prompt
        return "resultat"
    monkeypatch.setattr(pp.ollama_client, "generate", fake_generate)
    out = pp.run("summary", "transkript", model="gemma2:2b")
    assert out == "resultat"
    assert captured["model"] == "gemma2:2b"
    assert "transkript" in captured["prompt"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_postprocess.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# app/postprocess.py
"""Post-process a transcript with a local LLM via Ollama."""
from __future__ import annotations
from typing import Callable

from app import ollama_client

OPERATIONS: dict[str, str] = {
    "summary": "Sammanfatta följande transkript koncist på svenska:",
    "cleanup": "Städa upp följande transkript: rätta stavfel och interpunktion, "
               "behåll all betydelse och svara på svenska:",
    "bullets": "Sammanfatta följande transkript som en punktlista på svenska:",
}


def build_prompt(operation: str, transcript: str) -> str:
    instruction = OPERATIONS[operation]
    return f"{instruction}\n\n---\n{transcript}\n---"


def run(operation: str, transcript: str, model: str,
        token_cb: Callable[[str], None] | None = None) -> str:
    prompt = build_prompt(operation, transcript)
    return ollama_client.generate(model, prompt, token_cb=token_cb)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_postprocess.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add app/postprocess.py tests/test_postprocess.py
git commit -m "feat: LLM post-processing prompts and runner"
```

---

## Task 11: Manual integration check of the logic layer

No new product code — verify the runtimes work end-to-end before building GUI.

- [ ] **Step 1: Run the full test suite**

Run: `python -m pytest -q`
Expected: all tests PASS.

- [ ] **Step 2: Smoke-test hardware + recommendation from a REPL**

Run:
```bash
python -c "from pathlib import Path; from app.hardware import scan_hardware; from app.models_catalog import WHISPER_MODELS; from app.recommend import recommend_whisper; hw=scan_hardware(Path('models')); print(hw); print('best:', recommend_whisper(WHISPER_MODELS, hw)[1])"
```
Expected: prints real hardware (CUDA True, ~your VRAM) and a recommended Whisper model (a green KB-Whisper/large on a CUDA box).

- [ ] **Step 3: Smoke-test transcription on the existing sample**

Run:
```bash
python -c "from pathlib import Path; from app.transcriber import transcribe, write_outputs; segs=transcribe(Path('Mamma waw isolerad.wav'),'KBLab/kb-whisper-large','cuda','float16','sv', print); print(write_outputs(segs, Path('smoketest'), ['srt','txt']))"
```
Expected: progress percentages print, then `[WindowsPath('smoketest.srt'), WindowsPath('smoketest.txt')]`. (Downloads the model on first run.)

### FINDING (2026-06-14 integration run)

Hardware scan + recommendation verified on the real machine (RTX 4090, 24 GB → all
Whisper models green, best = KB-Whisper large). Real transcription of the 223 s sample
produced correct Swedish segments. **BUT** the process aborts (`Fatal Python error:
Aborted`) when the `WhisperModel` (CTranslate2) is deallocated *mid-program* — i.e. when
it goes out of scope or is `del`-eted while the interpreter keeps running. When the model
is kept alive until the process exits naturally (as the original `transcribe_kb.py` did),
it exits cleanly and the output files are written correctly.

**Consequence:** a long-running GUI must NEVER deallocate a `WhisperModel` mid-life, or the
first transcription kills the whole window. **Decision:** run each transcription in a
short-lived **subprocess** (`app/transcribe_cli.py`). The child keeps the model alive and
calls `os._exit(0)` after writing outputs, so no native destructor ever runs. The parent
(a QThread worker) streams progress from the child's stdout and reads the written files.
This isolates ALL native crashes from the GUI and mirrors the existing yt-dlp subprocess
pattern.

- [ ] **Step 4: Commit (document the finding)**

```bash
git add -A
git commit -m "test: verify logic layer; document CTranslate2 teardown finding" --allow-empty
```

---

## Task 11b: Subprocess transcription CLI + command builder

**Files:**
- Create: `app/transcribe_cli.py`
- Modify: `app/transcriber.py` (add pure `build_transcribe_cmd`)
- Test: `tests/test_transcribe_cmd.py`

The command builder is pure and TDD'd (mirrors `youtube.build_ytdlp_command`). The CLI
runtime is verified by the integration run, not unit tests.

- [ ] **Step 1: Write the failing test** → `tests/test_transcribe_cmd.py`:

```python
import sys
from pathlib import Path
from app.transcriber import build_transcribe_cmd

def test_cmd_has_module_and_args(tmp_path: Path):
    cmd = build_transcribe_cmd(
        audio=tmp_path / "a.wav", model_dir="m", device="cuda",
        compute_type="float16", language="sv",
        out_base=tmp_path / "out", formats=["srt", "txt"])
    assert cmd[0] == sys.executable
    assert cmd[1:3] == ["-m", "app.transcribe_cli"]
    assert "--device" in cmd and "cuda" in cmd
    assert "--formats" in cmd and "srt,txt" in cmd
    assert str(tmp_path / "a.wav") in cmd

def test_cmd_empty_language_passed_as_empty(tmp_path: Path):
    cmd = build_transcribe_cmd(
        audio=tmp_path / "a.wav", model_dir="m", device="cpu",
        compute_type="int8", language="",
        out_base=tmp_path / "out", formats=["srt"])
    i = cmd.index("--language")
    assert cmd[i + 1] == ""
```

- [ ] **Step 2: Run `python -m pytest tests/test_transcribe_cmd.py -v`; confirm FAIL (ImportError on build_transcribe_cmd).**

- [ ] **Step 3a: Add `build_transcribe_cmd` to the END of `app/transcriber.py`:**

```python
import sys


def build_transcribe_cmd(audio: Path, model_dir: str, device: str, compute_type: str,
                         language: str, out_base: Path, formats: list[str]) -> list[str]:
    """Build the argv to run one transcription in an isolated subprocess."""
    return [
        sys.executable, "-m", "app.transcribe_cli",
        "--audio", str(audio),
        "--model-dir", model_dir,
        "--device", device,
        "--compute-type", compute_type,
        "--language", language or "",
        "--out-base", str(out_base),
        "--formats", ",".join(formats),
    ]
```

- [ ] **Step 3b: Create `app/transcribe_cli.py`:**

```python
"""Run ONE transcription in an isolated process, then exit hard.

Why isolated: the CTranslate2 WhisperModel destructor can abort the process on
Windows/CUDA when deallocated mid-program. This short-lived process writes its
outputs, prints a `DONE` line, then calls os._exit(0) so no native destructor
ever runs. The parent GUI worker streams progress from stdout and reads the files.

Protocol on stdout (one per line):
  LOG <text>        human-readable log line
  PROGRESS <int>    percent complete
  FILE <path>       a written output file
  DONE              success sentinel (parent keys success off this, not exit code)
"""
from __future__ import annotations
import argparse
import os
import sys
from pathlib import Path

from faster_whisper import WhisperModel
from app.transcriber import Segment, write_outputs


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--audio", required=True)
    p.add_argument("--model-dir", required=True)
    p.add_argument("--device", required=True)
    p.add_argument("--compute-type", required=True)
    p.add_argument("--language", default="")
    p.add_argument("--out-base", required=True)
    p.add_argument("--formats", required=True)
    args = p.parse_args()

    print(f"LOG Laddar modell ({args.device}/{args.compute_type})...", flush=True)
    model = WhisperModel(args.model_dir, device=args.device, compute_type=args.compute_type)
    seg_iter, info = model.transcribe(args.audio, language=args.language or None)
    duration = getattr(info, "duration", 0) or 0

    segs: list[Segment] = []
    last = -1
    for s in seg_iter:
        segs.append(Segment(s.start, s.end, s.text.strip()))
        if duration:
            pct = min(100, int(s.end / duration * 100))
            if pct != last:
                last = pct
                print(f"PROGRESS {pct}", flush=True)
    print("PROGRESS 100", flush=True)

    formats = [f for f in args.formats.split(",") if f]
    for w in write_outputs(segs, Path(args.out_base), formats):
        print(f"FILE {w}", flush=True)
    print("DONE", flush=True)

    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)  # skip all native teardown — guarantees no CTranslate2 abort


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run `python -m pytest tests/test_transcribe_cmd.py -v`; confirm 2 PASS.**

- [ ] **Step 5: Integration-verify the CLI writes outputs and exits 0** (model already cached):

Run:
```bash
python -m app.transcribe_cli --audio "Mamma waw isolerad.wav" --model-dir "KBLab/kb-whisper-large" --device cuda --compute-type float16 --language sv --out-base smoketest --formats srt,txt
```
Expected: streams `LOG`/`PROGRESS n`/`FILE smoketest.srt`/`FILE smoketest.txt`/`DONE`, exit code 0, and `smoketest.srt` + `smoketest.txt` exist with Swedish text. Then delete smoketest.srt/smoketest.txt.

- [ ] **Step 6: Commit:**

```bash
git add app/transcribe_cli.py app/transcriber.py tests/test_transcribe_cmd.py
git commit -m "feat: isolated subprocess transcription to avoid CTranslate2 teardown abort"
```

---

## Task 12: Background workers

**Files:**
- Create: `app/workers.py`
- Test: `tests/test_workers.py`

Workers wrap the runtimes in `QThread` and emit Qt signals. NOTE: do not name a signal `finished` (QThread already has one) — use `done`.

- [ ] **Step 1: Write the failing test (worker construction smoke test)**

```python
# tests/test_workers.py
import pytest
pytest.importorskip("PySide6")
from pathlib import Path
from app.workers import TranscribeWorker, DownloadWorker, PullWorker, PostProcessWorker

def test_workers_have_expected_signals():
    for cls in (TranscribeWorker, DownloadWorker, PullWorker, PostProcessWorker):
        assert hasattr(cls, "progress")
        assert hasattr(cls, "log")
        assert hasattr(cls, "done")
        assert hasattr(cls, "failed")

def test_transcribe_worker_constructs(tmp_path: Path):
    w = TranscribeWorker(audio_path=tmp_path / "a.wav", model_dir="id",
                         device="cpu", compute_type="int8", language="sv",
                         out_base=tmp_path / "out", formats=["srt"])
    assert w.audio_path.name == "a.wav"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_workers.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# app/workers.py
"""QThread workers that run long operations off the UI thread."""
from __future__ import annotations
import subprocess
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from app import transcriber, whisper_manager, ollama_client, postprocess, youtube
from app.models_catalog import WhisperModelSpec

REPO_ROOT = Path(__file__).resolve().parent.parent  # so `-m app.transcribe_cli` resolves


class TranscribeWorker(QThread):
    progress = Signal(int)
    log = Signal(str)
    done = Signal(list)      # list[Path] of written files
    failed = Signal(str)

    def __init__(self, audio_path: Path, model_dir: str, device: str,
                 compute_type: str, language: str, out_base: Path, formats: list[str]):
        super().__init__()
        self.audio_path = audio_path
        self.model_dir = model_dir
        self.device = device
        self.compute_type = compute_type
        self.language = language
        self.out_base = out_base
        self.formats = formats

    def run(self):
        # Runs transcription in an isolated subprocess (see app/transcribe_cli.py):
        # the CTranslate2 model destructor can abort the process on Windows/CUDA, so we
        # never load the model in this GUI process. Success is keyed off the DONE line,
        # not the exit code (the child os._exit(0)s, but we stay robust either way).
        try:
            cmd = transcriber.build_transcribe_cmd(
                self.audio_path, self.model_dir, self.device, self.compute_type,
                self.language, self.out_base, self.formats)
            proc = subprocess.Popen(
                cmd, cwd=str(REPO_ROOT), stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
            assert proc.stdout is not None
            written: list[Path] = []
            done = False
            for line in proc.stdout:
                line = line.rstrip("\n")
                if line.startswith("PROGRESS "):
                    self.progress.emit(int(line[9:]))
                elif line.startswith("FILE "):
                    written.append(Path(line[5:]))
                elif line.startswith("LOG "):
                    self.log.emit(line[4:])
                elif line == "DONE":
                    done = True
                elif line:
                    self.log.emit(line)
            proc.wait()
            if not done:
                raise RuntimeError("Transkriberingen avslutades utan resultat")
            self.done.emit(written)
        except Exception as exc:  # surfaced to UI log
            self.failed.emit(str(exc))


class DownloadWorker(QThread):
    progress = Signal(int)
    log = Signal(str)
    done = Signal(str)       # final media file path as str
    failed = Signal(str)

    def __init__(self, url: str, output_dir: Path, cookies_file: Path | None):
        super().__init__()
        self.url = url
        self.output_dir = output_dir
        self.cookies_file = cookies_file

    def run(self):
        try:
            path = youtube.download(self.url, self.output_dir, self.cookies_file,
                                    log_cb=self.log.emit)
            self.done.emit(str(path))
        except Exception as exc:
            self.failed.emit(str(exc))


class PullWorker(QThread):
    progress = Signal(int)
    log = Signal(str)
    done = Signal(str)       # whisper local dir, or ollama model name
    failed = Signal(str)

    def __init__(self, whisper_spec: WhisperModelSpec | None = None,
                 models_root: Path | None = None, ollama_name: str | None = None):
        super().__init__()
        self.whisper_spec = whisper_spec
        self.models_root = models_root
        self.ollama_name = ollama_name

    def run(self):
        try:
            if self.whisper_spec is not None:
                path = whisper_manager.download_whisper(
                    self.whisper_spec, self.models_root, self.log.emit)
                self.done.emit(str(path))
            else:
                ollama_client.pull(
                    self.ollama_name,
                    progress_cb=lambda pct, status: (self.progress.emit(pct),
                                                     self.log.emit(status)))
                self.done.emit(self.ollama_name)
        except Exception as exc:
            self.failed.emit(str(exc))


class PostProcessWorker(QThread):
    progress = Signal(int)
    log = Signal(str)
    done = Signal(str)       # full result text
    failed = Signal(str)

    def __init__(self, operation: str, transcript: str, model: str):
        super().__init__()
        self.operation = operation
        self.transcript = transcript
        self.model = model

    def run(self):
        try:
            result = postprocess.run(self.operation, self.transcript, self.model,
                                     token_cb=self.log.emit)
            self.done.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_workers.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add app/workers.py tests/test_workers.py
git commit -m "feat: QThread workers for transcribe/download/pull/postprocess"
```

---

## Task 13: Models tab (hardware panel + model lists)

**Files:**
- Create: `app/ui/models_tab.py`

GUI is verified by launching, not unit tests. Keep widget construction in small helper methods.

- [ ] **Step 1: Implement the Models tab**

```python
# app/ui/models_tab.py
"""Tab showing scanned hardware and downloadable Whisper + LLM models."""
from __future__ import annotations
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox, QPushButton,
    QProgressBar,
)

from app.hardware import scan_hardware, HardwareInfo
from app.models_catalog import WHISPER_MODELS, LLM_MODELS
from app.recommend import recommend_whisper, recommend_llm, Fit
from app import whisper_manager, ollama_client
from app.workers import PullWorker

FIT_ICON = {Fit.GREEN: "🟢", Fit.YELLOW: "🟡", Fit.RED: "🔴"}


class ModelsTab(QWidget):
    def __init__(self, models_root: Path):
        super().__init__()
        self.models_root = models_root
        self.hw: HardwareInfo = scan_hardware(models_root)
        self._worker: PullWorker | None = None

        root = QVBoxLayout(self)
        root.addWidget(self._hardware_box())
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        root.addWidget(self._whisper_box())
        root.addWidget(self._llm_box())
        root.addWidget(self.progress)
        root.addStretch(1)

    def _hardware_box(self) -> QGroupBox:
        box = QGroupBox("Hårdvara")
        lay = QVBoxLayout(box)
        gpu = self.hw.gpu_name or "Ingen GPU"
        lay.addWidget(QLabel(
            f"GPU: {gpu} ({self.hw.vram_mb} MB VRAM, CUDA: "
            f"{'ja' if self.hw.has_cuda else 'nej'})"))
        lay.addWidget(QLabel(
            f"RAM: {self.hw.ram_mb} MB · CPU: {self.hw.cpu_cores} kärnor · "
            f"Ledig disk: {self.hw.free_disk_mb} MB"))
        return box

    def _whisper_box(self) -> QGroupBox:
        box = QGroupBox("Whisper-modeller (transkribering)")
        lay = QVBoxLayout(box)
        evals, best = recommend_whisper(WHISPER_MODELS, self.hw)
        for ev in evals:
            installed = whisper_manager.is_installed(ev.spec, self.models_root)
            star = " ⭐" if best and ev.spec.id == best.id else ""
            label = (f"{FIT_ICON[ev.fit]} {ev.spec.label}{star} — "
                     f"{ev.spec.download_mb} MB — {ev.reason}"
                     + ("  [installerad]" if installed else ""))
            lay.addLayout(self._model_row(
                label, enabled=ev.fit is not Fit.RED and not installed,
                on_click=lambda _=False, s=ev.spec: self._download_whisper(s)))
        return box

    def _llm_box(self) -> QGroupBox:
        box = QGroupBox("LLM-modeller (efterbearbetning via Ollama)")
        lay = QVBoxLayout(box)
        if not ollama_client.is_running():
            lay.addWidget(QLabel("Ollama körs inte — starta Ollama för att hantera LLM-modeller."))
            return box
        installed = set(ollama_client.list_models())
        evals, best = recommend_llm(LLM_MODELS, self.hw)
        for ev in evals:
            is_inst = ev.spec.name in installed
            star = " ⭐" if best and ev.spec.name == best.name else ""
            label = (f"{FIT_ICON[ev.fit]} {ev.spec.label}{star} — "
                     f"{ev.spec.download_mb} MB — {ev.reason}"
                     + ("  [installerad]" if is_inst else ""))
            lay.addLayout(self._model_row(
                label, enabled=ev.fit is not Fit.RED and not is_inst,
                on_click=lambda _=False, n=ev.spec.name: self._pull_llm(n)))
        return box

    def _model_row(self, text: str, enabled: bool, on_click) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(QLabel(text), stretch=1)
        btn = QPushButton("Ladda ner")
        btn.setEnabled(enabled)
        btn.clicked.connect(on_click)
        row.addWidget(btn)
        return row

    def _start(self, worker: PullWorker):
        self._worker = worker
        self.progress.setVisible(True)
        self.progress.setValue(0)
        worker.progress.connect(self.progress.setValue)
        worker.done.connect(lambda _=None: self.progress.setVisible(False))
        worker.failed.connect(lambda msg: self.progress.setFormat(f"Fel: {msg}"))
        worker.start()

    def _download_whisper(self, spec):
        self._start(PullWorker(whisper_spec=spec, models_root=self.models_root))

    def _pull_llm(self, name):
        self._start(PullWorker(ollama_name=name))
```

- [ ] **Step 2: Smoke-test the tab in isolation**

Run:
```bash
python -c "from PySide6.QtWidgets import QApplication; from pathlib import Path; from app.ui.models_tab import ModelsTab; app=QApplication([]); w=ModelsTab(Path('models')); w.show(); print('ok')"
```
Expected: prints `ok` with no exception (window may flash; close it).

- [ ] **Step 3: Commit**

```bash
git add app/ui/models_tab.py
git commit -m "feat: models tab with hardware panel and download buttons"
```

---

## Task 14: Transcribe tab

**Files:**
- Create: `app/ui/transcribe_tab.py`

- [ ] **Step 1: Implement the Transcribe tab**

```python
# app/ui/transcribe_tab.py
"""Tab for transcribing a local file or YouTube URL, with optional LLM post-processing."""
from __future__ import annotations
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QCheckBox, QProgressBar, QPlainTextEdit, QFileDialog, QGroupBox,
)

from app.hardware import scan_hardware
from app.models_catalog import WHISPER_MODELS
from app.recommend import evaluate_whisper
from app import whisper_manager, ollama_client
from app.workers import TranscribeWorker, DownloadWorker, PostProcessWorker

LANGUAGES = {"Svenska": "sv", "Engelska": "en", "Auto": ""}


class TranscribeTab(QWidget):
    def __init__(self, models_root: Path, cookies_file: Path | None):
        super().__init__()
        self.models_root = models_root
        self.cookies_file = cookies_file
        self.hw = scan_hardware(models_root)
        self._segments_text = ""
        self._workers: list = []

        root = QVBoxLayout(self)

        src = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("Fil (video/ljud) eller YouTube-URL")
        browse = QPushButton("Bläddra...")
        browse.clicked.connect(self._browse)
        src.addWidget(self.path_edit, stretch=1)
        src.addWidget(browse)
        root.addLayout(src)

        opts = QHBoxLayout()
        self.model_combo = QComboBox()
        self._refresh_models()
        self.lang_combo = QComboBox()
        self.lang_combo.addItems(LANGUAGES.keys())
        opts.addWidget(QLabel("Modell:"))
        opts.addWidget(self.model_combo, stretch=1)
        opts.addWidget(QLabel("Språk:"))
        opts.addWidget(self.lang_combo)
        root.addLayout(opts)

        fmt = QHBoxLayout()
        self.fmt_srt = QCheckBox("SRT"); self.fmt_srt.setChecked(True)
        self.fmt_txt = QCheckBox("TXT"); self.fmt_txt.setChecked(True)
        self.fmt_vtt = QCheckBox("VTT")
        for c in (self.fmt_srt, self.fmt_txt, self.fmt_vtt):
            fmt.addWidget(c)
        fmt.addStretch(1)
        self.start_btn = QPushButton("Starta")
        self.start_btn.clicked.connect(self._start)
        fmt.addWidget(self.start_btn)
        root.addLayout(fmt)

        self.progress = QProgressBar()
        root.addWidget(self.progress)
        self.log = QPlainTextEdit(); self.log.setReadOnly(True)
        root.addWidget(self.log, stretch=1)

        root.addWidget(self._llm_box())

    def _refresh_models(self):
        self.model_combo.clear()
        installed = whisper_manager.installed_specs(self.models_root)
        if not installed:
            self.model_combo.addItem("(inga modeller installerade — se Modeller-fliken)", None)
            return
        for spec in installed:
            self.model_combo.addItem(spec.label, spec)

    def _llm_box(self) -> QGroupBox:
        box = QGroupBox("Efterbearbeta med LLM (valfritt)")
        box.setCheckable(True)
        box.setChecked(False)
        lay = QHBoxLayout(box)
        self.op_combo = QComboBox()
        self.op_combo.addItems(["summary", "cleanup", "bullets"])
        self.llm_combo = QComboBox()
        if ollama_client.is_running():
            self.llm_combo.addItems(ollama_client.list_models() or ["(inga modeller)"])
        else:
            box.setEnabled(False)
            box.setTitle("Efterbearbeta med LLM (Ollama körs inte)")
        self.llm_btn = QPushButton("Kör")
        self.llm_btn.clicked.connect(self._postprocess)
        lay.addWidget(QLabel("Operation:")); lay.addWidget(self.op_combo)
        lay.addWidget(QLabel("Modell:")); lay.addWidget(self.llm_combo, stretch=1)
        lay.addWidget(self.llm_btn)
        return box

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Välj video eller ljud", "",
            "Media (*.mp4 *.mkv *.webm *.wav *.mp3 *.m4a);;Alla filer (*.*)")
        if path:
            self.path_edit.setText(path)

    def _formats(self) -> list[str]:
        out = []
        if self.fmt_srt.isChecked(): out.append("srt")
        if self.fmt_txt.isChecked(): out.append("txt")
        if self.fmt_vtt.isChecked(): out.append("vtt")
        return out

    def _start(self):
        source = self.path_edit.text().strip()
        if not source:
            self._append("Ange en fil eller URL först.")
            return
        if source.startswith("http"):
            self._append("Laddar ner video...")
            dl = DownloadWorker(source, self.models_root.parent / "downloads",
                                self.cookies_file)
            dl.log.connect(self._append)
            dl.failed.connect(self._append)
            dl.done.connect(self._transcribe_file)
            self._run(dl)
        else:
            self._transcribe_file(source)

    def _transcribe_file(self, path_str: str):
        spec = self.model_combo.currentData()
        if spec is None:
            self._append("Ingen modell installerad. Öppna Modeller-fliken.")
            return
        ev = evaluate_whisper(spec, self.hw)
        audio = Path(path_str)
        out_base = audio.with_suffix("")
        self.progress.setValue(0)
        self._append(f"Transkriberar {audio.name} med {spec.label}...")
        w = TranscribeWorker(audio, whisper_manager.model_dir_for(spec, self.models_root).as_posix(),
                             ev.device, ev.compute_type,
                             LANGUAGES[self.lang_combo.currentText()], out_base,
                             self._formats())
        w.progress.connect(self.progress.setValue)
        w.log.connect(self._append)
        w.failed.connect(self._append)
        w.done.connect(self._on_transcribed)
        self._run(w)

    def _on_transcribed(self, written: list):
        self._append("Klart! Sparade: " + ", ".join(str(p) for p in written))
        for p in written:
            if str(p).endswith(".txt"):
                self._segments_text = Path(p).read_text(encoding="utf-8")

    def _postprocess(self):
        if not self._segments_text:
            self._append("Inget transkript att bearbeta ännu.")
            return
        model = self.llm_combo.currentText()
        self._append(f"Efterbearbetar med {model}...")
        w = PostProcessWorker(self.op_combo.currentText(), self._segments_text, model)
        w.log.connect(self._append_inline)
        w.failed.connect(self._append)
        w.done.connect(lambda _=None: self._append("\n[Efterbearbetning klar]"))
        self._run(w)

    def _run(self, worker):
        self._workers.append(worker)
        worker.start()

    def _append(self, text: str):
        self.log.appendPlainText(text)

    def _append_inline(self, text: str):
        self.log.moveCursor(self.log.textCursor().End)
        self.log.insertPlainText(text)
```

- [ ] **Step 2: Smoke-test the tab in isolation**

Run:
```bash
python -c "from PySide6.QtWidgets import QApplication; from pathlib import Path; from app.ui.transcribe_tab import TranscribeTab; app=QApplication([]); w=TranscribeTab(Path('models'), None); w.show(); print('ok')"
```
Expected: prints `ok` with no exception.

- [ ] **Step 3: Commit**

```bash
git add app/ui/transcribe_tab.py
git commit -m "feat: transcribe tab (file/URL, model select, formats, LLM box)"
```

---

## Task 15: Main window + entry point

**Files:**
- Create: `app/ui/main_window.py`, `app/main.py`

- [ ] **Step 1: Implement the main window**

```python
# app/ui/main_window.py
"""Main application window with Transcribe and Models tabs."""
from __future__ import annotations
from pathlib import Path

from PySide6.QtWidgets import QMainWindow, QTabWidget, QLabel

from app.media import ffmpeg_available
from app.ui.transcribe_tab import TranscribeTab
from app.ui.models_tab import ModelsTab


class MainWindow(QMainWindow):
    def __init__(self, base_dir: Path):
        super().__init__()
        self.setWindowTitle("Transkribera")
        self.resize(820, 640)
        models_root = base_dir / "models"
        cookies = base_dir / "cookies.txt"
        cookies_file = cookies if cookies.exists() else None

        tabs = QTabWidget()
        tabs.addTab(TranscribeTab(models_root, cookies_file), "Transkribera")
        tabs.addTab(ModelsTab(models_root), "Modeller")
        self.setCentralWidget(tabs)

        if not ffmpeg_available():
            self.statusBar().addWidget(QLabel(
                "⚠ ffmpeg/ffprobe hittades inte — installera ffmpeg för full funktion."))
```

- [ ] **Step 2: Implement the entry point**

```python
# app/main.py
"""Launch the Transkribera desktop app."""
from __future__ import annotations
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from app.ui.main_window import MainWindow

BASE_DIR = Path(__file__).resolve().parent.parent


def main() -> int:
    app = QApplication(sys.argv)
    win = MainWindow(BASE_DIR)
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Launch the full app**

Run: `python -m app.main`
Expected: window opens with two tabs. Models tab shows real hardware and green/yellow/red models with a ⭐ recommendation. Close the window — exit code 0.

- [ ] **Step 4: Manual acceptance pass**

Verify by hand:
1. Models tab → download a small Whisper model (e.g. KB-Whisper small) → progress bar runs → row shows `[installerad]` after a re-open.
2. Transcribe tab → model dropdown now lists the installed model.
3. Pick `Mamma waw isolerad.wav`, language Svenska, SRT+TXT → Starta → progress fills, log shows segments, files written next to the input.
4. If Ollama is running: enable the LLM box, pick a model, Kör → summary streams into the log.

- [ ] **Step 5: Commit**

```bash
git add app/ui/main_window.py app/main.py
git commit -m "feat: main window, tabs, ffmpeg banner, entry point"
```

---

## Task 16: Final sweep

- [ ] **Step 1: Run the whole suite**

Run: `python -m pytest -q`
Expected: all green.

- [ ] **Step 2: Update README/notes (optional) and commit**

```bash
git add -A
git commit -m "docs: usage notes" --allow-empty
```

---

## Self-Review notes (author)

- **Spec coverage:** video+audio (Task 5 single code path), YouTube (Task 7), hardware scan (Task 3), recommend green/yellow/red + best (Task 4), Whisper download (Task 8), Ollama list/pull/generate (Task 9), LLM post-processing (Task 10), GUI desktop PySide6 with two tabs + threading (Tasks 12–15), SRT/TXT/VTT (Task 5), error handling: ffmpeg banner (Task 15), Ollama-not-running notice (Tasks 13/14), disk check + CPU fallback (Task 4), download failure surfaced (workers `failed` → log). All covered.
- **Signal naming:** `done`/`failed`/`progress`/`log` used consistently across `workers.py` and both tabs (not `finished`, which clashes with QThread).
- **Type consistency:** `model_dir_for`, `is_installed`, `download_whisper`, `installed_specs` names match between Task 8 and Tasks 12–14. `Fit`, `evaluate_whisper`, `recommend_whisper`, `evaluate_llm`, `recommend_llm` match between Task 4 and Task 13. `Segment`, `write_outputs`, `transcribe` match between Task 5 and Task 12.
- **Estimates:** VRAM/RAM/size numbers in the catalog are explicitly approximate; they drive only fit coloring and are safe to tune later.


---

## Tillägg 2026-06-15: GUI migrerat till webb-UI (Qt borttaget)

Fas 4 (GUI med PySide6) är **ersatt**. Gränssnittet är nu ett lokalt webb-UI: FastAPI-server
(`app/web/server.py`) + HTML/CSS/JS (`app/web/static/`) i ett pywebview-fönster
(`app/web/desktop.py`), entry `transkribera_web.py`, spec `Transkribera_web.spec`. Qt-filerna
(`app/ui/`, `app/main.py`, `app/workers.py`, `transkribera.py`, `Transkribera.spec`,
`tests/test_workers.py`) är borttagna. `app/`-kärnlogiken och den isolerade
transkriberings-subprocessen är oförändrade. Se designspecens "Tillägg 2026-06-15 (del 2)".
