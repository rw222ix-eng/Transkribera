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

import json
import sqlite3
import zipfile
from datetime import datetime
from pathlib import Path

# Files that make up the knowledge base (relative to base_dir).
BACKUP_FILES = ("transkribera.db", "history.json", "settings.json")

# Kopior som sparas på platsen. Databasen är 2,3 GB (sept 2026, nästan allt
# pappersversioner med bilder), så en kopia per kväll utan gallring fyller
# vilken disk som helst. Betygskopian är under 1 MB och får ligga längre.
BEHALL = 7
BEHALL_BETYG = 60


def _gallra(mapp: Path, monster: str, behall: int) -> None:
    """Behåll de `behall` senaste filerna som matchar. Namnen bär tidsstämpeln
    ÅÅÅÅMMDD-TTMM, så namnordning är tidsordning."""
    for gammal in sorted(mapp.glob(monster))[:-behall]:
        gammal.unlink(missing_ok=True)


def _ogonblicksbild(src: Path, dst: Path) -> bool:
    """Databasen går i WAL-läge: det som skrivits sedan senaste checkpoint
    ligger i transkribera.db-wal, inte i huvudfilen. Zippas huvudfilen rakt av
    saknas kvällens dikterade poäng i kopian. sqlite:s backup-API läser genom
    WAL:en och ger en hel bild även medan appen skriver. False = inte en
    sqlite-fil (testernas attrapp), då zippas filen som den är."""
    kalla = sqlite3.connect(str(src))
    mal = sqlite3.connect(str(dst))
    try:
        kalla.backup(mal)
        return True
    except sqlite3.DatabaseError:
        return False
    finally:
        mal.close()
        kalla.close()

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
    bild = base / ".backup-ogonblick.db"
    try:
        with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for name in BACKUP_FILES:
                src = base / name
                if src.exists() and src.is_file():
                    bild.unlink(missing_ok=True)
                    if name.endswith(".db") and _ogonblicksbild(src, bild):
                        zf.write(bild, arcname=name)
                    else:
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
    finally:
        bild.unlink(missing_ok=True)
    _gallra(out_dir, "transkribera-backup-*.zip", BEHALL)
    return {"path": str(dest), "files": included, "bytes": dest.stat().st_size,
            "plats": str(out_dir), "fallback": fallback}


def create_betygskopia(base: Path, dest_dir: Path | str, *,
                       now: datetime | None = None) -> dict:
    """Elevernas poäng som en liten JSON, till en ANNAN plats än kvällskopian.

    Hela databasen går till den externa disken (D:), som klarar en trasig
    E-disk men inte stöld eller brand. Poängen per uppgift och elev är det
    enda i appen som inte går att göra om (proven går att generera igen,
    elevernas svar gör det inte), och de är under 1 MB. Därför går de även
    till OneDrive (lärarens beslut 2026-09-24). Filen bär allt kursvyn
    behöver: klasslistan, varje rättat provs rader (nyckel, E/C/A-tak,
    förmåga) och elevernas värden per rad.

    Returns {path, bytes, plats, fallback, prov}."""
    from app import db, rattning

    base = Path(base)
    nu = now or datetime.now()
    out_dir, fallback = Path(str(dest_dir)).expanduser(), False
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        out_dir, fallback = base / "exports", True
        out_dir.mkdir(parents=True, exist_ok=True)
    conn = db.connect(base / "transkribera.db")
    try:
        klasser: dict[str, dict] = {}
        for r in conn.execute("SELECT * FROM rattning ORDER BY klass, datum, dokument_id"):
            d = db.get_dokument(conn, r["dokument_id"])
            papper = (d or {}).get("dokument") or {}
            k = klasser.setdefault(r["klass"] or "", {"prov": []})
            k["prov"].append({
                "dokument_id": r["dokument_id"], "exam_id": r["exam_id"],
                "titel": papper.get("titel"), "datum": papper.get("datum") or r["datum"],
                "kurs": r["kurs"], "moment": papper.get("moment"),
                "variant": papper.get("variant"), "granser": papper.get("granser"),
                # Grupprader (uppgiftens rubrik ovanför a/b) bär inga poäng.
                "rader": [{"nyckel": x["nyckel"], "peca": x.get("peca"),
                           "formaga": x.get("formaga"),
                           "kompensation": bool(x.get("kompensation"))}
                          for x in rattning.bygg(papper.get("uppgifter"),
                                                 papper.get("kompensation"))
                          if not x.get("grupp")],
                "resultat": {str(e): v for e, v in
                             db.get_elevresultat(conn, r["dokument_id"]).items()},
            })
        for klass, k in klasser.items():
            gid = db.get_or_create_group(conn, klass)
            k["elever"] = [{"id": e["id"], "namn": e["namn"], "aktiv": e["aktiv"]}
                           for e in db.list_elever(conn, gid)]
    finally:
        conn.close()
    dest = out_dir / f"betygsunderlag-{nu.strftime('%Y%m%d-%H%M')}.json"
    dest.write_text(json.dumps({"skapad": nu.isoformat(timespec="seconds"),
                                "klasser": klasser}, ensure_ascii=False, indent=1),
                    encoding="utf-8")
    _gallra(out_dir, "betygsunderlag-*.json", BEHALL_BETYG)
    return {"path": str(dest), "bytes": dest.stat().st_size, "plats": str(out_dir),
            "fallback": fallback,
            "prov": sum(len(k["prov"]) for k in klasser.values())}


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
