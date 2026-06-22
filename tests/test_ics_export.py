from datetime import datetime
from app import ics_export


def _item(**f):
    base = {"id": 1, "typ": "kalender", "text": "Prov om derivata",
            "due_date": "2026-05-21", "status": "öppen",
            "group": "NA21", "course": "Matematik 2b", "lesson_name": "lektion.mp3"}
    base.update(f)
    return base


def test_build_calendar_wraps_events():
    cal = ics_export.build_calendar([_item()], now=datetime(2026, 1, 1, 8, 0, 0))
    assert cal.startswith("BEGIN:VCALENDAR")
    assert cal.rstrip().endswith("END:VCALENDAR")
    assert "BEGIN:VEVENT" in cal and "END:VEVENT" in cal
    assert "DTSTART;VALUE=DATE:20260521" in cal
    assert "DTEND;VALUE=DATE:20260522" in cal          # all-day = exclusive next day
    assert "Prov om derivata" in cal
    assert "NA21" in cal                                # context in DESCRIPTION
    assert "\r\n" in cal                                # CRLF line endings


def test_skips_items_without_valid_date():
    cal = ics_export.build_calendar([_item(due_date=""), _item(due_date="ogiltigt")])
    assert "BEGIN:VEVENT" not in cal


def test_escapes_special_chars():
    cal = ics_export.build_calendar([_item(text="prov, kap 3; se facit")])
    assert "prov\\, kap 3\\; se facit" in cal


def test_stable_uid_is_deterministic():
    a = ics_export.build_calendar([_item()])
    b = ics_export.build_calendar([_item()])
    uid_a = [l for l in a.splitlines() if l.startswith("UID:")][0]
    uid_b = [l for l in b.splitlines() if l.startswith("UID:")][0]
    assert uid_a == uid_b                               # re-import updates, not duplicates


def test_long_summary_is_folded():
    cal = ics_export.build_calendar([_item(text="x" * 200)])
    assert all(len(line.encode("utf-8")) <= 75 for line in cal.split("\r\n"))
