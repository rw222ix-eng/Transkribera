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


def create_backup(base: Path, *, now: datetime | None = None,
                  dest_dir: Path | str | None = None) -> dict:
    """Zip the knowledge-base files into base/exports/ — eller till den plats
    läraren valt (Etapp 0.9).

    En säkerhetskopia som ligger kvar bredvid originalet skyddar mot ett
    misstag men inte mot en trasig disk, och det är den senare läraren är rädd
    för. `dest_dir` är därför hennes egen plats: en USB-sticka, en molnmapp,
    en nätverksenhet. Går den inte att skriva till faller kopian tillbaka på
    exports/ och SÄGER det — en kopia man tror finns är värre än ingen.

    Returns {path, files, bytes, plats, fallback}."""
    base = Path(base)
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M")
    fallback = False
    out_dir = base / "exports"
    if dest_dir:
        onskad = Path(str(dest_dir)).expanduser()
        try:
            onskad.mkdir(parents=True, exist_ok=True)
            prov = onskad / ".transkribera-skrivprov"
            prov.write_bytes(b"")
            prov.unlink()
            out_dir = onskad
        except OSError:
            fallback = True
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"transkribera-backup-{stamp}.zip"

    included: list[str] = []
    try:
        with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for name in BACKUP_FILES:
                src = base / name
                if src.exists() and src.is_file():
                    zf.write(src, arcname=name)
                    included.append(name)
            zf.writestr("manifest.txt", _MANIFEST.format(
                when=(now or datetime.now()).isoformat(timespec="seconds"),
                files=", ".join(included) or "(inga filer hittades)"))
    except OSError as e:
        # Tar disken slut mitt i zippandet ligger en HALV kopia kvar med rätt
        # namn och rätt datum — den ser ut som en säkerhetskopia ända tills
        # dagen man behöver den. Den städas bort, och felet sägs rakt ut.
        dest.unlink(missing_ok=True)
        raise OSError(e.errno, "säkerhetskopian gick inte att skriva färdigt") from e
    return {"path": str(dest), "files": included, "bytes": dest.stat().st_size,
            "plats": str(out_dir), "fallback": fallback}


# ── Kvällskopian (Etapp 0.9) ────────────────────────────────────────────────
# «Varje kväll» betyder varje kväll APPEN ÄR IGÅNG. En lokal app kan inte
# kopiera något när datorn är avstängd, och att lova det vore att lova något
# ingen kan hålla. Därför: en kontroll med jämna mellanrum medan appen lever,
# och en kopia så fort klockan passerat kvällen utan att dagen fått sin.
KVALL_TIMME = 18


def dags_for_kvallskopia(senast: str | None, now: datetime | None = None,
                         timme: int = KVALL_TIMME) -> bool:
    """Har dagens kvällskopia inte tagits än — och är det kväll?"""
    nu = now or datetime.now()
    if nu.hour < timme:
        return False
    if not senast:
        return True
    try:
        sist = datetime.fromisoformat(str(senast))
    except ValueError:
        return True
    return sist.date() < nu.date()
