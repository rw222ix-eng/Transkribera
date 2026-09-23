"""WB-JSON v1 — LLM-säker delmängd av whiteboard-motorns board-spec.

Motorns fulla spec är JS (bl.a. ``plots: [{ fn: (x) => … }]``) — funktioner
kan inte uttryckas i JSON och rå JS från en LLM ska aldrig eval:as. WB-JSON v1
är därför en strikt JSON-serialiserbar delmängd med två anpassningar:

* ``plots[].fn`` ersätts av ``plots[].expr`` — en uttryckssträng
  ("x^2 - 2*x + 1") som klienten kompilerar med en egen liten parser
  (``app/web/static/whiteboard/expr.js``). Den här modulen speglar parserns
  grammatik för serversidig syntaxvalidering (:func:`validate_expr`).
* Nästling är begränsad: ``callout``/``row``/``col`` får bara innehålla
  "löv"-sektioner (text/math/list/stack/divider/spacer + figurerna
  graph/shape), och ``row`` dessutom ``col``. Det håller json-schemat fritt
  från rekursion — llama-servers grammatiktvång får en ändlig grammatik — och
  begränsar samtidigt LLM:ens felyta. Figurerna släpptes in i behållarna när
  läraren sa att tavlan inte utnyttjade bredden: en graf till vänster och
  formlerna till höger om den kräver en ``row`` som får bära en ``graph``.

Tre lager:

1. Pydantic-modellerna (schema): :class:`BoardDoc` m.fl.
2. :func:`to_response_format` — json_schema-objektet till llama-server
   (samma mönster som ``EXTRACT_RESPONSE_FORMAT`` i app/postprocess.py).
3. :func:`validate_board_json` + :func:`validate_rules` — deterministisk
   validering; regelvalidatorerna fångar det schemat inte kan uttrycka
   (designprojektets SKILL.md-invarianter). Fel returneras som
   maskinläsbar lista ``[{"path", "code", "message"}]`` som
   reparationsloopen i app/lesson_board.py formulerar om till en
   korrigeringsprompt.
"""
from __future__ import annotations

import json
import re
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, ValidationError

# Tankstrecksvakten, delad med provet, arbetsbladet, gruppuppgiften och
# anteckningarna (spåret 2026-09-06). Beroendet går bara åt det här hållet.
from app import textvakt

Color = Literal["black", "blue", "red", "green", "orange", "purple"]


class _Model(BaseModel):
    # extra="forbid": okända props ska ge valideringsfel (inte tyst ignoreras)
    # så reparationsloopen kan tala om för modellen exakt vad som är fel.
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


# --------------------------------------------------------------- sektioner --

class _SectionBase(_Model):
    seed: int | None = None
    rotate: float | None = None
    color: Color | None = None
    gapAfter: float | None = None
    align: Literal["left", "center"] | None = None


class UnderlineOpts(_Model):
    color: Color | None = None
    amplitude: float | None = None
    thickness: float | None = None
    reserve: float | None = None


class HeadingSection(_SectionBase):
    kind: Literal["heading"]
    text: str
    size: float | None = None
    weight: int | None = None
    underline: UnderlineOpts | None = None


class TextSection(_SectionBase):
    kind: Literal["text"]
    text: str
    size: float | None = None
    weight: int | None = None
    nowrap: bool | None = None
    font: Literal["primary", "alt", "mono"] | None = None


class MathSection(_SectionBase):
    kind: Literal["math"]
    latex: str
    size: float | None = None
    display: bool | None = None


class ListSection(_SectionBase):
    kind: Literal["list"]
    items: list[str]
    bullet: str | None = None
    size: float | None = None
    indent: float | None = None
    gap: float | None = None


class StackRow(_Model):
    value: str
    op: str | None = None
    bar: Literal["above"] | None = None
    offset: int | None = None


class StackSection(_SectionBase):
    kind: Literal["stack"]
    rows: list[StackRow]
    digitSize: float | None = None
    gap: float | None = None


class DividerSection(_SectionBase):
    kind: Literal["divider"]
    width: float | None = None
    dashed: bool | None = None


class UnderlineSection(_SectionBase):
    kind: Literal["underline"]
    width: float | None = None
    amplitude: float | None = None
    thickness: float | None = None


class SpacerSection(_Model):
    kind: Literal["spacer"]
    size: float | None = None


class TableSection(_SectionBase):
    kind: Literal["table"]
    headers: list[str] | None = None
    rows: list[list[str]]
    cellW: float | None = None
    cellH: float | None = None


class CircleSection(_SectionBase):
    kind: Literal["circle"]
    text: str
    shape: Literal["ellipse", "rect"] | None = None
    size: float | None = None


class ShapeLabels(_Model):
    # Explicit modell (inte dict[Literal, str]): Pydantic gör dict-nycklar
    # till "propertyNames" i json-schemat, vilket llama.cpp-grammatiken inte
    # tvingar — modellen hittade då på hörnnamn (A/B/C) som nycklar.
    # Fasta optionella fält tvingas däremot av grammatiken (bench Fas 2).
    top: str | None = None
    left: str | None = None
    right: str | None = None
    bottom: str | None = None
    inside: str | None = None


class ShapeSection(_SectionBase):
    kind: Literal["shape"]
    type: Literal["right-triangle", "triangle", "rect", "circle"]
    width: float
    height: float
    # Motorns `angles`-prop är utelämnad ur v1 av samma grammatikskäl
    # (fri dict) — vinkelmarkeringar görs via graph-arcs i stället.
    labels: ShapeLabels | None = None


# ------------------------------------------------------------------- graf --

class PlotSpec(_Model):
    # expr i stället för motorns fn — kompileras av expr.js vid rendering.
    expr: str
    color: Color | None = None
    thickness: float | None = None
    steps: int | None = None


class PolygonSpec(_Model):
    pts: list[tuple[float, float]] = Field(min_length=3)
    fill: Color | None = None
    fillOpacity: float | None = None
    stroke: Color | None = None
    strokeWidth: float | None = None


class ArcSpec(_Model):
    cx: float
    cy: float
    r: float
    from_: float = Field(alias="from")
    to: float
    color: Color | None = None
    strokeWidth: float | None = None
    interior: tuple[float, float] | None = None
    label: str | None = None
    labelSize: float | None = None
    labelColor: Color | None = None
    labelWeight: int | None = None
    labelItalic: bool | None = None


class ArrowSpec(_Model):
    # Vektorer ritas ALLTID som arrows, aldrig polygoner (SKILL.md-invariant).
    from_: tuple[float, float] = Field(alias="from")
    to: tuple[float, float]
    color: Color | None = None
    strokeWidth: float | None = None
    headSize: float | None = None
    dashed: bool | None = None


class RightAngleSpec(_Model):
    x: float
    y: float
    leg1: tuple[float, float]
    leg2: tuple[float, float]
    size: float | None = None
    color: Color | None = None
    strokeWidth: float | None = None


class BraceSpec(_Model):
    x1: float
    y1: float
    x2: float
    y2: float
    bulge: float | None = None
    color: Color | None = None
    strokeWidth: float | None = None


class PointSpec(_Model):
    x: float
    y: float
    color: Color | None = None
    size: float | None = None
    label: str | None = None
    labelSize: float | None = None
    outward: tuple[float, float] | None = None
    labelGap: float | None = None


class GraphTextSpec(_Model):
    x: float
    y: float
    text: str
    size: float | None = None
    color: Color | None = None
    anchor: Literal["start", "middle", "end"] | None = None
    italic: bool | None = None
    weight: int | None = None
    rotate: float | None = None
    dx: float | None = None
    dy: float | None = None
    sup: str | None = None


class TickSpec(_Model):
    axis: Literal["x", "y"]
    at: float
    label: str | None = None
    size: float | None = None
    dx: float | None = None
    dy: float | None = None


