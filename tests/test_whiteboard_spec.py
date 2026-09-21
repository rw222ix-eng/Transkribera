"""WB-JSON v1: schema, regelvalidatorer och uttrycksparser-spegeln."""
import json
from pathlib import Path

import pytest

from app import whiteboard_spec as ws


def _board(**over):
    base = {
        "width": 900, "height": 780,
        "padding": {"top": 30, "right": 30, "bottom": 30, "left": 40},
        "chrome": "aluminium", "tray": True, "name": "test",
        "sections": [
            {"kind": "heading", "text": "Rubrik", "size": 34,
             "underline": {"color": "red"}},
            {"kind": "math", "latex": "a^2 + b^2 = c^2", "size": 30, "color": "blue"},
        ],
    }
    base.update(over)
    return base


def _doc(*boards):
    return {"title": "Testlektion", "boards": list(boards) or [_board()]}


# ------------------------------------------------------------------ schema --

def test_valid_doc_passes():
    doc, errors = ws.validate_board_json(_doc())
    assert doc is not None
    assert errors == []


def test_unknown_kind_rejected():
    doc, errors = ws.validate_board_json(_doc(_board(sections=[{"kind": "gif", "url": "x"}])))
    assert doc is None
    assert any(e["code"] == "schema" for e in errors)


def test_hex_color_rejected():
    doc, errors = ws.validate_board_json(
        _doc(_board(sections=[{"kind": "text", "text": "hej", "color": "#ff0000"}])))
    assert doc is None


def test_extra_properties_rejected():
    doc, errors = ws.validate_board_json(
        _doc(_board(sections=[{"kind": "text", "text": "hej", "hitta_pa": 1}])))
    assert doc is None


def test_fn_rejected_in_plots():
    """Motorns fn-fält är JS och finns inte i WB-JSON v1 — bara expr."""
    g = {"kind": "graph", "width": 400, "height": 300,
         "xRange": [-1, 5], "yRange": [-1, 5],
         "plots": [{"fn": "(x) => x*x", "color": "red"}]}
    doc, errors = ws.validate_board_json(_doc(_board(sections=[g])))
    assert doc is None


def test_nested_containers_limited_to_leaves():
    callout = {"kind": "callout", "children": [
        {"kind": "callout", "children": [{"kind": "text", "text": "djupt"}]}]}
    doc, errors = ws.validate_board_json(_doc(_board(sections=[callout])))
    assert doc is None  # callout i callout är utanför v1-delmängden


def test_shape_labels_reject_invented_keys():
    """Bench Fas 2: modellen satte hörnnamn (A/B/C) som labels-nycklar —
    explicit modell (inte dict) så grammatiktvånget stoppar det."""
    shape = {"kind": "shape", "type": "triangle", "width": 200, "height": 150,
             "labels": {"A": "hörn", "B": "hörn", "C": "hörn"}}
    doc, errors = ws.validate_board_json(_doc(_board(sections=[shape])))
    assert doc is None
    # …och schemat som skickas till grammatiken listar fälten explicit
    schema = ws.ShapeLabels.model_json_schema()
    assert set(schema["properties"]) == {"top", "left", "right", "bottom", "inside"}


def test_shape_angles_not_in_v1():
    shape = {"kind": "shape", "type": "triangle", "width": 200, "height": 150,
             "angles": {"A": "60°"}}
    doc, errors = ws.validate_board_json(_doc(_board(sections=[shape])))
    assert doc is None


def test_max_two_boards():
    doc, errors = ws.validate_board_json(_doc(_board(), _board(), _board()))
    assert doc is None


def test_response_format_shape():
    rf = ws.to_response_format()
    assert rf["type"] == "json_schema"
    assert rf["json_schema"]["name"] == "lektionstavla"
    schema = rf["json_schema"]["schema"]
    assert schema["type"] == "object"
    assert "boards" in schema["properties"]


# ------------------------------------------------------------ regelfel ----

def _graph(**over):
    g = {"kind": "graph", "width": 400, "height": 300,
         "xRange": [-1, 5], "yRange": [-1, 5]}
    g.update(over)
    return g


def test_point_outside_range_flagged():
    g = _graph(points=[{"x": 99, "y": 0, "label": "A"}])
    doc, errors = ws.validate_board_json(_doc(_board(sections=[g])))
    assert doc is not None
    assert any(e["code"] == "utanför-range" for e in errors)


