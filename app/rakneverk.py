"""Räkneverket: den DETERMINISTISKA domaren över facit och svarsalternativ.

Appen har haft två domare över ett färdigskrivet papper, och båda är
språkmodeller: nivådomaren (exam_gen.doma_nivaer) och räknedomaren
(exam_gen.doma_rakning). En modell som rättar en modell är billig att bygga och
omöjlig att lita på i det enda fall som räknas: när båda gör samma fel. Den här
modulen räknar i stället EFTER, med sympy och Math-Verify, utan modell, utan
kostnad och med samma svar varje gång.

TRE UTFALL, och bara ett av dem gör något:

* **verifierad**: ledet gick att räkna och stämde. Tyst.
* **motbevisad**: ledet gick att räkna och stämde INTE. Fyndet går in i den
  befintliga reparationsloopen (`_repair_until_valid`) som ett fel bland andra,
  med koden ``raknefel``.
* **otolkbar**: ledet gick inte att räkna (en figur som inte står i texten, ett
  ± , ett resonemang i ord). Tyst, alltid. FAIL-OPEN är hela kontraktet, precis
  som täckningsdomarens: en kontroll som inte gick igenom får aldrig underkänna
  ett papper som är rätt.

VAD SOM FAKTISKT PRÖVAS. Ingen modul kan räkna ut en fritt formulerad
matematikuppgift ur texten. Det den HÄR gör är tre saker som går att göra
säkert, och den låter bli allt annat:

1. **Likhetskedjorna i facit.** «$h(1{,}5) = 20 \\cdot 1{,}5 - 5 \\cdot 1{,}5^2 =
   30 - 11{,}25 = 18{,}75$» är fyra påståenden, och tre av dem är rena
   räkneidentiteter som antingen stämmer eller inte. Ett facit som räknar fel
   mitt i kedjan är precis det fel läraren upptäcker framför klassen.
2. **Roten som facit påstår.** Står det en ekvation i uppgiftstexten och ett
   «$x = 5$» i facit ska femman lösa ekvationen. Den kontrollen är en riktig
   omräkning, och den fäller det klassiska felet.
   Motsatt riktning, att facit TAPPAT en rot, prövas INTE: en tappad rot är
   ofta ett medvetet val («vid $t = 0$ kastas bollen, så svaret är 4 s»), och en
   vakt som inte kan skilja de fallen åt blir en vakt som ropar varje gång.
3. **Svarsalternativen.** Ett distraktoralternativ som råkar vara lika med rätt
   svar gör frågan olösbar, och det är ren aritmetik att upptäcka. Se
   :func:`laga_flerval`.

SVENSKA TAL ÄR EN FÄLLA I MATH-VERIFY. Biblioteket läser «12{,}5» som MÄNGDEN
$\\{5, 12\\}$. Decimalkommat är listseparator i dess grammatik. Varje tal måste
alltså gå genom :func:`normalisera` först. Det är inte en detalj: utan den raden
är varje svenskt decimaltal i appen feltolkat, och domaren hade fällt riktiga
facit.

MATH-VERIFYS ``parse`` ÄR EN SVARSPLOCKARE, INTE EN UTTRYCKSLÄSARE. Den är byggd
för att hitta det slutliga svaret i en modells svamlande svar, och det gör den
genom att LETA efter något som ser ut som ett svar, inte genom att läsa hela
strängen. «$20 \\cdot 1{,}5 - 5 \\cdot 1{,}5^2$» kommer tillbaka som «$1{,}5^2$»,
och «$12 \\cdot 16$» som «$16$». Att döma ett facit på den tolkningen hade fällt
varje riktig uträkning i appen; första mätningen gav elva «motbevisade» led på
ett arbetsblad där alla elva stämde. Uttryck läses därför med
``latex2sympy2_extended.latex2sympy`` (samma parser Math-Verify själv använder
under huven, fast utan plockandet), och ``parse``/``verify`` används bara där de
hör hemma: att avgöra om två färdiga SVAR är samma svar.

MATH-VERIFYS TIMEOUT ÄR TRASIG PÅ WINDOWS. Dess ``parsing_timeout`` startar en
delprocess (multiprocessing), och på Windows spawnas den ur en lokal funktion
som inte går att beta. Varje anrop dör med AttributeError, och biblioteket
sväljer felet och returnerar en TOM tolkning. Symptomet är alltså inte en krasch
utan en domare som tyst tycker att ingenting går att räkna. Därför skickas
``parsing_timeout=None``/``timeout_seconds=None`` överallt här, och skyddet mot
en uttolkning som spinner ligger i stället i STORLEKSGRÄNSERNA nedan (_MAX_LED,
_MAX_TECKEN): ett uttryck som är kort kan inte spinna länge.
"""
from __future__ import annotations

