from app import transcriber as T


def test_read_srt_recovers_segments(tmp_path):
    segs = [T.Segment(0.0, 2.5, "Hej där."), T.Segment(2.5, 5.0, "Andra raden.")]
    p = tmp_path / "x.srt"
    p.write_text(T.segments_to_srt(segs), encoding="utf-8")
    got = T.read_srt(p)
    assert [(round(g["start"], 1), round(g["end"], 1), g["text"]) for g in got] == [
        (0.0, 2.5, "Hej där."),
        (2.5, 5.0, "Andra raden."),
    ]


def test_read_srt_joins_multiline_text(tmp_path):
    p = tmp_path / "m.srt"
    p.write_text("1\n00:00:01,000 --> 00:00:03,000\nrad ett\nrad två\n", encoding="utf-8")
    got = T.read_srt(p)
    assert got == [{"start": 1.0, "end": 3.0, "text": "rad ett rad två"}]


def test_read_srt_accepts_vtt_dot_timestamps(tmp_path):
    p = tmp_path / "v.vtt"
    p.write_text("WEBVTT\n\n00:00:00.000 --> 00:00:01.500\nhej\n", encoding="utf-8")
    got = T.read_srt(p)
    assert got == [{"start": 0.0, "end": 1.5, "text": "hej"}]


def test_read_srt_missing_file_returns_empty(tmp_path):
    assert T.read_srt(tmp_path / "does-not-exist.srt") == []
