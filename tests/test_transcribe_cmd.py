import sys
from pathlib import Path
from app.transcriber import build_transcribe_cmd, build_parakeet_cmd, build_audio_correct_cmd

def test_cmd_has_module_and_args(tmp_path: Path):
    cmd = build_transcribe_cmd(
        audio=tmp_path / "a.wav", model_dir="m", device="cuda",
        compute_type="float16", language="sv",
        out_base=tmp_path / "out", formats=["srt", "txt"])
    assert cmd[0] == sys.executable
    assert cmd[1:3] == ["-m", "app.transcribe_cli"]
    assert "--device" in cmd and "cuda" in cmd
    assert "--formats" in cmd and "srt,txt" in cmd
    assert str(tmp_path / "a.wav") in cmd

def test_cmd_empty_language_passed_as_empty(tmp_path: Path):
    cmd = build_transcribe_cmd(
        audio=tmp_path / "a.wav", model_dir="m", device="cpu",
        compute_type="int8", language="",
        out_base=tmp_path / "out", formats=["srt"])
    i = cmd.index("--language")
    assert cmd[i + 1] == ""


def test_parakeet_cmd_has_module_and_args(tmp_path: Path):
    cmd = build_parakeet_cmd(
        audio=tmp_path / "a.wav", model_dir="m", language="en",
        out_base=tmp_path / "out", formats=["srt", "txt"])
    assert cmd[0] == sys.executable
    assert cmd[1:3] == ["-m", "app.parakeet_cli"]
    assert "--language" in cmd and "en" in cmd
    assert "--formats" in cmd and "srt,txt" in cmd
    # Parakeet is GPU-only — it must NOT carry faster-whisper device/compute knobs.
    assert "--device" not in cmd and "--compute-type" not in cmd
    assert str(tmp_path / "a.wav") in cmd


def test_audio_correct_cmd_has_module_and_args(tmp_path: Path):
    cmd = build_audio_correct_cmd(
        audio=tmp_path / "a.wav", model_dir="m", segments_json=str(tmp_path / "s.json"),
        out_base=tmp_path / "out", formats=["srt"])
    assert cmd[0] == sys.executable
    assert cmd[1:3] == ["-m", "app.audio_correct_cli"]
    assert "--segments" in cmd and str(tmp_path / "s.json") in cmd
    assert "--formats" in cmd and "srt" in cmd