import logging
import random
import re

_LOG = logging.getLogger(__name__)

# ── Verktygen, lånade sent ────────────────────────────────────────────────
# sympy tar ~1 s att importera och appen startar en webbserver. Modulen
# importeras därför av exam_gen vid start, men verktygen hämtas först när något
# faktiskt ska räknas. Saknas de går allt i «otolkbar», som om varje uttryck
# vore ett resonemang i ord. Ingen kodväg får krascha på att sympy inte finns.
_VERKTYG: dict | None = None


def verktyg() -> dict | None:
    """{sympy, latex2sympy, parse, verify, AppliedUndef} eller None när
    biblioteken saknas."""
    global _VERKTYG
    if _VERKTYG is None:
        try:
            import sympy
            from latex2sympy2_extended import latex2sympy
            from math_verify import parse, verify
            from sympy.core.function import AppliedUndef
            # Math-Verify skriver en varning per anrop om att timeouten är
            # avstängd. Den ÄR avstängd med flit (se modulens docstring), och en
            # varning per uppgift i lärarens logg är brus om ett medvetet val.
            for namn in ("math_verify", "math_verify.utils",
                         "math_verify.parser", "latex2sympy2_extended"):
                logging.getLogger(namn).setLevel(logging.ERROR)
            _VERKTYG = {"sympy": sympy, "latex2sympy": latex2sympy,
                        "parse": parse, "verify": verify,
                        "AppliedUndef": AppliedUndef}
        except Exception as e:                          # noqa: BLE001
            _LOG.info("räkneverket är avstängt: %s", e)
            _VERKTYG = {}
    return _VERKTYG or None


def tillgangligt() -> bool:
    return verktyg() is not None


# ── Normaliseringen ───────────────────────────────────────────────────────
# Svenska tal, skrivna som en svensk lärare skriver dem, till den form
# Math-Verify och sympy läser rätt.

# Decimalkommat, i alla former appen skriver det: «12,5», «12{,}5» och
# «12{,}\!5». Bara MELLAN siffror. Kommat i «$a$, $b$ och $c$» är en uppräkning
# och ska stå kvar (och gör segmentet otolkbart, vilket är rätt).
_KOMMA_RE = re.compile(r"(?<=\d)\s*(?:\{\s*,\s*\}|,)\s*(?=\d)")
# Tusenavskiljaren: hårt blanksteg, smalt blanksteg, vanligt blanksteg och
# LaTeX:ens «\,». «1 250» är ETT tal, inte «1» och «250».
_TUSEN_RE = re.compile(r"(?<=\d)(?:[ \u00a0\u202f\u2009]|\\[,;:!])(?=\d{3}(?!\d))")
# Enheter och pynt som inte bär matematik men bryter tolkningen.
_STRYK = (
    (re.compile(r"\\(?:left|right|displaystyle|quad|qquad)\b"), " "),
    (re.compile(r"\\[,;:!]"), " "),
    (re.compile(r"\\text\s*\{[^{}]*\}"), " "),
    (re.compile(r"\\mathrm\s*\{([^{}]*)\}"), r"\1"),
)


def normalisera(text: str) -> str:
    """Svensk matematiktext → den form Math-Verify läser rätt.

    Kommat först, tusenavskiljaren före det: «1 250,5» ska bli «1250.5», och
    körs kommat sist hinner tusenavskiljaren se «1250,5» och göra ingenting."""
    s = str(text or "")
    for _ in range(3):                    # «1 234 567» kräver flera svep
        ny = _TUSEN_RE.sub("", s)
        if ny == s:
            break
        s = ny
    s = _KOMMA_RE.sub(".", s)
    for regex, ersatt in _STRYK:
        s = regex.sub(ersatt, s)
    return s


# ── Vad som INTE går att räkna ────────────────────────────────────────────
# Listan är inte en smaksak. Varje tecken här gör ett led till ett PÅSTÅENDE
# och inte till en identitet: «$x = 3 \pm 2$» är två svar, «$t \approx 13{,}7$»
# är ett närmevärde, «$f'(1) = -3 < 0$» är en olikhet på slutet. Ett led med
# något av dem passerar tyst som otolkbart, alltså fail-open i praktiken.
_OMOJLIGT = re.compile(
    r"\\pm|\\mp|\\approx|\\neq|\\ne\b|\\le\b|\\leq|\\ge\b|\\geq|\\to\b"
    r"|\\lim|\\int|\\sum|\\prod|\\ldots|\\dots|\\cdots|\\begin|\\end"
    r"|\\cases|\\infty|\\forall|\\exists|\\in\b|\\subset|\\cup|\\cap"
    r"|\\Rightarrow|\\Leftrightarrow|\\implies|\\iff|\\vdots"
    r"|[<>≈≤≥±∈∞]|\.\.\.")
