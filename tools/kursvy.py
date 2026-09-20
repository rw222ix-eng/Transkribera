"""Kursvyn — elevens poäng PER NIVÅ över alla kursens prov, som betygsunderlag.

Lärarens modell (2026-09-20): kapitelproven ger F/E/C/A på totalpoängen, men
slutbetyget räknas inte som ett snitt av bokstäverna. Det räknas på summan av
E-, C- och A-poäng över kursens alla prov, som andel av varje nivås maxpoäng,
och på hur A-poängen är spridda över förmågorna (B/P/PL/M/R/K). Den här
skriver just det underlaget: en rad per elev, en kolumngrupp per prov, och
sist kursens summor, andelar och A-poäng per förmåga.

Källan är elevresultat (rättningsvyn eller tools/elevresultat_diktera.py),
raderna byggs ur pappret precis som routes_elever (inkl. kompensationsraden K,
som räknas i nivåsumman men inte i förmågorna — den säger inget om eleven).

    python -m tools.kursvy TE26A                 # tabell i terminalen
    python -m tools.kursvy TE26A --csv ut.csv    # för Google-arket
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROT))

from app import db, rattning  # noqa: E402

NIVA = ("E", "C", "A")


def prov_for_klass(conn, klass: str) -> list[dict]:
    """Rättade prov för klassen, äldst först: (dokument_id, papper, rader, gränser)."""
    ut = []
    for r in conn.execute(
            "SELECT dokument_id, datum FROM rattning WHERE klass = ? "
            "ORDER BY datum, dokument_id", (klass,)):
        d = db.get_dokument(conn, r["dokument_id"])
        if d is None:
            continue
        papper = d.get("dokument") or {}
        if str(papper.get("typ") or "").lower() != "prov":
            continue
        rader = rattning.bygg(papper.get("uppgifter"), papper.get("kompensation"))
        ut.append({
            "id": r["dokument_id"], "papper": papper, "rader": rader,
            "granser": rattning.granser(rader, sparade=papper.get("granser"),
                                        kurs=papper.get("kurs") or ""),
            "resultat": db.get_elevresultat(conn, r["dokument_id"]),
            "titel": papper.get("titel") or f"dokument {r['dokument_id']}",
            "datum": papper.get("datum") or r["datum"] or "",
        })
    return ut


def maxtripel(rader: list[dict]) -> list[int]:
    t = [0, 0, 0]
    for r in rader:
        if r.get("grupp"):
            continue
        for i, x in enumerate(r.get("peca") or [0, 0, 0]):
            t[i] += int(x or 0)
    return t


def formagor(rader: list[dict], varden: dict | None, niva: int) -> dict[str, int]:
    """Elevens poäng på EN nivå fördelade per förmåga (kompensationsraden
    utelämnad: den är ingen förmåga)."""
    ut: dict[str, int] = {}
    for r in rader:
        if r.get("grupp") or r.get("kompensation"):
            continue
        trip = rattning._elevtripel((varden or {}).get(r["nyckel"]),
                                    r.get("peca") or [0, 0, 0])
        if trip[niva]:
            f = str(r.get("formaga") or "?")
            ut[f] = ut.get(f, 0) + int(trip[niva])
    return ut


def bygg_vy(conn, klass: str) -> dict:
    gid = db.get_or_create_group(conn, klass)
    elever = db.list_elever(conn, gid)
    prov = prov_for_klass(conn, klass)
    kursmax = [0, 0, 0]
    for p in prov:
        p["max"] = maxtripel(p["rader"])
        kursmax = [a + b for a, b in zip(kursmax, p["max"])]
    rader_ut = []
    for e in elever:
        rad = {"elev": e["namn"], "aktiv": e["aktiv"], "prov": [], "summa": [0, 0, 0],
               "formagor": {"C": {}, "A": {}}, "skrivna": 0}
        for p in prov:
            varden = p["resultat"].get(e["id"])
            if not varden:
                rad["prov"].append(None)
                continue
            s = rattning.elevsummor(p["rader"], varden)
            b = rattning.betyg(s, p["granser"]) if not s["kvar"] else "?"
            rad["prov"].append({"e": s["e"], "c": s["c"], "a": s["a"],
                                "total": s["total"], "betyg": b, "kvar": s["kvar"]})
            rad["summa"] = [rad["summa"][0] + s["e"], rad["summa"][1] + s["c"],
                            rad["summa"][2] + s["a"]]
            rad["skrivna"] += 1
            for niva, i in (("C", 1), ("A", 2)):
                for f, n in formagor(p["rader"], varden, i).items():
                    rad["formagor"][niva][f] = rad["formagor"][niva].get(f, 0) + n
        rader_ut.append(rad)
    return {"klass": klass, "prov": prov, "kursmax": kursmax, "elever": rader_ut}


def andel(x: int, m: int) -> str:
    return f"{100 * x / m:.0f} %" if m else "–"


def till_rader(vy: dict) -> list[list]:
    """Tabellen som Google-arket får: rubrikrad + en rad per elev."""
    rub = ["Elev"]
    for p in vy["prov"]:
        k = f"{p['titel']} ({p['datum']})"
        rub += [f"{k} E/{p['max'][0]}", f"{k} C/{p['max'][1]}",
                f"{k} A/{p['max'][2]}", f"{k} tot", f"{k} betyg"]
    km = vy["kursmax"]
    rub += [f"Kurs E/{km[0]}", "E-andel", f"Kurs C/{km[1]}", "C-andel",
            f"Kurs A/{km[2]}", "A-andel", "C per förmåga", "A per förmåga", "Skrivna prov"]
    ut = [rub]
    for e in vy["elever"]:
        if not e["aktiv"] and not e["skrivna"]:
            continue
        rad = [e["elev"]]
        for p in e["prov"]:
            rad += ["", "", "", "", "skrev inte"] if p is None else [
                p["e"], p["c"], p["a"], p["total"], p["betyg"]]
        s = e["summa"]
        fm = lambda d: ", ".join(f"{f} {n}" for f, n in sorted(d.items(), key=lambda kv: -kv[1])) or "–"
        rad += [s[0], andel(s[0], km[0]), s[1], andel(s[1], km[1]),
                s[2], andel(s[2], km[2]), fm(e["formagor"]["C"]), fm(e["formagor"]["A"]),
                f"{e['skrivna']}/{len(vy['prov'])}"]
        ut.append(rad)
    return ut


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("klass")
    ap.add_argument("--db", type=Path, default=ROT / "transkribera.db")
    ap.add_argument("--csv", type=Path, help="skriv tabellen som CSV (UTF-8)")
    a = ap.parse_args(argv)
    conn = db.connect(str(a.db))
    try:
        vy = bygg_vy(conn, a.klass)
    finally:
        conn.close()
    rader = till_rader(vy)
    if a.csv:
        with a.csv.open("w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows(rader)
        print(f"skrev {a.csv} ({len(rader) - 1} elever, {len(vy['prov'])} prov)")
        return 0
    print(f"{vy['klass']}: {len(vy['prov'])} prov, kursmax E/C/A {vy['kursmax']}")
    for p in vy["prov"]:
        print(f"  {p['datum']} {p['titel']} (dokument {p['id']}) max {p['max']}")
    bredd = max(len(r[0]) for r in rader)
    for r in rader[1:]:
        s = r[-9:]
        print(f"  {r[0]:{bredd}}  E {s[0]:3} {s[1]:>5}  C {s[2]:3} {s[3]:>5}  "
              f"A {s[4]:3} {s[5]:>5}  A: {s[7]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