class GraphSection(_SectionBase):
    kind: Literal["graph"]
    width: float
    height: float
    xRange: tuple[float, float]
    yRange: tuple[float, float]
    grid: bool | None = None
    axes: bool | None = None
    gridStep: float | None = None
    xLabel: str | None = None
    yLabel: str | None = None
    padding: float | None = None
    polygons: list[PolygonSpec] | None = None
    plots: list[PlotSpec] | None = None
    arcs: list[ArcSpec] | None = None
    arrows: list[ArrowSpec] | None = None
    rightAngles: list[RightAngleSpec] | None = None
    braces: list[BraceSpec] | None = None
    points: list[PointSpec] | None = None
    texts: list[GraphTextSpec] | None = None
    ticks: list[TickSpec] | None = None


# --------------------------------------------------------------- behållare --
# Definieras EFTER graferna: en behållare får bära en figur (se modulens
# docstring), och Pydantic behöver klassen innan den refereras.

# Löv-sektioner som får ligga inuti callout/row/col (ingen rekursion —
# json-schemat förblir ändligt för grammatiktvånget).
# `underline` är med men INTE `heading`: motorn ritar en headings underline i
# sidflödet (layoutFlow), inte i renderSection, så en heading inne i en
# behållare hade tappat sitt streck utan att någon märkte det. Understrykningen
# som egen sektion fungerar överallt — och det är den läraren gör för hand.
LeafSection = Annotated[
    Union[TextSection, MathSection, ListSection, StackSection,
          DividerSection, UnderlineSection, SpacerSection, GraphSection,
          ShapeSection],
    Field(discriminator="kind"),
]


class CalloutSection(_SectionBase):
    kind: Literal["callout"]
    children: list[LeafSection]
    padding: float | None = None
    fill: bool | None = None
    fillOpacity: float | None = None


class ColSection(_SectionBase):
    kind: Literal["col"]
    children: list[LeafSection]
    gap: float | None = None
    flex: str | None = None
    width: float | None = None


# En row får bära en col — och bara där. Det är EN nivå djupare än löven och
# ger mönstret läraren bad om: figur till vänster, en spalt med formler till
# höger. Djupare än så går inte v1: schemat måste förbli ändligt.
RowChild = Annotated[
    Union[TextSection, MathSection, ListSection, StackSection,
          DividerSection, UnderlineSection, SpacerSection, GraphSection,
          ShapeSection, ColSection],
    Field(discriminator="kind"),
]


class RowSection(_SectionBase):
    kind: Literal["row"]
    children: list[RowChild]
    gap: float | None = None
    justify: Literal["flex-start", "center", "flex-end", "space-between"] | None = None
    wrap: bool | None = None
    width: float | None = None


Section = Annotated[
    Union[HeadingSection, TextSection, MathSection, ListSection, StackSection,
          TableSection, GraphSection, ShapeSection, CircleSection,
          UnderlineSection, DividerSection, CalloutSection, RowSection,
          ColSection, SpacerSection],
    Field(discriminator="kind"),
]


# ------------------------------------------------------------------ tavla --

class Padding(_Model):
    top: float = 30
    right: float = 30
    bottom: float = 30
    left: float = 30


class Column(_Model):
    weight: float = 1
    sections: list[Section]


class AnnotationArrow(_Model):
    kind: Literal["arrow"]
    x1: float
    y1: float
    x2: float
    y2: float
    color: Color | None = None


class AnnotationCircle(_Model):
    kind: Literal["circle"]
    text: str
    x: float
    y: float
    color: Color | None = None
    padding: float | None = None


Annotation = Annotated[
    Union[AnnotationArrow, AnnotationCircle], Field(discriminator="kind")
]


class Board(_Model):
    width: float
    height: float
    padding: Padding | None = None
    chrome: Literal["minimal", "aluminium", "wood", "blackboard", "paper"] | None = None
    tray: bool | None = None
    color: Color | None = None
    name: str | None = None
    gap: float | None = None
    sections: list[Section] | None = None
    columns: list[Column] | None = None
    annotations: list[Annotation] | None = None


class BoardDoc(_Model):
    """Toppnivån som LLM:en genererar: titel + en eller två tavlor."""
    title: str
    boards: list[Board] = Field(min_length=1, max_length=2)


def to_response_format() -> dict:
    """json_schema-objekt för llama-servers grammatiktvång
    (mönster: EXTRACT_RESPONSE_FORMAT i app/postprocess.py)."""
    return {
        "type": "json_schema",
        "json_schema": {"name": "lektionstavla", "schema": BoardDoc.model_json_schema()},
    }


# ------------------------------------------------- uttrycksparser (spegel) --
# Speglar grammatiken i app/web/static/whiteboard/expr.js — håll dem i synk.
# expr := term (('+'|'-') term)* ; term := unary (('*'|'/') unary)* ;
# unary := '-' unary | power ; power := atom ('^' unary)? ; atom := tal | x |
# konstant | funk '(' expr ')' | '(' expr ')'

EXPR_FUNCTIONS = ("sin", "cos", "tan", "sqrt", "log", "ln", "exp", "abs")
EXPR_CONSTANTS = ("pi", "e")

_TOKEN_RE = re.compile(r"\s*(?:(\d+(?:\.\d+)?)|([a-zA-Z]+)|([+\-*/^()]))")


class _ExprError(ValueError):
    pass


def _tokenize_expr(src: str) -> list[str]:
    tokens: list[str] = []
    pos = 0
    while pos < len(src):
        m = _TOKEN_RE.match(src, pos)
        if not m or m.end() == pos:
            rest = src[pos:].strip()
            if not rest:
                break
            raise _ExprError(f"otillåtet tecken '{rest[0]}'")
        num, ident, op = m.groups()
        if ident is not None:
            if ident != "x" and ident not in EXPR_FUNCTIONS and ident not in EXPR_CONSTANTS:
                raise _ExprError(
                    f"okänt namn '{ident}' (tillåtet: x, {', '.join(EXPR_FUNCTIONS + EXPR_CONSTANTS)})")
        tokens.append(num or ident or op)
        pos = m.end()
    return tokens


def _parse_expr(tokens: list[str]) -> None:
    """Ren syntaxkontroll (ingen evaluering) — kastar _ExprError vid fel."""
    i = 0

    def peek() -> str | None:
        return tokens[i] if i < len(tokens) else None

    def take() -> str:
        nonlocal i
        if i >= len(tokens):
            raise _ExprError("uttrycket slutar oväntat")
        i += 1
        return tokens[i - 1]

    def expr() -> None:
        term()
        while peek() in ("+", "-"):
            take()
            term()

    def term() -> None:
        unary()
        while peek() in ("*", "/"):
            take()
            unary()

    def unary() -> None:
        if peek() == "-":
            take()
            unary()
        else:
            power()

    def power() -> None:
        atom()
        if peek() == "^":
            take()
            unary()

    def atom() -> None:
        tok = take()
        if re.fullmatch(r"\d+(?:\.\d+)?", tok) or tok == "x" or tok in EXPR_CONSTANTS:
            return
        if tok in EXPR_FUNCTIONS:
            if take() != "(":
                raise _ExprError(f"'{tok}' måste följas av '('")
            expr()
            if take() != ")":
                raise _ExprError("')' saknas")
            return
        if tok == "(":
            expr()
            if take() != ")":
                raise _ExprError("')' saknas")
            return
        raise _ExprError(f"oväntat '{tok}'")

    expr()
    if i != len(tokens):
        raise _ExprError(f"oväntat '{tokens[i]}' efter uttryckets slut")


def validate_expr(src: str) -> str | None:
    """None om `src` är ett giltigt uttryck, annars svensk felbeskrivning."""
    try:
        tokens = _tokenize_expr(src)
        if not tokens:
            raise _ExprError("tomt uttryck")
        _parse_expr(tokens)
        return None
    except _ExprError as e:
        return str(e)


# --------------------------------------------------------- regelvalidering --

