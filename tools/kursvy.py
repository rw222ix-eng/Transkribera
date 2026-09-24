"""Kursvyn — elevens poäng PER NIVÅ över alla kursens prov, som betygsunderlag.

Lärarens modell (2026-09-20): kapitelproven ger F/E/C/A på totalpoängen, men
slutbetyget räknas inte som ett snitt av bokstäverna. Det räknas på summan av
E-, C- och A-poäng över kursens alla prov (totalen och varje nivås andel) och
på hur A-poängen är spridda över förmågorna (B/P/PL/M/R/K), se SLUTKRAV. Den
här skriver just det underlaget: en rad per elev, en kolumngrupp per prov, och
sist kursens summor, andelar, poäng per förmåga och ett preliminärt slutbetyg.

Källan är elevresultat (rättningsvyn eller tools/elevresultat_diktera.py),
raderna byggs ur pappret precis som routes_elever (inkl. kompensationsraden K,
som räknas i nivåsumman men inte i förmågorna — den säger inget om eleven).

    python -m tools.kursvy TE26A                 # tabell i terminalen
    python -m tools.kursvy TE26A --csv ut.csv    # för Google-arket

OMPROV: ett omprov är ett eget papper (TE26A:s omprov på kapitel 1 är exam
132, originalet exam 81) men samma moment i kursen. Pappren grupperas därför
på `moment` (avsnitten provet täcker), och varje elev räknas på ETT papper per
moment: det hen skrev, eller det bästa (högst total, vid lika det senaste) om
hen skrev båda. Maxpoängen följer pappret eleven skrev, så andelarna räknas
mot elevens egen max. Annars hade omprovet dubblerat kapitlets max för hela
klassen.
"""
from __future__ import annotations

import argparse
import csv
import math
import sys
from fractions import Fraction
from pathlib import Path

ROT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROT))

from app import db, rattning  # noqa: E402
from app.exam_spec import KRAV_DEFAULT  # noqa: E402

NIVA = ("E", "C", "A")

# SLUTBETYGET, PRELIMINÄRT (lärarens beslut 2026-09-24: en gräns nu, justeras
# när det finns fler prov). TOTALEN FÖRST: andelen av kursens alla poäng mot
# NP:s fem gränser (26/40/53/67/81 %, samma tal som proven). Sedan nivåkravet:
# D och C kräver en tredjedel resp. hälften av C-poängen, B och A en tredjedel
# resp. hälften av A-poängen spridda över minst två förmågor. Varje betyg
# kräver det förra. En elev med C på varje kapitelprov och en tredjedel av
# A-poängen får alltså B. E har inget nivåkrav: riktvärdet «2/3 av E-poängen»
# gav F åt sju TE26A-elever som fått E på provet, och läraren valde bort det.
# Senare prov väger inte tyngre (ännu): alla poäng räknas lika.
SLUTKRAV = (("E", KRAV_DEFAULT["e_andel"], None, None),
            ("D", KRAV_DEFAULT["d_andel"], 1, Fraction(1, 3)),
            ("C", KRAV_DEFAULT["c_andel"], 1, Fraction(1, 2)),
            ("B", KRAV_DEFAULT["b_andel"], 2, Fraction(1, 3)),
            ("A", KRAV_DEFAULT["a_andel"], 2, Fraction(1, 2)))
FORMAGOR_B_A = 2


def slutbetyg(summa: list[int], maxt: list[int], formagor_a: dict[str, int]) -> tuple[str, str]:
    """(förslag F/E/D/C/B/A, vad som fattas till nästa). Kraven är ≥ på exakta
    bråk, som provets gränser. En nivå utan maxpoäng kan inte uppfyllas."""
    def kvar(har: int, mx: int, andel: Fraction) -> int:
        return max(0, math.ceil(andel * mx) - har) if mx else -1

    spridda = sum(1 for n in formagor_a.values() if n > 0)
    betyg = "F"
    for bokstav, total_andel, niva, andel in SLUTKRAV:
        brist = []
        k = kvar(sum(summa), sum(maxt), total_andel)
        if k:
            brist.append(f"{k} poäng totalt" if k > 0 else "inga poäng att ta")
        k = kvar(summa[niva], maxt[niva], andel) if niva else 0
        if k:
            brist.append(f"{k} {NIVA[niva]}-poäng" if k > 0 else f"inga {NIVA[niva]}-poäng att ta")
        if niva == 2 and spridda < FORMAGOR_B_A:
            n = FORMAGOR_B_A - spridda
            brist.append(f"A-poäng i {n} {'förmåga' if n == 1 else 'förmågor'} till")
        if brist:
            return betyg, f"{bokstav}: " + ", ".join(brist)
        betyg = bokstav
    return betyg, ""


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
            "moment": str(papper.get("moment") or "").strip() or f"dokument {r['dokument_id']}",
            "omprov": str(papper.get("variant") or "").lower() == "omprov",
        })
    return ut


