import pytest
pytest.importorskip("PySide6")
from pathlib import Path
from app.workers import TranscribeWorker, DownloadWorker, PullWorker, PostProcessWorker

def test_workers_have_expected_signals():
    for cls in (TranscribeWorker, DownloadWorker, PullWorker, PostProcessWorker):
        assert hasattr(cls, "progress")
        assert hasattr(cls, "log")
        assert hasattr(cls, "done")
        assert hasattr(cls, "failed")

def test_transcribe_worker_constructs(tmp_path: Path):
    w = TranscribeWorker(audio_path=tmp_path / "a.wav", model_dir="id",
                         device="cpu", compute_type="int8", language="sv",
                         out_base=tmp_path / "out", formats=["srt"])
    assert w.audio_path.name == "a.wav"
