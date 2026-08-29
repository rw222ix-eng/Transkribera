"""Svårighetskalibreringen: vad eleverna säger om uppgifternas nivå.

Appen påstår tre saker om varje uppgift: en poängtrippel (E, C, A), en förmåga
och en nivå. Två domare prövar påståendet innan pappret trycks: nivådomaren
(en språkmodell) och räkneverket (sympy). Ingen av dem har sett en enda elev.

Den här modulen läser det ENDA underlag som vet: elevernas egna resultat
(migration v15: `rattning_rader` bär radens maxpoäng per nivå, `elevresultat`
bär vad varje elev tog på varje rad). Två mått, båda klassiska i provteori och
båda räknade med ren standardbibliotekmatematik:

* **p-värdet**: andelen av maxpoängen klassen tog. En A-uppgift som fyra av
  fem klarar är inte en A-uppgift, vad än rubriken säger.
* **diskrimineringen**: hur väl uppgiften skiljer starka elever från svaga,
  mätt som punktbiserial korrelation mellan uppgiftens poäng och elevens
  RESTPOÄNG (allt annat på pappret). Restpoängen och inte totalen: en uppgift
  som ingår i sin egen jämförelse korrelerar med sig själv, och det syns som en
  diskriminering som är för hög på precis de uppgifter som är värda mest.
  En uppgift nära noll mäter ingenting. Alla får samma poäng på den, eller så
  får de poäng slumpmässigt.

INGEN IRT, med flit. `girth` och tvåparametersmodeller är nästa steg och en
egen fråga: de kräver fler elever än en lärare har, och de kräver att någon
tolkar en modellanpassning. p-värde och restkorrelation kräver bara att man kan
läsa en procent, och de säger redan det som är värt att veta om ett prov för
tjugofem elever.

MÅTTEN ÄR RÅDGIVANDE. Flaggan säger «empirin säger emot etiketten», aldrig
«uppgiften är fel». En A-uppgift som alla klarade kan vara en A-uppgift som
klassen råkade kunna, och en E-uppgift som ingen klarade kan vara en E-uppgift
som lästes fel av alla. Läraren avgör; siffran är underlaget.
"""
from __future__ import annotations

import json
import math
import sqlite3
import sys

from app import db

# ── Vad empirin ska säga om varje nivå ────────────────────────────────────
# Banden är STARTVÄRDEN och ska justeras efter riktiga papper, inte efter
# tycke, samma regel som balansbanden i exam_spec. De är satta ur NP:s egen
# ordning: en E-uppgift är ingången (de flesta ska ta den), C är mitten, och en
# A-uppgift ska skilja de starkaste från resten och alltså INTE tas av alla.
BAND: dict[str, tuple[float, float]] = {
    "E": (0.55, 1.00),
    "C": (0.25, 0.85),
    "A": (0.05, 0.55),
}

# Under det här skiljer uppgiften inte starka elever från svaga. 0,15 är lågt
# satt med flit: en lärargrupp är liten, och tröskeln ska tända på uppgifter
# som är trasiga, inte på uppgifter som är lite trubbiga.
MIN_DISKRIMINERING = 0.15

# Färre elever än så är inte en mätning. Punktbiserialen på fyra elever svänger
# mellan −1 och 1 på en enda poäng.
MIN_ELEVER = 5
# Diskrimineringen kräver mer än p-värdet: en korrelation på fem punkter är
# nästan bara brus, och en flagga som bygger på brus är värre än ingen flagga.
MIN_ELEVER_DISKRIMINERING = 8

NIVAER = ("E", "C", "A")


def niva_ur_peca(peca) -> str | None:
    """Radens NIVÅ = den högsta nivå den ger poäng på.

    Samma regel som exam_gen._niva_ur_poang, och det är med flit: den nivån är
    det pappret PÅSTÅR, och det är påståendet empirin ska prövas mot."""
    try:
        e, c, a = (int(x or 0) for x in list(peca)[:3])
    except (TypeError, ValueError):
        return None
    if a > 0:
        return "A"
    if c > 0:
        return "C"
    return "E" if e > 0 else None


def _elevpoang(trippel) -> int | None:
    """Elevens poäng på en rad, eller None när raden inte är rättad.

    Skillnaden mellan «noll poäng» och «inte rättad» är hela skillnaden mellan
    en svår uppgift och en uppgift läraren hann till hälften."""
    if not isinstance(trippel, (list, tuple)):
        return None
    varden = [x for x in list(trippel)[:3] if x is not None]
    if not varden:
        return None
    try:
        return sum(int(x) for x in varden)
    except (TypeError, ValueError):
        return None


def korrelation(xs: list[float], ys: list[float]) -> float | None:
    """Pearsons r, eller None när den inte är definierad.

    None när någon av serierna är konstant: alla tog full pott, eller ingen tog
    något. Det är inte en korrelation på noll utan en frånvaro av mätning, och
    de två ska inte se likadana ut i en tabell."""
    n = len(xs)
    if n < 2 or n != len(ys):
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return None
    return sxy / math.sqrt(sxx * syy)


