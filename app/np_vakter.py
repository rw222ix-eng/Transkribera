"""NP-vakterna: sju räknade vakter som mäter ett provs SVÅRIGHET och FORM mot
nationella provens uppgiftsprofil (app/data/np_uppgiftsprofil.json), aldrig
dess ordval.

Skälet att de finns är lärarens dom över prov 88 (Ma 2a, 2026-09-22):
uppgifter som var för svåra för sin poäng, som föreskrev metoden, som låg
utanför kursen eller som hängde en A-poäng på ett krav uppgiften inte
ställde. Nivådomaren och nivårubriken (niva_rubrik) beskriver nivån i ORD;
det här är MÅTTEN, och de kostar ingenting: inget modellanrop, samma svar
varje gång. Samma kontrakt som exam_gen:s övriga räknade vakter (a_nivavakt,
kravradsvakt): ett fynd är `_err(path, code, message)`, en rad per bedömd
enhet (exam_gen.domarenheter: en deluppgift är sin egen enhet), tak per vakt,
och meddelandet säger vad som ska göras.

LÄRARENS DOM 2026-09-22 GÄLLER ÖVER ALLT HÄR: hennes förtydligande fraser
(«Avgör om Elin har hittat alla lösningar», «Visa hur du har räknat med hjälp
av miniräknare») är medvetna och står kvar. Ingen vakt fäller en uppgift för
ordval, för textlängd eller för att den är utförligare än NP. Textlängd mäter
inte nivån heller (medianstammen är lika på E, C och A i alla fyra kurserna).

MÄTNINGEN VARJE REGEL BYGGER PÅ (kurs → siffra ur profilens `mall`):

1. stegvakt — steg per poäng på LÖSNINGSUPPGIFTER. 90:e percentilen av
   steg_per_poang för lösningsenheter: 2a E 2,0 / C 1,6 / A 2,0; 2c 2,0 / 2,0 /
   2,0; 1a 2,0 / 2,0 / 1,5; 1c 1,8 / 1,7 / 1,5. Alltså aldrig över två steg
   per poäng, på någon nivå, i någon kurs. Kortsvaren (typ rutin) mäts INTE:
   ett A-kortsvar i kurs 2 ger 1 p för 3 steg (2a A_kortsvar: median 3,0) och
   är NP:s svåraste poäng per ord, med flit. Räknestegen räknas ur `losning`
   med heuristiken i rakna_steg (dokumenterad där).
2. poangformvakt — poäng per enhet. E-LÖSNINGAR: max 2 i alla fyra kurserna
   (2a: 45 av 55 E-enheter ger 1 p; ett E-kortsvar om 3 p är a/b/c-formen
   och skelettets egen, validate_stam vaktar den). A-lösningar: min 2 i 1a,
   1c och 2a (2a: alla elva 1-poängs A-enheter är kortsvar); 2c har EN
   A-lösning på 1 p
   (bedöm modellens begränsning) och får därför gränsen 1. Ingen enhet över
   4 p (2a: «aldrig över 4», 2c max 3; kurs 1:s 12-poängare är matrisbedömda
   delprov C-helheter, en form appen inte skriver). K-poäng i kurs 2: bara på
   C och A, bara i enheter med minst 3 p (2a k_poang.enhetsstorlek: 3 p ×8,
   4 p ×2, 1 p ×1; 2c: 3 p ×9). I kurs 1 finns K på E (1a: 4 E-poäng) och på
   2-poängare (1a ×5, 1c ×6), så K-reglerna gäller BARA kurs 2. Samma regler
   ligger i exam_spec.balanced_skeleton, som låser poängen innan modellen
   skriver; vakten här är backstoppet för refine och canvas.
3. metodvakt — «med pq-formeln/kvadreringsregeln/konjugatregeln» förekommer
   ALDRIG (2a: 0 av 112; 2c: 0 av 74; 1a: 0 av 71; 1c: 0 av 77). Det som
   finns är «med algebraisk metod» (2a ×3, 2c ×3), «använd formeln» (1a, 1c),
   «bryt ut» (1a, 1c) och «med hjälp av grafen» (2a ×6). Mäts i
   uppgiftstexten i den räknarfria delen.
4. parametervakt — bokstavskonstanter i stammen (utöver x, y, den okända och
   funktionsnamn). p90 per nivå, kortsvar/lösning: 2a E 0,4/0,5 · C 0/1,2 ·
   A 0/1,0; 2c E 0/0 · C 0/0,8 · A 1/1; 1c E 0/0 · C 0/0 · A 1/1; 1a E 2/0 ·
   C 1/2,8 · A 2/2. Taken i PARAMETERTAK per kurs. En konstant som får ett
   tal i deluppgiften («Låt c = 25») räknas inte, precis som profilens
   vt22:22 («v ersätts med ett tal»).
5. kursvakt — grannkursens INNEHÅLL (2c-tvärsnittets regel R1 träffar 20 av
   27 2c-unika rader och 0 av 47 delade; 1c-tvärsnittets regel 1 fångar 23 av
   39 1c-unika, precision mot 1a ≈97 %) och FORMEN «för varje x / för alla x /
   alla värden på». I 2a står den formen på 2 av 112 enheter (en C, en A);
   2c:s regel R2 säger att generaliseringen på A kräver ≥2 p och
   resonemangspoäng. I kurs 1: 0 av 71 (1a) och 0 av 77 (1c).
6. familjvakt — samma modellfamilj två gånger på ett prov. Lärarens dom över
   uppgift 3 och 8 i prov 88 («fast avgift + rörlig kostnad, sätt in» två
   gånger; NP har en per prov). Räknas som en linjär formel «bokstav = tal ±
   tal·bokstav» i stammen, eller samma scen.begrepp/forebild.sort.
7. doltkravvakt — en bedömningsrad som kräver något texten inte ber om
   (antagande, motivering, enhet). Prov 88 uppgift 11: A-poängen hängde på
   «antagandet utskrivet», ett krav uppgiften aldrig ställde. NP:s
   anvisningar kräver antaganden bara där stammen säger «anta att …» (2a:
   förtydligande på 5 av 22 A-enheter, alla i kontextuppgifter).

Kurser utan mätning (Ma3c, Ma4, okänt namn) prövas inte av de kursbundna
reglerna (4, 5 och K-delen av 2); de övriga gäller överallt, för de är
desamma i alla fyra kurserna.
"""
from __future__ import annotations