_DECIMAL_POINT_RE = re.compile(r"\d\.\d")
# Strängfält som INTE är läsbar text och därför undantas decimalkommakollen.
_DECIMAL_EXEMPT_KEYS = {"expr", "name", "kind", "font", "bullet", "op",
                        "anchor", "axis", "shape", "type", "flex", "justify"}
# Bench Fas 2: modellen skrev LaTeX i text-fält ("$ A = \\frac{1}{2}ab … $")
# och glömde dubblera backslash i JSON, så \f/\t blev kontrolltecken och
# kommandona trasiga ("rac", "imes"). Renderar utan [WB]-varningar men ser
# trasigt ut på tavlan — fångas därför deterministiskt här.
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_LATEX_COMMAND_RE = re.compile(r"\\[a-zA-Z]+")

# Kolumngap-approximation för bredd-budgeten (motorn flödar kolumner med ett
# internt mellanrum; exakt värde spelar mindre roll än att fånga grafer som
# är uppenbart för breda för sin kolumn).
_COL_GAP = 24.0
# Motorn sätter ingen bredd på fristående text-sektioner: en lång löptext
# mäts mot hela tavelbredden men placeras i ett smalare flöde → "ryms inte
# (bredd)" + överlapp med nästa sektion (bench Fas 2). Deterministisk gräns
# här ger modellen ett exakt, åtgärdbart fel FÖRE rendering.
#
# SÄNKTA 2026-09-05 (90 → 60 och 80 → 50). Lärarens dom över fem genererade
# tavlor: «det känns lite mycket på vissa ställen. Dels är det svårt att få med
# allt på tavlan när jag väl ska skriva allt detta, dels kan det vara svårt att
# hinna innan lektionen att rita och skriva allt, samt att det är svårt för
# eleverna att hänga med. Hellre korta namn bara i stället för hela meningar,
# och om det ska vara meningar ska de vara korta.» En rad på 90 tecken ÄR en
# mening; ett namn med sin förklaring ryms i 60. Metodstegen (listpunkter) är
# stödrepliker läraren ska ha i huvudet, inte skriva av: 50.
_MAX_TEXT_CHARS = 60
_MAX_ITEM_CHARS = 50
# TEXTBUDGETEN (Del F, lärarens fjärde dom). Reglerna ovan mäter en sektion i
# taget och släpper därför igenom en tavla som är full av korta rader — och det
# var precis vad läraren fick: hennes egen vänstertavla bar upplägg, nyckelfråga,
# två vägar OCH en funktion-mot-ekvation-jämförelse, drygt 550 tecken text, och
# hon skrev aldrig upp det mesta av det. «Det är för mycket att skriva.»
#
# Budgeten mäter SUMMAN av läsbar text per tavla — text-sektioner och
# listpunkter, inte rubriker (de är korta och nödvändiga), inte matte (formler
# är just det tavlan ska bära) och inte tabellceller (att flytta fyra fall från
# meningar till en tabell är precis åtgärden budgeten vill framkalla).
#
# Talet är MÄTT, inte satt: few-shotarna ligger på 49–194 tecken, förlagans
# underkända vänstertavla på 603 (23 textrutor) och dess högertavla på 812 —
# varav ~290 är sammanfattningen, som i WB-JSON blir en table och inte räknas.
# 400 lämnar alltså gott om luft för en tät men skrivbar tavla och fäller den
# som blivit ett föredrag.
#
# Och den kostar inga rundor. Omspelningen efter Del F (2026-08-09) gav en
# skarp tavla på 154 respektive 26 tecken — med en table-sektion på högertavlan
# — och den gick igenom på EN runda, precis som före budgeten.
#
# OMMÄTT 2026-08-21: lärarens egna nya krav på exemplen — Väg 1/Väg 2 som två
# rader, exakt-mot-närmevärde utskrivet, randfallet som egen vändning — landar
# på 430–500 tecken över en tvåkolumnstavla, och fyra inspelningar i rad föll
# på 400-taket trots att varje rad var beställd. Taket är per FLÖDE: en tavla
# med columns bär flera exempelspalter och får 250 per spalt (två kolumner →
# 500); en sections-tavla behåller 400. Fortfarande mätt, inte satt: lärarens
# underkända högertavla på 812 fälls med god marginal.
#
# SÄNKTA 2026-09-05 (400 → 280 och 250 → 170). Samma dom som sänkte
# radlängderna ovan: «det är svårt att få med allt på tavlan när jag väl ska
# skriva allt detta.» Räknat på den vänstertavla hon fällde blev det ~20
# skrivna enheter: rubrik, fyra agendapunkter, öppningsfråga, definition, två
# uppställningar med fyra etiketter, tre begreppsrader, två formler och ett
# vanligt fel med rubrik, formel och mening. Hennes eget tal var 12. Taken är
# mätta mot few-shotarna efter trimningen (vänstertavlorna 217–268, kolumnerna
# 83–154) och lämnar luft för en tät tavla, men fäller den som blivit ett
# föredrag. Läraren sänkte 400 själv i augusti; nu sänkte hon igen.
#
# OMMÄTT 2026-09-20 (280 → 390). Motsatt dom, samma lärare, över tavlan för
# Origo 2a 1.3 Andragradsekvationer: «rätt men för lite och för spretigt;
# eleverna får inte det som gör att de kan börja i boken.» Vänstern fick ett
# fast skelett med tre nya delar — ankaret med sin etikett, receptet och
# «Att tänka på» (lesson_board 8d, 8f, 8g) — och 280 räckte inte till dem.
# Taket är MÄTT, inte satt, precis som förut: few-shotarnas vänstertavlor
# bär efter omskrivningen 332, 338, 339 och 340 tecken, och 340 + 15 % är
# 391. Tak 390, alltså, och det är fortfarande ett tak: den fällda tavlans
# 603 tecken faller med stor marginal.
#
# Talet rör bara TAVLAN. Kolumntaket 170 står kvar orört — högertavlan
# ändrades inte, och dess spalter mäter 0–154. Modelltavlans 400 (nedan) står
# också kvar: den lämnar fortfarande mer, men marginalen är numera liten,
# för det mesta av det modelltavlan behövde extra plats till har blivit
# skelett för alla tavlor.
#
# SÄNKT 2026-09-21 (390 → 270). Lärarens dom över kvällens två tavlor
# (NA26F potenslagarna i regelsamlingsformen, IndA nollproduktmetoden):
# «de har blivit lite bättre. Problemet är bara att det blir så jävla mycket
# på vänstra tavlan. Det vore bra att korta ner det, kanske 30 %, bara ha
# kvar det mest väsentliga, ta bort lite text, och lägga till kanske någon
# pil eller två.» Hennes egen procent, alltså: 390 − 30 % är 273.
#
# Skelettet från 2026-09-20 står kvar — anatomin, ankaret, formeln,
# receptet, ett randfall — och det är TEXTEN omkring det som betalar:
# definitionsmeningen (den står redan i anatomin och i öppningsfrågan),
# den tredje agendapunkten, den tredje begreppsraden, den tredje
# receptpunkten och det tredje randfallet. Matematiken kostar fortfarande
# ingenting, och pilarna (\Downarrow mellan ankaret och formeln) är math:
# tråden blir tydligare samtidigt som tavlan blir tunnare.
#
# Mätt som förut, mot few-shotarna efter kortningen: deras vänstertavlor bär
# 162–180 tecken (var 235–260). Kvällens två tavlor mäter 303 (NA26F) och
# 442 (IndA) med de nya etikettreglerna och faller båda — det är hela
# poängen: det som ska falla är texten, inte skelettet, och båda tavlorna
# bär sitt skelett med god marginal under taket när prosan är struken.
_MAX_BOARD_TEXT = 270
_MAX_COLUMN_TEXT = 170
# MODELLTAVLOR FÅR MER (lärarens beslut 2026-09-17). Hennes godkända tavla
# för Liber Ma1c s. 69–72 (formler ur verkligheten: ställa upp, jämföra,
# rimlighet) bar 392 tecken på vänstern och 403 över två kolumner — varje
# bokstav förklarad med enhet, hela frågor om giltighet, tolkningen i ord —
# och föll på 280/340 fast varje rad var hennes egen. En modellektion är ord
# på ett sätt en algebralektion inte är. Taken nedan är mätta mot den tavlan
# (tests/test_modellregler.godkand_tavla) med samma luft som 280 lämnar
# few-shotarna.
#
# Vad som ÄR en modelltavla avgörs ur tavlan själv, inte ur uppdraget, för
# validate_board_json anropas från varje väg (skrivning, lapp, omskrivning,
# render-report) och bara tavlan följer med överallt. Kännetecknet är just
# det regel 8b annars förbjuder: en formel MED TAL på vänstertavlan, «K = 200
# + 0,80x», «V = 400 − 50t» — en bokstav till vänster om = och minst två
# tal (≥ 2 siffror eller decimaltal) till höger. Ett ensamt tal räcker inte
# (O = 2πr är geometri) och \frac{1}{2}bh har bara ensiffriga tal.
#
# MODELLTAKEN RÖRDES INTE 2026-09-21 när den vanliga budgeten gick till 270.
# De är mätta mot en tavla läraren själv godkände (392 tecken), och sänker
# man dem fälls hennes egen tavla av generatorn nästa gång någon skriver om
# den. Skillnaden 270/400 är stor nu, och den är det med flit: en
# modellektion är ord på ett sätt en algebralektion inte är.
_MAX_BOARD_TEXT_MODELL = 400
_MAX_COLUMN_TEXT_MODELL = 220
_ASPECT_TOLERANCE = 0.15  # motorn varnar vid >15 % avvikelse
_VERTEX_EPS = 1e-6


