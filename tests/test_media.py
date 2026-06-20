import os
import time
from pathlib import Path

import pytest

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
    monkeypatch.setattr(media.shutil, "which", lambda name: "/usr/bin/" + name)
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
    monkeypatch.setattr(media.shutil, "which", lambda name: "/usr/bin/" + name)
    a = tmp_path / "talk.mp3"
    a.write_text("audio", encoding="utf-8")

    def fake_run(cmd, cwd):
        (Path(cwd) / cmd[-1]).write_text("png", encoding="utf-8")
        return 0, ""
    monkeypatch.setattr(media, "_run", fake_run)

    out = media.make_thumbnail(a)
    assert out == tmp_path / "talk.thumb.png"
    assert out.exists()


def test_make_thumbnail_returns_cache_when_fresh(tmp_path, monkeypatch):
    monkeypatch.setattr(media.shutil, "which", lambda name: "/usr/bin/" + name)
    v = tmp_path / "clip.mp4"
    v.write_text("video", encoding="utf-8")
    cached = tmp_path / "clip.thumb.jpg"
    cached.write_text("old", encoding="utf-8")
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


def test_build_web_video_copy_cmd():
    assert media.build_web_video_copy_cmd("in.mkv", "out.mp4") == [
        "ffmpeg", "-y", "-i", "in.mkv", "-c:v", "copy", "-c:a", "aac",
        "-movflags", "+faststart", "out.mp4"]


def test_build_web_video_encode_cmd():
    assert media.build_web_video_encode_cmd("in.mkv", "out.mp4", "h264_nvenc") == [
        "ffmpeg", "-y", "-i", "in.mkv", "-c:v", "h264_nvenc", "-c:a", "aac",
        "-movflags", "+faststart", "out.mp4"]


def test_ensure_web_video_returns_input_for_web_format(tmp_path, monkeypatch):
    v = tmp_path / "clip.mp4"
    v.write_text("v", encoding="utf-8")
    monkeypatch.setattr(media, "_run", lambda *a, **k:
                        (_ for _ in ()).throw(AssertionError("no ffmpeg for web format")))
    assert media.ensure_web_video(v) == v


def test_ensure_web_video_copies_mkv(tmp_path, monkeypatch):
    v = tmp_path / "clip.mkv"
    v.write_text("v", encoding="utf-8")

    def fake_run(cmd, cwd):
        (Path(cwd) / cmd[-1]).write_text("mp4", encoding="utf-8")
        return 0, ""
    monkeypatch.setattr(media, "_run", fake_run)

    out = media.ensure_web_video(v)
    assert out == tmp_path / "clip.web.mp4"
    assert out.exists()


def test_ensure_web_video_falls_back_to_encode(tmp_path, monkeypatch):
    v = tmp_path / "clip.mkv"
    v.write_text("v", encoding="utf-8")
    calls = []

    def fake_run(cmd, cwd):
        calls.append(cmd)
        if "copy" in cmd:
            return 1, "incompatible"          # copy fails
        (Path(cwd) / cmd[-1]).write_text("mp4", encoding="utf-8")  # encode succeeds
        return 0, ""
    monkeypatch.setattr(media, "_run", fake_run)

    out = media.ensure_web_video(v)
    assert out == tmp_path / "clip.web.mp4"
    assert any("copy" in c for c in calls) and any("-c:v" in c for c in calls)


def test_ensure_web_video_raises_when_all_fail(tmp_path, monkeypatch):
    v = tmp_path / "clip.mkv"
    v.write_text("v", encoding="utf-8")
    monkeypatch.setattr(media, "_run", lambda cmd, cwd: (1, "fail"))
    with pytest.raises(RuntimeError):
        media.ensure_web_video(v)