import math
import re
from collections import Counter

from app import exam_spec, niva_rubrik

STEG_MAX_FYND = 4
POANGFORM_MAX_FYND = 4
METOD_MAX_FYND = 4
PARAMETER_MAX_FYND = 4
KURS_MAX_FYND = 4
FAMILJ_MAX_FYND = 3
DOLTKRAV_MAX_FYND = 4

# Steg per poäng på en lösningsuppgift: över två är över NP:s 90:e percentil
# i alla fyra kurserna (se modulens huvudkommentar, regel 1).
STEG_PER_POANG_TAK = 2.0
# Poäng per enhet (regel 2).
ENHET_MAX_POANG = 4
E_ENHET_MAX_POANG = 2
K_ENHET_MIN_POANG = 3
# A-lösningens minsta poäng per kurs; okänd kurs får den mätning tre av fyra
# kurser delar. 2c:s enda 1-poängs A-lösning står i huvudkommentaren.
A_LOSNING_MIN_POANG: dict[str, int] = {"1a": 2, "1c": 2, "2a": 2, "2c": 1}
A_LOSNING_MIN_OKAND = 2
# Bokstavskonstanter i stammen, högst, per kurs och nivå (regel 4). 1a:s tak
# är höga därför att 1a:s A-kortsvar LEVER på bokstäver (median 2): «uttryck
# i a och b» är där en E/C-form lika väl som en A-form.
PARAMETERTAK: dict[str, dict[str, int]] = {
    "2a": {"E": 0, "C": 1, "A": 2},
    "2c": {"E": 0, "C": 1, "A": 2},
    "1c": {"E": 0, "C": 1, "A": 2},
    "1a": {"E": 2, "C": 3, "A": 2},
}

