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
    python -m tools.kursvy --alla --csv ut.csv   # samlingsarket, alla klasser

KLASSARKET bär per prov del A, del B, totalt och provbetyget med pil, och
elevens poäng på varje deluppgift (läraren vill se var poängen satt inför
betygssamtalet). SAMLINGSARKET («Provresultat alla klasser», läraren
2026-10-02) är en rad per elev och skrivet papper, alla klasser.

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
import re
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

# PILREGELN (läraren 2026-10-02): högst så här många poäng under nästa
# provbetygs gräns ger «C → A», annars bara bokstaven. Gäller även F
# («F → E»). Bara muntligt och i StudyBee, aldrig ett eget betyg.
PIL_POANG = 3


def pilbetyg(betyg: str, total: int, gr: dict) -> str:
    """Provbetyget med pil mot nästa, om eleven ligger högst PIL_POANG under
    dess gräns. Ordningen är gränsernas egen (`betyg`), annars E, C, A."""
    ordning = [b for b in (gr.get("betyg") or ["E", "C", "A"]) if gr.get(b)]
    if betyg == "F":
        hogre = ordning
    else:
        hogre = ordning[ordning.index(betyg) + 1:] if betyg in ordning else []
    if not hogre:
        return betyg
    nasta = hogre[0]
    kvar = int(gr[nasta].get("minst") or 0) - total
    return f"{betyg} → {nasta}" if 0 < kvar <= PIL_POANG else betyg


def delprov(papper: dict, rader: list[dict]) -> dict[str, str]:
    """Radnyckel → «A» eller «B». Provet trycker sina delar som avsnitt
    (`avd` B = utan räknare, C = med), läraren kallar dem del A och del B:
    första avsnittet är del A, nästa del B. Kompensationsraden hör till ingen
    del."""
    avd = {}
    for i, u in enumerate(papper.get("uppgifter") or []):
        if isinstance(u, dict):
            avd[str(u.get("nr") or i + 1)] = str(u.get("avd") or "")
    namn = {a: "AB"[min(j, 1)] for j, a in enumerate(dict.fromkeys(avd.values()))}
    ut = {}
    for r in rader:
        if r.get("grupp") or r.get("kompensation"):
            continue
        m = re.match(r"\d+", str(r["nyckel"]))
        ut[r["nyckel"]] = namn.get(avd.get(m.group(0) if m else ""), "A")
    return ut


