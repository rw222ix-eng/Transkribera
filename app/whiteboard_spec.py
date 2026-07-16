"""WB-JSON v1 — LLM-säker delmängd av whiteboard-motorns board-spec.

Motorns fulla spec är JS (bl.a. ``plots: [{ fn: (x) => … }]``) — funktioner
kan inte uttryckas i JSON och rå JS från en LLM ska aldrig eval:as. WB-JSON v1
är därför en strikt JSON-serialiserbar delmängd med två anpassningar:

* ``plots[].fn`` ersätts av ``plots[].expr`` — en uttryckssträng
  ("x^2 - 2*x + 1") som klienten kompilerar med en egen liten parser
  (``app/web/static/whiteboard/expr.js``). Den här modulen speglar parserns
  grammatik för serversidig syntaxvalidering (:func:`validate_expr`).
* Nästling är begränsad: ``callout``/``row``/``col`` får bara innehålla
  "löv"-sektioner (text/math/list/stack/divider/spacer). Det håller
  json-schemat fritt från rekursion — llama-servers grammatiktvång får en
  ändlig grammatik — och begränsar samtidigt LLM:ens felyta.

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


class ShapeSection(_SectionBase):
    kind: Literal["shape"]
    type: Literal["right-triangle", "triangle", "rect", "circle"]
    width: float
    height: float
    labels: dict[Literal["top", "left", "right", "bottom", "inside"], str] | None = None
    angles: dict[str, str] | None = None


# Löv-sektioner som får ligga inuti callout/row/col (ingen rekursion —
# json-schemat förblir ändligt för grammatiktvånget).
LeafSection = Annotated[
    Union[TextSection, MathSection, ListSection, StackSection,
          DividerSection, SpacerSection],
    Field(discriminator="kind"),
]


class CalloutSection(_SectionBase):
    kind: Literal["callout"]
    children: list[LeafSection]
    padding: float | None = None
    fill: bool | None = None
    fillOpacity: float | None = None


class RowSection(_SectionBase):
    kind: Literal["row"]
    children: list[LeafSection]
    gap: float | None = None
    justify: Literal["flex-start", "center", "flex-end", "space-between"] | None = None
    wrap: bool | None = None
    width: float | None = None


class ColSection(_SectionBase):
    kind: Literal["col"]
    children: list[LeafSection]
    gap: float | None = None
    flex: str | None = None
    width: float | None = None


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

# Kolumngap-approximation för bredd-budgeten (motorn flödar kolumner med ett
# internt mellanrum; exakt värde spelar mindre roll än att fånga grafer som
# är uppenbart för breda för sin kolumn).
_COL_GAP = 24.0
_ASPECT_TOLERANCE = 0.15  # motorn varnar vid >15 % avvikelse
_VERTEX_EPS = 1e-6


def _err(path: str, code: str, message: str) -> dict:
    return {"path": path, "code": code, "message": message}


def _walk_strings(value, path: str, out: list[dict]) -> None:
    if isinstance(value, str):
        if _DECIMAL_POINT_RE.search(value):
            out.append(_err(path, "decimalpunkt",
                            f"'{value}' innehåller decimalpunkt — använd decimalkomma "
                            "(i LaTeX: 4{,}58)."))
    elif isinstance(value, dict):
        for k, v in value.items():
            if k in _DECIMAL_EXEMPT_KEYS:
                continue
            _walk_strings(v, f"{path}.{k}", out)
    elif isinstance(value, (list, tuple)):
        for idx, v in enumerate(value):
            _walk_strings(v, f"{path}[{idx}]", out)


def _iter_graphs(sections: list, width: float, path: str):
    """(graph, kolumnbredd, path) för alla grafer i ett sektionsflöde."""
    for si, sec in enumerate(sections or []):
        if isinstance(sec, GraphSection):
            yield sec, width, f"{path}[{si}]"


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

        for sections, width, path in flows:
            for g, col_w, gpath in _iter_graphs(sections, width, path):
                _validate_graph(g, col_w, gpath, errors)

    _walk_strings(doc.model_dump(exclude_none=True, by_alias=True), "doc", errors)
    return errors


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