def test_polygon_arc_without_interior_flagged():
    g = _graph(
        polygons=[{"pts": [[0, 0], [4, 0], [4, 3]]}],
        arcs=[{"cx": 0, "cy": 0, "r": 0.8, "from": 0, "to": 0.6435}],
    )
    doc, errors = ws.validate_board_json(_doc(_board(sections=[g])))
    assert any(e["code"] == "interior-saknas" for e in errors)


def test_polygon_arc_with_interior_ok():
    g = _graph(
        polygons=[{"pts": [[0, 0], [4, 0], [4, 3]]}],
        arcs=[{"cx": 0, "cy": 0, "r": 0.8, "from": 0, "to": 0.6435,
               "interior": [2.7, 1.0]}],
    )
    doc, errors = ws.validate_board_json(_doc(_board(sections=[g])))
    assert errors == []


def test_free_arc_needs_no_interior():
    g = _graph(arcs=[{"cx": 1, "cy": 1, "r": 0.5, "from": 0, "to": 1.5}])
    doc, errors = ws.validate_board_json(_doc(_board(sections=[g])))
    assert errors == []


def test_skew_circle_polygon_flagged():
    import math
    pts = [[3 * math.cos(2 * math.pi * i / 48), 3 * math.sin(2 * math.pi * i / 48)]
           for i in range(48)]
    # 400x300 med samma ranges ger olika px/enhet i x och y → ellips.
    g = _graph(xRange=[-4, 4], yRange=[-4, 4], polygons=[{"pts": pts}])
    doc, errors = ws.validate_board_json(_doc(_board(sections=[g])))
    assert any(e["code"] == "cirkelaspekt" for e in errors)


def test_square_circle_polygon_ok():
    import math
    pts = [[3 * math.cos(2 * math.pi * i / 48), 3 * math.sin(2 * math.pi * i / 48)]
           for i in range(48)]
    g = _graph(width=400, height=400, xRange=[-4, 4], yRange=[-4, 4],
               polygons=[{"pts": pts}])
    doc, errors = ws.validate_board_json(_doc(_board(sections=[g])))
    assert errors == []


def test_graph_wider_than_column_flagged():
    wide = _graph(width=800)
    board = _board(sections=None, columns=[
        {"weight": 1, "sections": [wide]},
        {"weight": 1, "sections": [{"kind": "text", "text": "höger"}]},
    ])
    doc, errors = ws.validate_board_json(_doc(board))
    assert any(e["code"] == "grafbredd" for e in errors)


def test_decimal_point_in_text_flagged():
    doc, errors = ws.validate_board_json(
        _doc(_board(sections=[{"kind": "text", "text": "svaret är 4.58 m"}])))
    assert any(e["code"] == "decimalpunkt" for e in errors)


def test_decimal_comma_in_latex_ok():
    doc, errors = ws.validate_board_json(
        _doc(_board(sections=[{"kind": "math", "latex": "h \\approx 4{,}58"}])))
    assert errors == []


def test_decimal_point_in_expr_allowed():
    g = _graph(plots=[{"expr": "0.5*x^2", "color": "red"}])
    doc, errors = ws.validate_board_json(_doc(_board(sections=[g])))
    assert errors == []


def test_long_text_flagged():
    """Bench Fas 2: långa löptexter spränger kolumnbredden i motorn —
    deterministisk gräns ger modellen ett åtgärdbart fel före rendering."""
    lang = "I denna lektion kommer vi att gå igenom hur man använder " \
           "areasatsen och sinussatsen för att beräkna okända sidor och " \
           "vinklar i godtyckliga trianglar."
    doc, errors = ws.validate_board_json(
        _doc(_board(sections=[{"kind": "text", "text": lang}])))
    assert any(e["code"] == "text-lang" for e in errors)


def test_long_list_item_flagged():
    item = "Standardvinklarna är 0, pi/6, pi/4, pi/3, pi/2 och deras " \
           "motsvarigheter i alla fyra kvadranter på enhetscirkeln"
    doc, errors = ws.validate_board_json(
        _doc(_board(sections=[{"kind": "list", "items": [item]}])))
    assert any(e["code"] == "text-lang" for e in errors)


def test_long_text_in_callout_flagged():
    lang = "x" * 120
    callout = {"kind": "callout", "children": [{"kind": "text", "text": lang}]}
    doc, errors = ws.validate_board_json(_doc(_board(sections=[callout])))
    assert any(e["code"] == "text-lang" for e in errors)


