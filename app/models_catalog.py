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
