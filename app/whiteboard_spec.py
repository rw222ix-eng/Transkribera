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
_MAX_TEXT_CHARS = 90
_MAX_ITEM_CHARS = 80
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
_MAX_BOARD_TEXT = 400
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


def _text_volym(sections: list) -> int:
    """Summan av läsbar text i ett sektionsflöde — text och listpunkter, ned
    genom callout/row/col. Rubriker och matte räknas inte: se _MAX_BOARD_TEXT."""
    summa = 0
    for sec in sections or []:
        if isinstance(sec, TextSection):
            summa += len(sec.text)
        elif isinstance(sec, ListSection):
            summa += sum(len(i) for i in sec.items)
        elif isinstance(sec, (CalloutSection, RowSection, ColSection)):
            summa += _text_volym(sec.children)
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
            volym += _text_volym(sections)
            for g, col_w, gpath in _iter_graphs(sections, width, path):
                _validate_graph(g, col_w, gpath, errors)
        if volym > _MAX_BOARD_TEXT:
            errors.append(_err(bpath, "textbudget",
                               f"tavlan bär {volym} tecken löpande text (taket "
                               f"är ~{_MAX_BOARD_TEXT}) — en tavla ska visa det "
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
            chunks = _split_text(sec["text"], 78)
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