def _err(path: str, code: str, message: str) -> dict:
    return {"path": path, "code": code, "message": message}


def _walk_strings(value, path: str, out: list[dict], key: str = "") -> None:
    if isinstance(value, str):
        if _DECIMAL_POINT_RE.search(value):
            out.append(_err(path, "decimalpunkt",
                            f"'{value}' innehåller decimalpunkt — använd decimalkomma "
                            "(i LaTeX: 4{,}58)."))
        if _CONTROL_CHAR_RE.search(value):
            out.append(_err(path, "kontrolltecken",
                            f"'{value[:60]}' innehåller kontrolltecken — troligen en "
                            "o-escapad backslash i JSON (\\f i \\frac blir sidmatning). "
                            "Backslash skrivs \\\\ i JSON-strängar."))
        if "$" in value:
            out.append(_err(path, "latex-i-text",
                            f"'{value[:60]}' innehåller $-tecken — matematik skrivs i "
                            "math-sektionens latex-fält, utan dollartecken."))
        elif key != "latex" and _LATEX_COMMAND_RE.search(value):
            out.append(_err(path, "latex-i-text",
                            f"'{value[:60]}' ser ut att innehålla LaTeX — matematik "
                            "skrivs i en math-sektion (fältet latex), inte i text/"
                            "list/tabeller."))
    elif isinstance(value, dict):
        for k, v in value.items():
            if k in _DECIMAL_EXEMPT_KEYS:
                continue
            _walk_strings(v, f"{path}.{k}", out, key=k)
    elif isinstance(value, (list, tuple)):
        for idx, v in enumerate(value):
            _walk_strings(v, f"{path}[{idx}]", out, key=key)


def _iter_graphs(sections: list, width: float, path: str):
    """(graph, tillgänglig bredd, path) för alla grafer i ett sektionsflöde.

    Går ned i callout/row/col: sedan figurerna får ligga i en row (figur till
    vänster, formler till höger) hade en graf inuti en behållare annars sluppit
    ALLA grafregler — bredd, cirkelaspekt, interior, uttryckssyntax. Bredden
    som skickas med är flödets, alltså tilltagen för en graf som delar raden
    med syskon; den fångar den grovt för breda grafen, inte den nätta."""
    for si, sec in enumerate(sections or []):
        if isinstance(sec, GraphSection):
            yield sec, width, f"{path}[{si}]"
        elif isinstance(sec, (CalloutSection, RowSection, ColSection)):
            yield from _iter_graphs(sec.children, width,
                                    f"{path}[{si}].children")


def _check_text_lengths(sections: list, path: str, errors: list[dict]) -> None:
    """Flagga löptexter som är för långa för ett kolumnflöde (se
    _MAX_TEXT_CHARS ovan). Gäller text-sektioner och list-punkter, även
    inuti callout/row/col."""
    for si, sec in enumerate(sections or []):
        spath = f"{path}[{si}]"
        if isinstance(sec, TextSection) and len(sec.text) > _MAX_TEXT_CHARS:
            errors.append(_err(spath, "text-lang",
                               f"texten är {len(sec.text)} tecken — dela upp i "
                               f"flera text-sektioner eller list-punkter "
                               f"(max ~{_MAX_TEXT_CHARS})."))
        elif isinstance(sec, ListSection):
            for ii, item in enumerate(sec.items):
                if len(item) > _MAX_ITEM_CHARS:
                    errors.append(_err(f"{spath}.items[{ii}]", "text-lang",
                                       f"listpunkten är {len(item)} tecken — "
                                       f"korta ner eller dela upp "
                                       f"(max ~{_MAX_ITEM_CHARS})."))
        elif isinstance(sec, (CalloutSection, RowSection, ColSection)):
            _check_text_lengths(sec.children, f"{spath}.children", errors)


def _check_rutor(sections: list, path: str, errors: list[dict]) -> None:
    """Inringande rutor (callout) är förbjudna på lektionstavlan.

    Lärarens dom när hon såg den första skarpa tavlan: «alla de här blå och
    röda rutorna, inringande liksom — det ser ganska fult ut, det gör jag inte
    på tavlan själv. Jag skriver bara tydligare rubriker, kanske i blått, och
    understrykningar.» Kravet står i prompten, men prompten driver — regeln
    här fäller ritningen deterministiskt och kostar på sin höjd en runda.
    Formen finns kvar i schemat så att äldre sparade tavlor fortfarande går
    att läsa in; det är GENERERINGEN som ska sluta rita rutor."""
    for si, sec in enumerate(sections or []):
        if isinstance(sec, CalloutSection):
            errors.append(_err(f"{path}[{si}]", "ruta",
                               "callout (inringande ruta) ritar läraren aldrig "
                               "— skriv i stället en kort rubrik med underline "
                               "(gärna blå, röd för 'Vanligt fel:') och låt "
                               "innehållet stå fritt under den."))
        elif isinstance(sec, (RowSection, ColSection)):
            _check_rutor(sec.children, f"{path}[{si}].children", errors)


# SIFFERVAKTEN (lärarens dom 2026-09-05, kväll). En tavla om linjära
# funktioner bar «y = 4 − 5x ⇒ k = −5, m = 4» på VÄNSTERN, efter Vanligt fel:
# ett sifferexempel på fel tavla, som regel 8b förbjuder utan att någon vakt
# fällde det. Regeln här fäller det deterministiskt, som rutorna: en fällning
# kostar på sin höjd en reparationsrunda, och domaren behöver då inte se det.
#
# FACITVAKTEN ÄR BORTA (lärarens dom 2026-09-23). Samma kväll 2026-09-05 fick
# vakten en andra halva för HÖGERTAVLAN, koden `facit`: «Jag kommer ju göra
# själva uträkningarna. Det räcker med en stark utgångspunkt. Massa färdiga
# uträkningar behövs inte.» Den halvan fällde «260 − 200 = 60 ⇒ k = 60» i ett
# exempel. Domen vändes 2026-09-23 över BA26B:s procenttavla: «Istället för
# all den här texten så är det ju bättre att ha själva uträkningen istället.
# Som ni har skrivit på tavlan.» Exemplen ÄR nu uträkningen, och en vakt som
# fällde den hade strukit precis det hon beställde. Den vända vakten, som
# fäller metodsteg i ord, ligger i lesson_board.utrakningsvakt och körs bara
# när tavlan GENERERAS (här körs validatorn också på hennes sparade tavlor).
#
# Vänsterns vakt står kvar oförändrad: där står bokstäver. KONSERVATIV med
# flit. En GIVEN ekvation är inte en uträkning: «x^2 + 6x - 7 = 0» och
# «y = -100x + 600» är bokstavsformler eller uppställningar. Det som fälls är
# ledet som RÄKNAR: en pil till ett svar i tal, eller en kedja som slutar i ett
# rent tal, med tal på båda sidor om likhetstecknet.
_PIL_RE = re.compile(r"\\(?:Rightarrow|Longrightarrow|implies|to|rightarrow|"
                     r"Leftrightarrow|leftrightarrow)\b")
