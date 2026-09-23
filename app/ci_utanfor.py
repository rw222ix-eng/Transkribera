"""Det som INTE står i nivåns centrala innehåll, och vakten som slår larm.

RICKARDS PRINCIP SEDAN 2026-09-17: det som inte står i kursens centrala
innehåll (GY25) undervisas inte, även om boken har det, och begreppen nämns
inte ens «för att eleverna ska känna igen dem senare». Samma dag ströks ur
Ma 1c: talföljder (Libers s. 80–84), lägesmått (s. 226–231, medelvärde, median
och typvärde står i 2a/2c), räta linjen på parameter- och normalform
(uppg. 6220–6224) och index (står i 1a:s programspecifika innehåll, inte i
1c:s). Ma 1a, 2a och 2c granskades samtidigt utan strykningar.

Planeringarna följde, appen gjorde det inte: sex dagar senare stod uppgift 10
på NA26F:s A-blad 2.5 som «Talföljd A är 5, 11, 17, 23 …» med «följd A ger
6m − 1» i facit, för bladet skrevs ur bokens sidor 64–88 och de rymmer
talföljdsavsnittet. Bladet fick byggas om för hand (2026-09-23).

Modulen gör två saker och båda är gratis, inget modellanrop:

* `build_utanfor` är raden i prompten: listan över det som inte får stå på
  pappret. Tom sträng för en kurs utan strykningar, och prompten är då byte
  för byte den som gick i väg förut.
* `ci_vakt` är vakten. Den läser uppgifternas text, lösning och bedömning
  (deluppgifterna med) och dokumentets titel, band och nyckelfråga, och ger
  ett fynd per uppgift där ett av orden står. Den körs i genereringens
  fixrunda och slutgrind (exam_gen._raknade_fynd), sist av allt i
  genereringen på alla tre dokumenttyperna (exam_gen.generate_exam, flagga)
  och i efterkontrollen efter varje svar (routes_exam.efterkontroll). Står
  ett fynd kvar följer det med pappret som varning i `errors`, och läraren
  ser det i canvasen före godkännandet.

Orden är MEDVETET snäva. «Följd» ensamt är vardagssvenska («till följd av»,
«tre dagar i följd»); vakten fäller bara formerna som betyder en talföljd
(«följd A», «följderna», «i följden»). Mönsteruppgifter med figurer och en
formel för figur n är tillåtna: de är «generella samband» (G25-M1C-PRO-1)
och ersatte talföljderna i planeringen.

Data per kurs står i UTANFOR. Nycklarna är niva_rubrik.kursnyckel: «1c» för
«Matematik, nivå 1c». En kurs som saknas har inga strykningar, och då tiger
vakten.
"""
from __future__ import annotations

import re

from app import niva_rubrik

CI_MAX_FYND = 6
KOD = "utanforci"

# (namn, i klartext för prompten, mönster). Mönstren läser råtext med LaTeX i,
# så `a_n` står som den skrivs: $a_n$, $a_{n}$, $a_{n+1}$.
UTANFOR: dict[str, list[tuple[str, str, re.Pattern]]] = {
    "1c": [
        ("talföljder",
         "talföljder: aritmetisk och geometrisk talföljd, formler för a_n, "
         "orden talföljd och följd",
         re.compile(
             r"(?i:talföljd)"
             r"|(?i:(?:aritmetisk|geometrisk)\w*\s+(?:tal)?(?:följd|summa|serie))"
             r"|(?<![\wåäö])[Ff]öljd(?:en|er|erna)?\s+[A-ZÅÄÖ](?![\wåäö])"
             r"|(?i:(?<![\wåäö])följderna(?![\wåäö]))"
             r"|(?i:(?<![\wåäö])i\s+följden(?![\wåäö]))"
             r"|(?i:(?<![\wåäö])rekursiv)"
             r"|(?i:n:te\s+(?:tal|term|element))"
             r"|(?<![A-Za-z\\])a_\{?n(?:\s*[+-]\s*1)?\}?(?![A-Za-z0-9])")),
        ("lägesmått och spridningsmått",
         "lägesmått och spridningsmått: medelvärde, median, typvärde, "
         "standardavvikelse, kvartiler och lådagram",
         re.compile(
             r"(?i:lägesmått|spridningsmått|medelvärde|typvärde"
             r"|standardavvikelse|kvartil|lådagram|variationsbredd"
             r"|(?<![\wåäö])median(?:en|värde\w*)?(?![\wåäö]))")),
        ("räta linjen på parameter- eller normalform",
         "räta linjen på parameterform eller normalform (riktningsvektor, "
         "normalvektor)",
         re.compile(
             r"(?i:parameterform|parameterframställning|normalform"
             r"|riktningsvektor|normalvektor)")),
        ("index",
         "index: indextal, KPI, prisindex och basår",
         re.compile(
             r"(?i:indextal|prisindex|löneindex|konsumentprisindex|indexserie"
             r"|basår)"
             r"|(?<![\wåäö])KPI(?![\wåäö])"
             # «index 100», «indexet 115,3», «index för år 2020». Ett
             # listindex i ett program («index 0 till 4») är programmering,
             # som står i 1c:s CI, och ska tiga: därför tre siffror.
             r"|(?i:(?<![\wåäö])index(?:et)?\s+(?:\$?\d{3}|för\s+år))")),
    ],
}