def test_textbudget_faller_en_pratig_tavla():
    """Lärarens fjärde dom: hennes egen vänstertavla bar 603 tecken text och
    hon skrev aldrig upp det mesta. Varje RAD var kort nog — det är MÄNGDEN som
    är felet, och den ser ingen per-sektionsregel."""
    rader = [{"kind": "text", "text": "En rad som är fullt rimlig i sig själv."}
             for _ in range(12)]
    doc, errors = ws.validate_board_json(_doc(_board(sections=rader)))
    budget = [e for e in errors if e["code"] == "textbudget"]
    assert budget, errors
    assert "SKRIVS" in budget[0]["message"]
    # Ingen enskild rad är för lång — det är just poängen.
    assert not any(e["code"] == "text-lang" for e in errors)


def test_textbudgeten_raknar_inte_matte_rubriker_och_tabellceller():
    """Åtgärden budgeten vill framkalla är att flytta prosa till formler och en
    tabell. Räknades tabellcellerna vore åtgärden verkningslös."""
    tung = _board(sections=[
        {"kind": "heading", "text": "En ovanligt lång rubrik om extrempunkter"},
        {"kind": "math", "latex": "f'(x) = 3x^2 - 12x + 9 = 3(x-1)(x-3)"},
        {"kind": "table", "headers": ["Uttryck", "Byggt av", "Regel", "Svar"],
         "rows": [["x^2 sin x", "två faktorer", "produktregeln",
                   "2x sin x + x^2 cos x"],
                  ["(3x+1)^5", "funktion i funktion", "kedjeregeln",
                   "15(3x+1)^4"]]},
    ])
    doc, errors = ws.validate_board_json(_doc(tung))
    assert not any(e["code"] == "textbudget" for e in errors), errors


def test_latex_in_text_flagged():
    """Bench Fas 2: modellen skrev LaTeX med $-tecken i text-sektioner —
    renderas som rå text på tavlan. Fångas deterministiskt."""
    doc, errors = ws.validate_board_json(
        _doc(_board(sections=[{"kind": "text",
                               "text": "Areasatsen: $ A = \\frac{1}{2}ab $"}])))
    assert any(e["code"] == "latex-i-text" for e in errors)


def test_latex_command_without_dollar_flagged_in_list():
    doc, errors = ws.validate_board_json(
        _doc(_board(sections=[{"kind": "list",
                               "items": ["Sinussatsen: \\frac{a}{\\sin A}"]}])))
    assert any(e["code"] == "latex-i-text" for e in errors)


def test_control_chars_flagged():
    """O-escapad backslash i JSON: \\f i \\frac blir sidmatningstecken."""
    doc, errors = ws.validate_board_json(
        _doc(_board(sections=[{"kind": "math", "latex": "A = \frac{1}{2}"}])))
    assert any(e["code"] == "kontrolltecken" for e in errors)


def test_latex_commands_allowed_in_math_latex():
    doc, errors = ws.validate_board_json(
        _doc(_board(sections=[{"kind": "math", "latex": "\\frac{a}{b} = \\sqrt{2}"}])))
    assert errors == []


def test_short_text_ok():
    doc, errors = ws.validate_board_json(
        _doc(_board(sections=[{"kind": "text", "text": "Kort och tydlig rad."}])))
    assert errors == []


def test_empty_board_flagged():
    doc, errors = ws.validate_board_json(_doc(_board(sections=None)))
    assert any(e["code"] == "tom-tavla" for e in errors)


def test_invalid_range_flagged():
    g = _graph(xRange=[5, -1])
    doc, errors = ws.validate_board_json(_doc(_board(sections=[g])))
    assert any(e["code"] == "range" for e in errors)


# ---------------------------------------------------------- normalisering --

def test_normalize_splits_long_text():
    lang = ("I denna lektion kommer vi att gå igenom hur man använder "
            "areasatsen och sinussatsen för att beräkna okända sidor och "
            "vinklar i godtyckliga trianglar.")
    data = _doc(_board(sections=[
        {"kind": "text", "text": lang, "size": 20, "color": "blue"}]))
    norm = ws.normalize_board(data)
    parts = norm["boards"][0]["sections"]
    assert len(parts) > 1
    assert all(p["kind"] == "text" and len(p["text"]) <= 90 for p in parts)
    assert all(p["color"] == "blue" for p in parts)      # stil följer med
    assert " ".join(p["text"] for p in parts) == lang    # inget innehåll tappas
    # …och efter normalisering passerar tavlan valideringen
    doc, errors = ws.validate_board_json(norm)
    assert errors == []