# ── Grannkursens innehåll (regel 5), som DATA per kurs ─────────────────
# Ordet i uppgiftstexten räcker; lösningens metod är kursdomarens sak (den
# LLM-domare som läser hela uppgiften, app/kursdomare.py). Listan är
# 2c-tvärsnittets R1 respektive 1c-tvärsnittets regel 1, med egna ord.
KURSINNEHALL: dict[str, list[tuple[str, re.Pattern]]] = {
    "2a": [
        ("logaritmlagar", re.compile(r"logaritmlag|lg-lag", re.I)),
        ("komplexa tal", re.compile(
            r"komplex[at]?\s+(?:tal|rot|rötter|lösning)|imaginär", re.I)),
        ("likformighet", re.compile(r"likformig", re.I)),
        ("cirkelgeometri", re.compile(
            r"randvinkel|medelpunktsvinkel|periferivinkel", re.I)),
        ("bisektris", re.compile(r"bisektris", re.I)),
        ("regression", re.compile(r"regression", re.I)),
        ("implikation/ekvivalens", re.compile(
            r"implikation|ekvivalen[st]|\\Rightarrow|\\Leftrightarrow|⇒|⇔",
            re.I)),
        ("talteori", re.compile(
            r"följande heltal|delbar[t]?\s+med|delbarhet", re.I)),
    ],
    "1a": [
        ("trigonometri", re.compile(
            r"(?<![\wåäö])(?:sin|cos|tan)(?![\wåäö])|sinus|cosinus|tangens"
            r"|trigonometri", re.I)),
        ("vektorer", re.compile(r"vektor", re.I)),
        ("formell funktionslära", re.compile(
            r"definitionsmängd|värdemängd", re.I)),
        ("potenslagar", re.compile(r"potenslag", re.I)),
        ("bevis", re.compile(r"(?<![\wåäö])bevis", re.I)),
        ("talsystem", re.compile(
            r"binär|primtal|talsystem|tvåsystem|basen två", re.I)),
    ],
    # 1c och 2c är de tyngre spåren: ingenting i grannkursen ligger utanför.
    "1c": [],
    "2c": [],
}
# Formen «för varje x / för alla x / alla värden på»: vad kursen tillåter.
# "aldrig" (kurs 1: 0 av 71 och 0 av 77), "A2R" (2a: bara A-enheter med ≥2 p
# och resonemangspoäng, 2c:s R2 lånad som gräns), "fritt" (2c).
GENERALISERING: dict[str, str] = {"1a": "aldrig", "1c": "aldrig",
                                  "2a": "A2R", "2c": "fritt"}
_GENERALISERING_RE = re.compile(
    r"för (?:varje|alla) \$?[a-zA-Z]\$?|för alla värden|alla värden på"
    r"|för varje värde|gäller för alla|för alla reella", re.I)

# Metodföreskriften (regel 3): formen «med/använd/genom <metod>». Verbet
# «Faktorisera …» är en uppgift (E-form i kurs 1), inte en föreskrift.
_METODFORESKRIFT_RE = re.compile(
    r"(?<![\wåäö])(?:med|använd|genom|via)\s+(?:hjälp\s+av\s+)?"
    r"(pq-formeln|kvadreringsreg(?:eln|lerna)|konjugatregeln"
    r"|nollproduktmetoden|faktorisering)(?![\wåäö])", re.I)

_MATH_RE = re.compile(r"\$([^$]+)\$")


def _err(path: str, code: str, message: str) -> dict:
    """Samma fyndform som exam_gen._err och exam_spec: reparationsrundan och
    efterkontrollen läser alla tre med samma _format_problems."""
    return {"path": path, "code": code, "message": message}


def _enheter(exam: dict) -> list[dict]:
    # exam_gen importerar den här modulen; importen står här nere så att de
    # två inte importerar varandra vid laddning.
    from app import exam_gen
    return exam_gen.domarenheter(exam or {})


def _uppgift(exam: dict, nr: str) -> dict:
    """Huvuduppgiften bakom enheten «12b» (för fälten enheten inte bär)."""
    m = re.match(r"\d+", str(nr or ""))
    i = int(m.group()) if m else 0
    uppgifter = (exam or {}).get("uppgifter") or []
    u = uppgifter[i - 1] if 0 < i <= len(uppgifter) else {}
    return u if isinstance(u, dict) else {}


