import sys
import types

import numpy as np

from app import parakeet_asr as pa


def test_decode_audio_converts_pcm_to_float32(monkeypatch):
    samples = np.array([0, 16384, -16384], dtype=np.int16)
    proc = types.SimpleNamespace(returncode=0, stdout=samples.tobytes(), stderr=b"")
    monkeypatch.setattr(pa.subprocess, "run", lambda *a, **k: proc)
    out = pa.decode_audio("x.mp4")
    assert out.dtype == np.float32
    assert abs(out[1] - 0.5) < 1e-3 and abs(out[2] + 0.5) < 1e-3


def test_decode_audio_raises_on_ffmpeg_error(monkeypatch):
    proc = types.SimpleNamespace(returncode=1, stdout=b"", stderr=b"boom")
    monkeypatch.setattr(pa.subprocess, "run", lambda *a, **k: proc)
    try:
        pa.decode_audio("x")
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "avkodning" in str(e)


def test_chunk_starts_single_window_for_short_audio():
    assert pa.chunk_starts(10.0) == [0.0]


def test_chunk_starts_overlapping_windows():
    starts = pa.chunk_starts(70.0)          # chunk 30, overlap 2 -> step 28
    assert starts[0] == 0.0 and starts[1] == 28.0
    assert len(starts) >= 3


def test_group_segments_breaks_on_sentence_end():
    # Tightly-spaced tokens (no big gap) ending in "." -> one sentence cue.
    segs = pa.group_segments(["Hej", " där", "."], [0.0, 0.3, 0.6], 1.5)
    assert len(segs) == 1
    assert segs[0].text == "Hej där."


def test_group_segments_breaks_on_silence_gap():
    segs = pa.group_segments(["a", "b"], [0.0, 3.0], 3.5)   # 3.0 s gap after "a"
    assert len(segs) == 2
    assert segs[0].text == "a" and segs[1].text == "b"


def test_providers_prefers_cuda_and_returns_tuples(monkeypatch):
    fake = types.SimpleNamespace(
        get_available_providers=lambda: ["CUDAExecutionProvider", "CPUExecutionProvider"])
    monkeypatch.setitem(sys.modules, "onnxruntime", fake)
    provs = pa._providers("cuda")
    assert provs[0] == ("CUDAExecutionProvider", {})


def test_providers_falls_back_to_cpu(monkeypatch):
    fake = types.SimpleNamespace(get_available_providers=lambda: ["CPUExecutionProvider"])
    monkeypatch.setitem(sys.modules, "onnxruntime", fake)
    assert pa._providers("cuda") == [("CPUExecutionProvider", {})]


def test_transcribe_loads_with_timestamps_and_groups(monkeypatch):
    captured = {}
    monkeypatch.setattr(pa, "decode_audio",
                        lambda a: np.zeros(int(2 * pa.SAMPLE_RATE), dtype=np.float32))
    monkeypatch.setattr(pa, "_providers", lambda d: [("CPUExecutionProvider", {})])

    class Res:
        tokens = ["Hej", " då", "."]
        timestamps = [0.0, 0.4, 0.8]

    class Model:
        def recognize(self, wav, sample_rate=16000):
            return Res()

    def load_model(runtime, path=None, providers=None):
        captured["runtime"] = runtime
        captured["path"] = path
        # onnx-asr: load_model(...).with_timestamps() enables token timestamps
        return types.SimpleNamespace(with_timestamps=lambda: Model())

    monkeypatch.setitem(sys.modules, "onnx_asr", types.SimpleNamespace(load_model=load_model))
    segs = pa.transcribe("a.mp4", "/m", "nemo-parakeet-tdt-0.6b-v2", "cuda")
    assert captured["runtime"] == "nemo-parakeet-tdt-0.6b-v2"
    assert captured["path"] == "/m"
    assert segs and segs[0].text == "Hej då."