def test_normalize_dedupes_consecutive_duplicates():
    sec = {"kind": "text", "text": "Topptriangelsatsen gäller."}
    data = _doc(_board(sections=[dict(sec), dict(sec)]))
    norm = ws.normalize_board(data)
    assert len(norm["boards"][0]["sections"]) == 1


def test_normalize_byter_thickness_till_strokewidth():
    """Modellen skriver envist thickness på pilar (två inspelningar av tre
    2026-08-21) — synonymen döps om deterministiskt i stället för att kosta
    en reparationsrunda. Andra okända nycklar ska fortfarande fällas."""
    data = _doc(_board(sections=[
        {"kind": "graph", "width": 400, "height": 300,
         "xRange": [-5, 5], "yRange": [-5, 5],
         "arrows": [{"from": [0, 0], "to": [2, 2], "thickness": 3},
                    {"from": [0, 0], "to": [1, 2],
                     "thickness": 9, "strokeWidth": 2}]}]))
    norm = ws.normalize_board(data)
    pilar = norm["boards"][0]["sections"][0]["arrows"]
    assert pilar[0] == {"from": [0, 0], "to": [2, 2], "strokeWidth": 3}
    # står strokeWidth redan där vinner den — thickness slängs bara
    assert pilar[1] == {"from": [0, 0], "to": [1, 2], "strokeWidth": 2}
    _, errors = ws.validate_board_json(norm)
    assert errors == []
    # en annan okänd nyckel städas INTE — den ska ge schemafel
    data2 = _doc(_board(sections=[
        {"kind": "graph", "width": 400, "height": 300,
         "xRange": [-5, 5], "yRange": [-5, 5],
         "arrows": [{"from": [0, 0], "to": [2, 2], "glow": True}]}]))
    _, errors2 = ws.validate_board_json(ws.normalize_board(data2))
    assert any(f["code"] == "schema" for f in errors2)


def test_normalize_handles_columns_and_callouts():
    lang = "x" * 60 + " " + "y" * 60
    board = _board(sections=None, columns=[
        {"weight": 1, "sections": [
            {"kind": "callout", "children": [{"kind": "text", "text": lang}]}]},
    ])
    norm = ws.normalize_board(_doc(board))
    children = norm["boards"][0]["columns"][0]["sections"][0]["children"]
    assert len(children) == 2


def test_normalize_explodes_inline_math_to_row():
    """Bench Fas 2: "Svar: … $\\frac{2}{9}$." i text → row med text+math."""
    data = _doc(_board(sections=[
        {"kind": "text", "text": "Svar: Sannolikheten är $\\frac{2}{9}$.",
         "size": 18, "color": "blue", "gapAfter": 12}]))
    norm = ws.normalize_board(data)
    row = norm["boards"][0]["sections"][0]
    assert row["kind"] == "row" and row["gapAfter"] == 12
    kinds = [c["kind"] for c in row["children"]]
    assert kinds == ["text", "math"]
    assert row["children"][1]["latex"] == "\\frac{2}{9}"
    assert row["children"][0]["color"] == "blue"
    doc, errors = ws.validate_board_json(norm)
    assert errors == []


def test_normalize_pure_inline_math_becomes_math_section():
    data = _doc(_board(sections=[{"kind": "text", "text": "$x^2 + 1$"}]))
    norm = ws.normalize_board(data)
    sec = norm["boards"][0]["sections"][0]
    assert sec["kind"] == "math" and sec["latex"] == "x^2 + 1"


def test_normalize_inline_math_i_behallare_stannar_som_lov():
    """Inuti en behållare är bara löv tillåtna — delarna läggs plant, ingen row.
    (Behållaren är en col: callout är förbjuden på tavlan, se rutregeln.)"""
    col = {"kind": "col", "children": [
        {"kind": "text", "text": "Svar: $\\frac{1}{2}$."}]}
    norm = ws.normalize_board(_doc(_board(sections=[col])))
    children = norm["boards"][0]["sections"][0]["children"]
    assert [c["kind"] for c in children] == ["text", "math"]
    doc, errors = ws.validate_board_json(norm)
    assert errors == []


