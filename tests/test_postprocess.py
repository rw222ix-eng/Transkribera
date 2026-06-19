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
    monkeypatch.setattr(pp.llm_client, "generate", fake_generate)
    out = pp.run("summary", "transkript", model="Qwen3-14B-Q8_0.gguf")
    assert out == "resultat"
    assert captured["model"] == "Qwen3-14B-Q8_0.gguf"
    assert "transkript" in captured["prompt"]
