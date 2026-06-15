from app import whisper_manager as wm
from app.models_catalog import WhisperModelSpec


def test_progress_percent_basic():
    total_mb = 100
    half = 50 * 1024 * 1024
    assert wm._progress_percent(half, total_mb) == 50


def test_progress_percent_capped_at_99():
    total_mb = 100
    over = 200 * 1024 * 1024
    assert wm._progress_percent(over, total_mb) == 99


def test_progress_percent_zero_total():
    assert wm._progress_percent(123, 0) == 0


def test_download_whisper_reports_progress(tmp_path, monkeypatch):
    spec = WhisperModelSpec("Acme/test-whisper", "Test", 1, 1000, 500, "sv", 1)
    target = wm.model_dir_for(spec, tmp_path)

    def fake_snapshot(repo_id, local_dir):
        # Simulate a completed download by creating model.bin.
        target.mkdir(parents=True, exist_ok=True)
        (target / "model.bin").write_bytes(b"x" * 1024)

    monkeypatch.setattr(wm, "snapshot_download", fake_snapshot)
    seen = []
    out = wm.download_whisper(spec, tmp_path, progress_cb=seen.append)
    assert out == target
    assert seen and seen[-1] == 100  # final 100% reported