def test_rutor_falls_deterministiskt():
    """Lärarens dom: «alla de här blå och röda rutorna, inringande liksom — det
    gör jag inte på tavlan själv.» Prompten säger det, men prompten driver;
    regeln fäller."""
    callout = {"kind": "callout", "children": [
        {"kind": "text", "text": "Svar: 12 cm"}]}
    _doc_, errors = ws.validate_board_json(_doc(_board(sections=[callout])))
    assert [e["code"] for e in errors] == ["ruta"]
    # …även nedgrävd i en row/col, där den annars sluppit undan.
    djup = {"kind": "row", "children": [
        {"kind": "col", "children": [{"kind": "text", "text": "x"}]}]}
    assert ws.validate_board_json(_doc(_board(sections=[djup])))[1] == []


# ------------------------------------------------------------ facitvakten --
# Lärarens dom (2026-08-20, upprepad 2026-09-05 när en tavla om linjära
# funktioner skrev ut hela avläsningen): «Jag kommer ju göra själva
# uträkningarna. Det räcker med en stark utgångspunkt. Massa färdiga
# uträkningar behövs inte.» Vakten är KONSERVATIV: en given ekvation är inte
# en uträkning, och tavlans egen fallgrop under «Vanligt fel:» är beställd.
#
# LaTeX skrivs med BS + kommandonamn i stället för dubbla backslashar: de
# blir oläsliga i en testfil full av dem, och det är exakt de raderna som
# avgör om vakten fäller rätt.
BS = chr(92)


def _hoger(sektioner):
    """En högertavla med EN exempelkolumn — boards[1], där exempel bor."""
    b = _board(width=1800, name="hoger")
    del b["sections"]
    b["columns"] = [{"weight": 1, "sections": sektioner}]
    return _doc(_board(), b)


def _tex(kort):
    for tecken, kommando in (("QQQ", "sqrt"), ("RR", "Rightarrow"),
                             ("QQ", "quad"), ("SS", ";"), ("TT", "to"),
                             ("CC", "cdot"), ("FF", "frac"), ("KK", ","),
                             ("PM", "pm")):
        kort = kort.replace(tecken, BS + kommando)
    return kort


UTRAKNINGAR = [
    "260 - 200 = 60 RR k = 60,QQ m = 200",
    "y = 60x RR k = 60,SS m = 0",
    "(0,KK 600) TT (1,KK 500) RR k = -100,SS m = 600",
    "A = 3 CC 4 = 12",
]
GIVNA = [
    "x^2 + 6x - 7 = 0",
    "f(x) = -x^2 - 2x + 3",
    "FF{x+2}{3} + FF{x+2}{6}",
    "y = -100x + 600",
    "a^2 + b^2 = c^2",
    "y = kx + m",
    "A = a^2 RR a = QQQ{A}",
    "(a + b)(c + d) = ac + ad + bc + bd",
    "2x^2 + 3x = 5x^2",
]


@pytest.mark.parametrize("latex", UTRAKNINGAR)
def test_fardig_utrakning_i_ett_exempel_falls(latex):
    _d, fel = ws.validate_board_json(_hoger([
        {"kind": "heading", "text": "Exempel 1"},
        {"kind": "math", "latex": _tex(latex)}]))
    assert [e["code"] for e in fel] == ["facit"], (latex, fel)


@pytest.mark.parametrize("latex", GIVNA)
def test_uppgiftens_egen_rad_star_kvar(latex):
    """Ekvationen som GES är ingen uträkning och ska stå kvar."""
    _d, fel = ws.validate_board_json(_hoger([
        {"kind": "heading", "text": "Exempel 1"},
        {"kind": "math", "latex": _tex(latex)}]))
    assert fel == [], (latex, fel)


def test_det_felaktiga_ledet_under_vanligt_fel_ar_bestallt():
    """Regel 9 BER om det felaktiga ledet i en math-sektion. Vakten får inte
    fälla tavlans egen fallgrop — men bara den FÖRSTA math-raden efter
    rubriken undantas: det var raden EFTER förklaringen som var facit."""
    rader = [
        {"kind": "heading", "text": "Exempel 1"},
        {"kind": "text", "text": "Vanligt fel:"},
        {"kind": "underline"},
        {"kind": "math", "latex": _tex("2x = 10 RR x = 5")},
        {"kind": "text", "text": "Saldot minskar."}]
    assert ws.validate_board_json(_hoger(rader))[1] == []
    dalig = rader + [{"kind": "math", "latex": _tex("y = 60x RR k = 60,SS m = 0")}]
    assert [e["code"] for e in ws.validate_board_json(_hoger(dalig))[1]] == ["facit"]