# Exponenter, index och rotindex är inte «tal» eleven räknar med: a^2 + b^2 =
# c^2 är bokstäver, \sqrt[3]{x} likaså. De städas bort före sifferletandet,
# annars fälldes Pythagoras sats som ett sifferexempel.
_HAK_RE = re.compile(r"\[[^\]]*\]")
_INDEX_HOJD_RE = re.compile(r"[\^_](\{[^}]*\}|.)")
_RENT_TAL_RE = re.compile(r"^[\s{(\,;]*-?\d+(?:\{,\}\d+|,\d+)?[\s})\,;.]*$")
_BOKSTAV_LIKA_TAL_RE = re.compile(r"[A-Za-z]\s*=\s*-?\d")


def _talrensad(latex: str) -> str:
    """LaTeX utan det som ser ut som siffror men inte är tal att räkna med."""
    s = _HAK_RE.sub(" ", latex or "")
    s = _INDEX_HOJD_RE.sub(" ", s)
    return _LATEX_COMMAND_RE.sub(" ", s)


def _har_tal(text: str) -> bool:
    return bool(re.search(r"\d", text))


def _ar_utrakning(latex: str) -> bool:
    """En math-rad som RÄKNAR: «⇒ k = 60» eller en kedja som slutar i ett tal."""
    ren = _talrensad(latex)
    pil = _PIL_RE.search(latex or "")
    if pil:
        svans = _talrensad((latex or "")[pil.end():])
        if _BOKSTAV_LIKA_TAL_RE.search(svans):
            return True
    led = ren.split("=")
    if len(led) >= 3 and _RENT_TAL_RE.match(led[-1]) and _har_tal(led[-1]):
        return True
    return False


def _tal_pa_bada_sidor(latex: str) -> bool:
    led = _talrensad(latex).split("=")
    return any(_har_tal(led[i]) and _har_tal(led[i + 1])
               for i in range(len(led) - 1))


# «ATT TÄNKA PÅ» BÄR RANDFALL, INTE UTRÄKNINGAR (lärarens dom 2026-09-20,
# andra rundan, över den skarpa kontrolltavlan för Origo 2a 1.3). Blocket kom
# till samma morgon och blev genast tunt: domaren fällde x^2 = -20 och
# x = ±√27 som «andra sifferrad på vänstern» (jobb 480, seq 7–8), och kvar
# stod «saknar lösning» och en fråga utan svar. Randfallet ÄR ett tal — «en
# kvadrat blir aldrig negativ» går inte att visa i bokstäver — så raderna
# under rubriken är illustrationer, inte exempel på fel tavla.
#
# Undantaget är smalt med flit: HÖGST TRE math-rader, och bara de som står
# efter rubrikraden i samma flöde. Ankarregeln (ovan) gäller fortfarande för
# raden FÖRE formeln, och allt annat med tal fälls som förut.
_ATT_TANKA_PA = "att tänka på"
_RANDFALL_TAK = 3
# ETIKETTERNA SOM ÅKER GRATIS ÄR TVÅ (2026-09-21). Prompten säger HÖGST TVÅ
# rader under «Att tänka på» sedan lärarens dom om vänsterns 30 %; skriver
# modellen en tredje kostar dess etikett full budget och tavlan faller på
# «textbudget» — det fyndet säger stryk, och det är rätt åtgärd. Math-taket
# står kvar på tre: en tredje sifferrad ska fällas som för mycket TEXT, inte
# som ett sifferexempel på vänstern (koden siffror_vanster säger «flytta
# raden till exemplet», och det är fel råd för ett randfall).
_FRIA_ETIKETTER = 2
# Etiketten under en randfallsrad är en bildtext till matematiken, inte prosa:
# «x^2 = 0: en enda rot» är fyra ord. Längre än så är det en mening, och då
# vägs den som en mening. Talet är ordregeln mätt i tecken, och det gick
# 45 → 30 med samma dom: sex ord var en bisats, fyra är en bildtext.
_ETIKETT_MAX = 30


def _randfallsblocket(sections: list) -> tuple[list, list]:
    """(math-raderna, etiketterna) under rubriken «Att tänka på» i ETT flöde.

    Blocket börjar vid rubrikraden och slutar vid «Vanligt fel:» eller vid
    flödets slut. Listorna är kapade — vakten och budgeten ska inte kunna
    öppnas på vid gavel av en rubrik: math vid :data:`_RANDFALL_TAK`,
    etiketterna vid :data:`_FRIA_ETIKETTER`."""
    matte: list = []
    etiketter: list = []
    i_blocket = False
    for sec in sections or []:
        if isinstance(sec, (TextSection, HeadingSection)):
            # Numret räknas bort: sedan formdomen 2026-09-20 (kväll) heter
            # rubriken «3. Att tänka på» — numreringen är dispositionen,
            # det närmaste en pil motorn kan rita i flödet.
            lag = re.sub(r"^\s*\d+\.\s*", "",
                         str(getattr(sec, "text", "")).strip().lower())
            if lag.startswith(_ATT_TANKA_PA):
                i_blocket = True
                continue
            if lag.startswith("vanligt fel"):
                break
            if (i_blocket and isinstance(sec, TextSection)
                    and len(sec.text) <= _ETIKETT_MAX
                    and len(etiketter) < _FRIA_ETIKETTER):
                etiketter.append(sec)
        elif (i_blocket and isinstance(sec, MathSection)
                and len(matte) < _RANDFALL_TAK):
            matte.append(sec)
    return matte, etiketter


def _fritt_vanligt_fel(sections: list) -> object | None:
    """Det FELAKTIGA ledet under «Vanligt fel:» är beställt (regel 9) och är
    undantaget från båda vakterna — annars fällde de tavlans egen fallgrop.
    Undantaget gäller den FÖRSTA math-sektionen efter rubriken, inte resten:
    det var just raden EFTER förklaringen som var sifferexemplet.

    RADEN ÄR VALFRI sedan 2026-09-12 (spåret 2026-09-06: läraren strök den ur
    5 av 5 tavlor). Reglerna här rör inte det valet åt någotdera hållet: ingen
    KRÄVER raden — saknas rubriken finns inget undantag och siffervakten dömer
    hela vänstern — och ingen FÖRBJUDER den. Det är prompten och
    lesson_board.vanligtfel_kvar som bär krysset, för det är bara de som vet
    vad läraren valde."""
    sett = False
    for sec in sections or []:
        if isinstance(sec, (TextSection, HeadingSection)):
            if str(getattr(sec, "text", "")).strip().lower().startswith("vanligt fel"):
                sett = True
        elif sett and isinstance(sec, MathSection):
            return sec
    return None


def _ar_bokstavsformel(latex: str) -> bool:
    """Den ALLMÄNNA formeln: bokstäver, inga tal att räkna med. Exponenter och
    index räknas inte som tal (x^2 = a och x_1 är bokstavsformler) — samma
    rensning som siffervakten själv gör, så att de två aldrig blir osams."""
    ren = _talrensad(latex or "")
    return not _har_tal(ren) and bool(re.search(r"[A-Za-z]", ren))


