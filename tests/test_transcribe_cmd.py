import sys
from pathlib import Path
from app.transcriber import build_transcribe_cmd

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

def test_build_audio_correct_cmd(tmp_path: Path):
    from app.transcriber import build_audio_correct_cmd
    cmd = build_audio_correct_cmd(
        audio=tmp_path / "a.mp4", model_dir="m", segments_json="segs.json",
        out_base=tmp_path / "out", formats=["srt"], language="sv")
    assert "app.audio_correct_cli" in cmd
    assert cmd[cmd.index("--segments") + 1] == "segs.json"
    assert cmd[cmd.index("--language") + 1] == "sv"