def maxtripel(rader: list[dict]) -> list[int]:
    """Provets max per nivå. Kompensationsraden är en bonus UTÖVER provet
    (TE26A prov 1: 27 p plus 1 till alla), precis som i provets gränser, så
    den räknas i elevens summa men inte i maxen."""
    t = [0, 0, 0]
    for r in rader:
        if r.get("grupp") or r.get("kompensation"):
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
    moment: dict[str, list[int]] = {}
    for i, p in enumerate(prov):
        p["max"] = maxtripel(p["rader"])
        moment.setdefault(p["moment"], []).append(i)
    # Momentets max för den som inte skrivit något: originalets, inte omprovets.
    std = {m: prov[next((i for i in ix if not prov[i]["omprov"]), ix[0])]["max"]
           for m, ix in moment.items()}
    kursmax = [sum(t[n] for t in std.values()) for n in range(3)]
    rader_ut = []
    for e in elever:
        rad = {"elev": e["namn"], "aktiv": e["aktiv"], "prov": [], "summa": [0, 0, 0],
               "max": [0, 0, 0], "formagor": {"C": {}, "A": {}}, "skrivna": 0}
        for p in prov:
            varden = p["resultat"].get(e["id"])
            if not varden:
                rad["prov"].append(None)
                continue
            s = rattning.elevsummor(p["rader"], varden)
            b = rattning.betyg(s, p["granser"]) if not s["kvar"] else "?"
            rad["prov"].append({"e": s["e"], "c": s["c"], "a": s["a"], "total": s["total"],
                                "betyg": b, "kvar": s["kvar"], "raknas": False})
        for m, ix in moment.items():
            gjorda = [i for i in ix if rad["prov"][i]]
            if not gjorda:
                rad["max"] = [a + b for a, b in zip(rad["max"], std[m])]
                continue
            # Bästa pappret: högst total, vid lika det senaste (prov står i datumordning).
            i = max(gjorda, key=lambda j: (rad["prov"][j]["total"], j))
            res, p = rad["prov"][i], prov[i]
            res["raknas"] = True
            rad["summa"] = [rad["summa"][0] + res["e"], rad["summa"][1] + res["c"],
                            rad["summa"][2] + res["a"]]
            rad["max"] = [a + b for a, b in zip(rad["max"], p["max"])]
            rad["skrivna"] += 1
            for niva, n in (("C", 1), ("A", 2)):
                for f, x in formagor(p["rader"], p["resultat"][e["id"]], n).items():
                    rad["formagor"][niva][f] = rad["formagor"][niva].get(f, 0) + x
        rad["forslag"], rad["nasta"] = (slutbetyg(rad["summa"], rad["max"],
                                                  rad["formagor"]["A"])
                                        if rad["skrivna"] else ("–", ""))
        rader_ut.append(rad)
    return {"klass": klass, "prov": prov, "moment": moment, "kursmax": kursmax,
            "elever": rader_ut}


def andel(x: int, m: int) -> str:
    return f"{100 * x / m:.0f} %" if m else "–"


def till_rader(vy: dict) -> list[list]:
    """Tabellen som Google-arket får: rubrikrad + en rad per elev. Kursens
    poäng skrivs «7 av 9», eftersom maxen följer pappret eleven skrev (Sheets
    hade läst «7/9» som ett datum)."""
    rub = ["Elev"]
    for p in vy["prov"]:
        k = f"{p['titel']} ({p['datum']})"
        rub += [f"{k} E/{p['max'][0]}", f"{k} C/{p['max'][1]}",
                f"{k} A/{p['max'][2]}", f"{k} tot", f"{k} betyg"]
    rub += ["Kurs E", "E-andel", "Kurs C", "C-andel", "Kurs A", "A-andel",
            "C per förmåga", "A per förmåga", "Skrivna prov",
            "Slutbetyg (preliminärt)", "Till nästa betyg"]
    ut = [rub]
    for e in vy["elever"]:
        if not e["aktiv"] and not e["skrivna"]:
            continue
        rad = [e["elev"]]
        for i, p in enumerate(e["prov"]):
            if p is None:
                annat = any(e["prov"][j] for j in vy["moment"][vy["prov"][i]["moment"]])
                rad += ["", "", "", "", "" if annat else "skrev inte"]
            else:
                rad += [p["e"], p["c"], p["a"], p["total"],
                        p["betyg"] if p["raknas"] else f"{p['betyg']} (räknas ej)"]
        s, m = e["summa"], e["max"]
        fm = lambda d: ", ".join(f"{f} {n}" for f, n in sorted(d.items(), key=lambda kv: -kv[1])) or "–"
        rad += [f"{s[0]} av {m[0]}", andel(s[0], m[0]), f"{s[1]} av {m[1]}", andel(s[1], m[1]),
                f"{s[2]} av {m[2]}", andel(s[2], m[2]), fm(e["formagor"]["C"]),
                fm(e["formagor"]["A"]), f"{e['skrivna']}/{len(vy['moment'])}",
                e["forslag"], e["nasta"]]
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
    print(f"{vy['klass']}: {len(vy['prov'])} prov i {len(vy['moment'])} moment, "
          f"kursmax E/C/A {vy['kursmax']}")
    for p in vy["prov"]:
        print(f"  {p['datum']} {p['titel']}{' (omprov)' if p['omprov'] else ''} "
              f"(dokument {p['id']}) max {p['max']}")
    visas = [e for e in vy["elever"] if e["aktiv"] or e["skrivna"]]
    bredd = max((len(e["elev"]) for e in visas), default=4)
    for e in visas:
        s, m = e["summa"], e["max"]
        print(f"  {e['elev']:{bredd}}  E {s[0]:3} {andel(s[0], m[0]):>5}  "
              f"C {s[1]:3} {andel(s[1], m[1]):>5}  A {s[2]:3} {andel(s[2], m[2]):>5}  "
              f"{e['forslag']:1}  {e['nasta']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
