"""Bundlat centralt innehåll för matematikkurserna (Fas 3).

Statisk, offline, versionerad data (`app/data/centralt_innehall/*.json`,
fält `lasar_version` för Gy11/Gy25) som seedas in i `course_content` vid
appstart (idempotent — se db.seed_course_content). Texterna är kondenserade
parafraser av det centrala innehållet, inte Skolverkets exakta formuleringar.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def data_dir() -> Path:
    # Frozen: PyInstaller packar bundlad data under sys._MEIPASS
    # (jfr _static_dir i app/web/server.py).
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", ".")) / "app" / "data" / "centralt_innehall"
    return Path(__file__).resolve().parent / "data" / "centralt_innehall"


def load_centralt_innehall() -> list[dict]:
    """Alla kursfiler som en lista av {"kurs", "lasar_version", "innehall"}.
    En trasig fil hoppas över (seedningen får aldrig stoppa appstarten)."""
    out: list[dict] = []
    d = data_dir()
    if not d.is_dir():
        return out
    for f in sorted(d.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("kurs"):
                out.append(data)
        except (OSError, json.JSONDecodeError):
            continue
    return out