# Ett kvarvarande komma efter normaliseringen är en UPPRÄKNING («$x = 1, 5$»),
# och en uppräkning är inte ett tal. Samma sak med semikolon.
_UPPRAKNING = re.compile(r"[,;]")

# Storleksgränser. De ersätter Math-Verifys egen timeout, som inte fungerar på
# Windows (se modulens docstring): ett uttryck som är kort kan inte spinna länge.
_MAX_TECKEN = 400              # per led
_MAX_LED = 8                   # per likhetskedja
_MAX_SEGMENT = 60              # matteavsnitt per dokument som prövas


_MATTE_RE = re.compile(r"\$([^$]{1,400})\$")


def mattesegment(text: str) -> list[str]:
    """Alla «$…$»-avsnitt i en text, normaliserade. Text utanför dollartecknen
    är resonemang på svenska och prövas aldrig."""
    return [normalisera(m.group(1)) for m in _MATTE_RE.finditer(str(text or ""))]


def _rakningsbar(led: str) -> bool:
    led = led.strip()
    return (bool(led) and len(led) <= _MAX_TECKEN
            and not _OMOJLIGT.search(led) and not _UPPRAKNING.search(led))


# «=» delar, men inte när det sitter i «\ne», «\le», «\geq», «<=», «:=» eller
# «==». _OMOJLIGT har redan tagit de LaTeX-skrivna varianterna; den här vakten
# tar de rå-skrivna.
_LIKHET_RE = re.compile(r"(?<![<>=!:])=(?!=)")


def led_i_kedjan(segment: str) -> list[str]:
    """«a = b = c» → [a, b, c]. Ett segment utan likhetstecken ger ett led."""
    if not _rakningsbar(segment):
        return []
    bitar = [b.strip() for b in _LIKHET_RE.split(segment)]
    bitar = [b for b in bitar if b]
    return bitar if len(bitar) <= _MAX_LED else []


# ── Tolkningen ────────────────────────────────────────────────────────────

def tolka(led: str):
    """Ett normaliserat matteled → ett sympy-uttryck, eller None.

    HELA strängen läses, inte en bit ur den. Se modulens docstring om varför
    Math-Verifys egen ``parse`` inte duger här. Går det inte är svaret None, och
    None betyder ALLTID «otolkbar», aldrig «fel»."""
    v = verktyg()
    if v is None or not _rakningsbar(led):
        return None
    try:
        ut = v["latex2sympy"](led.strip())
    except Exception:                                   # noqa: BLE001
        return None
    try:
        return ut if isinstance(ut, v["sympy"].Basic) else None
    except Exception:                                   # noqa: BLE001
        return None


def _slutet_tal(uttryck) -> bool:
    """Ett uttryck som går att räkna ut till ETT tal: inga obekanta, inga
    funktioner appen inte känner («$A(12)$» är inte ett tal, det är ett anrop av
    en funktion som bara står i uppgiftstexten)."""
    v = verktyg()
    if v is None or uttryck is None:
        return False
    try:
        if uttryck.free_symbols or uttryck.atoms(v["AppliedUndef"]):
            return False
        return bool(uttryck.is_number)
    except Exception:                                   # noqa: BLE001
        return False


_DECIMAL_RE = re.compile(r"\d+\.(\d+)")


def _minsta_decimaler(*texter: str) -> int:
    """Hur många decimaler det MINST precisa talet i leden är skrivet med.

    Talet avgör toleransen, och det är hela poängen: «$= 18{,}75 = 18{,}8$» är
    en avrundning och inte ett räknefel. Vem som avrundar hur är talvaktens
    fråga (exam_gen.talsignaler), inte den här domarens."""
    d = [len(m.group(1)) for t in texter for m in _DECIMAL_RE.finditer(t)]
    return min(d) if d else 0


def _tolerans(*texter: str) -> float:
    """Hur mycket två led får skilja sig utan att det är ett fel.

    Heltal: 0,5. Alla riktiga heltalsfel är minst 1 stort, och ingen har
    avrundat något. Decimaler: en enhet på sista decimalen. Det är precis den
    slack en avrundning mitt i en kedja kostar, och mindre än varje riktigt
    räknefel jag sett i ett facit."""
    d = _minsta_decimaler(*texter)
    return 0.5 if d == 0 else 10.0 ** (-d)


def _talvarde(uttryck) -> complex | None:
    v = verktyg()
    try:
        return complex(v["sympy"].N(uttryck, 30))
    except Exception:                                   # noqa: BLE001
        return None


def lika_tal(a, b, tolerans: float = 0.5) -> bool | None:
    """Två slutna tal: lika (True), olika (False) eller obedömbara (None)."""
    ta, tb = _talvarde(a), _talvarde(b)
    if ta is None or tb is None:
        return None
    return abs(ta - tb) <= tolerans


