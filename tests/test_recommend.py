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