def matt(rader: list[dict], resultat: dict) -> list[dict]:
    """Ett mått per uppgiftsrad: p-värde, diskriminering, nivå och antal elever.

    `rader` är rättningens rader (db.get_rattning → «rader»), `resultat`
    elevernas siffror (db.get_elevresultat → {elev_id: {nyckel: [E, C, A]}})."""
    poang_rader = [r for r in rader or []
                   if not r.get("grupp") and r.get("nyckel")]
    tak = {r["nyckel"]: sum(int(x or 0) for x in (r.get("peca") or [])[:3])
           for r in poang_rader}
    # Elevens poäng per nyckel, med None kvar för det som inte rättats.
    per_elev: dict[int, dict[str, int]] = {}
    for elev_id, per_nyckel in (resultat or {}).items():
        rent = {}
        for nyckel, trippel in (per_nyckel or {}).items():
            if nyckel not in tak:
                continue                 # en rad som inte finns på pappret
            v = _elevpoang(trippel)
            if v is not None:
                rent[str(nyckel)] = max(0, min(tak[nyckel], v))
        if rent:
            per_elev[elev_id] = rent
    ut: list[dict] = []
    for r in poang_rader:
        nyckel = r["nyckel"]
        maxp = tak.get(nyckel) or 0
        har = [(e, v[nyckel]) for e, v in per_elev.items() if nyckel in v]
        rad = {
            "nyckel": nyckel,
            "text": " ".join(str(r.get("text") or "").split())[:120],
            "formaga": r.get("formaga") or None,
            "ci": list(r.get("ci") or []),
            "niva": niva_ur_peca(r.get("peca")),
            "peca": list(r.get("peca") or []),
            "max": maxp,
            "elever": len(har),
            "p": None, "diskriminering": None,
        }
        if maxp > 0 and len(har) >= MIN_ELEVER:
            rad["p"] = round(sum(v for _e, v in har) / (maxp * len(har)), 4)
            if len(har) >= MIN_ELEVER_DISKRIMINERING:
                egna = [float(v) for _e, v in har]
                # RESTPOÄNGEN, allt eleven tog UTOM den här raden.
                rest = [float(sum(x for k, x in per_elev[e].items()
                                  if k != nyckel))
                        for e, _v in har]
                d = korrelation(egna, rest)
                # En uppgift där ALLA tog samma poäng har ingen korrelation,
                # men det är inte samma sak som att måttet saknas. Den skiljer
                # bevisligen ingen elev från någon annan, och det är precis det
                # måttet ska säga. Noll, inte tomt.
                #
                # Är det RESTEN som är konstant (alla lika starka i övrigt)
                # står None kvar: då går det inte att avgöra något, och en
                # nolla där hade sett ut som en dom.
                if d is None and len(set(egna)) == 1 and len(set(rest)) > 1:
                    d = 0.0
                rad["diskriminering"] = round(d, 4) if d is not None else None
        ut.append(rad)
    return ut


def flaggor(matten: list[dict]) -> list[dict]:
    """Uppgifterna vars empiri säger emot etiketten."""
    ut: list[dict] = []
    for m in matten:
        niva, p = m.get("niva"), m.get("p")
        if niva in BAND and p is not None:
            lag, hog = BAND[niva]
            if p > hog:
                ut.append(dict(m, flagga="for_latt", varfor=(
                    f"{niva}-uppgift som klassen tog {round(p * 100)} % av. "
                    f"Bandet för {niva} slutar vid {round(hog * 100)} %. "
                    "Uppgiften mäter en lägre nivå än den är poängsatt för.")))
            elif p < lag:
                ut.append(dict(m, flagga="for_svar", varfor=(
                    f"{niva}-uppgift som klassen tog {round(p * 100)} % av. "
                    f"Bandet för {niva} börjar vid {round(lag * 100)} %. "
                    "Uppgiften mäter en högre nivå än den är poängsatt för, "
                    "eller är otydligt ställd.")))
        d = m.get("diskriminering")
        if d is not None and d < MIN_DISKRIMINERING:
            ut.append(dict(m, flagga="skiljer_inte", varfor=(
                f"uppgiften skiljer inte starka elever från svaga "
                f"(punktbiserial {d:+.2f}, gränsen är "
                f"{MIN_DISKRIMINERING:+.2f}). Antingen tog alla samma poäng, "
                "eller så avgörs den av något annat än kunnandet.")))
    return ut


def per_niva(matten: list[dict]) -> dict:
    """Sammandraget per E/C/A: hur många uppgifter, hur svåra de blev."""
    ut = {}
    for niva in NIVAER:
        egna = [m for m in matten if m.get("niva") == niva]
        pv = [m["p"] for m in egna if m.get("p") is not None]
        dv = [m["diskriminering"] for m in egna
              if m.get("diskriminering") is not None]
        ut[niva] = {
            "uppgifter": len(egna),
            "matta": len(pv),
            "band": list(BAND[niva]),
            "p_medel": round(sum(pv) / len(pv), 4) if pv else None,
            "p_min": round(min(pv), 4) if pv else None,
            "p_max": round(max(pv), 4) if pv else None,
            "diskriminering_medel": (round(sum(dv) / len(dv), 4) if dv
                                     else None),
        }
    return ut


