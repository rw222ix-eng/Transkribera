"""Spårexporten: de senaste 30 dagarnas spar-rader till spardata/spar.jsonl.

Bron mellan lärarens maskin och söndagsrutinen i molnet. Molnagenten klonar
repot från GitHub och kan inte nå transkribera.db — men SPÅRET (app/spar.py)
får resa dit: det bär lärarens egna ändringsmeningar och API-anrop, ingen
elevdata. Resten av databasen (elever, betyg, rättningar) stannar lokalt,
och det är hela skillnaden mellan den här filen och att pusha databasen.

Rullande 30 dagar och deterministisk ordning: samma innehåll ger samma bytes,
så söndagar utan ny användning ger ingen ny commit. Äldre veckor finns kvar i
git-historiken om någon vill se längre tillbaka.

Körs av tools/spar_export.ps1 (schemalagd söndagar) eller för hand:
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
    with open(utfil, "w", encoding="utf-8", newline="\n") as f:
        for tid, art, vag, doktyp, dok_id, detalj in rader:
            f.write(json.dumps(
                {"tid": tid, "art": art, "vag": vag, "doktyp": doktyp,
                 "dok_id": dok_id, "detalj": json.loads(detalj) if detalj else None},
                ensure_ascii=False) + "\n")
    return len(rader)


if __name__ == "__main__":
    n = exportera()
    print(f"{n} rader -> {UTFIL}")
    sys.exit(0)