# ── Numbas-tricket: likhet i slumpade punkter ─────────────────────────────
# `simplify` är det uppenbara valet och fel val: den kan spinna i minuter på ett
# uttryck och svarar ändå «vet inte» på de svåra fallen. Numbas (matematik-
# systemet bakom flera brittiska universitets självrättning) gör i stället det
# som fungerar i praktiken, sätter in slumpade tal i BÅDA uttrycken och
# jämför resultaten. Två uttryck som är lika i tolv slumpade punkter är lika, och
# de som inte är det avslöjas av den första punkten.
_PUNKTER = 12
_MIN_PUNKTER = 4
_FRO = 20260829                # samma slumptal varje körning. Domen ska vara
                               # deterministisk, inte «oftast likadan»


def likvardiga(a, b) -> bool | None:
    """Är två uttryck samma sak? True/False/None (går inte att avgöra).

    None är ett riktigt svar och det vanligaste när något är konstigt. Den som
    frågar ska behandla det som «rör den inte»."""
    v = verktyg()
    if v is None or a is None or b is None:
        return None
    sym = v["sympy"]
    try:
        if a.atoms(v["AppliedUndef"]) or b.atoms(v["AppliedUndef"]):
            return None
        fri = a.free_symbols | b.free_symbols
    except Exception:                                   # noqa: BLE001
        return None
    if not fri:
        return lika_tal(a, b, tolerans=1e-9)
    if len(fri) > 3:
        return None
    # Skiljer sig de obekanta åt är uttrycken olika saker: «$2x$» och «$2y$» är
    # två svarsalternativ och inte ett.
    if a.free_symbols != b.free_symbols:
        return False
    slump = random.Random(_FRO)
    traffar = 0
    for _ in range(_PUNKTER):
        # Bråk och inte flyttal: ett rationellt insättningsvärde håller sympy
        # exakt där det går, och 1/3 av punkterna hamnar inte på en singularitet
        # bara för att nämnaren råkade bli noll i flyttal.
        subs = {s: sym.Rational(slump.randint(-97, 97), slump.randint(2, 17))
                for s in fri}
        va, vb = _talvarde(a.subs(subs)), _talvarde(b.subs(subs))
        if va is None or vb is None:
            continue
        if any(x != x or abs(x) == float("inf") for x in (va, vb)):
            continue          # NaN eller pol, punkten säger ingenting
        skala = max(1.0, abs(va), abs(vb))
        if abs(va - vb) > 1e-9 * skala:
            return False
        traffar += 1
    return True if traffar >= _MIN_PUNKTER else None


# ── Fynden ────────────────────────────────────────────────────────────────

def _err(path: str, code: str, message: str) -> dict:
    """Samma form som exam_gen._err. Kopierad och inte importerad: exam_gen
    importerar den här modulen, och beroendet ska gå åt ett håll."""
    return {"path": path, "code": code, "message": message}


# Koden är `raknefel` och INTE `rakning`. Räknedomarens fynd heter `rakning`,
# och två kontroller som delar kod går inte att skilja åt i lärarens felruta,
# eller i ett test som mäter vad den ena av dem hittade.
KOD = "raknefel"

# Taket är detsamma som domarnas (exam_gen.MAX_DOMAR_PROBLEM) och av samma skäl:
# fler än så är inte en lista fel utan ett underkänt papper, och en
# reparationsprompt med tjugo krav lagar ingenting.
MAX_FYND = 6


def _kort(text: str, tak: int = 90) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= tak else text[:tak - 1] + "…"


def granska_kedjor(nr: str, losning: str) -> tuple[list[dict], dict]:
    """Likhetskedjorna i ETT facit. Returnerar (fynd, statistik).

    BARA SLUTNA TAL PÅ BÅDA SIDOR, och den regeln är dyrköpt. Ett led med en
    obekant i sig är nästan aldrig en identitet i ett facit. Det är en
    EKVATION, alltså ett påstående om vilket värde som söks och inte om vad två
    uttryck är värda. «$x^2 - 5x = 0$» och «$20t - 5t^2 = 0$» är riktiga rader i
    riktiga lösningsförslag, och en domare som läser dem som identiteter fäller
    dem båda. Första mätningen mot kassetterna gav sju sådana fällningar på ett
    band där facit var rätt hela vägen.

    Det som blir kvar, «$20 \\cdot 1{,}5 - 5 \\cdot 1{,}5^2 = 30 - 11{,}25 =
    18{,}75$», är däremot påståenden om tal, och de stämmer eller stämmer inte.
    Det är där räknefelen i ett facit sitter."""
    fynd: list[dict] = []
    stat = {"verifierade": 0, "motbevisade": 0, "otolkbara": 0}
    for segment in mattesegment(losning)[:_MAX_SEGMENT]:
        led = led_i_kedjan(segment)
        if len(led) < 2:
            stat["otolkbara"] += max(0, len(led))
            continue
        for vanster, hoger in zip(led, led[1:]):
            a, b = tolka(vanster), tolka(hoger)
            if not (_slutet_tal(a) and _slutet_tal(b)):
                stat["otolkbara"] += 1
                continue
            dom = lika_tal(a, b, _tolerans(vanster, hoger))
            if dom is None:
                stat["otolkbara"] += 1
            elif dom:
                stat["verifierade"] += 1
            else:
                stat["motbevisade"] += 1
                fynd.append(_err(
                    f"uppgift {nr}", KOD,
                    f"uppgift {nr}: ledet «{_kort(vanster, 60)} = "
                    f"{_kort(hoger, 60)}» i lösningsförslaget stämmer inte: "
                    "vänsterledet och högerledet är inte samma tal. Rätta "
                    "räkningen eller ändra uppgiftens tal; uppgift och facit "
                    "ska ändras TILLSAMMANS."))
    return fynd, stat


