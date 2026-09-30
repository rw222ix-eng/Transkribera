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


def test_lektionstiden_kostar_inget_i_budgeten():
    """Tiden sätts av systemet efter valideringen (lesson_board.satt_tid),
    som «Förra gången». Den skarpa pq-tavlan 2026-09-27 gick igenom på 186
    av 190 och fälldes sedan på 197 när klockslaget kommit dit."""
    med = ws.validate_board_json(_doc(_board(sections=[
        {"kind": "text", "text": "08:10–09:40"},
        {"kind": "text", "text": "En rad som kostar"}])))[0]
    utan = ws.validate_board_json(_doc(_board(sections=[
        {"kind": "text", "text": "En rad som kostar"}])))[0]
    assert (ws._text_volym(med.boards[0].sections)
            == ws._text_volym(utan.boards[0].sections) == 17)


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


# ---------------------------------------------- facitvakten och siffrorna --
# Facitvakten (2026-09-05, koden `facit`) fällde uträkningar i exemplen på
# högertavlan: «Massa färdiga uträkningar behövs inte.» Lärarens dom
# 2026-09-23 vände det: «Istället för all den här texten så är det ju bättre
# att ha själva uträkningen istället.» Högertavlan döms därför inte längre
# här (den vända vakten, lesson_board.utrakningsvakt, körs vid genereringen).
# Siffervakten på VÄNSTERN står kvar: den är KONSERVATIV, en given ekvation
# är inte en uträkning, och tavlans egen fallgrop under «Vanligt fel:» är
# beställd.
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
def test_utrakningen_i_ett_exempel_star_kvar(latex):
    """Samma rader som facitvakten fällde till 2026-09-23. Nu är de
    exemplets uträkning, och validatorn har inget att säga om dem."""
    _d, fel = ws.validate_board_json(_hoger([
        {"kind": "heading", "text": "Exempel 1"},
        {"kind": "math", "latex": _tex(latex)}]))
    assert fel == [], (latex, fel)


@pytest.mark.parametrize("latex", UTRAKNINGAR)
def test_samma_rader_pa_vanstern_falls_fortfarande(latex):
    """Vänstern bär bokstäver (regel 8b), och den domen rördes inte."""
    vanster = _board(sections=[{"kind": "math", "latex": _tex(latex)}])
    fel = ws.validate_board_json(_doc(vanster))[1]
    assert [e["code"] for e in fel] == ["siffror_vanster"], (latex, fel)


@pytest.mark.parametrize("latex", GIVNA)
def test_uppgiftens_egen_rad_star_kvar(latex):
    """Ekvationen som GES är ingen uträkning och ska stå kvar."""
    _d, fel = ws.validate_board_json(_hoger([
        {"kind": "heading", "text": "Exempel 1"},
        {"kind": "math", "latex": _tex(latex)}]))
    assert fel == [], (latex, fel)


