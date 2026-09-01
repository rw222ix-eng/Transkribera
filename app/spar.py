"""Användarspåret — vad läraren faktiskt gör i appen, sparat i databasen.

Poängen är inte felsökning (det gör transkribera.log) utan förbättring: efter
några veckors användning ska det gå att fråga databasen «vilka funktioner
används mest?», «vad ber Rickard canvaschatten om, och på vilka papper?»,
«vilka rutor skrivs om gång på gång?» — och bygga om appen efter svaren.
Rapporten läses med `python -m tools.spar`.

Tre sorters rader (`art`):
  * `api`    — ett API-anrop som ÄNDRAR något (POST/PUT/DELETE), loggat av
               middlewaren i server.py. Vägen är normaliserad (id:n utbytta)
               så att raderna går att räkna per funktion, inte per papper.
  * `onske`  — lärarens egen mening i canvaschatten, med målet hon pekade på.
               Det är den enda platsen där hennes ord passerar appen utan att
               annars sparas: jobb_events har modellens svar, inte frågan.
  * `utfall` — vad varvet faktiskt ändrade (dokumentdiffens element-id:n),
               loggat när jobbet är klart. Paras med sitt `onske` via dok_id
               och tid; ihop säger de «bad om X, fick Y ändrat».

Loggningen får ALDRIG fälla appen: varje skrivning sväljer sina egna fel.
Ett tappat spår är ett hål i statistiken, inte ett trasigt varv.
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime

from app import db

# Id-segment i en API-väg: heltal (exams, bok-sidor) eller planeringens
# 12-teckens hex-pid. Byts mot {id} så att /api/exams/17/refine och
# /api/exams/93/refine räknas som SAMMA funktion.
_ID_SEGMENT = re.compile(r"^(\d+|[0-9a-f]{12})$")


def normalisera(vag: str) -> str:
    """API-vägen med dokument-id:n utbytta mot {id}."""
    delar = vag.split("/")
    return "/".join("{id}" if _ID_SEGMENT.match(d) else d for d in delar)


def logga(db_file, art: str, *, vag: str | None = None,
          doktyp: str | None = None, dok_id=None, detalj: dict | None = None) -> None:
    """Skriv en spårrad. Sväljer alla fel — se modulhuvudet."""
    try:
        conn = db.connect(db_file)
        try:
            conn.execute(
                "INSERT INTO spar (tid, art, vag, doktyp, dok_id, detalj) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (datetime.now().isoformat(timespec="seconds"), art, vag,
                 doktyp, str(dok_id) if dok_id is not None else None,
                 json.dumps(detalj, ensure_ascii=False) if detalj else None))
            conn.commit()
        finally:
            conn.close()
    except (sqlite3.Error, OSError):
        pass
