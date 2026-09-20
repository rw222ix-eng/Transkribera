"""Dikterade provresultat in i elevresultat — samma väg som rättningsvyn.

Läraren läser upp poängen per elev och deluppgift i chatten; den här skriver
in dem exakt som PUT /api/dokument/{id}/elevresultat (routes_elever.py) gör:
stada → elevresultat_till_rattning → sammanfatta → save_rattning +
save_elevresultat. Klassrättningen räknas ur elevraderna, aldrig tvärtom.

Textformatet, en elev per rad:

    Anna: 1 1, 2a 1, 2b 0, 3 1, 4 2, 5a 1, 5b 0 ...
    Bo 1 0 2a 1 ...            (kolon och komman är valfria)

Nyckeln är radens nyckel på pappret (1, 2a, 12b), poängen ett heltal. Varje
rad på pappret bär EN nivå (peca = [E,C,A] med en nolla-fri plats), så en
siffra räcker: den läggs på radens nivå. En rad som inte nämns lämnas tom
(None), inte noll — «ej rättad» och «0 poäng» är olika saker för betyget.

Elever som inte finns i klasslistan läggs till sist; ingen befintlig elev
inaktiveras (save_elever gör det, därför synkas unionen).

    python -m tools.elevresultat_diktera 131 resultat.txt --torr
    python -m tools.elevresultat_diktera 131 resultat.txt
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROT))

from app import db, rattning  # noqa: E402

_PAR = re.compile(r"(\d+[a-z]?)\s*[:=]?\s*(-?\d+(?:[.,]\d+)?)")


def tolka(text: str) -> dict[str, dict[str, float]]:
    """{namn: {nyckel: poäng}} ur den dikterade texten."""
    ut: dict[str, dict[str, float]] = {}
    for rad in text.splitlines():
        rad = rad.strip()
        if not rad or rad.startswith("#"):
            continue
        if ":" in rad:
            namn, rest = rad.split(":", 1)
        else:
            m = re.match(r"^(\D[^\d]*?)\s+(\d.*)$", rad)
            if not m:
                raise SystemExit(f"kan inte tolka raden: {rad!r}")
            namn, rest = m.group(1), m.group(2)
        namn = namn.strip()
        if not namn:
            raise SystemExit(f"rad utan namn: {rad!r}")
        par = {}
        for nyckel, varde in _PAR.findall(rest):
            if nyckel in par:
                raise SystemExit(f"{namn}: nyckel {nyckel} två gånger")
            par[nyckel] = float(varde.replace(",", "."))
        if not par:
            raise SystemExit(f"{namn}: inga poäng på raden")
        ut[namn] = par
    return ut


def till_tripel(rader: list[dict], per_nyckel: dict[str, float],
                namn: str) -> dict[str, list]:
    tak = {r["nyckel"]: list(r.get("peca") or [0, 0, 0])
           for r in rader if not r.get("grupp") and r.get("nyckel")}
    ut = {}
    for nyckel, p in per_nyckel.items():
        if nyckel not in tak:
            raise SystemExit(f"{namn}: nyckel {nyckel} finns inte på pappret "
                             f"(finns: {', '.join(tak)})")
        t = tak[nyckel]
        nivaer = [i for i in range(3) if t[i] > 0]
        if len(nivaer) != 1:
            raise SystemExit(f"{namn}: rad {nyckel} har tak {t}, ange nivån")
        i = nivaer[0]
        if not 0 <= p <= t[i]:
            raise SystemExit(f"{namn}: rad {nyckel} = {p}, tak {t[i]}")
        trip: list = [None, None, None]
        trip[i] = int(round(p))
        ut[nyckel] = trip
    return ut


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("dokument_id", type=int)
    ap.add_argument("fil", type=Path)
    ap.add_argument("--db", type=Path, default=ROT / "transkribera.db")
    ap.add_argument("--torr", action="store_true", help="räkna, skriv inget")
    a = ap.parse_args(argv)

    dikterat = tolka(a.fil.read_text(encoding="utf-8"))
    conn = db.connect(str(a.db))
    try:
        d = db.get_dokument(conn, a.dokument_id)
        if d is None:
            raise SystemExit(f"okänt dokument {a.dokument_id}")
        papper = d.get("dokument") or {}
        rader = rattning.bygg(papper.get("uppgifter"))
        gr = rattning.granser(rader, sparade=papper.get("granser"),
                              kurs=papper.get("kurs") or "")
        gid = db.get_or_create_group(conn, papper.get("klass") or "")
        print(f"dokument {a.dokument_id}: prov {papper.get('provId')} "
              f"«{papper.get('titel')}» {papper.get('klass')} "
              f"{papper.get('datum')} · gränser E/C/A "
              f"{gr.get('E', {}).get('minst')}/{gr.get('C', {}).get('minst')}/"
              f"{gr.get('A', {}).get('minst')} av {gr.get('total')}")

        befintliga = db.list_elever(conn, gid)
        namn_lista = [e["namn"] for e in befintliga if e["aktiv"]]
        nya = [n for n in dikterat if n.lower() not in
               {e["namn"].lower() for e in befintliga}]
        if nya and not a.torr:
            db.save_elever(conn, gid, namn_lista + nya)
        elever = {e["namn"].lower(): e["id"]
                  for e in (db.list_elever(conn, gid) if not a.torr
                            else befintliga)}
        for i, n in enumerate(nya):
            elever.setdefault(n.lower(), -(i + 1))  # torrkörning: låtsas-id

        resultat = {elever[n.lower()]: till_tripel(rader, per, n)
                    for n, per in dikterat.items()}
        rent = rattning.stada(rader, resultat)
        for n in dikterat:
            eid = elever[n.lower()]
            s = rattning.elevsummor(rader, rent.get(eid))
            b = rattning.betyg(s, gr) if not s["kvar"] else f"— ({s['kvar']} rader kvar)"
            print(f"  {n:20} E {s['e']:2}  C {s['c']:2}  A {s['a']:2}  "
                  f"tot {s['total']:2}/{s['tak']}  {b}")

        if a.torr:
            print("torrkörning, inget skrivet")
            return 0
        antal, varden = rattning.elevresultat_till_rattning(rent)
        res = rattning.sammanfatta(papper.get("uppgifter"), varden, antal,
                                   rattning.rader_per_nyckel(rent))
        db.save_rattning(conn, a.dokument_id, elever=res["elever"],
                         andel=res["rattat"]["andel"], rader=res["rader"],
                         exam_id=papper.get("provId"), klass=papper.get("klass"),
                         kurs=papper.get("kurs"), datum=papper.get("datum"))
        db.save_elevresultat(conn, a.dokument_id, rent)
        print(f"sparat: {antal} elever, nya i klasslistan: {len(nya)}, "
              f"klassens andel {res['rattat']['andel']}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
