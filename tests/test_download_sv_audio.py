"""Tester för testdata-generatorn (tests/download_sv_audio.py).

Rena funktioner — kräver inte ffmpeg eller nätverk.
"""
import json
from pathlib import Path

from tests.download_sv_audio import build_variants, ffmpeg_cmd, write_metadata


def test_build_variants_har_alla_kvaliteter_och_langder():
    v = build_variants(base_duration=223.0)
    namn = {x["file"] for x in v}
    assert {
        "kvalitet_32k_brus.mp3", "kvalitet_64k.mp3", "kvalitet_128k.mp3",
        "kvalitet_hifi_48k24.wav", "langd_2min.mp3", "langd_15min.mp3",
        "langd_45min.mp3",
    } <= namn
    for x in v:
        assert x["language"] == "sv"
        assert x["duration_sec"] > 0
        assert x["expected_word_count_approx"] > 0


def test_build_variants_quick_hoppar_over_langa(tmp_path):
    v = build_variants(base_duration=223.0, quick=True)
    namn = {x["file"] for x in v}
    assert "langd_2min.mp3" in namn
    assert "langd_15min.mp3" not in namn
    assert "langd_45min.mp3" not in namn


def test_ffmpeg_cmd_loopar_langa_varianter(tmp_path):
    v = [x for x in build_variants(223.0) if x["file"] == "langd_45min.mp3"][0]
    cmd = ffmpeg_cmd(v, Path("bas.wav"), tmp_path)
    assert "-stream_loop" in cmd and "-t" in cmd
    assert cmd[cmd.index("-t") + 1] == "2700"
    # -stream_loop måste stå före -i för att gälla insignalen
    assert cmd.index("-stream_loop") < cmd.index("-i")


def test_ffmpeg_cmd_brusvariant_mixar_brus(tmp_path):
    v = [x for x in build_variants(223.0) if x["file"] == "kvalitet_32k_brus.mp3"][0]
    cmd = ffmpeg_cmd(v, Path("bas.wav"), tmp_path)
    joined = " ".join(cmd)
    assert "anoisesrc" in joined and "amix" in joined
    assert "32k" in joined


def test_ffmpeg_cmd_hifi_ar_24bit_48khz(tmp_path):
    v = [x for x in build_variants(223.0) if x["file"] == "kvalitet_hifi_48k24.wav"][0]
    cmd = ffmpeg_cmd(v, Path("bas.wav"), tmp_path)
    assert "pcm_s24le" in cmd
    assert "48000" in cmd


def test_write_metadata_skriver_json(tmp_path):
    p = write_metadata(tmp_path, build_variants(223.0))
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["language"] == "sv"
    assert all("expected_word_count_approx" in e for e in data["files"])
    assert all("bitrate" in e and "duration_sec" in e for e in data["files"])
