"""Back up the local knowledge base to a single zip.

Everything a teacher builds over years lives in two small files next to the exe
(``transkribera.db`` + ``history.json``, plus ``settings.json``). There was no
deliberate backup — only the move-the-folder path relocation. This bundles them
into one timestamped zip under ``exports/`` the teacher can copy somewhere safe.

Restore is intentionally NOT automated: swapping the SQLite file under a running
app risks WAL corruption, and overwriting live data is a deliberate, careful act.
The zip is a plain archive — restoring is "close the app, unzip the files back
next to the exe" (see manifest.txt inside the zip).
"""
from __future__ import annotations

import zipfile
from datetime import datetime
from pathlib import Path

# Files that make up the knowledge base (relative to base_dir).
BACKUP_FILES = ("transkribera.db", "history.json", "settings.json")

_MANIFEST = (
    "Transkribera — säkerhetskopia\n"
    "Skapad: {when}\n\n"
    "Innehåll: {files}\n\n"
    "Återställning: stäng appen och packa upp filerna bredvid exe-filen\n"
    "(samma mapp som history.json). Gör en kopia av nuvarande filer först.\n"
)


def create_backup(base: Path, *, now: datetime | None = None) -> dict:
    """Zip the knowledge-base files into base/exports/. Returns {path, files,
    bytes}. Only files that exist are included; missing ones are skipped."""
    base = Path(base)
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M")
    out_dir = base / "exports"
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"transkribera-backup-{stamp}.zip"

    included: list[str] = []
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name in BACKUP_FILES:
            src = base / name
            if src.exists() and src.is_file():
                zf.write(src, arcname=name)
                included.append(name)
        zf.writestr("manifest.txt", _MANIFEST.format(
            when=(now or datetime.now()).isoformat(timespec="seconds"),
            files=", ".join(included) or "(inga filer hittades)"))
    return {"path": str(dest), "files": included, "bytes": dest.stat().st_size}