def kalibrera_papper(conn: sqlite3.Connection, dokument_id: int) -> dict | None:
    """ETT rättat papper genom kalibreringen."""
    rattning = db.get_rattning(conn, int(dokument_id))
    if not rattning:
        return None
    resultat = db.get_elevresultat(conn, int(dokument_id))
    if not resultat:
        return None
    matten = matt(rattning.get("rader") or [], resultat)
    return {
        "dokument_id": int(dokument_id),
        "exam_id": rattning.get("exam_id"),
        "kurs": rattning.get("kurs"),
        "klass": rattning.get("klass"),
        "datum": rattning.get("datum"),
        "elever": len(resultat),
        "uppgifter": matten,
        "per_niva": per_niva(matten),
        "flaggor": flaggor(matten),
    }


def papper_med_resultat(conn: sqlite3.Connection, *, kurs: str | None = None,
                        klass: str | None = None) -> list[int]:
    """Dokument-id:n för de rättade papper som har elevsiffror."""
    villkor, params = ["EXISTS (SELECT 1 FROM elevresultat e "
                       "WHERE e.dokument_id = r.dokument_id)"], []
    if (kurs or "").strip():
        villkor.append("r.kurs = ?")
        params.append(kurs.strip())
    if (klass or "").strip():
        villkor.append("r.klass = ?")
        params.append(klass.strip())
    rader = conn.execute(
        "SELECT r.dokument_id FROM rattning r WHERE " + " AND ".join(villkor)
        + " ORDER BY COALESCE(r.datum, r.updated_at) DESC, r.dokument_id DESC",
        params).fetchall()
    return [int(r["dokument_id"]) for r in rader]


def kalibrera(conn: sqlite3.Connection, *, kurs: str | None = None,
              klass: str | None = None,
              dokument_id: int | None = None) -> dict:
    """Hela passet: ett papper eller alla rättade i en kurs.

    Nivåsammandraget räknas om över ALLA uppgifter tillsammans och inte som ett
    medelvärde av pappersmedelvärden. Ett prov med två A-uppgifter ska inte
    väga lika tungt som ett med åtta."""
    ids = ([int(dokument_id)] if dokument_id is not None
           else papper_med_resultat(conn, kurs=kurs, klass=klass))
    papper = [p for p in (kalibrera_papper(conn, i) for i in ids)
              if p is not None]
    alla = [u for p in papper for u in p["uppgifter"]]
    return {
        "papper": papper,
        "uppgifter": len(alla),
        "per_niva": per_niva(alla),
        "flaggor": [f for p in papper for f in p["flaggor"]],
        # Vad som INTE gick att mäta, sagt rakt ut. Ett tomt flaggfält kan
        # betyda «allt stämmer» eller «ingenting mättes», och de två är inte
        # samma besked.
        "omatta": sum(1 for u in alla if u.get("p") is None),
        "grans": {"min_elever": MIN_ELEVER,
                  "min_elever_diskriminering": MIN_ELEVER_DISKRIMINERING,
                  "min_diskriminering": MIN_DISKRIMINERING,
                  "band": {n: list(b) for n, b in BAND.items()}},
    }


def main(argv: list[str] | None = None) -> int:
    """`python -m app.kalibrering [--db FIL] [--kurs X] [--klass Y] [--dok N]`

    Skriver JSON på stdout. Rutten (GET /api/exams/kalibrering) svarar med
    exakt samma struktur. Den här vägen finns för att kunna köra måttet på en
    kopia av databasen utan att starta appen."""
    import argparse
    from pathlib import Path

    # STDOUT ÄR UTF-8, ALLTID. På Windows är den annars den lokala kodsidan
    # (cp1252), och flaggtexterna bär «», – och ±: en rörledning fick trasiga
    # byte och `json.loads` på andra sidan föll på «invalid start byte». Samma
    # fälla som fejk-CLI:t gick i (tests/fejk.py), och samma rad lagar den.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):                # pragma: no cover
        pass
    p = argparse.ArgumentParser(description="Svårighetskalibrering ur "
                                            "elevresultaten")
    p.add_argument("--db", default="transkribera.db", help="sökväg till DB:n")
    p.add_argument("--kurs", default=None)
    p.add_argument("--klass", default=None)
    p.add_argument("--dok", type=int, default=None, help="ett enda papper")
    a = p.parse_args(argv)
    fil = Path(a.db)
    if not fil.exists():
        print(json.dumps({"error": f"ingen databas på {fil}"},
                         ensure_ascii=False))
        return 1
    conn = db.connect(fil)
    try:
        ut = kalibrera(conn, kurs=a.kurs, klass=a.klass, dokument_id=a.dok)
    finally:
        conn.close()
    print(json.dumps(ut, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":                              # pragma: no cover
    raise SystemExit(main())