def _text(e: dict) -> str:
    return f"{e['kort'].get('stam', '')} {e['kort'].get('text', '')}".strip()


def _kurs(exam: dict, kurs: str) -> str:
    """Kursen anroparen skickade, annars provets egen (`exam.kurs`)."""
    return str(kurs or (exam or {}).get("kurs") or "")


def _kursnyckel(kurs: str) -> str | None:
    return niva_rubrik.kursnyckel(kurs or "")


def _ar_kurs_2(kurs: str) -> bool:
    niva = niva_rubrik.kursniva(kurs or "")
    return bool(niva and niva[0] == 2)


def _poang(e: dict) -> int:
    try:
        return sum(int(x) for x in (e.get("poang") or (0, 0, 0)))
    except (TypeError, ValueError):
        return 0


# ── 1. STEGVAKTEN ────────────────────────────────────────────────────────
# Stegord: ordet som binder ett räknesteg till nästa. «X ger Y» är två steg
# (teckna, lös); «X och Y» är ett (samma operation två gånger, som att
# utveckla två parenteser); «X, alltså Y» är ett (samma steg, omskrivet).
_STEGORD_RE = re.compile(
    r"(?<![\wåäö])(?:ger|blir|så|då|dvs|d\.v\.s\.|följaktligen)(?![\wåäö])",
    re.I)
_MENING_RE = re.compile(r"(?<=[.!?;])\s+|\n+")
_LIKHET_RE = re.compile(r"=|\\approx|≈")
_PLATS_RE = re.compile(r"\x00(\d+)\x00")


def rakna_steg(losning: str) -> int:
    """Räknesteg i en lösningstext, heuristiskt.

    Ett steg är ett LED med minst en likhet ($…=…$ eller ≈). Leden är
    meningens delar mellan stegorden («ger», «blir», «så», «då»); «och» och
    «alltså» binder INTE (parallella operationer, respektive samma steg
    omskrivet). Den första meningen hoppas över när den är svaret (inget
    stegord, högst ett matteblock): prompten ber om svaret först.

    Kalibrerad på prov 88: uppgift 9 («ekvation ger n = 10. Med 12 lag blir
    m = 66 och 66 − 45 = 21») räknas som tre steg, som läraren räknade;
    uppgift 4 (insättning ger c = 15; pq-formeln ger x = 4 ± 1) som fyra på
    två poäng; uppgift 7 (utveckla två parenteser, förenkla till 9) som två.
    Osäkerheten är ±1 på fyrstegslösningar, samma som profilens egen
    handräkning (2a-tvärsnittet, «Osäkerheter»)."""
    block: list[str] = []

    def _ers(m: re.Match) -> str:
        block.append(m.group(1))
        return f" \x00{len(block) - 1}\x00 "

    t = _MATH_RE.sub(_ers, str(losning or ""))
    meningar = [m for m in _MENING_RE.split(t) if m.strip()]

    def har_likhet(led: str) -> bool:
        return any(_LIKHET_RE.search(block[int(i)])
                   for i in _PLATS_RE.findall(led))

    steg = 0
    for i, mening in enumerate(meningar):
        if (i == 0 and not _STEGORD_RE.search(mening)
                and len(_PLATS_RE.findall(mening)) <= 1):
            continue
        steg += sum(1 for led in _STEGORD_RE.split(mening) if har_likhet(led))
    return steg


def stegvakt(exam: dict) -> list[dict]:
    """Fler räknesteg än poängen betalar för, på lösningsuppgifter."""
    fel: list[dict] = []
    for e in _enheter(exam):
        if (e.get("typ") or "") == "rutin":
            continue
        poang = _poang(e)
        if poang <= 0:
            continue
        steg = rakna_steg(e["kort"].get("losning", ""))
        if steg / poang <= STEG_PER_POANG_TAK:
            continue
        fel.append(_err(
            f"uppgift {e['nr']}", "stegvakt",
            f"Uppgift {e['nr']} ger {poang} p men lösningen har {steg} "
            "räknesteg. Nationella provet betalar högst två steg per poäng på "
            "en lösningsuppgift, på alla nivåer. Höj poängen till "
            f"{math.ceil(steg / STEG_PER_POANG_TAK)} (en rad per poäng i "
            "bedömningen) eller ta bort ett steg ur uppgiften. Nivån och "
            "förmågan står kvar."))
    return fel[:STEG_MAX_FYND]


