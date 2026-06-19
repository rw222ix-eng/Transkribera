from app.models_catalog import WHISPER_MODELS, LLM_MODELS, WhisperModelSpec, LLMModelSpec

def test_whisper_catalog_is_well_formed():
    assert len(WHISPER_MODELS) >= 1
    ids = [m.id for m in WHISPER_MODELS]
    assert len(ids) == len(set(ids)), "duplicate Whisper ids"
    for m in WHISPER_MODELS:
        assert isinstance(m, WhisperModelSpec)
        assert m.download_mb > 0
        assert m.vram_int8_mb <= m.vram_fp16_mb
        assert m.rank > 0

def test_llm_catalog_is_well_formed():
    assert len(LLM_MODELS) >= 1
    names = [m.name for m in LLM_MODELS]
    assert len(names) == len(set(names)), "duplicate LLM names"
    for m in LLM_MODELS:
        assert isinstance(m, LLMModelSpec)
        assert m.download_mb > 0 and m.vram_mb > 0 and m.ram_mb > 0

def test_kb_whisper_large_present_for_swedish():
    sv = [m for m in WHISPER_MODELS if m.id == "KBLab/kb-whisper-large"]
    assert sv and sv[0].languages == "sv"

def test_catalog_is_locked_to_chosen_models():
    # Transcription: exactly two locked engines (kb-whisper + Parakeet). LLM: one.
    assert [m.id for m in WHISPER_MODELS] == [
        "KBLab/kb-whisper-large", "istupakov/parakeet-tdt-0.6b-v3-onnx"]
    assert [m.name for m in LLM_MODELS] == ["gemma4:26b-a4b-it-qat"]


def test_parakeet_is_english_onnx_engine():
    para = next(m for m in WHISPER_MODELS if m.id == "istupakov/parakeet-tdt-0.6b-v3-onnx")
    assert para.engine == "parakeet"
    assert para.languages == "en"
    # kb-whisper must remain the faster-whisper engine
    kb = next(m for m in WHISPER_MODELS if m.id == "KBLab/kb-whisper-large")
    assert kb.engine == "faster-whisper"
