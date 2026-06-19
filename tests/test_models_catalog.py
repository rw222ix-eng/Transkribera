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
    # Locked to exactly one local GGUF served by the bundled llama.cpp server.
    assert len(LLM_MODELS) == 1
    names = [m.name for m in LLM_MODELS]
    assert len(names) == len(set(names)), "duplicate LLM names"
    assert names == ["Qwen3-14B-Q8_0.gguf"]
    for m in LLM_MODELS:
        assert isinstance(m, LLMModelSpec)
        assert m.download_mb > 0 and m.vram_mb > 0 and m.ram_mb > 0

def test_kb_whisper_large_present_for_swedish():
    sv = [m for m in WHISPER_MODELS if m.id == "KBLab/kb-whisper-large"]
    assert sv and sv[0].languages == "sv"