# Uppgiften måste SÄGA att den handlar om en ekvation. Utan den grinden blir
# varenda likhet i en uppgiftstext en ekvation att pröva facit mot, och en
# uppgiftstext är full av likheter som är något annat: givna värden, formler,
# definitioner. Orden är de svenska en uppgift faktiskt använder.
_EKVATIONSORD = re.compile(r"ekvation|lös\b|lösa\b|lösning", re.I)


def _basnamn(namn: str) -> str:
    """«x_1» och «x'» hör till «x». Facit skriver rötterna med index där
    uppgiften skriver den nakna bokstaven, och en jämförelse på hela namnet
    hade missat precis de fall som är värda att pröva."""
    return str(namn or "").split("_")[0].rstrip("'")


def _ekvation(uttryck):
    """Uttrycket som (obekant, vänsterled − högerled), eller None.

    Krav, och vart och ett har sitt skäl:

    * det ska VARA en likhet, inte ett uttryck;
    * EXAKT en obekant. «$x(40 - 2x) = k$» har två och är en familj ekvationer,
      inte en ekvation;
    * inga funktionsanrop. «$A(t) = 12 + 0{,}5t^2$» DEFINIERAR en funktion, och
      att sätta in ett tal i den definitionen bevisar ingenting;
    * ingen sida får vara en naken symbol. «$c = 7$» är ett GIVET värde i
      uppgiftstexten, och ett givet är inte något facit ska lösa.
    """
    v = verktyg()
    if v is None or uttryck is None:
        return None
    sym = v["sympy"]
    if not isinstance(uttryck, sym.Equality):
        return None
    try:
        vanster, hoger = uttryck.lhs, uttryck.rhs
        if uttryck.atoms(v["AppliedUndef"]):
            return None
        fria = uttryck.free_symbols
        if len(fria) != 1:
            return None
        if vanster.is_Symbol or hoger.is_Symbol:
            return None
        return next(iter(fria)), vanster - hoger
    except Exception:                                   # noqa: BLE001
        return None


def _rotpastaenden(losning: str) -> list[tuple[str, str, object]]:
    """[(basnamn, som det stod, värdet)]: facitets påstådda rötter.

    Bara «symbol = tal». «$x = 3 \\pm 2$» sållas bort av _OMOJLIGT långt innan
    den här, och «$x^2 = 25$» faller på att vänsterledet inte är en naken
    symbol."""
    v = verktyg()
    if v is None:
        return []
    ut = []
    for segment in mattesegment(losning)[:_MAX_SEGMENT]:
        x = tolka(segment)
        try:
            if not isinstance(x, v["sympy"].Equality) or not x.lhs.is_Symbol:
                continue
        except Exception:                               # noqa: BLE001
            continue
        if _slutet_tal(x.rhs):
            ut.append((_basnamn(x.lhs.name), segment.strip(), x.rhs))
    return ut


