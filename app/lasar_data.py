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
from pathlib import Path


def data_dir() -> Path:
    # Frozen: PyInstaller packar bundlad data under sys._MEIPASS
    # (jfr course_data.data_dir och _static_dir i app/web/server.py).
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", ".")) / "app" / "data" / "lasar"
    return Path(__file__).resolve().parent / "data" / "lasar"


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