def test_det_felaktiga_ledet_under_vanligt_fel_ar_bestallt():
    """Regel 9 BER om det felaktiga ledet i en math-sektion. Siffervakten får
    inte fälla tavlans egen fallgrop, men bara den FÖRSTA math-raden efter
    rubriken undantas: det var raden EFTER förklaringen som var sifferexemplet.
    (Prövades på högertavlan till 2026-09-23, då facitvakten ströks.)"""
    rader = [
        {"kind": "heading", "text": "Linjära funktioner"},
        {"kind": "text", "text": "Vanligt fel:"},
        {"kind": "underline"},
        {"kind": "math", "latex": _tex("2x = 10 RR x = 5")},
        {"kind": "text", "text": "Saldot minskar."}]
    assert ws.validate_board_json(_doc(_board(sections=rader)))[1] == []
    dalig = rader + [{"kind": "math", "latex": _tex("y = 60x RR k = 60,SS m = 0")}]
    fel = ws.validate_board_json(_doc(_board(sections=dalig)))[1]
    assert [e["code"] for e in fel] == ["siffror_vanster"], fel


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
    väsentliga, ta bort lite text». Taket sänktes igen 2026-09-27, 270 →
    190, när receptet ströks (lesson_board 8f), och mättes om 2026-09-29
    till 205 mot lärarens tavla «Formler» (se _MAX_BOARD_TEXT)."""
    fel = ws.validate_board_json(_kontrolltavlan())[1]
    assert [f["code"] for f in fel] == ["textbudget"], fel
    assert "~205" in fel[0]["message"]


def test_randfallen_under_att_tanka_pa_ar_inte_undantagna_langre():
    """«Att tänka på» är struket (lärarens dom 2026-09-29, Rickard): «de här
    att tänka på, det kommer ju egentligen när vi löser uppgifterna sen. Så
    det behöver vi inte.» Här stod sedan 2026-09-20 fyra tester för
    undantaget: tre math-rader under rubriken släpptes av siffervakten, också
    under den numrerade rubriken, och två etiketter var fria i budgeten. Nu
    döms raderna som vilken rad som helst på vänstern: sifferraderna med pil
    fälls, och etiketterna kostar."""
    doc = _kontrolltavlan()
    spalt = _att_tanka_pa_spalten(doc)
    del spalt[-3:]
    fore = ws._text_volym(ws.validate_board_json(doc)[0].boards[0].sections)
    spalt += RANDFALLEN
    parsed, fel = ws.validate_board_json(doc)
    fallda = [f["message"] for f in _utan_budget(fel)
              if f["code"] == "siffror_vanster"]
    assert len(fallda) == 2 and "x^2 = 0" in fallda[0], fel
    etiketter = sum(len(s["text"]) for s in RANDFALLEN if s["kind"] == "text")
    assert ws._text_volym(parsed.boards[0].sections) == fore + etiketter
    assert not hasattr(ws, "_randfallsblocket")


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


def test_tick_etiketterna_far_avstand_fran_axeln():
    """Lärarens dom 2026-09-23 kväll: grafen var «slarvigt ritad». Motorn
    ritar en tick-etikett i datakoordinaten plus dx/dy, med 0 som förval, så
    «1» stod mitt på x-axeln. Normaliseringen fyller i facits avstånd där
    fälten SAKNAS, också inne i en row/col, och rör inte det som är satt."""
    graf = {"kind": "graph", "width": 360, "height": 230,
            "xRange": [0, 3.8], "yRange": [0, 280],
            "ticks": [{"axis": "x", "at": 1, "label": "1"},
                      {"axis": "y", "at": 80, "label": "80"},
                      {"axis": "x", "at": 2, "label": "2", "dy": 0},
                      {"axis": "y", "at": 160, "label": "160", "dx": -12}]}
    data = _doc(_board(sections=[
        {"kind": "row", "children": [
            {"kind": "col", "width": 400, "children": [graf]}]}]))
    ut = ws.normalize_board(data)
    ticks = ut["boards"][0]["sections"][0]["children"][0]["children"][0]["ticks"]
    assert ticks[0] == {"axis": "x", "at": 1, "label": "1", "dy": 22}
    assert ticks[1] == {"axis": "y", "at": 80, "label": "80", "dx": -8, "dy": 6}
    assert ticks[2]["dy"] == 0 and "dx" not in ticks[2]
    assert ticks[3]["dx"] == -12 and ticks[3]["dy"] == 6
    # Originalet rörs inte, och tavlan validerar som förut.
    assert "dy" not in graf["ticks"][0]
    assert ws.validate_board_json(ut)[1] == []


def test_bagar_i_grader_blir_radianer():
    """Jobb 1185 (NA26F Trigonometri 2026-10-02): modellen skrev vinkeln v
    som {"from": 143.13, "to": 180}, motorn läser radianer och ritade en
    nästan hel cirkel utanför triangeln. Normaliseringen räknar om grader
    och rör inte bågar som redan står i radianer."""
    import math
    tri = [[0, 0], [4, 0], [0, 3]]
    graf = {"kind": "graph", "width": 360, "height": 280,
            "xRange": [-0.5, 4.5], "yRange": [-0.5, 3.5],
            "polygons": [{"pts": tri}],
            "arcs": [{"cx": 4, "cy": 0, "r": 0.6, "from": 143.13, "to": 180,
                      "interior": [1.33, 1]},
                     {"cx": 0, "cy": 0, "r": 0.4, "from": 0,
                      "to": math.pi / 2, "interior": [1.33, 1]},
                     {"cx": 0, "cy": 3, "r": 0.5, "from": -90, "to": -36.87,
                      "interior": [1.33, 1]}]}
    data = _doc(_board(sections=[
        {"kind": "row", "children": [
            {"kind": "col", "width": 400, "children": [graf]}]}]))
    ut = ws.normalize_board(data)
    bagar = ut["boards"][0]["sections"][0]["children"][0]["children"][0]["arcs"]
    assert bagar[0]["from"] == pytest.approx(math.radians(143.13), abs=1e-6)
    assert bagar[0]["to"] == pytest.approx(math.pi, abs=1e-6)
    assert bagar[1]["from"] == 0 and bagar[1]["to"] == math.pi / 2
    assert bagar[2]["from"] == pytest.approx(-math.pi / 2, abs=1e-6)
    assert bagar[2]["to"] == pytest.approx(math.radians(-36.87), abs=1e-6)
    # Originalet rörs inte, och tavlan validerar.
    assert graf["arcs"][0]["from"] == 143.13
    assert ws.validate_board_json(ut)[1] == []


def _figur(ut: dict) -> dict:
    return ut["boards"][0]["sections"][0]


def test_figurtexter_forankras_utanfor_benet():
    """Lärarens handrättning 2026-09-30 (NA26F, dokument 304): motorn
    förankrar figurtexter i `start`, modellen skriver mitten, och «a = 12 m»
    kröp in över triangelns lodräta ben. Text vänster om ett lodrätt ben
    får `end` strax utanför benet, text inne i figuren eller vid en annan
    kant `middle` på samma plats. En satt anchor rörs inte. Två likformiga
    trianglar: «12» vid den lillas ben ligger inne i den stora men utanför
    sin egen, och förankras vid den lillas ben."""
    graf = {"kind": "graph", "width": 290, "height": 175,
            "xRange": [-0.6, 3.8], "yRange": [-0.35, 2.75], "axes": False,
            "polygons": [{"pts": [[0, 0], [3.2, 0], [0, 2.4]]},
                         {"pts": [[1.6, 0], [3.2, 0], [1.6, 1.2]]}],
            "texts": [{"x": -0.3, "y": 1.2, "text": "24"},
                      {"x": 1.35, "y": 0.6, "text": "12"},
                      {"x": 2.6, "y": 0.85, "text": "20"},
                      {"x": 1.6, "y": -0.25, "text": "b = ?"},
                      {"x": -0.3, "y": 0.5, "text": "egen", "anchor": "start"}]}
    ut = ws.normalize_board(_doc(_board(sections=[graf])))
    t = _figur(ut)["texts"]
    assert t[0]["anchor"] == "end" and -0.2 < t[0]["x"] < 0
    assert t[1]["anchor"] == "end" and 1.4 < t[1]["x"] < 1.6
    assert (t[2]["anchor"], t[2]["x"]) == ("middle", 2.6)
    assert (t[3]["anchor"], t[3]["x"]) == ("middle", 1.6)
    assert (t[4]["anchor"], t[4]["x"]) == ("start", -0.3)
    assert "anchor" not in graf["texts"][0]
    assert ws.validate_board_json(ut)[1] == []
    # En funktionsgraf utan polygoner rörs inte.
    kurva = {"kind": "graph", "width": 300, "height": 200,
             "xRange": [-1, 5], "yRange": [-1, 5],
             "plots": [{"expr": "x"}], "texts": [{"x": 2, "y": 3, "text": "y = x"}]}
    ut = ws.normalize_board(_doc(_board(sections=[kurva])))
    assert "anchor" not in _figur(ut)["texts"][0]


def test_bagens_etikett_i_en_spetsig_vinkel_blir_en_text_vid_horet():
    """Samma handrättning: v i triangeln 5-12-13 (22,6°) lades av motorn
    långt ut på bisektrisen. Under 30° blir etiketten en egen text vid
    bisektrisen, avståndet r + 0,22 från hörnet; en bredare vinkel behåller
    sin etikett."""
    import math
    graf = {"kind": "graph", "width": 400, "height": 175,
            "xRange": [-1.05, 5.15], "yRange": [-0.45, 1.3], "axes": False,
            "polygons": [{"pts": [[0, 0], [1.2, 0], [0, 0.5]]},
                         {"pts": [[2.5, 0], [4.9, 0], [2.5, 1.2]]}],
            "arcs": [{"cx": 1.2, "cy": 0, "r": 0.3,
                      "from": math.pi - math.atan2(0.5, 1.2), "to": math.pi,
                      "interior": [0.7, 0.08], "label": "v",
                      "labelColor": "blue"},
                     {"cx": 4.9, "cy": 0, "r": 0.4, "from": 180 - 26.57,
                      "to": 180, "interior": [4.4, 0.1], "label": "u"}]}
    ut = ws.normalize_board(_doc(_board(sections=[graf])))
    g = _figur(ut)
    assert "label" not in g["arcs"][0]
    v = [t for t in g["texts"] if t["text"] == "v"]
    assert len(v) == 1 and v[0]["anchor"] == "middle"
    assert v[0]["color"] == "blue" and 0.6 < v[0]["x"] < 0.75
    assert 0 < v[0]["y"] < 0.15
    # 26,57° i grader räknas först om till radianer och är också spetsig.
    assert "label" not in g["arcs"][1]
    assert [t["text"] for t in g["texts"]] == ["v", "u"]
    bred = {**graf, "arcs": [{"cx": 0, "cy": 0.5, "r": 0.2,
                              "from": -math.pi / 2,
                              "to": -math.atan2(0.5, 1.2),
                              "interior": [0.3, 0.2], "label": "w"}]}
    ut = ws.normalize_board(_doc(_board(sections=[bred])))
    assert _figur(ut)["arcs"][0]["label"] == "w"
    assert ws.validate_board_json(ut)[1] == []


def test_ar_inte_etiketterna_kostar_inget_i_budgeten():
    """ÄR/INTE (lärarens dom 2026-09-23 kväll): ett fall som ÄR begreppet och
    ett som INTE är det, var sin math-rad med en etikett under. Etiketterna
    är bildtexter, som ankarets, och vägs inte som prosa. INTE-raden känns
    igen på ≠ eller på etikettens «: inte». Högerns text friar de aldrig."""
    def spalt(*rader):
        return _board(sections=[{"kind": "row", "children": [
            {"kind": "col", "width": 400, "children": list(rader)}]}])

    kvot = spalt(
        {"kind": "math", "latex": "y = k \\cdot x"},
        {"kind": "text", "text": "k är kvoten y/x, lika i varje punkt."},
        {"kind": "math", "latex": "\\frac{80}{1} = \\frac{160}{2}"},
        {"kind": "text", "text": "Samma kvot: proportionellt."},
        {"kind": "math", "latex": "\\frac{300}{2} \\neq \\frac{500}{4}"},
        {"kind": "text", "text": "Olika kvot: inte proportionellt."})
    graf = spalt(
        {"kind": "math", "latex": "f(x) = ax^2 + bx + c"},
        {"kind": "math", "latex": "f(x) = x^2 - 6x + 5"},
        {"kind": "text", "text": "Med x²: andragradsfunktion."},
        {"kind": "math", "latex": "f(x) = -6x + 5"},
        {"kind": "text", "text": "Utan x²: inte andragradsfunktion."})
    for tavla, fria in ((kvot, ["Samma kvot: proportionellt.",
                               "Olika kvot: inte proportionellt."]),
                        (graf, ["Med x²: andragradsfunktion.",
                                "Utan x²: inte andragradsfunktion."])):
        sek = ws.validate_board_json(_doc(tavla))[0].boards[0].sections
        assert [e.text for e in ws._ar_inte_etiketter(sek)] == fria
        assert ws._text_volym(sek, vanster=True) == \
            ws._text_volym(sek) - sum(len(t) for t in fria)
    # Utan ≠ och utan «: inte» finns inget par, och det röda felet under
    # «Vanligt fel:» är aldrig ett.
    ingen = spalt(
        {"kind": "math", "latex": "a^2 + b^2 = c^2"},
        {"kind": "text", "text": "Katet: vid räta vinkeln"},
        {"kind": "text", "text": "Vanligt fel:", "color": "red", "weight": 700},
        {"kind": "math", "latex": "2^5 + 2^3 \\neq 2^8", "color": "red"},
        {"kind": "text", "text": "Regeln gäller gånger.", "color": "red"})
    sek = ws.validate_board_json(_doc(ingen))[0].boards[0].sections
    assert ws._ar_inte_etiketter(sek) == []


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