# ── 2. POÄNGFORMEN ───────────────────────────────────────────────────────

def poangformvakt(exam: dict, kurs: str = "") -> list[dict]:
    """Poäng per enhet mot NP:s form: E högst 2, A-lösning minst 2, aldrig
    över 4, och i kurs 2 K-poäng bara på C/A i enheter om minst 3 p."""
    kurs = _kurs(exam, kurs)
    nyckel = _kursnyckel(kurs)
    a_min = A_LOSNING_MIN_POANG.get(nyckel or "", A_LOSNING_MIN_OKAND)
    kurs2 = _ar_kurs_2(kurs)
    fel: list[dict] = []
    for e in _enheter(exam):
        nr, poang, niva = e["nr"], _poang(e), e.get("niva")
        typ, formaga = (e.get("typ") or ""), (e.get("formaga") or "")
        try:
            e_p = int((e.get("poang") or (0, 0, 0))[0])
        except (TypeError, ValueError):
            e_p = 0
        skal: list[str] = []
        if poang > ENHET_MAX_POANG:
            skal.append(f"är värd {poang} p, och nationella provet ger aldrig "
                        f"mer än {ENHET_MAX_POANG} p på en enhet. Dela den i "
                        "deluppgifter eller sänk poängen")
        elif niva == "E" and typ != "rutin" and poang > E_ENHET_MAX_POANG:
            # Ett kortsvar om 3 p är a/b/c-formen (skelettet delar det så);
            # det mäts inte här utan av validate_stam.
            skal.append(f"är en E-lösning värd {poang} p; NP:s E-enheter ger "
                        "1 eller 2 p. Dela den i a) och b) eller sänk till 2 p")
        if kurs2 and formaga == "K" and e_p > 0:
            skal.append("bär kommunikationspoäng på E-nivå, och i kurs 2 "
                        "finns ingen EK-poäng. Flytta poängen till C eller "
                        "byt förmåga")
        elif kurs2 and formaga == "K" and poang < K_ENHET_MIN_POANG:
            skal.append(f"har förmågan Kommunikation men bara {poang} p. I "
                        "kurs 2 ges K-poängen för redovisningen av en hel "
                        "lösning och finns bara i enheter om minst 3 p "
                        "(2 + 1 K). Höj till 3 p med en egen K-rad i "
                        "bedömningen, eller byt förmåga till den som "
                        "uppgiften faktiskt prövar")
        if niva == "A" and typ != "rutin" and poang < a_min:
            skal.append(f"är en A-uppgift med fullständig lösning värd "
                        f"{poang} p. I NP är varje A-poäng på 1 p ett "
                        "kortsvar; en A-lösning ger minst 2 p. Höj till 2 p "
                        "(lägg till ett steg som får sin egen rad) eller gör "
                        "den till ett kortsvar med typen \"rutin\"")
        if not skal:
            continue
        fel.append(_err(f"uppgift {nr}", "poangform",
                        f"Uppgift {nr} " + ". Dessutom: uppgiften ".join(skal)
                        + ". Behåll del och plats i stegringen."))
    return fel[:POANGFORM_MAX_FYND]


# ── 3. METODVAKTEN ───────────────────────────────────────────────────────

def metodvakt(exam: dict) -> list[dict]:
    """«Lös … med pq-formeln» i den räknarfria delen: metoden ÄR det som
    prövas, och NP skriver den aldrig ut."""
    fel: list[dict] = []
    for e in _enheter(exam):
        if e.get("del") not in (None, "B"):
            continue
        m = _METODFORESKRIFT_RE.search(_text(e))
        if not m:
            continue
        fel.append(_err(
            f"uppgift {e['nr']}", "metodvakt",
            f"Uppgift {e['nr']} föreskriver metoden («{m.group(0)}»). "
            "Nationella provet föreskriver aldrig metod i den räknarfria "
            "delen; det som förekommer är «med algebraisk metod», «använd "
            "formeln», «bryt ut» och «med hjälp av grafen». Stryk "
            "metodangivelsen och låt eleven välja. Samma uppgift i övrigt, "
            "samma poäng."))
    return fel[:METOD_MAX_FYND]


