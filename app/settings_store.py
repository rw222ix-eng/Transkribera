"""Appens inställningar: en liten JSON-fil i basmappen (offline, en användare).
Säkerhetskopians plats och kvällsschema och exempelschemats markering bor här.
Modelldisken (`models_dir`) som filen byggdes för försvann 2026-10-07 med
transkriberingen; en gammal nyckel i filen läses aldrig och skadar inte.
Varje funktion tar ``base`` så att den går att testa mot en tom mapp.
"""
from __future__ import annotations

import json
from pathlib import Path


def settings_path(base: Path) -> Path:
    return Path(base) / "settings.json"


def load(base: Path) -> dict:
    """Read the settings dict; an absent/corrupt file degrades to empty."""
    try:
        data = json.loads(settings_path(base).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save(base: Path, data: dict) -> None:
    settings_path(base).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
