from pathlib import Path
from app import llm_manager as lm

SPEC = lm.GGUFModelSpec(
    repo_id="Qwen/Qwen3-14B-GGUF", filename="Qwen3-14B-Q8_0.gguf",
    label="Qwen3 14B Q8_0", download_mb=14971)

def test_model_dir_is_repo_scoped(tmp_path):
    d = lm.model_dir_for(SPEC, tmp_path)
    assert d == tmp_path / "llm" / "Qwen__Qwen3-14B-GGUF"

def test_model_path_is_file_in_dir(tmp_path):
    assert lm.model_path_for(SPEC, tmp_path) == \
        tmp_path / "llm" / "Qwen__Qwen3-14B-GGUF" / "Qwen3-14B-Q8_0.gguf"

def test_is_installed_false_then_true(tmp_path):
    assert lm.is_installed(SPEC, tmp_path) is False
    p = lm.model_path_for(SPEC, tmp_path)
    p.parent.mkdir(parents=True)
    p.write_bytes(b"x")
    assert lm.is_installed(SPEC, tmp_path) is True

def test_active_llm_is_a_spec():
    assert isinstance(lm.ACTIVE_LLM, lm.GGUFModelSpec)
    assert lm.ACTIVE_LLM.filename.endswith(".gguf")
    assert lm.ACTIVE_LLM.repo_id == "Qwen/Qwen3-14B-GGUF"

def test_download_calls_hf_hub(monkeypatch, tmp_path):
    called = {}
    def fake_dl(repo_id, filename, local_dir, **kw):
        called["repo_id"] = repo_id
        p = Path(local_dir) / filename
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x")
        return str(p)
    monkeypatch.setattr(lm, "hf_hub_download", fake_dl)
    path = lm.download_gguf(SPEC, tmp_path)
    assert called["repo_id"] == "Qwen/Qwen3-14B-GGUF"
    assert lm.is_installed(SPEC, tmp_path)
    assert path == lm.model_path_for(SPEC, tmp_path)