def test_sifferexempel_pa_vanstern_falls():
    """«y = 4 - 5x => k = -5, m = 4» stod på vänstern, efter Vanligt fel.
    Regel 8b förbjöd det redan; ingen vakt fällde det."""
    vanster = _board(sections=[
        {"kind": "heading", "text": "Linjära funktioner"},
        {"kind": "math", "latex": _tex("y = kx + m")},
        {"kind": "text", "text": "Vanligt fel:"},
        {"kind": "math", "latex": _tex("y = 4 - 5x RR k = 5")},
        {"kind": "text", "text": "Tecknet framför x hör till k."},
        {"kind": "math", "latex": _tex("y = 4 - 5x RR k = -5,SS m = 4")}])
    fel = ws.validate_board_json(_doc(vanster))[1]
    assert [e["code"] for e in fel] == ["siffror_vanster"], fel
    assert "sections[5]" in fel[0]["path"]


def test_vansterns_bokstavsformler_star_kvar():
    """Pythagoras sats är bokstäver: exponenterna är inte tal att räkna med."""
    for latex in ("a^2 + b^2 = c^2", "y = kx + m", "x^2 + 6x - 7 = 0",
                  "(a + b)(c + d) = ac + ad + bc + bd", "A = a^2 RR a = QQQ{A}"):
        vanster = _board(sections=[{"kind": "math", "latex": _tex(latex)}])
        assert ws.validate_board_json(_doc(vanster))[1] == [], latex


def test_vakten_gar_ned_i_row_och_col():
    """Den fällda tavlan bar båda raderna nedgrävda i en row/col."""
    rad = {"kind": "row", "children": [
        {"kind": "col", "children": [
            {"kind": "math", "latex": _tex("y = 4 - 5x RR k = -5,SS m = 4")}]}]}
    fel = ws.validate_board_json(_doc(_board(sections=[rad])))[1]
    assert [e["code"] for e in fel] == ["siffror_vanster"]


# ------------------------------------------------------------- ankaret ----
# Lärarens dom 2026-09-20 (Origo 2a 1.3): «rätt men för lite och för
# spretigt; eleverna får inte det som gör att de kan börja i boken.» Hon bad
# om x^2 = 64 ⇒ x = ±8 före den allmänna formeln, och siffervakten strök den.
# Undantaget är ETT ankare, och de tre testerna nedan är hela definitionen.
def _vanster_med(rader):
    return _doc(_board(sections=[{"kind": "row", "children": [
        {"kind": "col", "children": rader}]}]))


ANKARET = {"kind": "math", "latex": _tex("x^2 = 64 RR x = PM 8")}
FORMELN = {"kind": "math", "latex": _tex("x^2 = a RR x = PM QQQ{a}")}


def test_ankaret_gar_igenom_siffervakten():
    """Ankaret står DIREKT FÖRE bokstavsformeln det förklarar — och bara
    därför får det stå: raden är varför ±:et finns."""
    fel = ws.validate_board_json(_vanster_med([
        {"kind": "text", "text": "Kvadratrot: ETT tal, alltid positivt"},
        ANKARET,
        {"kind": "text", "text": "Både 8 och −8 i kvadrat blir 64."},
        FORMELN]))[1]
    assert fel == [], fel


def test_ett_andra_sifferled_falls_anda():
    """ETT ankare, inte två. Det andra har ingen formel efter sig och är
    tillbaka till det regel 8b alltid har förbjudit: ett exempel på vänstern."""
    fel = ws.validate_board_json(_vanster_med([
        ANKARET,
        FORMELN,
        {"kind": "math", "latex": _tex("x^2 = 25 RR x = PM 5")}]))[1]
    assert [e["code"] for e in fel] == ["siffror_vanster"], fel


# ------------------------------------------------- «Att tänka på»-raderna --
# Andra rundan 2026-09-20, mätt på den skarpa kontrolltavlan för Origo 2a 1.3
# (tests/tavlor/kontroll-origo-2a-1-3.json). Blocket kom samma morgon och blev
# tunt därför att domaren fällde x^2 = -20 och x = ±√27 som «andra sifferrad
# på vänstern» (jobb 480, seq 7–8). Ett randfall ÄR ett tal: «en kvadrat blir
# aldrig negativ» går inte att visa i bokstäver.
def _kontrolltavlan() -> dict:
    with open(Path(__file__).parent / "tavlor" / "kontroll-origo-2a-1-3.json",
              encoding="utf-8") as f:
        return json.load(f)


