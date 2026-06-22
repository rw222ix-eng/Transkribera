"""Build an iCalendar (.ics) file from lesson agenda items — locally, offline.

The app is local/offline (no Google Calendar etc. for real data), so we hand-roll
RFC 5545 instead of pulling in a dependency or a cloud service. Each dated insight
becomes an all-day VEVENT the teacher can import into whatever calendar they use.
"""
from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta

PRODID = "-//Transkribera//Lektionsagenda//SV"


def _escape(text: str) -> str:
    """Escape a TEXT value per RFC 5545 §3.3.11 (backslash, comma, semicolon,
    newline)."""
    return (str(text or "")
            .replace("\\", "\\\\")
            .replace("\n", "\\n")
            .replace(",", "\\,")
            .replace(";", "\\;"))


def _fold(line: str) -> str:
    """Fold a content line to <=75 octets with CRLF + space continuation
    (RFC 5545 §3.1). Folds on a byte budget so multi-byte å/ä/ö aren't split mid
    character."""
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    out, chunk = [], b""
    limit = 75
    for ch in line:
        b = ch.encode("utf-8")
        if len(chunk) + len(b) > limit:
            out.append(chunk.decode("utf-8"))
            chunk = b
            limit = 74           # continuation lines start with one leading space
        else:
            chunk += b
    out.append(chunk.decode("utf-8"))
    return "\r\n ".join(out)


def _parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat((value or "").strip()[:10])
    except ValueError:
        return None


def _uid(item: dict) -> str:
    """Stable UID per insight so re-importing updates rather than duplicates."""
    seed = f"{item.get('id')}-{item.get('due_date')}-{item.get('text')}"
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:20] + "@transkribera"


def build_calendar(items: list[dict], *, now: datetime | None = None) -> str:
    """Render agenda items (db.agenda shape) to an .ics string. Items without a
    valid due_date are skipped. All-day events on the due date."""
    stamp = (now or datetime.now()).strftime("%Y%m%dT%H%M%S")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:{PRODID}",
             "CALSCALE:GREGORIAN", "METHOD:PUBLISH"]
    for it in items:
        d = _parse_date(it.get("due_date"))
        if d is None:
            continue
        ctx = " · ".join(x for x in (it.get("group"), it.get("course"),
                                     it.get("lesson_name")) if x)
        typ = it.get("typ") or "kalender"
        summary = f"[{typ}] {it.get('text') or ''}".strip()
        lines += [
            "BEGIN:VEVENT",
            f"UID:{_uid(it)}",
            f"DTSTAMP:{stamp}",
            f"DTSTART;VALUE=DATE:{d.strftime('%Y%m%d')}",
            # All-day event: DTEND is the exclusive next day.
            f"DTEND;VALUE=DATE:{(d + timedelta(days=1)).strftime('%Y%m%d')}",
            _fold("SUMMARY:" + _escape(summary)),
        ]
        if ctx:
            lines.append(_fold("DESCRIPTION:" + _escape(ctx)))
        if it.get("status") == "klar":
            lines.append("STATUS:CONFIRMED")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
