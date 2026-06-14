from app.media import parse_duration

def test_parse_duration_reads_value():
    assert parse_duration("duration=123.456\n") == 123.456

def test_parse_duration_missing_returns_none():
    assert parse_duration("codec=h264\n") is None

def test_parse_duration_na_returns_none():
    assert parse_duration("duration=N/A\n") is None