# ── 4. PARAMETERVAKTEN ───────────────────────────────────────────────────
_TEXTCMD_RE = re.compile(r"\\(?:text|mathrm|operatorname|mbox)\s*\{[^}]*\}")
_CMD_RE = re.compile(r"\\[a-zA-Z]+")
_SUB_RE = re.compile(r"_\{[^}]*\}|_[a-zA-Z0-9]")
_LHS_RE = re.compile(r"^\s*([a-zA-Z])(?:_\{[^}]*\}|_[a-zA-Z0-9])?\s*=")
_TILLDELAD_RE = re.compile(r"^\s*([a-zA-Z])\s*=\s*-?\d")
_DAR_AR_RE = re.compile(r"\$([a-zA-Z])\$\s+(?:är|betecknar|anger|står för)")
_FUNK_RE = re.compile(r"([a-zA-Z])\s*\(")


def konstanter(text: str) -> set[str]:
    """Bokstavskonstanterna i en uppgiftstext, med profilens definition:
    bokstäver i matten utöver x, y, den okända och funktionsnamnen.

    Bort räknas det som texten själv definierar: vänsterledet i en given
    formel («R = 45n − 12 000» definierar R), bokstaven som förklaras («där
    n är antalet luncher»), den som får ett tal («Låt c = 25»), och
    funktionsnamn (bokstav följd av parentes). Saknas x och y är den
    vanligaste kvarvarande bokstaven den okända."""
    rakning: Counter = Counter()
    definierade: set[str] = set()
    for b in _MATH_RE.findall(str(text or "")):
        m = _LHS_RE.match(b)
        if m:
            definierade.add(m.group(1))
        m = _TILLDELAD_RE.match(b)
        if m:
            definierade.add(m.group(1))
        ren = _SUB_RE.sub(" ", _CMD_RE.sub(" ", _TEXTCMD_RE.sub(" ", b)))
        definierade |= set(_FUNK_RE.findall(ren))
        rakning.update(re.findall(r"[a-zA-Z]", ren))
    definierade |= set(_DAR_AR_RE.findall(str(text or "")))
    kvar = set(rakning) - definierade - {"x", "y"}
    if "x" not in rakning and "y" not in rakning and kvar:
        kvar.discard(max(sorted(kvar), key=lambda b: rakning[b]))
    return kvar


def parametervakt(exam: dict, kurs: str = "") -> list[dict]:
    """Fler bokstavskonstanter i stammen än kursens nivå bär."""
    kurs = _kurs(exam, kurs)
    tak = PARAMETERTAK.get(_kursnyckel(kurs) or "")
    if not tak:
        return []
    fel: list[dict] = []
    for e in _enheter(exam):
        niva = e.get("niva")
        if niva not in tak:
            continue
        k = konstanter(_text(e))
        if len(k) <= tak[niva]:
            continue
        fel.append(_err(
            f"uppgift {e['nr']}", "parametervakt",
            f"Uppgift {e['nr']} ({niva}) bär {len(k)} bokstavskonstanter i "
            f"texten ({', '.join(sorted(k))}); nationella provets "
            f"{_kursnyckel(kurs)}-uppgifter på {niva} har högst {tak[niva]}. "
            "Ge en konstant ett tal, eller låt uppgiften pröva det den "
            "prövar med en bokstav färre. Samma poäng, samma förmåga."))
    return fel[:PARAMETER_MAX_FYND]


# ── 5. KURSVAKTEN ────────────────────────────────────────────────────────

