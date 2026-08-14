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

import re
from pathlib import Path, PureWindowsPath

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


# ── Filnamn som går att skriva (Etapp 2) ───────────────────────────────────
# En inspelning heter det läraren döpte den till, och namnet kommer utifrån:
# från webbläsarens filväljare, från en URL-nedladdning, från en telefon som
# spelat in. `Path(name).name` tar bort mappdelarna men inte tecknen Windows
# vägrar skriva — och `? * : | < > "` i ett filnamn gav OSError inne i
# uppladdningen, alltså ett 500-svar utan besked mitt i en lektion som just
# spelats in. Ett kolon är värre än så: `x:y.mp3` skapar en NTFS-dataström på
# filen `x`, så uppladdningen «lyckas» och filen finns ändå inte.
_OTILLATNA = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_name(raw: str, fallback: str = "fil", *, max_len: int = 120) -> str:
    """Ett filnamn som säkert går att skriva, med ändelsen kvar.

    Ändelsen behålls separat: klipps namnet på längden ska «.mp3» följa med,
    annars vet varken spelaren eller ffmpeg vad filen är."""
    # PureWindowsPath, inte Path: `Path` betyder POSIX-regler på Mac och Linux,
    # där `\` är ett vanligt tecken i ett filnamn. `..\..\Windows\evil.mp3` från
    # en Windows-webbläsare blev då EN namndel, och `x:y.mp3` blev `xy.mp3` i
    # stället för `y.mp3` — mappdelen och NTFS-dataströmmen överlevde som text i
    # namnet. Windows-reglerna är strikt hårdare (`\` OCH `/` separerar, `x:` är
    # en enhet) och är dessutom de enda som är säkra att köra överallt: samma
    # uppladdning ska ge samma filnamn oavsett var appen kör. På Windows är det
    # exakt vad `Path` redan gjorde — ingen beteendeskillnad där.
    stam = PureWindowsPath(str(raw or "")).name
    if stam in (".", ".."):
        stam = ""
    p = PureWindowsPath(stam)
    ext = _OTILLATNA.sub("", p.suffix)[:16]
    namn = _OTILLATNA.sub("", p.stem).strip().strip(".")
    if not namn:
        return fallback
    return namn[:max(1, max_len - len(ext))] + ext
