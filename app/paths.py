"""Re-root stored absolute paths under the current base_dir.

history.json and the lesson DB store absolute paths to results (under
``Transkriberingar/``) and in-app recordings (under ``downloads/``). If the
app/exe folder is moved, those absolutes no longer exist and the files appear
to vanish (player, thumbnail, reveal, delete all break).

``relocate`` resolves a stored path against the CURRENT base by matching the
well-known anchor folder, so a moved app still finds its own files. It is
backward compatible and migration-free: a path that still exists (or has no
anchor) is returned unchanged — only genuinely missing paths are re-rooted.
"""
from __future__ import annotations

from pathlib import Path

# Folders the app owns under base_dir; everything it stores lives under one of these.
ANCHORS = ("Transkriberingar", "downloads")


def relocate(base: Path | str, stored: str | Path | None) -> Path | None:
    """Resolve a stored path against the current ``base``.

    Returns ``None`` for empty input. Tries the path as-is first; if it is
    missing, rebuilds it under ``base`` from the last anchor segment
    (``Transkriberingar/…`` or ``downloads/…``) when that re-rooted path exists.
    Otherwise returns the original path unchanged (the caller decides how to
    handle a still-missing file)."""
    if not stored:
        return None
    p = Path(stored)
    if p.exists():
        return p
    parts = p.parts
    for anchor in ANCHORS:
        if anchor in parts:
            idx = len(parts) - 1 - parts[::-1].index(anchor)   # last occurrence
            candidate = Path(base).joinpath(*parts[idx:])
            if candidate.exists():
                return candidate
    return p