def granska_rot(nr: str, text: str, losning: str) -> tuple[list[dict], dict]:
    """Löser facitets svar den ekvation uppgiften ställer?

    EN riktning prövas: att ett värde facit påstår är en rot verkligen är det.
    Att facit TAPPAT en rot prövas inte. «vid $t = 0$ kastas bollen, så svaret
    är 4 s» är ett medvetet bortval och inte ett fel, och en vakt som inte kan
    skilja de fallen åt är en vakt som ropar varje gång."""
    stat = {"verifierade": 0, "motbevisade": 0, "otolkbara": 0}
    if not tillgangligt() or not _EKVATIONSORD.search(text or ""):
        return [], stat
    ekvationer = [e for e in (_ekvation(tolka(s))
                              for s in mattesegment(text)[:_MAX_SEGMENT])
                  if e is not None]
    rotter = _rotpastaenden(losning)
    if not ekvationer or not rotter:
        return [], stat
    fynd: list[dict] = []
    for sym, rest in ekvationer:
        egna = [r for r in rotter if r[0] == _basnamn(sym.name)]
        for _namn, sagt, varde in egna:
            noll = _talvarde(_satt_in(rest, sym, varde))
            if noll is None:
                stat["otolkbara"] += 1
                continue
            if abs(noll) <= 1e-6 * _skala(rest, sym, varde):
                stat["verifierade"] += 1
                continue
            stat["motbevisade"] += 1
            fynd.append(_err(
                f"uppgift {nr}", KOD,
                f"uppgift {nr}: facit svarar «{_kort(sagt, 40)}», men det "
                "värdet löser inte uppgiftens ekvation. Sätt in det och "
                "kontrollera. Rätta facit eller ändra uppgiftens tal; uppgift "
                "och facit ska ändras TILLSAMMANS."))
    return fynd, stat


def _satt_in(uttryck, sym, varde):
    try:
        return uttryck.subs({sym: varde})
    except Exception:                                   # noqa: BLE001
        return None


def _skala(rest, sym, varde) -> float:
    """Hur stora talen i ekvationen är. Resten mäts mot dem och inte mot noll.

    Utan skalan är «$0{,}000\\,001$» ett fel i en ekvation vars termer är
    miljoner, och «$0{,}5$» inget fel alls i en vars termer är tiondelar."""
    storst = 1.0
    try:
        for term in (rest.args or (rest,)):
            v = _talvarde(_satt_in(term, sym, varde))
            if v is not None and abs(v) == abs(v):      # inte NaN
                storst = max(storst, abs(v))
    except Exception:                                   # noqa: BLE001
        return 1.0
    return storst


def enheter(exam: dict) -> list[dict]:
    """[{nr, text, losning}]: en rad per uppgift och deluppgift som HAR ett
    facit. Numreringen är domarenheternas («4», «4b») så att fynden pekar på
    samma uppgift som nivå- och räknedomarens gör."""
    ut: list[dict] = []
    for i, u in enumerate((exam or {}).get("uppgifter") or [], 1):
        if not isinstance(u, dict):
            continue
        delar = [d for d in (u.get("deluppgifter") or []) if isinstance(d, dict)]
        if delar:
            for j, d in enumerate(delar):
                ut.append({"nr": f"{i}{chr(ord('a') + j)}",
                           "text": f"{u.get('text') or ''} {d.get('text') or ''}",
                           "losning": d.get("losning") or "",
                           "uppgift": u, "enhet": d})
            continue
        ut.append({"nr": str(i), "text": u.get("text") or "",
                   "losning": u.get("losning") or "",
                   "uppgift": u, "enhet": u})
    return ut


def granska(exam: dict) -> dict:
    """Hela pappret genom räkneverket.

    {"fel": [...], "statistik": {"verifierade", "motbevisade", "otolkbara",
    "enheter"}}. `fel` är tomt när biblioteken saknas. Då är varje led
    otolkbart per definition, och otolkbart fäller aldrig."""
    stat = {"verifierade": 0, "motbevisade": 0, "otolkbara": 0, "enheter": 0}
    fynd: list[dict] = []
    if not tillgangligt():
        return {"fel": [], "statistik": stat}
    for e in enheter(exam):
        if not (e["losning"] or "").strip():
            continue
        stat["enheter"] += 1
        for f, s in (granska_kedjor(e["nr"], e["losning"]),
                     granska_rot(e["nr"], e["text"], e["losning"])):
            fynd += f
            for k, n in s.items():
                stat[k] += n
    return {"fel": fynd[:MAX_FYND], "statistik": stat}


def sammanfattning(stat: dict) -> str:
    """Statistikraden läraren läser i loggen."""
    return (f"Räkneverket: {stat.get('verifierade', 0)} led verifierade, "
            f"{stat.get('motbevisade', 0)} motbevisade, "
            f"{stat.get('otolkbara', 0)} otolkbara "
            f"({stat.get('enheter', 0)} facit).")


# ══════════════════════════════ RÄKNEFELSBIBLIOTEKET ═══════════════════════
#
# Ett distraktoralternativ ska vara det eleven FÅR när hon gör ett bestämt fel,
# inte ett tal bredvid det rätta. Funktionerna nedan är de fel en
# gymnasielärare ser varje vecka, uttryckta som räkning på det verifierade
# facit-svaret. De används BARA efter modellen (prompten rörs aldrig, se
# kassetteregeln), och bara när ett alternativ måste bytas ut.
#
# Var och en returnerar en LISTA kandidater, och en tom lista betyder «det här
# felet går inte att göra på det här svaret». Det är inte ett undantag utan
# själva formen: «glömd ±-rot» är omöjlig på ett svar som redan är positivt.


