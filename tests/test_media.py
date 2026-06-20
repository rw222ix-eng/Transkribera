from pathlib import Path
from app import media
from app.media import parse_duration

def test_parse_duration_reads_value():
    assert parse_duration("duration=123.456\n") == 123.456

def test_parse_duration_missing_returns_none():
    assert parse_duration("codec=h264\n") is None

def test_parse_duration_na_returns_none():
    assert parse_duration("duration=N/A\n") is None


def test_build_thumbnail_cmd_video_seeks_and_scales():
    cmd = media.build_thumbnail_cmd("v.mkv", "v.thumb.jpg", "video", seek=12.0)
    assert cmd == ["ffmpeg", "-y", "-ss", "12.0", "-i", "v.mkv",
                   "-frames:v", "1", "-vf", "scale=640:-2", "v.thumb.jpg"]


def test_build_thumbnail_cmd_audio_uses_showwavespic():
    cmd = media.build_thumbnail_cmd("a.mp3", "a.thumb.png", "audio")
    assert cmd == ["ffmpeg", "-y", "-i", "a.mp3", "-filter_complex",
                   "showwavespic=s=640x200:colors=#3B5BDB", "a.thumb.png"]


def test_make_thumbnail_video_generates_jpg(tmp_path, monkeypatch):
    v = tmp_path / "clip.mp4"
    v.write_text("video", encoding="utf-8")
    monkeypatch.setattr(media, "probe_duration", lambda p: 100.0)

    def fake_run(cmd, cwd):
        (Path(cwd) / cmd[-1]).write_text("jpg", encoding="utf-8")
        return 0, ""
    monkeypatch.setattr(media, "_run", fake_run)

    out = media.make_thumbnail(v)
    assert out == tmp_path / "clip.thumb.jpg"
    assert out.exists()


def test_make_thumbnail_audio_generates_png(tmp_path, monkeypatch):
    a = tmp_path / "talk.mp3"
    a.write_text("audio", encoding="utf-8")
    monkeypatch.setattr(media, "_run", lambda cmd, cwd:
                        ((Path(cwd) / cmd[-1]).write_text("png", encoding="utf-8"), 0, "")[1:])

    out = media.make_thumbnail(a)
    assert out == tmp_path / "talk.thumb.png"
    assert out.exists()


def test_make_thumbnail_returns_cache_when_fresh(tmp_path, monkeypatch):
    v = tmp_path / "clip.mp4"
    v.write_text("video", encoding="utf-8")
    cached = tmp_path / "clip.thumb.jpg"
    cached.write_text("old", encoding="utf-8")
    import os, time
    os.utime(cached, (time.time() + 10, time.time() + 10))

    def boom(*a, **k):
        raise AssertionError("ffmpeg should not run when cache is fresh")
    monkeypatch.setattr(media, "_run", boom)

    out = media.make_thumbnail(v)
    assert out == cached


def test_make_thumbnail_returns_none_when_ffmpeg_fails(tmp_path, monkeypatch):
    v = tmp_path / "clip.mp4"
    v.write_text("video", encoding="utf-8")
    monkeypatch.setattr(media, "probe_duration", lambda p: None)
    monkeypatch.setattr(media, "_run", lambda cmd, cwd: (1, "boom"))
    assert media.make_thumbnail(v) is None
