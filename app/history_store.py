"""Persist transcription history to a JSON file next to the app.

Each entry holds enough to re-open (stored transcript), re-run (original source),
and display the Models/History rows. Degrades gracefully: any read/write error
yields an empty list rather than crashing the UI.
"""
from __future__ import annotations
import json
from pathlib import Path

MAX_ENTRIES = 200


def _read(path: Path) -> list:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _write(path: Path, items: list) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def load_history(path: Path) -> list:
    return _read(path)


def add_history(path: Path, entry: dict) -> dict:
    items = [e for e in _read(path) if e.get("id") != entry.get("id")]
    items.insert(0, entry)
    _write(path, items[:MAX_ENTRIES])
    return entry


def delete_history(path: Path, entry_id: str) -> None:
    _write(path, [e for e in _read(path) if e.get("id") != entry_id])