def _teckenfel(varde, led):
    """Ett minustecken som tappats någonstans på vägen."""
    return [-varde] if varde != 0 else []


def _glomd_rot(varde, led):
    """«$\\pm$» blev «$+$»: eleven tog bara den positiva roten.

    Går bara att göra på ett NEGATIVT svar. Det är där den tappade halvan
    finns. Står den före teckenfelet i listan med flit: när båda kan ge samma
    tal är det här namnet det som säger läraren något."""
    try:
        return [-varde] if varde.is_negative else []
    except Exception:                                   # noqa: BLE001
        return []


def _kvadreringsregeln(varde, led):
    """$(a+b)^2 = a^2 + b^2$, kvadreringsregeln utan mittentermen.

    Felet finns bara att göra där det står en kvadrerad summa, alltså på ett
    svar som fortfarande bär sitt uttryck. Ett färdigt tal har ingen parentes
    kvar att göra fel på."""
    v = verktyg()
    if v is None:
        return []
    sym = v["sympy"]

    def fel(nod):
        if isinstance(nod, sym.Pow) and nod.exp == 2 and isinstance(nod.base, sym.Add):
            return sym.Add(*[t ** 2 for t in nod.base.args])
        return nod

    ut = []
    for kandidat in [varde] + list(led or []):
        try:
            bytt = kandidat.replace(
                lambda n: isinstance(n, sym.Pow) and n.exp == 2
                and isinstance(n.base, sym.Add), fel)
        except Exception:                               # noqa: BLE001
            continue
        if bytt != kandidat:
            ut.append(bytt)
    return ut


def _faktor_tva(varde, led):
    """Tvåan som glömdes eller kom med en gång för mycket: halva basen i en
    triangel, derivatan av $x^2$, dubbla roten."""
    v = verktyg()
    if v is None or varde == 0:
        return []
    tva = v["sympy"].Integer(2)
    return [varde * tva, varde / tva]


def _fel_tiopotens(varde, led):
    """Kommat på fel plats: en tiopotens fel i endera riktningen."""
    v = verktyg()
    if v is None or varde == 0:
        return []
    tio = v["sympy"].Integer(10)
    return [varde * tio, varde / tio]


def _delresultat(varde, led):
    """Ett mellanled som lämnats in som slutsvar.

    Det klassiska felet på en flerstegsuppgift, och den enda distraktorn som
    inte går att räkna fram: den måste HÄMTAS ur lösningsgången. Därför bär
    `led` facitets egna mellanled."""
    ut = []
    for x in led or []:
        if x != varde and x not in ut:
            ut.append(x)
    return ut


def _avrundningsfel(varde, led):
    """Avhugget i stället för avrundat, eller avrundat ett steg för tidigt."""
    v = verktyg()
    if v is None:
        return []
    sym = v["sympy"]
    try:
        if not varde.is_real or varde.is_Integer:
            return []
        f = float(varde)
    except Exception:                                   # noqa: BLE001
        return []
    ut = []
    for decimaler in (1, 0):
        hugget = int(f * 10 ** decimaler) / 10 ** decimaler
        for kandidat in (sym.Float(hugget), sym.Float(round(f, decimaler))):
            if kandidat not in ut:
                ut.append(kandidat)
    return ut


RAKNEFEL: tuple[tuple[str, object], ...] = (
    ("glömd ±-rot", _glomd_rot),
    ("teckenfel", _teckenfel),
    ("kvadreringsregeln", _kvadreringsregeln),
    ("faktor 2", _faktor_tva),
    ("fel tiopotens", _fel_tiopotens),
    ("delresultat som slutsvar", _delresultat),
    ("avrundningsfel", _avrundningsfel),
)


def kandidater(ratt, led=None) -> list[tuple[str, object]]:
    """[(felets namn, uttrycket)]: hela biblioteket tillämpat på ett svar,
    i listans ordning och utan dubbletter."""
    ut: list[tuple[str, object]] = []
    sedda = []
    for namn, fel in RAKNEFEL:
        try:
            forslag = fel(ratt, led or [])
        except Exception:                               # noqa: BLE001
            continue
        for x in forslag:
            if x is None or x == ratt or any(x == y for y in sedda):
                continue
            sedda.append(x)
            ut.append((namn, x))
    return ut


# ── Alternativen som text ─────────────────────────────────────────────────