# ANKARET (lärarens dom 2026-09-20 över Origo 2a 1.3 Andragradsekvationer):
# «rätt men för lite och för spretigt; eleverna får inte det som gör att de
# kan börja i boken». Vänstern bar x^2 = a ⇒ x = ±√a i rena bokstäver, och
# ±:et stod där utan sitt varför. Hon bad om raden x^2 = 64 ⇒ x = ±8 FÖRE
# formeln, och lappen strök den som «ett uträknat sifferexempel» (jobb 480,
# event 3). Regeln fällde alltså precis det hon bad om.
#
# Undantaget är ETT ankare per vänstertavla, och definitionen är
# deterministisk så att vakten, prompten och domaren pekar på SAMMA rad: den
# första math-raden med tal vars NÄSTA math-syskon i samma flöde är en
# bokstavsformel. Ankaret får alltså bara stå där det hör hemma — direkt före
# den allmänna formel det förklarar. Ett andra sifferled har ingen formel
# efter sig och fälls som förut, och så gör också ett ankare som står ensamt
# utan formeln det är till för.
def _ar_pilrad(latex: str) -> bool:
    """En math-sektion som bara är en PIL: «\\Downarrow», «\\Longrightarrow».

    Röda tråden på vänstern ritas med en sådan rad (lärarens dom 2026-09-20:
    «inga pilar, ingen tydlig disposition»). Motorns egen arrow är en
    annotation i absoluta pixlar och kan inte ligga mellan två sektioner i
    flödet, men KaTeX ritar pilen — och en pil mellan ankaret och formeln
    får inte bryta ankarregeln bara för att den står emellan."""
    ren = _talrensad(latex or "")
    return not re.search(r"[A-Za-z0-9]", ren) and bool((latex or "").strip())


def _ankarkandidater(sections: list, ut: list) -> None:
    math = [s for s in (sections or []) if isinstance(s, MathSection)]
    plats = {id(s): i for i, s in enumerate(math)}
    for sec in sections or []:
        if isinstance(sec, MathSection):
            i = plats[id(sec)]
            # Pilraderna hoppas över: nästa math som SÄGER något är formeln.
            nasta = next((m for m in math[i + 1:] if not _ar_pilrad(m.latex)),
                         None)
            if nasta is not None and _har_tal(_talrensad(sec.latex)) \
                    and _ar_bokstavsformel(nasta.latex):
                ut.append(sec)
        elif isinstance(sec, (CalloutSection, RowSection, ColSection)):
            _ankarkandidater(sec.children, ut)


def _ankaret(sections: list):
    """Den första ankarkandidaten i tavlans läsordning, eller None."""
    ut: list = []
    _ankarkandidater(sections, ut)
    return ut[0] if ut else None


def _check_siffror_vanster(sections: list, path: str,
                           errors: list[dict]) -> None:
    """Siffervakten på VÄNSTERTAVLAN (regel 8b). Högertavlan döms inte här
    sedan 2026-09-23, se kommentaren ovan om facitvakten."""
    # Ankaret slås upp EN gång per flöde och bärs sedan ned genom row/col:
    # undantaget gäller tavlan, inte varje spalt för sig.
    _siffror_rek(sections, path, errors, _ankaret(sections))


def _siffror_rek(sections: list, path: str, errors: list[dict],
                 ankare) -> None:
    undantag = _fritt_vanligt_fel(sections)
    # Randfallen slås upp per FLÖDE, som «Vanligt fel»: rubriken och raderna
    # under den står i samma col, och en rubrik i en annan spalt är en annan
    # sak. Se _randfallsblocket.
    randfall = _randfallsblocket(sections)[0]
    for si, sec in enumerate(sections or []):
        spath = f"{path}[{si}]"
        if isinstance(sec, MathSection):
            if sec is undantag or (ankare is not None and sec is ankare) \
                    or any(sec is r for r in randfall):
                continue
            # Regel 8b: på vänstern står bokstäver. En rad som RÄKNAR med
            # tal är ett exempel, och exempel bor på högertavlan, utom
            # ankaret ovan, som är beställt.
            if _ar_utrakning(sec.latex) and _tal_pa_bada_sidor(sec.latex):
                errors.append(_err(spath, "siffror_vanster",
                                   f"'{sec.latex[:60]}' är ett uträknat "
                                   "sifferexempel på vänstertavlan, där "
                                   "står bokstäver. Stryk raden, eller "
                                   "flytta den till det exempel den hör "
                                   "till."))
        elif isinstance(sec, (CalloutSection, RowSection, ColSection)):
            _siffror_rek(sec.children, f"{spath}.children", errors, ankare)


# TANKSTRECKSVAKTEN (spåret 2026-09-06: «skriv kortare utan em dash», sex
# gånger på fyra papper under en vecka). Regeln är delad — app/textvakt.py —
# och gäller det som står som SPRÅK på tavlan: text-sektioner, rubriker och
# listpunkter.
#
# Inte `latex`: där betyder strecken något annat (intervall, minus, notation),
# och matematiken är inte den prosa läraren klagade på. Inte heller `bullet`:
# listans punkttecken ÄR ett tankstreck i appens egna few-shot-exempel
# («bullet: "–"»), och det är en punkt i marginalen och inte en mening.
#
# Sifferspannet är undantaget av samma skäl som i exam_spec, fast starkare:
# prompten BER om det. lesson_board regel 2 skriver «Boken s. 27–30, uppg.
# 1218–1227» och few-shot-tavlan har «Boken s. 88–90, uppg. 3110–3118» i
# agendan. Utan undantaget hade vakten fällt det prompten beställde, varje varv.
def _check_tankstreck(sections: list, path: str, errors: list[dict]) -> None:
    for si, sec in enumerate(sections or []):
        spath = f"{path}[{si}]"
        if isinstance(sec, (TextSection, HeadingSection)):
            errors += textvakt.granska([(f"{spath}.text", sec.text)],
                                       tillat_spann=True)
        elif isinstance(sec, ListSection):
            errors += textvakt.granska(
                [(f"{spath}.items[{ii}]", item)
                 for ii, item in enumerate(sec.items)], tillat_spann=True)
        elif isinstance(sec, (CalloutSection, RowSection, ColSection)):
            _check_tankstreck(sec.children, f"{spath}.children", errors)


_MODELL_VL_RE = re.compile(r"^\s*[A-Za-z]\s*(\([a-z]\))?\s*=")
_MODELL_TAL_RE = re.compile(r"\d{2,}|\d+(?:\{,\}|,)\d+")


def _ar_modellformel(latex: str) -> bool:
    """«K = 200 + 0{,}80x»: en bokstav (eller V(t)) till vänster om =, och
    till höger minst två tal som inte är ensiffriga heltal."""
    m = _MODELL_VL_RE.match(latex or "")
    if not m:
        return False
    hoger = _talrensad(latex[m.end():])
    return len(_MODELL_TAL_RE.findall(hoger)) >= 2


def _math_i_flodet(sections: list, ut: list[str]) -> None:
    for sec in sections or []:
        if isinstance(sec, MathSection):
            ut.append(sec.latex)
        elif isinstance(sec, (CalloutSection, RowSection, ColSection)):
            _math_i_flodet(sec.children, ut)


def ar_modelltavla(board) -> bool:
    """Bär vänstertavlan en formel ur verkligheten? Se _MAX_BOARD_TEXT_MODELL."""
    rader: list[str] = []
    _math_i_flodet(getattr(board, "sections", None), rader)
    for col in getattr(board, "columns", None) or []:
        _math_i_flodet(col.sections, rader)
    return any(_ar_modellformel(r) for r in rader)


