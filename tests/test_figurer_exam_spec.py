"""Skärmens figurkatalog (app/web/ui/figurer.js) ritar provets figurrecept.

Arbetsbladets och gruppuppgiftens PDF är skärmens avritning, inte LaTeX. När
generatorn skrev {"typ": "linjar", "k": 2, "m": 1} kände figurer.js inte typen,
och uppgiften stod med «Figuren visar grafen till …» utan graf (NA26F, exam
160, 2026-10-02). Testerna här kräver att VARJE typ i exam_spec.Figur ger
CeTZ-källa, och att graferna har samma fönster, ticks och kurva som
exam_figures.py ritar på LaTeX-pappret."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import typing
from pathlib import Path

import pytest

from app import exam_figures, exam_spec

UI = Path(__file__).resolve().parent.parent / "app" / "web" / "ui"

pytestmark = pytest.mark.skipif(shutil.which("node") is None,
                                reason="node saknas")

EXEMPEL = [
    exam_spec.FigLinjar(typ="linjar", k=2, m=1),
    exam_spec.FigLinjar(typ="linjar", k=-3, m=4),
    exam_spec.FigAndragrad(typ="andragrad", a=1, b=-4, c=3),
    exam_spec.FigAndragrad(typ="andragrad", a=-0.5, b=2, c=-6),
    exam_spec.FigExponential(typ="exponential", C=2, bas=1.5),
    exam_spec.FigExponential(typ="exponential", C=-800, bas=0.8),
    exam_spec.FigNormalfordelning(typ="normalfordelning", mu=170, sigma=7.5),
    exam_spec.FigTriangel(typ="triangel", a=3, b=4, c=5),
    exam_spec.FigEnhetscirkel(typ="enhetscirkel", vinkel=130),
    exam_spec.FigStapeldiagram(typ="stapeldiagram",
                               kategorier=["Buss", "Cykel*", "_Bil_"],
                               varden=[12, 7, 3]),
    exam_spec.FigLadagram(typ="ladagram", min=2, q1=5, median=7.5, q3=9, max=14),
]


def _spec_typer() -> set[str]:
    union = typing.get_args(exam_spec.Figur)[0]
    return {typing.get_args(m.model_fields["typ"].annotation)[0]
            for m in typing.get_args(union)}


def _node(kod: str, data) -> object:
    skript = ("global.window = {};"
              f"require({json.dumps(str(UI / 'figurer.js'))});"
              "const F = window.Figurer;"
              "const data = JSON.parse(process.argv[1]);"
              + kod)
    ut = subprocess.run(["node", "-e", skript, json.dumps(data)],
                        capture_output=True, text=True, encoding="utf-8",
                        check=True)
    return json.loads(ut.stdout)


def test_varje_exam_spec_typ_ger_cetz_kalla():
    figurer = [f.model_dump() for f in EXEMPEL]
    assert {f["typ"] for f in figurer} == _spec_typer(), \
        "ett nytt recept i exam_spec saknar exempel här (och kanske i figurer.js)"
    kallor = _node("process.stdout.write(JSON.stringify("
                   "data.map(f => F.kalla(f))))", figurer)
    for f, k in zip(figurer, kallor):
        assert k and "line(" in k, f
        # Ingen NaN eller Infinity får nå CeTZ: då kompileras ingenting.
        assert "NaN" not in k and "Infinity" not in k, f
    for f, k in zip(figurer, kallor):
        if f["typ"] in ("linjar", "andragrad", "exponential"):
            assert "paint: blue" in k, f            # kurvan
            assert "[$x$]" in k and "[$y$]" in k, f  # axlarna
    tri = kallor[[f["typ"] for f in figurer].index("triangel")]
    assert "[$c$ = 5]" in tri
    # Stapelnamnen sätts som strängar: «*» och «_» är bokstäver, inte markup.
    stapel = kallor[[f["typ"] for f in figurer].index("stapeldiagram")]
    assert '[#"Cykel*"]' in stapel and '[#"_Bil_"]' in stapel


def test_tavlans_triangel_ar_orord():
    """Tavlans och de gamla bladens triangel har hörn och sidetiketter, inte
    tre tal. Den formen ska ritas som förut."""
    gammal = {"typ": "triangel", "rattVid": "B", "sidaAB": "a",
              "sidaBC": "b", "sidaCA": "c"}
    k = _node("process.stdout.write(JSON.stringify(F.kalla(data)))", gammal)
    assert k.startswith("let a = (0, 0)") and "content(((a.at(0)" in k


def _tikz_ticks(tikz: str):
    xs = [(float(g), lbl) for g, lbl in re.findall(
        r"\\node\[below\] at \(([-\d.e+]+),-0\.18\) \{\\footnotesize ([^}]*)\}",
        tikz)]
    ys = [(float(g), lbl) for g, lbl in re.findall(
        r"\\node\[left\] at \(-0\.18,([-\d.e+]+)\) \{\\footnotesize ([^}]*)\}",
        tikz)]
    plot = re.search(r"plot coordinates \{(.*?)\};", tikz).group(1)
    pts = [tuple(map(float, p.split(",")))
           for p in re.findall(r"\(([^)]*)\)", plot)]
    return xs, ys, pts


@pytest.mark.parametrize("fig", [f for f in EXEMPEL
                                 if f.typ in ("linjar", "andragrad",
                                              "exponential")],
                         ids=lambda f: json.dumps(f.model_dump()))
def test_grafen_har_pappers_fonster_och_ticks(fig):
    """Samma fönster (alla fyra kvadranter), samma ticks på samma ställen och
    samma kurva som LaTeX-pappret."""
    xs, ys, pts = _tikz_ticks(exam_figures.render_figur(fig))
    assert len(xs) >= 3 and len(ys) >= 3 and len(pts) == 81
    js = _node(
        "const L = F.prov.fonster(data);"
        "const lbl = (v, g) => ({g, t: F.prov.etikett(v)});"
        "process.stdout.write(JSON.stringify({"
        " x: L.xticks.map((v, i) => [v, lbl(v, L.xmaj[i])]).filter(p => Math.abs(p[0]) >= 1e-9).map(p => p[1]),"
        " y: L.yticks.map((v, i) => [v, lbl(v, L.ymaj[i])]).filter(p => Math.abs(p[0]) >= 1e-9).map(p => p[1]),"
        " p: L.punkter}))", fig.model_dump())

    def norm(t):
        return t.replace("−", "-")

    assert [norm(d["t"]) for d in js["x"]] == [lbl for _, lbl in xs]
    assert [norm(d["t"]) for d in js["y"]] == [lbl for _, lbl in ys]
    for d, (g, _) in zip(js["x"] + js["y"], xs + ys):
        assert d["g"] == pytest.approx(g, abs=1e-3)
    assert len(js["p"]) == len(pts)
    for (jx, jy), (px, py) in zip(js["p"], pts):
        assert jx == pytest.approx(px, abs=1e-3)
        assert jy == pytest.approx(py, abs=1e-3)


def test_nice_ticks_som_python():
    fall = [(-1, 7), (-2.28, 16.28), (0, 12), (0.1, 0.9), (-800, 3),
            (0, 0.037), (12, 12)]
    js = _node("process.stdout.write(JSON.stringify("
               "data.map(([a, b]) => F.prov.niceTicks(a, b))))", fall)
    for (lo, hi), j in zip(fall, js):
        assert j == pytest.approx(exam_figures._nice_ticks(lo, hi)), (lo, hi)