def formatera(uttryck, mall: str = "") -> str:
    """Ett sympy-uttryck till svensk matematiktext, i samma skepnad som
    alternativet det ersätter: dollartecken om grannarna har det, decimalkomma
    alltid (LaTeX-formen «{,}», som resten av appen skriver den)."""
    v = verktyg()
    if v is None:
        return ""
    sym = v["sympy"]
    try:
        if uttryck.is_Integer:
            kropp = str(int(uttryck))
        elif uttryck.is_Rational and not uttryck.is_Integer:
            kropp = (f"\\frac{{{uttryck.p}}}{{{uttryck.q}}}" if uttryck.q > 0
                     else sym.latex(uttryck))
        elif uttryck.is_Float:
            # Sex decimaler räcker för allt en gymnasieuppgift svarar, och
            # nollorna på slutet ska inte följa med: «18{,}750000» är inget
            # svarsalternativ någon skriver.
            kropp = f"{float(uttryck):.6f}".rstrip("0").rstrip(".")
        else:
            kropp = sym.latex(uttryck)
    except Exception:                                   # noqa: BLE001
        return ""
    kropp = kropp.replace(".", "{,}")
    return f"${kropp}$" if "$" in (mall or "") else kropp


def _mellanled(losning: str) -> list:
    """Facitets egna mellanled som tal, underlaget till «delresultat som
    slutsvar»."""
    ut = []
    for segment in mattesegment(losning)[:_MAX_SEGMENT]:
        for bit in led_i_kedjan(segment):
            x = tolka(bit)
            if _slutet_tal(x) and x not in ut:
                ut.append(x)
    return ut


def laga_flerval(exam: dict) -> list[str]:
    """Distraktorerna, prövade och lagade EFTER modellen.

    Två fel gör en flervalsfråga olöslig, och båda är ren aritmetik att hitta:
    ett alternativ som är lika med det rätta (då finns två rätta svar), och två
    alternativ som är lika med varandra (då är det ena bortkastat). Likheten
    mäts med Numbas-tricket (:func:`likvardiga`) och inte med `simplify`. «$0
    {,}5$» och «$\\frac{1}{2}$» ÄR samma alternativ, och det är just den sortens
    krock modellen gör.

    Kollisionen lagas med ett namngivet räknefel ur biblioteket ovan, inte med
    ett slumptal: ett alternativ ska vara det eleven får när hon räknar fel, och
    ett tal bredvid det rätta lär henne ingenting.

    FAIL-OPEN: går ett alternativ inte att tolka rörs det aldrig («☐ Kordasatsen»
    är ett fullgott svarsalternativ och inte ett tal), och finns ingen kandidat
    som är skild från alla andra lämnas raden som den är. Returnerar en rad per
    ändring, för loggen."""
    logg: list[str] = []
    if not tillgangligt():
        return logg
    for e in enheter(exam):
        enhet = e["enhet"]
        alt = enhet.get("alternativ")
        ratt_i = enhet.get("ratt_alternativ")
        if not isinstance(alt, list) or len(alt) < 2:
            continue
        if not isinstance(ratt_i, int) or not 0 <= ratt_i < len(alt):
            continue
        tolkade = [tolka(s) for s in
                   [normalisera(str(a or "")).strip("$ ") for a in alt]]
        ratt = tolkade[ratt_i]
        if ratt is None:
            continue                      # rätt svar är text, inget att räkna
        led = _mellanled(e["losning"])
        for i, x in enumerate(tolkade):
            if i == ratt_i or x is None:
                continue
            krock = _krockar(i, x, tolkade, ratt_i)
            if not krock:
                continue
            ny = _ersattning(ratt, led, tolkade, alt[ratt_i])
            if ny is None:
                logg.append(f"uppgift {e['nr']}: alternativ "
                            f"{chr(ord('A') + i)} krockar med {krock}, men "
                            "inget räknefel gav ett skilt svar, lämnat orört.")
                continue
            namn, uttryck = ny
            alt[i] = formatera(uttryck, alt[ratt_i])
            tolkade[i] = uttryck
            logg.append(f"uppgift {e['nr']}: alternativ {chr(ord('A') + i)} "
                        f"krockade med {krock}, bytt mot «{alt[i]}» "
                        f"({namn}).")
    return logg


def _krockar(i: int, x, tolkade: list, ratt_i: int) -> str:
    """Vad alternativ `i` krockar med, som text, eller tomt."""
    if likvardiga(tolkade[ratt_i], x) is True:
        return "det rätta svaret"
    for j in range(i):
        if j != ratt_i and tolkade[j] is not None \
                and likvardiga(tolkade[j], x) is True:
            return f"alternativ {chr(ord('A') + j)}"
    return ""


def _ersattning(ratt, led, tolkade: list, mall: str):
    """Första räknefelet som ger ett svar skilt från allt annat på raden."""
    for namn, uttryck in kandidater(ratt, led):
        if any(t is not None and likvardiga(t, uttryck) is True
               for t in tolkade):
            continue
        if not formatera(uttryck, mall):
            continue
        return namn, uttryck
    return None