def radnamn(r: dict) -> str:
    """«6b A2», «10 C1A1»: deluppgiften och dess poäng per nivå."""
    niv = "".join(f"{NIVA[i]}{n}" for i, n in enumerate(r.get("peca") or []) if n)
    return f"{r['nyckel']} {niv}".strip()


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
        delar = delprov(papper, rader)
        delmax = {"A": 0, "B": 0}
        for rad in rader:
            if rad.get("nyckel") in delar:
                delmax[delar[rad["nyckel"]]] += sum(int(x or 0) for x in rad.get("peca") or [])
        ut.append({
            "id": r["dokument_id"], "papper": papper, "rader": rader,
            "delar": delar, "delmax": delmax,
            "komp": any(rad.get("kompensation") for rad in rader),
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
            per_rad, dels, k = {}, {"A": 0, "B": 0}, 0
            for r in p["rader"]:
                if r.get("grupp"):
                    continue
                trip = rattning._elevtripel(varden.get(r["nyckel"]), r.get("peca") or [0, 0, 0])
                x = None if all(t is None for t in trip) else sum(t or 0 for t in trip)
                if r.get("kompensation"):
                    k = x or 0
                    continue
                per_rad[r["nyckel"]] = x
                dels[p["delar"][r["nyckel"]]] += x or 0
            rad["prov"].append({"e": s["e"], "c": s["c"], "a": s["a"], "total": s["total"],
                                "betyg": b, "kvar": s["kvar"], "raknas": False,
                                "pil": b if b == "?" else pilbetyg(b, s["total"], p["granser"]),
                                "del": dels, "k": k, "rader": per_rad})
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
    hade läst «7/9» och «1/1» som datum)."""
    rub = ["Elev"]
    for p in vy["prov"]:
        k = f"{p['titel']} ({p['datum']})"
        rub += [f"{k} del A /{p['delmax']['A']}", f"{k} del B /{p['delmax']['B']}"]
        rub += [f"{k} kompensation"] if p["komp"] else []
        rub += [f"{k} E/{p['max'][0]}", f"{k} C/{p['max'][1]}",
                f"{k} A/{p['max'][2]}", f"{k} totalt /{sum(p['max'])}", f"{k} betyg"]
        rub += [f"{k} uppg {radnamn(r)}" for r in p["rader"] if r.get("nyckel") in p["delar"]]
    rub += ["Kurs E", "E-andel", "Kurs C", "C-andel", "Kurs A", "A-andel",
            "C per förmåga", "A per förmåga", "Skrivna prov",
            "Slutbetyg (preliminärt)", "Till nästa betyg"]
    ut = [rub]
    for e in vy["elever"]:
        if not e["aktiv"] and not e["skrivna"]:
            continue
        rad = [e["elev"]]
        for i, p in enumerate(e["prov"]):
            prov = vy["prov"][i]
            nycklar = [r["nyckel"] for r in prov["rader"] if r.get("nyckel") in prov["delar"]]
            if p is None:
                annat = any(e["prov"][j] for j in vy["moment"][prov["moment"]])
                rad += ([""] * (6 + prov["komp"]) + ["" if annat else "skrev inte"]
                        + [""] * len(nycklar))
            else:
                rad += [p["del"]["A"], p["del"]["B"]]
                rad += [p["k"]] if prov["komp"] else []
                rad += [p["e"], p["c"], p["a"], p["total"],
                        p["pil"] if p["raknas"] else f"{p['pil']} (räknas ej)"]
                rad += ["" if p["rader"][n] is None else p["rader"][n] for n in nycklar]
        s, m = e["summa"], e["max"]
        fm = lambda d: ", ".join(f"{f} {n}" for f, n in sorted(d.items(), key=lambda kv: -kv[1])) or "–"
        rad += [f"{s[0]} av {m[0]}", andel(s[0], m[0]), f"{s[1]} av {m[1]}", andel(s[1], m[1]),
                f"{s[2]} av {m[2]}", andel(s[2], m[2]), fm(e["formagor"]["C"]),
                fm(e["formagor"]["A"]), f"{e['skrivna']} av {len(vy['moment'])}",
                e["forslag"], e["nasta"]]
        ut.append(rad)
    return ut


SAMLING_RUBRIK = ["Klass", "Elev", "Prov", "Datum", "Del A", "Del A max", "Del B",
                  "Del B max", "Kompensation", "Totalt", "Max", "Betyg",
                  "E-poäng", "C-poäng", "A-poäng"]


def samling(conn) -> list[list]:
    """Samlingsarket: en rad per elev och skrivet papper, klasserna i den
    ordning de skrev sitt första prov. Omprovet är en egen rad («(omprov)»),
    med elevens räknade papper oavsett om det är det bästa: arket visar vad
    som hände, kursvyn vad som räknas."""
    klasser = [r["klass"] for r in conn.execute(
        "SELECT klass, MIN(datum) AS d FROM rattning GROUP BY klass ORDER BY d, klass")]
    ut = [SAMLING_RUBRIK]
    for klass in klasser:
        vy = bygg_vy(conn, klass)
        for i, prov in enumerate(vy["prov"]):
            namn = prov["titel"] + (" (omprov)" if prov["omprov"] else "")
            for e in vy["elever"]:
                p = e["prov"][i]
                if p is None:
                    continue
                ut.append([klass, e["elev"], namn, prov["datum"],
                           p["del"]["A"], prov["delmax"]["A"], p["del"]["B"],
                           prov["delmax"]["B"], p["k"] if prov["komp"] else "",
                           p["total"], sum(prov["max"]), p["pil"], p["e"], p["c"], p["a"]])
    return ut


def skriv_csv(fil: Path, rader: list[list]) -> None:
    with fil.open("w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rader)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("klass", nargs="?")
    ap.add_argument("--alla", action="store_true",
                    help="samlingsarket: en rad per elev och prov, alla klasser")
    ap.add_argument("--db", type=Path, default=ROT / "transkribera.db")
    ap.add_argument("--csv", type=Path, help="skriv tabellen som CSV (UTF-8)")
    a = ap.parse_args(argv)
    if bool(a.klass) == a.alla:
        ap.error("ange en klass eller --alla")
    conn = db.connect(str(a.db))
    try:
        if a.alla:
            rader = samling(conn)
            if a.csv:
                skriv_csv(a.csv, rader)
                print(f"skrev {a.csv} ({len(rader) - 1} rader)")
            else:
                for r in rader:
                    print("\t".join(str(x) for x in r))
            return 0
        vy = bygg_vy(conn, a.klass)
    finally:
        conn.close()
    rader = till_rader(vy)
    if a.csv:
        skriv_csv(a.csv, rader)
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
