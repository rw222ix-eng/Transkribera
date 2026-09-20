"""Spårexporten: de senaste 30 dagarnas spar-rader till spardata/spar.jsonl.

Bron mellan lärarens maskin och söndagsrutinen i molnet. Molnagenten klonar
repot från GitHub och kan inte nå transkribera.db — men SPÅRET (app/spar.py)
får resa dit: det bär lärarens egna ändringsmeningar och API-anrop, ingen
elevdata. Resten av databasen (elever, betyg, rättningar) stannar lokalt,
och det är hela skillnaden mellan den här filen och att pusha databasen.

Rullande 30 dagar och deterministisk ordning: samma innehåll ger samma bytes,
så dagar utan ny användning ger ingen ny commit. Äldre veckor finns kvar i
git-historiken om någon vill se längre tillbaka.

Stämpeln spardata/exporterad.txt skrivs BARA när raderna ändrats, så att
arbetsträdet är rent mellan körningarna. Den finns för att molnrutinen ska
kunna säga «exporten är N dagar gammal» i stället för att gissa: söndagen
2026-09-20 kördes rutinen för hand före veckans export och analyserade en
vecka gammal fil som om appen stått oanvänd. Därför går exporten numera
dagligen (spar_export.ps1), och stämpeln säger när den senast bar ny data.

Körs av tools/spar_export.ps1 (schemalagd dagligen 05:00) eller för hand:
    python -m tools.spar_export
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

from app import db

ROT = Path(__file__).resolve().parent.parent
UTFIL = ROT / "spardata" / "spar.jsonl"
STAMPEL = ROT / "spardata" / "exporterad.txt"


def exportera(db_file: Path = ROT / "transkribera.db",
              utfil: Path = UTFIL, dagar: int = 30) -> int:
    sedan = (datetime.now() - timedelta(days=dagar)).isoformat(timespec="seconds")
    conn = db.connect(db_file)
    try:
        rader = conn.execute(
            "SELECT tid, art, vag, doktyp, dok_id, detalj FROM spar "
            "WHERE tid >= ? ORDER BY id", (sedan,)).fetchall()
    finally:
        conn.close()
    utfil.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(
        {"tid": tid, "art": art, "vag": vag, "doktyp": doktyp,
         "dok_id": dok_id, "detalj": json.loads(detalj) if detalj else None},
        ensure_ascii=False) + "\n" for tid, art, vag, doktyp, dok_id, detalj in rader)
    gammal = utfil.read_text(encoding="utf-8") if utfil.exists() else None
    if text != gammal:
        utfil.write_text(text, encoding="utf-8", newline="\n")
        (utfil.parent / STAMPEL.name).write_text(
            f"exporterad: {datetime.now().isoformat(timespec='seconds')}\n"
            f"rader: {len(rader)}\n"
            f"forsta_rad: {rader[0][0] if rader else '-'}\n"
            f"sista_rad: {rader[-1][0] if rader else '-'}\n"
            f"fonster_dagar: {dagar}\n"
            "schema: dagligen 05:00 lokal tid (tools/spar_export.ps1); "
            "ingen ny stämpel = inga nya rader den dagen\n",
            encoding="utf-8", newline="\n")
    return len(rader)


if __name__ == "__main__":
    n = exportera()
    print(f"{n} rader -> {UTFIL}")
    sys.exit(0)
