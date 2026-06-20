"""Static catalog of downloadable models with hardware requirements.

VRAM/RAM/size figures are approximate working estimates used for the
green/yellow/red fit logic and for the redesigned Models tab's chips
(speed, context, capabilities). Tune freely as real numbers are observed.
"""
from dataclasses import dataclass, field


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
    # ---- presentation (Models tab chips) ----
    rtf: float = 0.0   # speed, × realtime on a recent GPU (estimate)
    score: float = 0.0 # capability/precision score (defaults to rank if 0)
    # ---- transcription backend ----
    engine: str = "whisper"   # "whisper" (faster-whisper/CT2) | "parakeet" (onnx-asr)
    runtime: str = ""         # onnx-asr model key for the parakeet engine

    @property
    def vram_gb(self) -> float:
        return round(self.vram_fp16_mb / 1024, 1)


@dataclass(frozen=True)
class LLMModelSpec:
    name: str          # GGUF filename served by llama.cpp, e.g. "Qwen3-14B-Q8_0.gguf"
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


WHISPER_MODELS: list[WhisperModelSpec] = [
    WhisperModelSpec("Systran/faster-whisper-tiny", "Whisper tiny", 75, 1000, 500, "multi", 1, rtf=50, score=1),
    WhisperModelSpec("Systran/faster-whisper-base", "Whisper base", 145, 1200, 600, "multi", 2, rtf=40, score=2),
    WhisperModelSpec("Systran/faster-whisper-small", "Whisper small", 480, 2000, 1000, "multi", 3, rtf=30, score=3),
    WhisperModelSpec("Systran/faster-whisper-medium", "Whisper medium", 1500, 5000, 2500, "multi", 4, rtf=12, score=4),
    WhisperModelSpec("Systran/faster-whisper-large-v3", "Whisper large-v3", 3000, 10000, 5000, "multi", 5, rtf=7, score=4.5),
    WhisperModelSpec("Systran/faster-distil-whisper-large-v3", "Distil large-v3 (snabb)", 1500, 6000, 3000, "multi", 4,
                     "Snabbare, något lägre noggrannhet", rtf=14, score=4),
    WhisperModelSpec("KBLab/kb-whisper-tiny", "KB-Whisper tiny (sv)", 75, 1000, 500, "sv", 3, rtf=50, score=3),
    WhisperModelSpec("KBLab/kb-whisper-small", "KB-Whisper small (sv)", 480, 2000, 1000, "sv", 4, rtf=30, score=4),
    WhisperModelSpec("KBLab/kb-whisper-medium", "KB-Whisper medium (sv)", 1500, 5000, 2500, "sv", 5, rtf=12, score=5),
    WhisperModelSpec("KBLab/kb-whisper-large", "KB-Whisper large (sv)", 3000, 10000, 5000, "sv", 6,
                     "Bäst för svenska", rtf=7, score=5.5),
    # English uses NVIDIA Parakeet (a different ASR architecture than Whisper),
    # run via onnx-asr / ONNX Runtime. languages="en" makes the language picker
    # auto-select it for Engelska. id = HF repo to download; runtime = onnx-asr key.
    WhisperModelSpec("istupakov/parakeet-tdt-0.6b-v2-onnx", "Parakeet TDT 0.6B (en)",
                     2500, 2500, 1300, "en", 4, "Engelska — snabb (NVIDIA Parakeet)",
                     rtf=25, score=3.5,
                     engine="parakeet", runtime="nemo-parakeet-tdt-0.6b-v2"),
]

# Local GGUFs served by the bundled llama.cpp server (Phase 0 spike). The text
# model is the default; the vision model is loaded on demand for image chat
# (see gpu_arbiter.ensure_model / llm_manager.VISION_LLM).
LLM_MODELS: list[LLMModelSpec] = [
    LLMModelSpec("Qwen3-14B-Q8_0.gguf", "Qwen3 14B (Q8_0)", 14971, 16000, 24000, 6,
                 "Korrigering & sammanfattning (llama.cpp)", toks=55, ctx="40k",
                 uses=("text", "sv"),
                 files=("PDF", "TXT", "Markdown", "DOCX")),
    LLMModelSpec("gemma-3-4b-it-Q4_K_M.gguf", "Gemma 3 4B (vision)", 3341, 6000, 9000, 4,
                 "Bildanalys i chatten (llama.cpp)", toks=70, ctx="8k",
                 uses=("text", "vision"), vision=True,
                 files=()),
]
