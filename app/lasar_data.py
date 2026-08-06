"""Bundlade läsårsdata: loven, de röda dagarna och studiedagarna (Fas 0.1).

Samma mönster som course_data.py — statisk, offline, versionerad JSON i
``app/data/lasar/*.json`` som seedas in i ``lov``-tabellen vid appstart
(idempotent, se db.seed_lov).

Varför en fil och inte bara en tabell: en färsk installation utan Google-konto
måste ändå veta när skolan är stängd, annars ritar veckovyn lovveckor som
arbetsveckor. Synkar läraren sin Google Kalender skriver den ovanpå — se
db.replace_lov.
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path


def _rot() -> Path:
    # Frozen: PyInstaller packar bundlad data under sys._MEIPASS
    # (jfr course_data.data_dir och _static_dir i app/web/server.py).
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", ".")) / "app" / "data"
    return Path(__file__).resolve().parent / "data"


def data_dir() -> Path:
    return _rot() / "lasar"


def load_lov() -> list[dict]:
    """Alla läsårsfilers lovposter som en platt lista
    ``{"fran", "till", "namn", "typ"}``. En trasig fil hoppas över —
    seedningen får aldrig stoppa appstarten."""
    out: list[dict] = []
    d = data_dir()
    if not d.is_dir():
        return out
    for f in sorted(d.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        for p in data.get("lov") or []:
            if isinstance(p, dict) and p.get("fran") and p.get("till") and p.get("namn"):
                out.append({"fran": p["fran"], "till": p["till"],
                            "namn": p["namn"], "typ": p.get("typ") or "lov"})
    out.sort(key=lambda p: (p["fran"], p["till"], p["namn"]))
    return out


# ------------------------------------------------------------ exempelschemat --
# En färsk installation utan Google-koppling har inget schema, och då finns
# ingen vecka att planera i — hela planeringen går inte att prova. Filen
# app/data/exempelschema.json är därför en avritning av en riktig
# gymnasielärarvecka (se kommentaren i filen). Den seedas EN gång och skrivs
# över i sin helhet vid första kalendersynken: den är en startpunkt, aldrig ett
# påstående om att läraren har de här lektionerna.


def load_exempelschema() -> dict:
    """{"termin", "schema", "aterkommande", …} eller {} om filen saknas."""
    f = _rot() / "exempelschema.json"
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _lovdag(datum: str, lov: list[dict]) -> bool:
    return any(p["fran"] <= datum <= p["till"] for p in lov)


def expandera_poster(aterkommande: list[dict], fran: str, till: str,
                     lov: list[dict] | None = None) -> list[dict]:
    """Veckoposterna (mentorstid, konferens) som DATUM, dag för dag över
    läsåret. Lektionerna behöver ingen expansion — de är ett veckomönster som
    gränssnittet räknar om per dag — men en post ligger på en bestämd dag.
    Lovdagar hoppas över: skolan är stängd, och en konferens under sportlovet
    hade varit appens påhitt."""
    lov = lov or []
    try:
        d, slut = date.fromisoformat(fran), date.fromisoformat(till)
    except (TypeError, ValueError):
        return []
    per_dag: dict[int, list[dict]] = {}
    for p in aterkommande or []:
        try:
            per_dag.setdefault(int(p.get("dag") or 0), []).append(p)
        except (TypeError, ValueError):
            continue
    ut: list[dict] = []
    while d <= slut:
        iso = d.isoformat()
        if not _lovdag(iso, lov):
            for p in per_dag.get(d.isoweekday(), []):
                ut.append({"datum": iso, "tid": p.get("tid") or "",
                           "titel": p.get("titel") or "", "klass": p.get("klass") or ""})
        d += timedelta(days=1)
    return ut