def _ankaretiketten(sections: list):
    """Etiketten direkt under ankaret, eller None.

    Ankaret är en math-rad och kostar ingenting i budgeten; etiketten under
    det («8 och −8 i kvadrat blir 64») är dess andra halva och är lika lite
    prosa som randfallens bildtexter. Den skulle annars kunna vara det som
    fäller tavlan — och det var precis vad som hände i den andra skarpa
    körningen (jobb 481, seq 13): vänstern låg på 381 av 390, och
    budgetlappen strök ankaret MED etikett för att komma under."""
    ankare = _ankaret(sections)
    if ankare is None:
        return None
    syskon: list = []

    def leta(secs: list) -> bool:
        for i, sec in enumerate(secs or []):
            if sec is ankare:
                syskon.extend(secs[i + 1:i + 2])
                return True
            if isinstance(sec, (CalloutSection, RowSection, ColSection)) \
                    and leta(sec.children):
                return True
        return False

    leta(sections)
    nasta = syskon[0] if syskon else None
    if isinstance(nasta, TextSection) and len(nasta.text) <= _ETIKETT_MAX:
        return nasta
    return None


def _text_volym(sections: list, vanster: bool = False) -> int:
    """Summan av läsbar text i ett sektionsflöde — text och listpunkter, ned
    genom callout/row/col. Rubriker och matte räknas inte: se _MAX_BOARD_TEXT.

    Randfallens etiketter räknas inte heller (2026-09-20, andra rundan): de
    är bildtexter till en math-rad, inte prosa, och när budgeten vägde dem
    som meningar lappade den bort just de rader domaren nyss hade beställt
    (jobb 480, seq 13). Undantaget är kapat till TVÅ rader à 30 tecken
    (2026-09-21, lärarens 30 %) — en längre rad är en mening och vägs som en
    mening, och den tredje raden ska kosta. Se _randfallsblocket.

    `vanster` friar också ankarets etikett (tredje rundan, jobb 481). Den
    flaggan finns för att ankaret bara går att känna igen på vänstertavlan:
    mönstret «sifferrad, etikett, bokstavsformel» kan uppstå av en slump i en
    exempelspalt, och där ska raden vägas som vilken text som helst."""
    fria: set[int] = set()
    if vanster:
        etikett = _ankaretiketten(sections)
        if etikett is not None:
            fria.add(id(etikett))
    return _volym_rek(sections, fria)


def _ar_rubrikrad(sec) -> bool:
    """En KORT fet text är en rubrik, inte prosa.

    Rubriker kostar ingenting i budgeten — men bara som HeadingSection, och
    schemat tillåter ingen heading inne i en col (bara löv). Vänsterns
    skelett bor i två col (lesson_board regel 6), så dess rubriker — «1. Vad
    är det?», «3. Att tänka på», «Vanligt fel:» — måste skrivas som text med
    weight 700. Att de då plötsligt vägde som meningar var ett mätfel som
    kom ur schemat, inte ur tavlan (uppmätt 2026-09-20, kväll: de tre
    numrerade rubrikerna kostade 43 tecken av 390 på varje vänstertavla).
    Taket är smalt med flit: en fet rad längre än så är en mening."""
    return (isinstance(sec, TextSection) and sec.weight == 700
            and len(sec.text) <= 20)


def _volym_rek(sections: list, fria: set[int]) -> int:
    # Randfallen slås upp per FLÖDE (rubriken och raderna står i samma col),
    # ankarets etikett en gång och bärs sedan ned: den bor i en col, och ett
    # nytt uppslag där hade inte hittat bokstavsformeln ovanför.
    lokala = fria | {id(s) for s in _randfallsblocket(sections)[1]}
    summa = 0
    for sec in sections or []:
        if isinstance(sec, TextSection):
            if id(sec) in lokala or _ar_rubrikrad(sec):
                continue
            summa += len(sec.text)
        elif isinstance(sec, ListSection):
            summa += sum(len(i) for i in sec.items)
        elif isinstance(sec, (CalloutSection, RowSection, ColSection)):
            summa += _volym_rek(sec.children, fria)
    return summa


def _validate_graph(g: GraphSection, col_width: float, path: str,
                    errors: list[dict]) -> None:
    x_min, x_max = g.xRange
    y_min, y_max = g.yRange
    if x_max <= x_min or y_max <= y_min:
        errors.append(_err(path, "range",
                           "xRange/yRange måste vara stigande intervall."))
        return

    if g.width > col_width + 2:
        errors.append(_err(path, "grafbredd",
                           f"grafen är {g.width:.0f} px bred men kolumnen rymmer bara "
                           f"~{col_width:.0f} px — minska width eller öka kolumnens weight."))

    def in_range(x: float, y: float) -> bool:
        return x_min <= x <= x_max and y_min <= y <= y_max

    for pi, p in enumerate(g.points or []):
        if not in_range(p.x, p.y):
            errors.append(_err(f"{path}.points[{pi}]", "utanför-range",
                               f"punkten ({p.x}, {p.y}) ligger utanför xRange/yRange."))
    for ti, t in enumerate(g.texts or []):
        if not in_range(t.x, t.y):
            errors.append(_err(f"{path}.texts[{ti}]", "utanför-range",
                               f"texten '{t.text}' på ({t.x}, {t.y}) ligger utanför xRange/yRange."))

    # Cirkelpolygoner (≥32 punkter) kräver kvadratisk pixel-aspekt, annars
    # renderas cirkeln som ellips (SKILL.md-invariant 4).
    pad = g.padding if g.padding is not None else 30.0
    px_per_x = (g.width - 2 * pad) / (x_max - x_min)
    px_per_y = (g.height - 2 * pad) / (y_max - y_min)
    has_circleish = any(len(poly.pts) >= 32 for poly in (g.polygons or []))
    if has_circleish and px_per_y > 0:
        skew = abs(px_per_x / px_per_y - 1.0)
        if skew > _ASPECT_TOLERANCE:
            errors.append(_err(path, "cirkelaspekt",
                               f"grafen har en cirkelpolygon men pixel-aspekten avviker "
                               f"{skew * 100:.0f} % — justera width/height eller xRange/yRange "
                               "så (width-2*padding)/(xMax-xMin) = (height-2*padding)/(yMax-yMin)."))

    # Arcs på polygonhörn kräver interior-hint (SKILL.md-invariant 2).
    vertices = [tuple(pt) for poly in (g.polygons or []) for pt in poly.pts]
    for ai, arc in enumerate(g.arcs or []):
        at_vertex = any(abs(arc.cx - vx) < _VERTEX_EPS and abs(arc.cy - vy) < _VERTEX_EPS
                        for vx, vy in vertices)
        if at_vertex and arc.interior is None:
            errors.append(_err(f"{path}.arcs[{ai}]", "interior-saknas",
                               f"vinkelbågen i hörnet ({arc.cx}, {arc.cy}) saknar 'interior' "
                               "— ange en punkt inuti figuren (t.ex. polygonens centroid)."))

    for pi, plot in enumerate(g.plots or []):
        msg = validate_expr(plot.expr)
        if msg:
            errors.append(_err(f"{path}.plots[{pi}].expr", "uttrycksfel",
                               f"'{plot.expr}': {msg}"))


