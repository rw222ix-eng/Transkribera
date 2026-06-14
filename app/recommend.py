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