def kursvakt(exam: dict, kurs: str = "") -> list[dict]:
    """Innehåll som hör hemma i grannkursen, och generaliseringens form."""
    nyckel = _kursnyckel(_kurs(exam, kurs))
    if not nyckel:
        return []
    granne = {"1a": "1c", "2a": "2c"}.get(nyckel)
    innehall = KURSINNEHALL.get(nyckel, [])
    form = GENERALISERING.get(nyckel, "fritt")
    fel: list[dict] = []
    for e in _enheter(exam):
        nr, text = e["nr"], _text(e)
        traff = next(((namn, p.search(text)) for namn, p in innehall
                      if p.search(text)), None)
        if traff:
            namn, m = traff
            fel.append(_err(
                f"uppgift {nr}", "kursvakt",
                f"Uppgift {nr} handlar om {namn} («{m.group(0)}»), och det "
                f"innehållet finns i nationella provet för {granne} men inte "
                f"för {nyckel}. Byt ut uppgiften mot en som prövar samma "
                "förmåga inom kursens eget innehåll, samma del och samma "
                "poäng."))
            continue
        m = _GENERALISERING_RE.search(text)
        if not m or form == "fritt":
            continue
        tillatet = (form == "A2R" and e.get("niva") == "A" and _poang(e) >= 2
                    and (e.get("formaga") or "") == "R")
        if tillatet:
            continue
        skal = ("den formen finns inte i nationella provet för kurs 1"
                if form == "aldrig" else
                f"det är {granne}:s form: i {nyckel}:s nationella prov står "
                "en generalisering över alla x bara på A-enheter med minst "
                "2 p och resonemangspoäng")
        fel.append(_err(
            f"uppgift {nr}", "kursvakt",
            f"Uppgift {nr} ber om något som ska gälla generellt («{m.group(0)}»"
            f"), och {skal}. Fråga i stället efter ett bestämt värde eller ett "
            "bestämt fall, eller gör uppgiften till en resonemangsuppgift om "
            "minst 2 A-poäng. Samma del."))
    return fel[:KURS_MAX_FYND]


# ── 6. FAMILJVAKTEN ──────────────────────────────────────────────────────
_LINJAR_RE = re.compile(
    r"^[a-zA-Z]=(?:[\d,.]+[a-zA-Z][+-][\d,.]+|[\d,.]+[+-][\d,.]+[a-zA-Z])$")


def _linjar_modell(text: str) -> bool:
    """Bär stammen en formel «bokstav = tal ± tal·bokstav»?"""
    for b in _MATH_RE.findall(str(text or "")):
        t = _SUB_RE.sub("", b).replace("{,}", ",")
        t = re.sub(r"\\(?:cdot|times|,|;|:| )|[{}\s]", "", t)
        if _LINJAR_RE.match(t):
            return True
    return False


def familjvakt(exam: dict) -> list[dict]:
    """Två eller fler uppgifter ur samma modellfamilj på samma prov."""
    familjer: dict[tuple[str, str], list[int]] = {}
    for i, u in enumerate((exam or {}).get("uppgifter") or [], 1):
        if not isinstance(u, dict):
            continue
        nycklar: list[tuple[str, str]] = []
        text = " ".join([str(u.get("text") or "")]
                        + [str(d.get("text") or "")
                           for d in (u.get("deluppgifter") or [])
                           if isinstance(d, dict)])
        if _linjar_modell(text):
            nycklar.append(("linjär modell med fast och rörlig del "
                            "(bokstav = tal ± tal·bokstav)", ""))
        scen = u.get("scen") if isinstance(u.get("scen"), dict) else {}
        begrepp = " ".join(str(scen.get("begrepp") or "").lower().split())
        if begrepp:
            nycklar.append(("scen", begrepp))
        fb = u.get("forebild") if isinstance(u.get("forebild"), dict) else {}
        sort = " ".join(str(fb.get("sort") or "").lower().split())
        if sort:
            nycklar.append(("förebild", sort))
        for n in nycklar:
            familjer.setdefault(n, []).append(i)
    fel: list[dict] = []
    sedda: set[tuple[int, ...]] = set()
    for (slag, varde), nummer in familjer.items():
        if len(nummer) < 2 or tuple(nummer) in sedda:
            continue
        sedda.add(tuple(nummer))
        namn = slag if not varde else f"samma {slag} («{varde}»)"
        lista = ", ".join(str(n) for n in nummer[:-1]) + f" och {nummer[-1]}"
        fel.append(_err(
            f"uppgift {nummer[-1]}", "familjvakt",
            f"Uppgift {lista} bygger på samma modellfamilj: {namn}. "
            "Nationella provet har en sådan per prov. Behåll uppgift "
            f"{nummer[0]} och byt ut de andra mot uppgifter ur andra "
            "modellfamiljer, samma del, samma poäng och samma förmåga."))
    return fel[:FAMILJ_MAX_FYND]


