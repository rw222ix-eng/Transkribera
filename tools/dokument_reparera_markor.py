"""Reparera basen efter «Fortsätt ändra»-buggen: markören som hoppade bakåt,
dubbletten som godkännandet lade bredvid, och exams-raden som blev kvar som
utkast fast pappret är godkänt.

Bakgrunden (2026-09-13): plan.js fortsattAndra skickade `markor: 0` på ett
godkänt prov. `GET /api/dokument` returnerar den version markören står på, så
prov 44 «Kapitel 1» visades utan lärarens fem egna bilder — de ligger i v3–v7,
markören stod på v0. Samma sekund skapade omgodkännandet en ny rad (130) i
stället för att byta status på 86, och /oppna hade redan satt exams.status till
'utkast'.

Verktyget lagar bara det som är trasigt, aldrig mer:

  1. MARKÖREN flyttas till sista versionen — men bara när sista versionen bär
     bildnycklar som markörens version SAKNAR. Den vidare regeln «markören står
     före sista versionen och en senare version bär bilder» träffar tolv papper
     till i den här basen, och alla tolv visar redan alla sina bilder: att
     flytta deras markör hade bytt ut innehållet läraren ser, utan att laga
     något. Bildförlusten är symtomet, och det är symtomet vi lagar.
  2. DUBBLETTEN raderas bara när den är bevisligen tom: ett godkänt dokument
     med samma provId som ett annat godkänt dokument, EN enda version, `bilder`
     tomt, och `uppgifter` byte-identiska med originalets v0. Ett papper med
     egna bilder eller egna uppgifter är lärarens arbete och rörs aldrig.
  3. EXAMS.STATUS stämplas om till 'godkänt' med samma db-funktion som
     approve använder (set_exam_artifacts(approve=True)) — bara när dokumentet
     är godkänt OCH pdf:en faktiskt ligger på disk. Ingen fil, ingen stämpel.

Förval är --dry-run: ingenting skrivs, allt som SKULLE göras skrivs ut, rad för
rad och id för id. --verkstall skriver, och tar först en säkerhetskopia.

Användning:
    python -m tools.dokument_reparera_markor              # dry-run
    python -m tools.dokument_reparera_markor --verkstall
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import db  # noqa: E402

DB = Path(__file__).resolve().parents[1] / "transkribera.db"

# Statussträngarna skiljer sig mellan tabellerna och det är inget skrivfel:
# dokument-raden bär 'godkant' (den kommer från frontendens plan.js), exams-raden
# bär 'godkänt' (den sätts av set_exam_artifacts). Skriver man fel av dem
# matchar ingenting och verktyget säger glatt «inget att göra».
DOK_GODKANT = "godkant"
EXAM_GODKANT = "godkänt"


# ── läsning ─────────────────────────────────────────────────────────────────

def _versioner(conn: sqlite3.Connection, dokument_id: int) -> list[sqlite3.Row]:
    """Versionernas bildnycklar och provId — utan att läsa bloberna.

    Ett papper med egna bilder är 17 MB per version. json_each låter sqlite
    plocka ut nycklarna utan att python bygger en dict av tre megabyte base64
    per bild, och hela genomsökningen tar under två sekunder på 345 versioner.
    """
    return conn.execute(
        "SELECT v.version, "
        "  (SELECT group_concat(j.key) FROM json_each(v.data, '$.bilder') j) AS nycklar, "
        "  json_extract(v.data, '$.provId') AS provid "
        "FROM dokument_versioner v WHERE v.dokument_id = ? ORDER BY v.version",
        (dokument_id,)).fetchall()


def _nycklar(rad: sqlite3.Row) -> set[str]:
    return set((rad["nycklar"] or "").split(",")) - {""}


def _godkanda(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT id, markor FROM dokument WHERE status = ? ORDER BY id",
        (DOK_GODKANT,)).fetchall()


def hitta_markorfel(conn: sqlite3.Connection) -> list[dict]:
    """Godkända papper där markörens version saknar bilder som sista versionen
    bär. Det är precis den skada `markor: 0` gjorde."""
    ut = []
    for rad in _godkanda(conn):
        vs = _versioner(conn, rad["id"])
        if len(vs) < 2:
            continue
        m = max(0, min(int(rad["markor"] or 0), len(vs) - 1))
        if m == len(vs) - 1:
            continue
        saknas = _nycklar(vs[-1]) - _nycklar(vs[m])
        if not saknas:
            continue
        ut.append({"id": rad["id"], "markor": m, "sista": len(vs) - 1,
                   "provid": vs[-1]["provid"], "saknade_bilder": sorted(saknas),
                   "bilder_efter": sorted(_nycklar(vs[-1]))})
    return ut


def _uppgifter(conn: sqlite3.Connection, dokument_id: int, version: int):
    rad = conn.execute(
        "SELECT json_extract(data, '$.uppgifter') AS u FROM dokument_versioner "
        "WHERE dokument_id = ? AND version = ?", (dokument_id, version)).fetchone()
    return json.loads(rad["u"]) if rad and rad["u"] else None


def hitta_dubbletter(conn: sqlite3.Connection) -> list[dict]:
    """Tomma kopior som ett omgodkännande lade bredvid originalet.

    Fyra villkor måste hålla samtidigt, och det är avsiktligt strängt: en enda
    version (inget arbete att förlora), tom `bilder` (inga egna bilder att
    förlora), samma provId som ett annat GODKÄNT papper med FLER versioner
    (originalet finns kvar), och identiska `uppgifter` som originalets v0
    (samma papper, inte ett omtag). Nio provId i den här basen bär flera
    godkända dokument; åtta av dem har egna bilder i kopian och rörs inte."""
    per: dict[int, list[dict]] = {}
    for rad in _godkanda(conn):
        vs = _versioner(conn, rad["id"])
        if not vs:
            continue
        pid = vs[0]["provid"]
        if pid is None:
            continue
        per.setdefault(int(pid), []).append(
            {"id": rad["id"], "antal": len(vs), "bilder": _nycklar(vs[0])})
    ut = []
    for pid, rader in sorted(per.items()):
        if len(rader) < 2:
            continue
        original = max(rader, key=lambda r: (r["antal"], r["id"]))
        for r in rader:
            if r is original or r["antal"] != 1 or r["bilder"]:
                continue
            if original["antal"] < 2:
                continue
            if _uppgifter(conn, r["id"], 0) != _uppgifter(conn, original["id"], 0):
                continue
            ut.append({"id": r["id"], "provid": pid, "original": original["id"],
                       "original_versioner": original["antal"]})
    return ut


def hitta_examstatus(conn: sqlite3.Connection) -> list[dict]:
    """Prov vars dokument är godkänt och vars pdf ligger på disk, men vars
    exams-rad står kvar som utkast (/oppna stämplade om den och godkännandet
    hittade aldrig tillbaka). Utan pdf på disk görs ingenting: en godkänd rad
    utan fil är precis det routes_exam vägrar skriva."""
    provid = {}
    for rad in _godkanda(conn):
        vs = _versioner(conn, rad["id"])
        if vs and vs[0]["provid"] is not None:
            provid.setdefault(int(vs[0]["provid"]), []).append(rad["id"])
    ut = []
    for pid, dokument in sorted(provid.items()):
        ex = conn.execute("SELECT status FROM exams WHERE id = ?", (pid,)).fetchone()
        if ex is None or ex["status"] == EXAM_GODKANT:
            continue
        pdf = conn.execute(
            "SELECT id, pdf_path FROM exam_versions WHERE exam_id = ? "
            "AND pdf_path IS NOT NULL ORDER BY version DESC", (pid,)).fetchall()
        traff = next((p for p in pdf if os.path.exists(p["pdf_path"])), None)
        if traff is None:
            continue
        ut.append({"provid": pid, "status": ex["status"], "dokument": dokument,
                   "version_id": traff["id"], "pdf": traff["pdf_path"]})
    return ut


# ── skrivning ───────────────────────────────────────────────────────────────

def sakerhetskopiera(db_path: Path, *, nu: datetime | None = None) -> Path:
    """En kopia av hela basen innan något skrivs.

    app/backup.py:s create_backup är lärarens egen kvällskopia: en zip med
    db + history.json + settings.json under exports/, tidsstämplad till
    MINUTEN. Den passar inte här — två körningar samma minut skriver över
    varandras kopia, och det som behövs före en reparation är en fil man kan
    byta rakt in, inte ett arkiv att packa upp. Därför en ren .db med sekunder
    i namnet, skriven med sqlites egen backup-API så WAL:en kommer med."""
    mal_dir = db_path.parent / "Transkriberingar" / "backup"
    mal_dir.mkdir(parents=True, exist_ok=True)
    stamp = (nu or datetime.now()).strftime("%Y%m%d-%H%M%S")
    mal = mal_dir / f"transkribera-{stamp}.db"
    kalla = sqlite3.connect(str(db_path))
    kopia = sqlite3.connect(str(mal))
    try:
        kalla.backup(kopia)
    finally:
        kopia.close()
        kalla.close()
    return mal


def reparera(conn: sqlite3.Connection, fynd: dict) -> list[str]:
    """Verkställ fynden. Ordningen spelar roll: markören först (då syns
    bilderna även om något senare steg faller), dubbletten sedan, exams sist."""
    gjort = []
    for f in fynd["markor"]:
        db.update_dokument(conn, f["id"], markor=f["sista"])
        gjort.append(f"dokument {f['id']}: markör {f['markor']} → {f['sista']}")
    for f in fynd["dubbletter"]:
        db.delete_dokument(conn, f["id"])
        gjort.append(f"dokument {f['id']} raderat (dubblett av {f['original']})")
    for f in fynd["exams"]:
        db.set_exam_artifacts(conn, f["provid"], version_id=f["version_id"],
                              approve=True)
        gjort.append(f"exams {f['provid']}: {f['status']} → {EXAM_GODKANT}")
    return gjort


# ── utskrift ────────────────────────────────────────────────────────────────

def samla(conn: sqlite3.Connection) -> dict:
    return {"markor": hitta_markorfel(conn),
            "dubbletter": hitta_dubbletter(conn),
            "exams": hitta_examstatus(conn)}


def skriv_ut(fynd: dict) -> None:
    print("MARKÖR — godkänt papper vars markör står på en version utan bilderna")
    for f in fynd["markor"] or []:
        print(f"  dokument {f['id']} (prov {f['provid']}): markör {f['markor']} "
              f"→ {f['sista']}; saknade bilder {', '.join(f['saknade_bilder'])} "
              f"(efteråt: {', '.join(f['bilder_efter'])})")
    if not fynd["markor"]:
        print("  (inget)")
    print("DUBBLETT — tom kopia av ett godkänt papper, RADERAS med --verkstall")
    for f in fynd["dubbletter"] or []:
        print(f"  dokument {f['id']} (prov {f['provid']}): 1 version, bilder {{}}, "
              f"uppgifter identiska med dokument {f['original']} v0 "
              f"({f['original_versioner']} versioner)")
    if not fynd["dubbletter"]:
        print("  (inget)")
    print("EXAMS — dokumentet godkänt och pdf:en på disk, men provraden är utkast")
    for f in fynd["exams"] or []:
        print(f"  exams {f['provid']}: {f['status']} → {EXAM_GODKANT} "
              f"(dokument {', '.join(str(i) for i in f['dokument'])}; {f['pdf']})")
    if not fynd["exams"]:
        print("  (inget)")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", type=Path, default=DB)
    p.add_argument("--dry-run", action="store_true", default=True)
    p.add_argument("--verkstall", action="store_true",
                   help="skriv ändringarna (annars visas de bara)")
    a = p.parse_args(argv)
    conn = db.connect(a.db)
    try:
        fynd = samla(conn)
        skriv_ut(fynd)
        antal = sum(len(v) for v in fynd.values())
        if not a.verkstall:
            print(f"\nDRY-RUN — {antal} ändringar. Kör med --verkstall för att skriva.")
            return 0
        if not antal:
            print("\nInget att göra.")
            return 0
        kopia = sakerhetskopiera(Path(a.db))
        print(f"\nSäkerhetskopia: {kopia}")
        for rad in reparera(conn, fynd):
            print("  ", rad)
        kvar = samla(conn)
        print(f"Kvar efter reparation: {sum(len(v) for v in kvar.values())}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