def utanfor(kurs: str) -> list[tuple[str, str, re.Pattern]]:
    """Kursens strykningar, tom lista när kursen inte har några."""
    return UTANFOR.get(niva_rubrik.kursnyckel(kurs or "") or "", [])


def build_utanfor(kurs: str) -> str:
    """Promptraden. Tom sträng utan strykningar (kassetteregeln: prompten ska
    då vara byte för byte den som gick i väg förut)."""
    lista = utanfor(kurs)
    if not lista:
        return ""
    rader = "\n".join(f"- {klartext}" for _n, klartext, _p in lista)
    return (
        f"UTANFÖR KURSEN. Det här står inte i det centrala innehållet för "
        f"{kurs} och får inte förekomma någonstans på pappret, varken i "
        "uppgifter, lösningar eller bedömning, och orden nämns inte, även om "
        "boken har avsnittet:\n"
        f"{rader}\n"
        "Mönster med figurer (hur många stickor figur n har) och formler för "
        "sådana samband går bra: det är generella samband, och de står i "
        "kursen. Skriv dem som mönster och figurer, aldrig som talföljder.")


def _texter(u: dict) -> list[str]:
    ut = [str(u.get(f) or "") for f in ("text", "losning", "bedomning",
                                        "utforlig")]
    for d in u.get("deluppgifter") or []:
        if isinstance(d, dict):
            ut += [str(d.get(f) or "") for f in ("text", "losning",
                                                 "bedomning", "utforlig")]
    return ut


def _traff(texter: list[str], lista) -> tuple[str, str] | None:
    for namn, _klartext, monster in lista:
        for t in texter:
            m = monster.search(t)
            if m:
                return namn, m.group(0).strip()
    return None


def ci_vakt(exam: dict | None, kurs: str = "") -> list[dict]:
    """Ett fynd per uppgift (och ett för dokumentets egna fält) där något
    utanför kursens centrala innehåll står. Samma fyndform som de andra
    räknade vakterna: {path, code, message}."""
    if not isinstance(exam, dict):
        return []
    kurs = str(kurs or exam.get("kurs") or "")
    lista = utanfor(kurs)
    if not lista:
        return []
    fel: list[dict] = []
    for i, u in enumerate(exam.get("uppgifter") or [], 1):
        if not isinstance(u, dict):
            continue
        traff = _traff(_texter(u), lista)
        if not traff:
            continue
        namn, ord_ = traff
        fel.append({
            "path": f"uppgift {i}", "code": KOD,
            "message": (
                f"Uppgift {i} handlar om {namn} («{ord_}»), och det står inte "
                f"i det centrala innehållet för {kurs}. Byt ut uppgiften mot "
                "en inom kursens innehåll, samma del, samma poäng och samma "
                "förmåga, och låt inte orden stå kvar i text, lösning eller "
                "bedömning."
                + (" Ett mönster med figurer (antal stickor i figur n) går "
                   "bra." if namn == "talföljder" else ""))})
    doktext = [str(exam.get(f) or "") for f in ("titel", "instruktion",
                                                 "nyckelfraga")]
    traff = _traff(doktext, lista)
    if traff:
        namn, ord_ = traff
        fel.append({
            "path": "dokumentet", "code": KOD,
            "message": (
                f"Pappret nämner {namn} («{ord_}») i titeln, bandet eller "
                f"nyckelfrågan, och det står inte i det centrala innehållet "
                f"för {kurs}. Skriv om den raden utan orden.")})
    return fel[:CI_MAX_FYND]