# ── 7. DOLT-KRAV-VAKTEN ──────────────────────────────────────────────────
# (namn, kravet i bedömningsraden, det texten måste säga för att kravet ska
# vara ställt). Redovisning prövas bara på kortsvar: en lösningsuppgift har
# kravraden «Fullständig lösning krävs» tryckt på pappret (exam_latex._krav).
DOLDA_KRAV: list[tuple[str, re.Pattern, re.Pattern]] = [
    ("ett antagande",
     re.compile(r"antagande|antar att|förutsätt", re.I),
     re.compile(r"(?<![\wåäö])anta(?:g|r|gande)?(?![\wåäö])|förutsätt", re.I)),
    ("en motivering",
     re.compile(r"motiver|förklar", re.I),
     re.compile(r"motiver|förklar|varför|resoner|undersök|avgör|visa|utred"
                r"|(?<![\wåäö])hur(?![\wåäö])|stämmer|rätt", re.I)),
    ("en enhet",
     re.compile(r"(?<![\wåäö])enhet", re.I),
     re.compile(r"(?<![\wåäö])enhet|kronor|(?<![\wåäö])kr(?![\wåäö])|meter"
                r"|(?<![\wåäö])m(?![\wåäö])|m²|m\^2|liter|procent|%|timm"
                r"|minut|sekund|(?<![\wåäö])kg(?![\wåäö])|(?<![\wåäö])km"
                r"(?![\wåäö])|grader", re.I)),
    ("en redovisning",
     re.compile(r"redovis|visar (?:hur|räkningen|beräkningen)|tydlig lösning",
                re.I),
     re.compile(r"redovis|visa (?:hur|din|dina)|lösning", re.I)),
]


def doltkravvakt(exam: dict) -> list[dict]:
    """En bedömningsrad som kräver något uppgiftstexten inte ber om."""
    fel: list[dict] = []
    for e in _enheter(exam):
        nr, text = e["nr"], _text(e)
        u = _uppgift(exam, nr)
        rader = [r for r in exam_spec.bedomningsrader(e.get("bedomning"))
                 if not r["not"]]
        for r in rader:
            for namn, krav, staller in DOLDA_KRAV:
                if not krav.search(r["krav"]):
                    continue
                if namn == "en redovisning" and (e.get("typ") or "") != "rutin":
                    continue
                if namn == "en enhet" and str(u.get("enhet") or "").strip():
                    continue
                if staller.search(text):
                    continue
                fel.append(_err(
                    f"uppgift {nr}", "doltkrav",
                    f"Uppgift {nr}: bedömningsraden «+{r['poang']} {r['niva']} "
                    f"{r['krav']}» kräver {namn}, men uppgiftstexten ber inte "
                    "om det. Eleven kan inte få poängen för något hon inte "
                    "blev ombedd att göra. Skriv kravet i uppgiften eller "
                    "stryk det ur bedömningsraden. Poängen står kvar."))
                break
            else:
                continue
            break
    return fel[:DOLTKRAV_MAX_FYND]


# ── ALLA SJU, i läsordning ───────────────────────────────────────────────
KODER = ("stegvakt", "poangform", "metodvakt", "parametervakt", "kursvakt",
         "familjvakt", "doltkrav")


def np_vakter(exam: dict, kurs: str = "") -> list[dict]:
    """De sju vakterna på ett prov, i den ordning läraren läser dem. Körs på
    profilen «prov» i exam_gen._raknade_fynd (fixrundan och slutgrinden) och i
    routes_exam.efterkontroll (canvasen och Laga-knappen)."""
    return (stegvakt(exam) + poangformvakt(exam, kurs) + metodvakt(exam)
            + parametervakt(exam, kurs) + kursvakt(exam, kurs)
            + familjvakt(exam) + doltkravvakt(exam))
