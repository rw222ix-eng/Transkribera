from pathlib import Path
from app.models_catalog import WhisperModelSpec
from app import whisper_manager as wm

SPEC = WhisperModelSpec("KBLab/kb-whisper-large", "L", 3000, 10000, 5000, "sv", 6)

def test_model_dir_is_under_root(tmp_path: Path):
    d = wm.model_dir_for(SPEC, tmp_path)
    assert d.parent == tmp_path
    assert "kb-whisper-large" in d.name

def test_not_installed_when_no_model_bin(tmp_path: Path):
    assert wm.is_installed(SPEC, tmp_path) is False

def test_installed_when_model_bin_present(tmp_path: Path):
    d = wm.model_dir_for(SPEC, tmp_path)
    d.mkdir(parents=True)
    (d / "model.bin").write_bytes(b"x")
    assert wm.is_installed(SPEC, tmp_path) is True

def test_download_calls_snapshot(monkeypatch, tmp_path: Path):
    called = {}
    def fake_snapshot(repo_id, local_dir, **kw):
        called["repo_id"] = repo_id
        Path(local_dir).mkdir(parents=True, exist_ok=True)
        (Path(local_dir) / "model.bin").write_bytes(b"x")
        return local_dir
    monkeypatch.setattr(wm, "snapshot_download", fake_snapshot)
    path = wm.download_whisper(SPEC, tmp_path)
    assert called["repo_id"] == "KBLab/kb-whisper-large"
    assert wm.is_installed(SPEC, tmp_path)
    assert (path / "model.bin").exists()
