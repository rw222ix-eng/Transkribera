from app import postprocess


def test_should_translate():
    assert postprocess.should_translate("en", "sv")
    assert postprocess.should_translate("sv", "en")
    assert not postprocess.should_translate("en", "en")
    assert not postprocess.should_translate("EN", "en")  # case-insensitive
    assert not postprocess.should_translate("", "sv")
    assert not postprocess.should_translate("en", "")


def test_translate_segments_batch_preserves_timestamps(monkeypatch):
    def fake_gen(model, prompt, **kw):
        return "1. Hej\n2. Världen"
    monkeypatch.setattr(postprocess.ollama_client, "generate", fake_gen)
    segs = [{"start": 0.0, "end": 1.0, "text": "Hello"},
            {"start": 1.0, "end": 2.0, "text": "World"}]
    out = postprocess.translate_segments(segs, "en", "sv", "m", batch_size=8)
    assert [s["text"] for s in out] == ["Hej", "Världen"]
    assert [(s["start"], s["end"]) for s in out] == [(0.0, 1.0), (1.0, 2.0)]


def test_translate_segments_count_guard_falls_back_per_cue(monkeypatch):
    calls = {"n": 0}

    def fake_gen(model, prompt, **kw):
        calls["n"] += 1
        if "1. " in prompt and "2. " in prompt:   # the batched call
            return "1. bara en rad"               # only 1 of 2 -> misaligned
        return "översatt"                          # per-cue calls
    monkeypatch.setattr(postprocess.ollama_client, "generate", fake_gen)
    segs = [{"start": 0, "end": 1, "text": "A"}, {"start": 1, "end": 2, "text": "B"}]
    out = postprocess.translate_segments(segs, "en", "sv", "m")
    assert [s["text"] for s in out] == ["översatt", "översatt"]
    assert calls["n"] == 3   # 1 batch + 2 per-cue fallback


def test_translate_segments_keeps_source_when_empty(monkeypatch):
    def fake_gen(model, prompt, **kw):
        if "1. " in prompt and "2. " in prompt:
            return "garbage without numbers"   # misaligned -> fallback
        return "   "                            # per-cue returns nothing usable
    monkeypatch.setattr(postprocess.ollama_client, "generate", fake_gen)
    segs = [{"start": 0, "end": 1, "text": "Keep me"},
            {"start": 1, "end": 2, "text": "And me"}]
    out = postprocess.translate_segments(segs, "en", "sv", "m")
    assert [s["text"] for s in out] == ["Keep me", "And me"]


def test_translate_segments_empty_input():
    assert postprocess.translate_segments([], "en", "sv", "m") == []


def test_translate_segments_streams_via_token_cb(monkeypatch):
    monkeypatch.setattr(postprocess.ollama_client, "generate",
                        lambda model, prompt, **kw: "1. Hej\n2. Världen")
    segs = [{"start": 0.0, "end": 1.0, "text": "Hello"},
            {"start": 1.0, "end": 2.0, "text": "World"}]
    streamed = []
    postprocess.translate_segments(segs, "en", "sv", "m", token_cb=streamed.append)
    assert streamed == ["Hej\n", "Världen\n"]