def _att_tanka_pa_spalten(doc: dict) -> list:
    """Vänstertavlans andra col — den som bär skelettet."""
    return doc["boards"][0]["sections"][-1]["children"][1]["children"]


# BUDGETFYNDET RÄKNAS BORT I DE HÄR TESTERNA (2026-09-21). Fixturen är den
# skarpa tavlan från 2026-09-20 och bär 288 tecken; taket gick samma vecka
# till 270 på lärarens ord («det blir så jävla mycket på vänstra tavlan …
# kanske 30 %»). Tavlan är alltså FÖR LÅNG nu, och det är hela poängen med
# sänkningen — men det som prövas här är randfallens undantag från
# SIFFERVAKTEN, inte budgeten. Att taket biter mäts för sig, i
# test_gamla_kontrolltavlan_faller_pa_det_nya_taket.
def _utan_budget(fel: list) -> list:
    return [f for f in fel if f.get("code") != "textbudget"]


# Etiketterna är korta med flit: taket gick 45 → 30 tecken 2026-09-21, och
# «En kvadrat blir aldrig negativ.» var 31 och vägdes som en mening.
RANDFALLEN = [
    {"kind": "math", "latex": _tex("x^2 = -20")},
    {"kind": "text", "text": "Aldrig negativ."},
    {"kind": "math", "latex": _tex("x^2 = 0 RR x = 0")},
    {"kind": "text", "text": "Noll ger en enda rot."},
    {"kind": "math", "latex": _tex("x^2 = 27 RR x = PM QQQ{27}")},
    {"kind": "text", "text": "Exakt om inget sägs."},
]


def test_kontrolltavlan_ar_giltig_som_den_star():
    """Fixturen är den tavla läraren dömde, byte för byte. Ändras vakterna
    ska det synas här först — budgeten undantagen, se _utan_budget."""
    doc, fel = ws.validate_board_json(_kontrolltavlan())
    assert doc is not None and _utan_budget(fel) == [], fel


def test_gamla_kontrolltavlan_faller_pa_det_nya_taket():
    """Och åt andra hållet: tavlan som gick igenom på 390 gör det inte på
    270. Det är vad läraren beställde 2026-09-21 — «bara ha kvar det mest
    väsentliga, ta bort lite text»."""
    fel = ws.validate_board_json(_kontrolltavlan())[1]
    assert [f["code"] for f in fel] == ["textbudget"], fel
    assert "270" in fel[0]["message"]


def test_randfallen_under_att_tanka_pa_gar_igenom():
    """De tre rader läraren bad om i andra rundan. Två av dem fälls utan
    undantaget: x^2 = 0 ⇒ x = 0 och x^2 = 27 ⇒ x = ±√27 har tal på båda sidor
    om pilen, och det är precis formen siffervakten finns för — utom här,
    där talet ÄR poängen."""
    doc = _kontrolltavlan()
    spalt = _att_tanka_pa_spalten(doc)
    del spalt[-3:]                        # den tunna versionen läraren fällde
    spalt += RANDFALLEN
    _d, fel = ws.validate_board_json(doc)
    assert _utan_budget(fel) == [], fel


def test_randfallen_kanns_igen_ocksa_under_den_numrerade_rubriken():
    """Rubriken heter «3. Att tänka på» sedan formdomen 2026-09-20 (kväll):
    numreringen är dispositionen. Kände vakten inte igen den föll randfallen
    igen — och det var precis vad som hände i första renderingen av tredje
    rundans tavla. (Pilen mellan receptet och rubriken, 6c, är en ren
    math-rad och stör inte uppslagningen.)"""
    doc = _kontrolltavlan()
    spalt = _att_tanka_pa_spalten(doc)
    rubrik = next(s for s in spalt if s.get("text") == "Att tänka på")
    rubrik["text"] = "3. Att tänka på"
    del spalt[-3:]
    spalt.insert(len(spalt) - 1, {"kind": "math", "latex": "\\Downarrow"})
    spalt += RANDFALLEN
    _d, fel = ws.validate_board_json(doc)
    assert _utan_budget(fel) == [], fel


