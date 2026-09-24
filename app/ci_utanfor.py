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

IMPLIKATION OCH EKVIVALENS (Rickard 2026-09-25). Pilarna ⇒, ⇐ och ⇔ och
begreppen står i 2b:s och 2c:s centrala innehåll («Logik och geometri»),
inte i 1a, 1b, 1c eller 2a. Kursplanen styr (Rickard 2026-09-24 kväll: «om
det finns i kursplanen så ska den vara där»), så 2b är utan förbud. Ändå stod de på TE26A:s godkända prov 129 (uppgift 12)
och på fem blad ur proven, också NA26F:s 134 och 136 fast prov 126 saknade
dem. En omskrivning 23/9 bad om «2.2 (implikation ⇒ och ekvivalens ⇔)» för
att Libers avsnitt 2.2 tycktes sakna uppgift (sidan 55 är implikation), och
lärarens formdom över den uppgiften blev en regel i exam_gen.INSTRUCTION med
pilarna som exempel, i varje prompt. Ingen vakt hade 1c-raden. Nu står den
för de fyra nivåerna, i text, facit och bedömning: «ger» och «alltså»
mellan stegen, aldrig en pil.

Data per kurs står i UTANFOR. Nycklarna är steg och spår ur
niva_rubrik.kursniva: «1c» för «Matematik, nivå 1c», «2b» för «Matematik 2b».
(kursnyckel duger inte: den ger None för 2b, som saknar uppmätta NP.) En
kurs som saknas har inga strykningar, och då tiger vakten.
"""
from __future__ import annotations

import re

from app import niva_rubrik

CI_MAX_FYND = 6
KOD = "utanforci"

# Pilarna som tecken och som LaTeX, och orden. LaTeX-namnen läses med stor
# bokstav och utan (?i): \overrightarrow{AB} är en vektor, och vektorer står i
# 1c. «Medför» står inte med, det är vardagssvenska («det medför en kostnad»).
_IMPLIKATION = (
    "implikation och ekvivalens",
    "implikation och ekvivalens: pilarna ⇒, ⇐ och ⇔, också mellan stegen i "
    "en lösning, och orden implikation och ekvivalens",
    re.compile(
        r"[⇒⇐⇔⟹⟸⟺]"
        r"|\\(?:Rightarrow|Leftarrow|Leftrightarrow|Longrightarrow"
        r"|Longleftarrow|Longleftrightarrow|implies|impliedby|iff)(?![A-Za-z])"
        r"|(?i:implikation|ekvivalen[st])"
        r"|(?i:(?<![\wåäö])om\s+och\s+endast\s+om(?![\wåäö]))"))

# (namn, i klartext för prompten, mönster). Mönstren läser råtext med LaTeX i,
# så `a_n` står som den skrivs: $a_n$, $a_{n}$, $a_{n+1}$.
UTANFOR: dict[str, list[tuple[str, str, re.Pattern]]] = {
    "1a": [_IMPLIKATION],
    "1b": [_IMPLIKATION],
    "2a": [_IMPLIKATION],
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
        _IMPLIKATION,
    ],
}


# ── KVADRERINGS- OCH KONJUGATREGLERNA I NIVÅ 1 (Rickards dom 2026-09-24) ──
# De står i det centrala innehållet för 2a och 2c, inte för 1a och 1c, och
# Skolverkets formelblad för nivå 1 saknar dem av just det skälet. Ändå fick
# fem av bladen inför proven 24/9 (134, 136, 142, 143, 147) uppgifter som
# «(a + b)² − (a − b)²», «4x² − (x + 3)²» och «visa att x² + 12x + 36 är en
# kvadrat». Orden står sällan i uppgiften, så vakten läser MATTEN: en parentes
# med en bokstav och ett plus eller minus, i kvadrat, som ska utvecklas
# (samma mattestycke har ett likhetstecken och en kvadrat till), faktoriseras
# eller förenklas, och produkten (a + b)(a − b). En formel som bara ska räknas
# ut, h = (12 − 0,5t)², står kvar.
#
# Först bara på övningspappren (proven var granskade och godkända, och en ny
# vakt på provet är lärarens beslut). Nu i UTANFOR för 1a, 1b och 1c, se
# nedanför _KVADRERING.
_LATEXORD = re.compile(r"\\[A-Za-z]+")
_MATTESTYCKE = re.compile(r"\$\$?([^$]+)\$\$?")
_KVADRATPARENTES = re.compile(r"\(([^()]*)\)\s*\^\s*\{?\s*2\s*\}?")
_ENSAM_BOKSTAV = re.compile(r"(?<![A-Za-z])[A-Za-z](?![A-Za-z])")
_KVADRAT = re.compile(r"\^\s*\{?\s*2\s*\}?")
_PARENTESPAR = re.compile(r"\(([^()]+)\)\s*(?:\\cdot\s*)?\(([^()]+)\)")
_TVA_TERMER = re.compile(r"^\s*([^+\-−]+?)\s*([+\-−])\s*([^+\-−]+?)\s*$")
_UTVECKLA = re.compile(r"(?i:utveckla|förenkla|faktorisera|skrivas?\s+som\s+"
                       r"(?:en\s+)?kvadrat|kvadratkomplett)")
_KVADRERINGSORD = re.compile(
    r"(?i:kvadreringsregel|konjugatregel|konjugat(?:et|en|er|erna)?\b"
    r"|kvadratkomplett\w*|differens(?:en)?\s+(?:av|mellan)\s+två\s+kvadrater"
    r"|jämn\s+kvadrat)")


class _Traff:
    """Det lilla av re.Match som _traff läser."""

    def __init__(self, text: str):
        self._text = text

    def group(self, _n: int = 0) -> str:
        return self._text


def _ren(s: str) -> str:
    return re.sub(r"\s+", "", _LATEXORD.sub("", s.replace("−", "-")))


def _konjugat(a: str, b: str) -> bool:
    """(p + q)(p − q) eller (p − q)(p + q), samma två termer."""
    ma, mb = _TVA_TERMER.match(_ren(a)), _TVA_TERMER.match(_ren(b))
    if not (ma and mb):
        return False
    return ({ma.group(2), mb.group(2)} == {"+", "-"}
            and ma.group(1) == mb.group(1) and ma.group(3) == mb.group(3)
            and bool(_ENSAM_BOKSTAV.search(ma.group(1) + ma.group(3))))


class _Kvadreringsregler:
    """re-lik sökare: `.search(text)` ger en träff eller None."""

    def search(self, text: str) -> _Traff | None:
        text = str(text or "")
        m = _KVADRERINGSORD.search(text)
        if m:
            return _Traff(m.group(0))
        verb = bool(_UTVECKLA.search(_MATTESTYCKE.sub(" ", text)))
        for stycke in _MATTESTYCKE.findall(text):
            s = stycke.replace("\\left", "").replace("\\right", "")
            for par in _PARENTESPAR.finditer(s):
                if _konjugat(par.group(1), par.group(2)):
                    return _Traff(par.group(0).strip())
            for kv in _KVADRATPARENTES.finditer(s):
                inre = _LATEXORD.sub(" ", kv.group(1)).strip().lstrip("+-−")
                if not (_ENSAM_BOKSTAV.search(inre)
                        and re.search(r"[+\-−]", inre)):
                    continue
                ovrigt = s[:kv.start()] + s[kv.end():]
                identitet = "=" in s and _KVADRAT.search(ovrigt)
                tva_kvadrater = re.search(r"[-−]", ovrigt) and _KVADRAT.search(
                    ovrigt)
                if identitet or tva_kvadrater or verb:
                    return _Traff(kv.group(0).strip())
        return None


_KVADRERING = ("kvadrerings- och konjugatreglerna",
               "kvadrerings- och konjugatreglerna och kvadratkomplettering: "
               "ingen kvadrat av en parentes att utveckla, ingen differens av "
               "två kvadrater att faktorisera, inget uttryck som ska kännas "
               "igen som en kvadrat. Att multiplicera parenteser term för "
               "term, bryta ut en gemensam faktor och förkorta ingår",
               _Kvadreringsregler())
# PROVEN OCKSÅ, samma princip som implikationen (Rickard 2026-09-24 kväll):
# det som inte står i kursens centrala innehåll ska ut ur proven. GY25 har
# reglerna bara i 2a och 2c. De godkända proven 126, 129, 131 och 132 klarar
# vakten; gamla 119 och 81 hade inte gjort det.
for _niva in ("1a", "1b", "1c"):
    UTANFOR.setdefault(_niva, []).append(_KVADRERING)
# Det som bara ska gälla övningspapper, tills läraren sagt ja för proven.
# Tom sedan kvadreringsreglerna flyttade till UTANFOR; mekanismen står kvar.
BARA_OVNING: dict[str, list[tuple]] = {}


def _nyckel(kurs: str) -> str:
    """«1c», «2b» … ur kursnamnet, tom sträng när namnet inte säger nivån."""
    niva = niva_rubrik.kursniva(kurs or "")
    return f"{niva[0]}{niva[1]}" if niva else ""


def utanfor(kurs: str, profil: str = "prov") -> list[tuple]:
    """Kursens strykningar, tom lista när kursen inte har några. Profilen
    avgör om BARA_OVNING räknas med; förvalet «prov» lämnar provet som det
    var, byte för byte."""
    nyckel = _nyckel(kurs)
    lista = list(UTANFOR.get(nyckel, []))
    if profil != "prov":
        lista += BARA_OVNING.get(nyckel, [])
    return lista


def pilar_forbjudna(kurs: str) -> bool:
    """Står implikation och ekvivalens utanför kursen? Tavlan frågar, för den
    skriver då «ger» i stället för ⇒ (lesson_board.pilar_till_ger)."""
    return any(n == _IMPLIKATION[0] for n, _k, _p in utanfor(kurs))


def build_utanfor(kurs: str, profil: str = "prov") -> str:
    """Promptraden. Tom sträng utan strykningar (kassetteregeln: prompten ska
    då vara byte för byte den som gick i väg förut)."""
    lista = utanfor(kurs, profil)
    if not lista:
        return ""
    rader = "\n".join(f"- {klartext}" for _n, klartext, _p in lista)
    monster = (
        "Mönster med figurer (hur många stickor figur n har) och formler för "
        "sådana samband går bra: det är generella samband, och de står i "
        "kursen. Skriv dem som mönster och figurer, aldrig som talföljder."
        if any(n == "talföljder" for n, _k, _p in lista) else "")
    if any(n == _IMPLIKATION[0] for n, _k, _p in lista):
        monster = (monster + "\n" if monster else "") + (
            "Mellan stegen i en lösning skrivs «ger» eller «alltså», aldrig "
            "en pil.")
    return (
        f"UTANFÖR KURSEN. Det här står inte i det centrala innehållet för "
        f"{kurs} och får inte förekomma någonstans på pappret, varken i "
        "uppgifter, lösningar eller bedömning, och orden nämns inte, även om "
        "boken har avsnittet:\n"
        f"{rader}\n" + monster).rstrip("\n")


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


def ci_vakt(exam: dict | None, kurs: str = "",
            profil: str = "prov") -> list[dict]:
    """Ett fynd per uppgift (och ett för dokumentets egna fält) där något
    utanför kursens centrala innehåll står. Samma fyndform som de andra
    räknade vakterna: {path, code, message}. `profil` som i utanfor()."""
    if not isinstance(exam, dict):
        return []
    kurs = str(kurs or exam.get("kurs") or "")
    lista = utanfor(kurs, profil)
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
                   "bra." if namn == "talföljder" else "")
                + (" Att multiplicera parenteser term för term, bryta ut en "
                   "gemensam faktor och förkorta går bra."
                   if namn == _KVADRERING[0] else "")
                + (" Står pilen bara mellan stegen i lösningen räcker det att "
                   "skriva «ger» eller «alltså» i stället, och uppgiften får "
                   "stå kvar."
                   if namn == _IMPLIKATION[0] else ""))})
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
