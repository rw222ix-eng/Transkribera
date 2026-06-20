import types

import numpy as np

from app import audio_correct_cli as ac


def test_prompt_for_language_and_default():
    assert "svenska" in ac._prompt_for("sv").lower()
    assert "english" in ac._prompt_for("en").lower()
    assert ac._prompt_for("xx") == ac._prompt_for("sv")     # unknown -> Swedish


def test_build_conv_has_text_and_audio_parts():
    conv = ac._build_conv("utkast: {text}", "hej", np.zeros(3, dtype=np.float32))
    kinds = [p["type"] for p in conv[0]["content"]]
    assert "text" in kinds and "audio" in kinds


def test_clean_strips_wrapping_quotes_and_falls_back():
    assert ac._clean('"Hej där"', "d") == "Hej där"
    assert ac._clean("   ", "utkast") == "utkast"           # empty -> keep draft


def test_decode_audio_raises_on_ffmpeg_error(monkeypatch):
    proc = types.SimpleNamespace(returncode=1, stdout=b"", stderr=b"boom")
    monkeypatch.setattr(ac.subprocess, "run", lambda *a, **k: proc)
    try:
        ac.decode_audio("x")
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "avkodning" in str(e)
