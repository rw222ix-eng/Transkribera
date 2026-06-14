from pathlib import Path
from app.youtube import build_ytdlp_command

def test_command_includes_url_and_default_format(tmp_path: Path):
    cmd = build_ytdlp_command("https://yt/abc", cookies_file=None, output_dir=tmp_path)
    assert cmd[0] == "yt-dlp"
    assert "https://yt/abc" == cmd[-1]
    assert "bv*+ba/b" in cmd
    assert "mkv" in cmd

def test_command_adds_cookies_when_present(tmp_path: Path):
    cookies = tmp_path / "cookies.txt"
    cookies.write_text("x", encoding="utf-8")
    cmd = build_ytdlp_command("u", cookies_file=cookies, output_dir=tmp_path)
    assert "--cookies" in cmd and str(cookies) in cmd

def test_command_omits_cookies_when_missing(tmp_path: Path):
    cmd = build_ytdlp_command("u", cookies_file=tmp_path / "nope.txt", output_dir=tmp_path)
    assert "--cookies" not in cmd
