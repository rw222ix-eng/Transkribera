"""WB-JSON v1: schema, regelvalidatorer och uttrycksparser-spegeln."""
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


def test_empty_board_flagged():
    doc, errors = ws.validate_board_json(_doc(_board(sections=None)))
    assert any(e["code"] == "tom-tavla" for e in errors)


def test_invalid_range_flagged():
    g = _graph(xRange=[5, -1])
    doc, errors = ws.validate_board_json(_doc(_board(sections=[g])))
    assert any(e["code"] == "range" for e in errors)


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
