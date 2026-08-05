"""Argv:n till det enda pass som fortfarande kör i en egen process.

Transkriberingens argv är borta med Whisper: ljudet går till OpenAI och
tidsättningen sker i serverprocessen. Ljudrättningen (Gemma på GPU:n) kör kvar
isolerat, för den ska släppa allt sitt VRAM när den är klar.
"""
from pathlib import Path

from app.transcriber import build_audio_correct_cmd


def test_build_audio_correct_cmd(tmp_path: Path):
    cmd = build_audio_correct_cmd(
        audio=tmp_path / "a.mp4", model_dir="m", segments_json="segs.json",
        out_base=tmp_path / "out", formats=["srt"], language="sv")
    assert "app.audio_correct_cli" in cmd
    assert cmd[cmd.index("--segments") + 1] == "segs.json"
    assert cmd[cmd.index("--language") + 1] == "sv"


def test_audio_correct_cmd_tar_med_ljud_och_format(tmp_path: Path):
    cmd = build_audio_correct_cmd(
        audio=tmp_path / "lektion.wav", model_dir="m", segments_json="s.json",
        out_base=tmp_path / "ut", formats=["srt", "txt"])
    assert cmd[cmd.index("--audio") + 1] == str(tmp_path / "lektion.wav")
    assert cmd[cmd.index("--formats") + 1] == "srt,txt"
    assert cmd[cmd.index("--language") + 1] == ""
