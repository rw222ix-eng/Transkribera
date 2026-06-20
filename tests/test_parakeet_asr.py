import sys
import types

from app import parakeet_asr as pa


def test_group_splits_on_pause():
    words = [(0.0, 0.5, "a"), (0.6, 1.0, "b"), (3.0, 3.5, "c")]  # 2.0 s gap before c
    segs = pa.group_segments(words)
    assert len(segs) == 2
    assert segs[0].text == "a b" and segs[1].text == "c"
    assert segs[0].start == 0.0 and segs[0].end == 1.0


def test_group_splits_on_word_count():
    words = [(i * 0.1, i * 0.1 + 0.05, "w") for i in range(30)]  # contiguous, no pause
    segs = pa.group_segments(words)
    assert len(segs) >= 2
    assert all(len(s.text.split()) <= pa.MAX_SEG_WORDS for s in segs)


def test_group_fixes_spacing_before_punctuation():
    seg = pa.group_segments([(0.0, 0.3, "hej"), (0.3, 0.5, ",")])[0]
    assert seg.text == "hej,"


def test_word_tuples_accepts_dicts():
    res = types.SimpleNamespace(timestamps=[{"start": 0, "end": 1, "word": "hi"}])
    assert pa._word_tuples(res, 5.0) == [(0.0, 1.0, "hi")]


def test_word_tuples_accepts_tuples():
    res = types.SimpleNamespace(timestamps=[(0.0, 0.5, "a"), (0.5, 1.0, "b")])
    assert pa._word_tuples(res, 5.0) == [(0.0, 0.5, "a"), (0.5, 1.0, "b")]


def test_word_tuples_falls_back_to_single_cue():
    assert pa._word_tuples("plain text", 7.0) == [(0.0, 7.0, "plain text")]


def test_providers_prefers_cuda_when_available(monkeypatch):
    fake = types.SimpleNamespace(
        get_available_providers=lambda: ["CUDAExecutionProvider", "CPUExecutionProvider"])
    monkeypatch.setitem(sys.modules, "onnxruntime", fake)
    assert pa._providers("cuda")[0] == "CUDAExecutionProvider"


def test_providers_falls_back_to_cpu(monkeypatch):
    fake = types.SimpleNamespace(get_available_providers=lambda: ["CPUExecutionProvider"])
    monkeypatch.setitem(sys.modules, "onnxruntime", fake)
    assert pa._providers("cuda") == ["CPUExecutionProvider"]


def test_transcribe_loads_model_and_groups(monkeypatch):
    captured = {}
    class FakeModel:
        def recognize(self, wav, timestamps=False):
            captured["timestamps"] = timestamps
            return types.SimpleNamespace(
                text="hello world",
                timestamps=[(0.0, 0.5, "hello"), (0.6, 1.0, "world")])
    fake = types.SimpleNamespace()
    def load_model(runtime, path=None, providers=None):
        captured["runtime"] = runtime
        captured["path"] = path
        return FakeModel()
    fake.load_model = load_model
    monkeypatch.setitem(sys.modules, "onnx_asr", fake)
    monkeypatch.setattr(pa, "_decode_to_wav", lambda a: "x.wav")
    monkeypatch.setattr(pa, "_probe_duration", lambda a: 1.0)
    monkeypatch.setattr(pa, "_providers", lambda d: ["CPUExecutionProvider"])

    segs = pa.transcribe("a.mp4", "/models/parakeet", "nemo-parakeet-tdt-0.6b-v2", "cpu")
    assert captured["runtime"] == "nemo-parakeet-tdt-0.6b-v2"
    assert captured["path"] == "/models/parakeet"
    assert captured["timestamps"] is True
    assert len(segs) == 1 and segs[0].text == "hello world"


def test_transcribe_handles_old_onnx_asr_without_timestamps(monkeypatch):
    class OldModel:
        def recognize(self, wav):              # no timestamps kwarg -> TypeError path
            return "just text"
    fake = types.SimpleNamespace(load_model=lambda *a, **k: OldModel())
    monkeypatch.setitem(sys.modules, "onnx_asr", fake)
    monkeypatch.setattr(pa, "_decode_to_wav", lambda a: "x.wav")
    monkeypatch.setattr(pa, "_probe_duration", lambda a: 4.0)
    monkeypatch.setattr(pa, "_providers", lambda d: ["CPUExecutionProvider"])

    segs = pa.transcribe("a.mp4", "/m", "nemo-parakeet-tdt-0.6b-v2", "cpu")
    assert len(segs) == 1
    assert segs[0].text == "just text"
    assert segs[0].end == 4.0           # fallback cue spans the probed duration
