"""Local app settings — a tiny JSON file next to history.json (offline, single
user). Today it holds one thing: where the downloaded models live (the
"download disk" the user picks in the UI). Kept deliberately small and
GUI-agnostic; every function takes ``base`` so it is trivially testable.
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


def default_models_root(base: Path) -> Path:
    return Path(base) / "models"


def get_models_root(base: Path) -> Path:
    """The configured models directory, or the default ``base/models`` when the
    user has not picked another disk."""
    val = load(base).get("models_dir")
    return Path(val) if val else default_models_root(base)


def set_models_root(base: Path, models_dir: str | Path | None) -> Path:
    """Persist where models are stored and return the effective root. ``None``
    (or empty) clears the override and falls back to ``base/models``. The target
    directory is created so a following download lands cleanly."""
    data = load(base)
    if models_dir:
        root = Path(models_dir)
        data["models_dir"] = str(root)
    else:
        data.pop("models_dir", None)
        root = default_models_root(base)
    save(base, data)
    root.mkdir(parents=True, exist_ok=True)
    return root
