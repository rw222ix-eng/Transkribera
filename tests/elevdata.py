"""Elevdata in i en testbas, samma väg som tools/elevresultat_diktera.py går.

Rättningsvyn och dess rutter (PUT /api/groups/{id}/elever, PUT
/api/dokument/{id}/elevresultat) togs bort 2026-10-07. Poängen skrivs nu bara
av diktatverktyget, rakt i databasen, och testerna som behöver en rättad klass
bygger den här i stället. Stegen är verktygets och den borttagna ruttens:
stada → elevresultat_till_rattning → sammanfatta → save_rattning +
save_elevresultat. Klassens rättning räknas ur elevraderna, aldrig tvärtom.

Filen ligger under tests/ men är ingen testfil.
"""
from __future__ import annotations

from pathlib import Path

from app import db, rattning


def _conn(bas):
    return db.connect(Path(bas) / "transkribera.db")


def spara_elever(bas, group_id: int, namn: list[str]) -> list[dict]:
    """Klasslistan för gruppen, som den sparas (db.save_elever)."""
    conn = _conn(bas)
    try:
        return db.save_elever(conn, group_id, list(namn))
    finally:
        conn.close()


def rader(bas, dokument_id: int) -> list[dict]:
    """Rättningens rader ur pappret: nyckel, nivåtak (peca) och CI per rad."""
    conn = _conn(bas)
    try:
        papper = (db.get_dokument(conn, dokument_id) or {}).get("dokument") or {}
    finally:
        conn.close()
    return rattning.bygg(papper.get("uppgifter"), papper.get("kompensation"))


def spara_elevresultat(bas, dokument_id: int, resultat: dict) -> dict | None:
    """Elevernas poäng och klassens rättning ur dem. Returnerar `rattat`
    (andel och svaga moment), eller None när ingen elev har några poäng."""
    conn = _conn(bas)
    try:
        papper = (db.get_dokument(conn, dokument_id) or {}).get("dokument") or {}
        r = rattning.bygg(papper.get("uppgifter"), papper.get("kompensation"))
        rent = rattning.stada(r, resultat)
        antal, varden = rattning.elevresultat_till_rattning(rent)
        if not antal:
            return None
        res = rattning.sammanfatta(papper.get("uppgifter"), varden, antal,
                                   rattning.rader_per_nyckel(rent),
                                   kompensation=papper.get("kompensation"))
        db.save_rattning(conn, dokument_id, elever=res["elever"],
                         andel=res["rattat"]["andel"], rader=res["rader"],
                         exam_id=papper.get("provId"), klass=papper.get("klass"),
                         kurs=papper.get("kurs"), datum=papper.get("datum"))
        db.save_elevresultat(conn, dokument_id, rent)
        return res["rattat"]
    finally:
        conn.close()