def test_en_fjarde_randfallsrad_falls():
    """Undantaget är kapat vid tre math-rader. En fjärde sifferrad under
    rubriken är tillbaka till exempel på fel tavla."""
    doc = _kontrolltavlan()
    spalt = _att_tanka_pa_spalten(doc)
    del spalt[-3:]
    spalt += RANDFALLEN + [
        {"kind": "math", "latex": _tex("x^2 = 49 RR x = PM 7")},
        {"kind": "text", "text": "Sju och minus sju."}]
    _d, fel = ws.validate_board_json(doc)
    assert [f["code"] for f in _utan_budget(fel)] == ["siffror_vanster"], fel
    assert "49" in _utan_budget(fel)[0]["message"]


def test_randfallens_etiketter_kostar_inget_i_budgeten():
    """Etiketten är en bildtext till math-raden, inte prosa. När budgeten
    vägde den som en mening lappade den bort just de rader domaren nyss hade
    beställt (jobb 480, seq 13).

    TVÅ ÅKER GRATIS sedan 2026-09-21 (_FRIA_ETIKETTER): prompten säger HÖGST
    TVÅ rader under «Att tänka på», och en tredje ska kosta sin plats."""
    def volym(d):
        return ws._text_volym(ws.validate_board_json(d)[0].boards[0].sections)

    doc = _kontrolltavlan()
    spalt = _att_tanka_pa_spalten(doc)
    del spalt[-3:]
    fore = volym(doc)
    spalt += RANDFALLEN[:4]
    # Två math-rader och två etiketter, 36 tecken — budgeten rör sig inte.
    assert volym(doc) == fore, (fore, volym(doc))
    # Den TREDJE etiketten vägs som vilken text som helst.
    spalt += RANDFALLEN[4:]
    assert volym(doc) == fore + len("Exakt om inget sägs.")
    # …och en LÅNG rad under rubriken är en mening och vägs som en mening.
    spalt.append({"kind": "text", "text": "x" * 50})
    assert volym(doc) == fore + len("Exakt om inget sägs.") + 50


def test_ankare_utan_bokstavsformel_efter_sig_falls():
    """Utan formeln under sig är sifferraden inget ankare utan ett exempel —
    det är formeln som gör raden till ett varför."""
    fel = ws.validate_board_json(_vanster_med([
        ANKARET,
        {"kind": "text", "text": "Både 8 och −8 i kvadrat blir 64."}]))[1]
    assert [e["code"] for e in fel] == ["siffror_vanster"], fel


def test_figur_i_row_valideras_som_en_figur():
    """Figurerna får ligga i en row (figur till vänster, formler till höger).
    Då måste grafreglerna gälla DÄR INNE också — annars blir raden en dörr
    förbi bredd, cirkelaspekt och uttryckssyntax."""
    graf = {"kind": "graph", "width": 2000, "height": 300,
            "xRange": [0, 5], "yRange": [0, 5],
            "plots": [{"expr": "x^^2"}]}
    rad = {"kind": "row", "children": [
        graf, {"kind": "col", "children": [{"kind": "math", "latex": "k = 2"}]}]}
    _doc_, errors = ws.validate_board_json(_doc(_board(sections=[rad])))
    koder = {e["code"] for e in errors}
    assert "grafbredd" in koder and "uttrycksfel" in koder


def test_normalize_leaves_original_untouched():
    lang = "z" * 120
    data = _doc(_board(sections=[{"kind": "text", "text": lang}]))
    ws.normalize_board(data)
    assert data["boards"][0]["sections"][0]["text"] == lang


# --------------------------------------------------------- uttrycksparsern --

@pytest.mark.parametrize("expr", [
    "x", "42", "3.5", "pi", "e",
    "x^2 - 2*x + 1",
    "sin(x)", "cos(2*x)", "sqrt(x + 1)",
    "-x", "--x", "2^-x",
    "abs(x)/2 + ln(x)",
    "0.5*x^2 + exp(-x)",
    "(x + 1)*(x - 1)",
])
def test_valid_expressions(expr):
    assert ws.validate_expr(expr) is None, expr


@pytest.mark.parametrize("expr", [
    "", "  ",
    "y + 1",                    # okänd variabel
    "x; alert(1)",              # otillåtna tecken
    "x + ",                     # slutar oväntat
    "sin x",                    # funktion utan parentes
    "foo(x)",                   # okänd funktion
    "(x + 1",                   # obalanserad parentes
    "x ** 2",                   # JS-potens — vi kräver ^
    "1..2",
    "x!",
    "Math.pow(x, 2)",
])
def test_invalid_expressions(expr):
    assert ws.validate_expr(expr) is not None, expr
