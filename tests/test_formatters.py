from app.transcriber import (
    Segment, format_timestamp_srt, format_timestamp_vtt,
    segments_to_srt, segments_to_vtt, segments_to_txt,
)

SEGS = [Segment(0.0, 1.5, "Hej"), Segment(1.5, 3.25, "världen")]

def test_srt_timestamp():
    assert format_timestamp_srt(3661.5) == "01:01:01,500"

def test_vtt_timestamp():
    assert format_timestamp_vtt(3661.5) == "01:01:01.500"

def test_segments_to_srt():
    out = segments_to_srt(SEGS)
    assert out == (
        "1\n00:00:00,000 --> 00:00:01,500\nHej\n\n"
        "2\n00:00:01,500 --> 00:00:03,250\nvärlden\n\n"
    )

def test_segments_to_vtt_has_header():
    out = segments_to_vtt(SEGS)
    assert out.startswith("WEBVTT\n\n")
    assert "00:00:00.000 --> 00:00:01.500\nHej" in out

def test_segments_to_txt_is_plain_lines():
    assert segments_to_txt(SEGS) == "Hej\nvärlden\n"