def validate_rules(doc: BoardDoc) -> list[dict]:
    """Deterministiska regler som json-schemat inte kan uttrycka.
    Returnerar en maskinläsbar fellista (tom = allt ok)."""
    errors: list[dict] = []
    modell = bool(doc.boards) and ar_modelltavla(doc.boards[0])
    for bi, board in enumerate(doc.boards):
        bpath = f"boards[{bi}]"
        pad = board.padding or Padding()
        inner_w = board.width - pad.left - pad.right

        flows: list[tuple[list, float, str]] = []
        if board.sections:
            flows.append((board.sections, inner_w, f"{bpath}.sections"))
        if board.columns:
            total = sum(c.weight for c in board.columns) or 1.0
            avail = inner_w - _COL_GAP * (len(board.columns) - 1)
            for ci, col in enumerate(board.columns):
                flows.append((col.sections, avail * col.weight / total,
                              f"{bpath}.columns[{ci}].sections"))
        if not board.sections and not board.columns:
            errors.append(_err(bpath, "tom-tavla",
                               "tavlan saknar både sections och columns."))

        volym = 0
        for sections, width, path in flows:
            _check_text_lengths(sections, path, errors)
            _check_rutor(sections, path, errors)
            _check_tankstreck(sections, path, errors)
            # `vanster` friar ankarets etikett, och ankaret finns bara på
            # boards[0], samma gräns som siffervakten drar.
            volym += _text_volym(sections, vanster=(bi == 0))
            # Siffervakten (2026-09-05, kväll). Vänstertavlan är boards[0],
            # och där fälls sifferexemplet. Exempeltavlorna döms inte längre:
            # sedan lärarens dom 2026-09-23 ÄR exemplen uträkningen. Se
            # _check_siffror_vanster.
            if bi == 0:
                _check_siffror_vanster(sections, path, errors)
            for g, col_w, gpath in _iter_graphs(sections, width, path):
                _validate_graph(g, col_w, gpath, errors)
        # Kolumntavlan bär flera exempelspalter — taket skalar per spalt
        # (se OMMÄTT-kommentaren vid _MAX_BOARD_TEXT).
        per_kolumn, per_tavla = ((_MAX_COLUMN_TEXT_MODELL, _MAX_BOARD_TEXT_MODELL)
                                 if modell else (_MAX_COLUMN_TEXT, _MAX_BOARD_TEXT))
        tak = (per_kolumn * len(board.columns) if board.columns else per_tavla)
        if volym > tak:
            errors.append(_err(bpath, "textbudget",
                               f"tavlan bär {volym} tecken löpande text (taket "
                               f"är ~{tak}) — en tavla ska visa det "
                               "som SKRIVS under lektionen, inte allt som sägs. "
                               "Stryk det som bara ska berättas, gör om steg "
                               "till math-sektioner och samla flera fall i en "
                               "table-sektion i stället för i meningar."))

    _walk_strings(doc.model_dump(exclude_none=True, by_alias=True), "doc", errors)
    return errors


def _split_text(text: str, limit: int) -> list[str]:
    """Radbryt vid ordgränser till bitar om högst `limit` tecken."""
    words = text.split()
    chunks: list[str] = []
    cur = ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > limit:
            chunks.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        chunks.append(cur)
    return chunks or [text]


_INLINE_MATH_RE = re.compile(r"\$([^$]+)\$")


def _explode_inline_math(sec: dict) -> list[dict] | None:
    """text med $-inline-matte ("Svar: … $\\frac{2}{9}$.") → sekvens av
    text- och math-delar. Motorn renderar aldrig LaTeX i text-fält, och
    LLM-reparationer rättade inte mönstret pålitligt (bench Fas 2).
    Returnerar del-listan (utan wrapper) eller None om inget att göra."""
    text = sec.get("text")
    if sec.get("kind") != "text" or not isinstance(text, str) \
            or not _INLINE_MATH_RE.search(text):
        return None
    parts: list[dict] = []
    pos = 0
    base = {k: sec[k] for k in ("size", "color") if sec.get(k) is not None}
    for m in _INLINE_MATH_RE.finditer(text):
        before = text[pos:m.start()].strip()
        if before:
            parts.append({"kind": "text", "text": before, **base})
        parts.append({"kind": "math", "latex": m.group(1).strip(), **base})
        pos = m.end()
    after = text[pos:].strip()
    if after and after not in (".", ",", "!", "?"):
        parts.append({"kind": "text", "text": after, **base})
    return parts or None


def _normalize_sections(sections: list, in_container: bool = False) -> list:
    out: list = []
    prev = None
    for sec in sections or []:
        if not isinstance(sec, dict):
            out.append(sec)
            prev = sec
            continue
        # Dedupe: identiska konsekutiva sektioner (reparationsrundor har
        # duplicerat sektioner, vilket alltid ger element-överlapp).
        if prev is not None and sec == prev:
            continue
        prev = sec
        parts = _explode_inline_math(sec)
        if parts is not None:
            if in_container or (len(parts) == 1 and parts[0]["kind"] == "math"):
                # Inuti callout/row/col är bara löv tillåtna (WB-JSON v1) —
                # lägg delarna plant; en ren matte-text blir en math-sektion.
                if not in_container:
                    for k in ("gapAfter", "align", "seed", "rotate"):
                        if sec.get(k) is not None:
                            parts[0][k] = sec[k]
                out.extend(parts)
            else:
                row = {"kind": "row", "children": parts, "gap": 8}
                for k in ("gapAfter", "align", "seed", "rotate"):
                    if sec.get(k) is not None:
                        row[k] = sec[k]
                out.append(row)
            continue
        if sec.get("kind") == "text" and isinstance(sec.get("text"), str) \
                and len(sec["text"]) > _MAX_TEXT_CHARS:
            # Bredden följer taket i stället för att stå som en egen siffra
            # (78 mot det gamla taket 90). När läraren sänkte taket till 60
            # 2026-09-05 delade normaliseringen fortfarande i 78-teckensbitar,
            # och varje bit föll direkt på text-lang-regeln efteråt.
            chunks = _split_text(sec["text"], max(24, _MAX_TEXT_CHARS - 12))
            for i, chunk in enumerate(chunks):
                part = dict(sec)
                part["text"] = chunk
                if i < len(chunks) - 1:
                    part["gapAfter"] = 4      # radavstånd inom samma stycke
                out.append(part)
        elif sec.get("kind") in ("callout", "row", "col") \
                and isinstance(sec.get("children"), list):
            sec = dict(sec)
            sec["children"] = _normalize_sections(sec["children"],
                                                  in_container=True)
            out.append(sec)
        else:
            out.append(sec)
    return out


def _byt_thickness(nod) -> None:
    """arrows[].thickness → strokeWidth, rekursivt. Bara i arrows-listor och
    bara när strokeWidth inte redan står där — allt annat okänt ska fortsatt
    fällas av schemat, inte städas undan."""
    if isinstance(nod, dict):
        for pil in (nod.get("arrows") or []):
            if isinstance(pil, dict) and "thickness" in pil:
                pil.setdefault("strokeWidth", pil["thickness"])
                del pil["thickness"]
        for v in nod.values():
            _byt_thickness(v)
    elif isinstance(nod, list):
        for v in nod:
            _byt_thickness(v)


def normalize_board(data: dict) -> dict:
    """Deterministisk normalisering FÖRE validering/rendering (bench Fas 2):

    * långa text-sektioner radbryts i flera korta (motorn sätter ingen bredd
      på fristående text — långa löptexter spränger annars kolumnbredden,
      och LLM-reparationer kortade dem inte pålitligt),
    * identiska konsekutiva sektioner dedupas (reparationsrundor har
      duplicerat sektioner),
    * arrows[].thickness döps om till strokeWidth (modellen skriver envist
      thickness — två inspelningar av tre 2026-08-21 — och en entydig synonym
      ska inte kosta en reparationsrunda; okända nycklar i övrigt fälls
      fortfarande av extra="forbid").

    Ren dict-transform — påverkar inte listpunkter (att korta dem är ett
    innehållsbeslut som lämnas till modellen via text-lang-regeln)."""
    if not isinstance(data, dict):
        return data
    data = json.loads(json.dumps(data))          # djupkopia, rör ej original
    _byt_thickness(data)
    for board in data.get("boards") or []:
        if not isinstance(board, dict):
            continue
        if isinstance(board.get("sections"), list):
            board["sections"] = _normalize_sections(board["sections"])
        for col in board.get("columns") or []:
            if isinstance(col, dict) and isinstance(col.get("sections"), list):
                col["sections"] = _normalize_sections(col["sections"])
    return data


def validate_board_json(data) -> tuple[BoardDoc | None, list[dict]]:
    """Validera rå JSON (dict) → (BoardDoc, []) eller (None/BoardDoc, fellista).

    Schemafel (Pydantic) och regelfel returneras i samma maskinläsbara form
    så reparationsloopen kan hantera dem enhetligt."""
    try:
        doc = BoardDoc.model_validate(data)
    except ValidationError as e:
        errors = [
            _err(".".join(str(p) for p in err["loc"]), "schema", err["msg"])
            for err in e.errors()
        ]
        return None, errors
    return doc, validate_rules(doc)
