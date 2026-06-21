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


VSPEC = lm.VISION_LLM


def test_vision_spec_has_mmproj_text_model_does_not():
    assert lm.VISION_LLM.is_vision is True
    assert lm.VISION_LLM.mmproj_filename.endswith(".gguf")
    assert lm.ACTIVE_LLM.is_vision is False


def test_spec_by_name_resolves_and_misses():
    assert lm.spec_by_name(lm.ACTIVE_LLM.filename) is lm.ACTIVE_LLM
    assert lm.spec_by_name(lm.VISION_LLM.filename) is lm.VISION_LLM
    assert lm.spec_by_name("nope.gguf") is None


def test_mmproj_path_for(tmp_path):
    assert lm.mmproj_path_for(lm.ACTIVE_LLM, tmp_path) is None
    p = lm.mmproj_path_for(lm.VISION_LLM, tmp_path)
    assert p is not None and p.name == lm.VISION_LLM.mmproj_filename


def test_vision_is_installed_requires_both_weights_and_mmproj(tmp_path):
    lm.model_dir_for(lm.VISION_LLM, tmp_path).mkdir(parents=True)
    lm.model_path_for(lm.VISION_LLM, tmp_path).write_bytes(b"x")
    assert lm.is_installed(lm.VISION_LLM, tmp_path) is False       # mmproj still missing
    lm.mmproj_path_for(lm.VISION_LLM, tmp_path).write_bytes(b"y")
    assert lm.is_installed(lm.VISION_LLM, tmp_path) is True


def test_delete_gguf_removes_weights_and_mmproj(tmp_path):
    d = lm.model_dir_for(lm.VISION_LLM, tmp_path)
    d.mkdir(parents=True)
    lm.model_path_for(lm.VISION_LLM, tmp_path).write_bytes(b"x")
    lm.mmproj_path_for(lm.VISION_LLM, tmp_path).write_bytes(b"y")
    assert lm.delete_gguf(lm.VISION_LLM, tmp_path) is True
    assert not d.exists()
    assert lm.is_installed(lm.VISION_LLM, tmp_path) is False


def test_delete_gguf_missing_returns_false(tmp_path):
    assert lm.delete_gguf(SPEC, tmp_path) is False


def test_delete_gguf_refuses_outside_root(tmp_path, monkeypatch):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "m.gguf").write_bytes(b"x")
    monkeypatch.setattr(lm, "model_dir_for", lambda spec, root: outside)
    assert lm.delete_gguf(SPEC, tmp_path / "models") is False
    assert outside.exists()


def test_download_vision_fetches_weights_and_mmproj(monkeypatch, tmp_path):
    got = []
    def fake_dl(repo_id, filename, local_dir, **kw):
        got.append(filename)
        p = Path(local_dir) / filename
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x")
        return str(p)
    monkeypatch.setattr(lm, "hf_hub_download", fake_dl)
    lm.download_gguf(lm.VISION_LLM, tmp_path)
    assert lm.VISION_LLM.filename in got
    assert lm.VISION_LLM.mmproj_filename in got
    assert lm.is_installed(lm.VISION_LLM, tmp_path)
