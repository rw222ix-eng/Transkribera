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
    # A long-context text model (default) plus an on-demand vision model.
    names = [m.name for m in LLM_MODELS]
    assert len(names) == len(set(names)), "duplicate LLM names"
    assert "Qwen3-14B-Q8_0.gguf" in names
    for m in LLM_MODELS:
        assert isinstance(m, LLMModelSpec)
        assert m.download_mb > 0 and m.vram_mb > 0 and m.ram_mb > 0


def test_llm_catalog_has_a_vision_model():
    vision = [m for m in LLM_MODELS if m.vision]
    assert vision, "expected a vision-capable LLM in the catalog"
    assert vision[0].name == "gemma-3-4b-it-Q4_K_M.gguf"

def test_kb_whisper_large_present_for_swedish():
    sv = [m for m in WHISPER_MODELS if m.id == "KBLab/kb-whisper-large"]
    assert sv and sv[0].languages == "sv"
