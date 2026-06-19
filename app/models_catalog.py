"""Static catalog of downloadable models with hardware requirements.

VRAM/RAM/size figures are approximate working estimates used for the
green/yellow/red fit logic and for the redesigned Models tab's chips
(speed, context, capabilities). Tune freely as real numbers are observed.

LOCKED CATALOG: transcription is restricted to two engines — KB-Whisper large
(Swedish, faster-whisper / CTranslate2) and Parakeet TDT 0.6B v3 (English, an
NVIDIA NeMo transducer run via ONNX / onnx-asr, always on the GPU) — plus a
single LLM, Gemma 4 26B-A4B (for both correction and analysis). Do not add other
models here — the UI is driven by these lists, so extra entries would become
user-selectable again. The ``engine`` field on WhisperModelSpec selects the
inference backend ("faster-whisper" vs "parakeet"); /api/transcribe dispatches on it.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class WhisperModelSpec:
    id: str            # HuggingFace repo id (CTranslate2/faster-whisper, or ONNX repo for parakeet)
    label: str         # display name
    download_mb: int
    vram_fp16_mb: int  # approx VRAM for float16 on GPU
    vram_int8_mb: int  # approx VRAM for int8 on GPU
    languages: str     # "sv", "en", or "multi"
    rank: int          # higher = more accurate (used to pick "best")
    note: str = ""
    # ---- presentation (Models tab chips) ----
    rtf: float = 0.0   # speed, × realtime on a recent GPU (estimate)
    score: float = 0.0 # capability/precision score (defaults to rank if 0)
    # ---- inference backend ----
    engine: str = "faster-whisper"  # "faster-whisper" (CTranslate2) | "parakeet" (onnx-asr, GPU)

    @property
    def vram_gb(self) -> float:
        return round(self.vram_fp16_mb / 1024, 1)


@dataclass(frozen=True)
class LLMModelSpec:
    name: str          # Ollama model name, e.g. "llama3.1:8b"
    label: str
    download_mb: int
    vram_mb: int       # recommended VRAM to run on GPU
    ram_mb: int        # recommended RAM for CPU fallback
    rank: int          # higher = more capable
    note: str = ""
    # ---- presentation (Models tab chips) ----
    toks: int = 0                       # tokens/s estimate
    ctx: str = "128k"                   # context window
    uses: tuple = ("text",)            # capability tags: text/sv/vision/omni
    vision: bool = False
    files: tuple = ("PDF", "TXT", "Markdown")

    @property
    def vram_gb(self) -> float:
        return round(self.vram_mb / 1024, 1)


# Locked transcription engines:
#  - KB-Whisper large  : Swedish, faster-whisper/CTranslate2 (CUDA float16).
#  - Parakeet TDT 0.6B v3 : English, NVIDIA NeMo transducer run via onnx-asr on the
#    GPU (CUDA/TensorRT execution provider). NOT a Whisper model — separate engine.
WHISPER_MODELS: list[WhisperModelSpec] = [
    WhisperModelSpec("KBLab/kb-whisper-large", "KB-Whisper large (sv)", 3000, 10000, 5000, "sv", 6,
                     "Bäst för svenska", rtf=7, score=5.5),
    WhisperModelSpec("istupakov/parakeet-tdt-0.6b-v3-onnx", "Parakeet TDT 0.6B v3 (en)",
                     3000, 2500, 1200, "en", 5,
                     "Engelska, NVIDIA Parakeet (ONNX, GPU)", rtf=30, score=5.0,
                     engine="parakeet"),
]

# Locked: only Gemma 4 26B-A4B (used for both correction and analysis, reasoning off).
LLM_MODELS: list[LLMModelSpec] = [
    LLMModelSpec("gemma4:26b-a4b-it-qat", "Gemma 4 26B-A4B", 15000, 16000, 24000, 6,
                 "Korrigering & analys", toks=140, ctx="256k", uses=("text", "sv"),
                 files=("PDF", "TXT", "Markdown", "DOCX")),
]
