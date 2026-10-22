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
    # Sträckan med fyllda ändpunkter (exam 260 uppg 9, bokens 4202/4206).
    exam_spec.FigLinjar(typ="linjar", k=-1, m=3, fonster=(-3, 5),
                        stracka=(-2, 4)),
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
    # Siffrorna står vid axlarna (Rickard 2026-10-22), inte vid rutans kant.
    xs = [(float(g), lbl) for g, lbl in re.findall(
        r"\\node\[below,fill=white,inner sep=1pt\] at \(([-\d.e+]+),[-\d.e+]+\) "
        r"\{\\footnotesize ([^}]*)\}", tikz)]
    ys = [(float(g), lbl) for g, lbl in re.findall(
        r"\\node\[left,fill=white,inner sep=1pt\] at \([-\d.e+]+,([-\d.e+]+)\) "
        r"\{\\footnotesize ([^}]*)\}", tikz)]
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


# ── Linjens sträcka och fönster (exam 260 uppg 9, 2026-10-16) ────────────

def _uppg9() -> dict:
    """Exam 260 v1254 uppgift 9, ordagrant: stammen säger ändpunkterna, a)
    frågar efter definitionsmängden och facit säger den."""
    return {
        "text": ("Funktionen $f$ har en graf som är en sträcka.\n"
                 "Figuren visar den räta linje som sträckan ligger på.\n"
                 "Sträckan går från punkten $(-2,\\ 5)$ till punkten "
                 "$(4,\\ -1)$.\nBåda ändpunkterna hör till grafen."),
        "losning": "",
        "figur": {"typ": "linjar", "k": -1, "m": 3},
        "deluppgifter": [
            {"text": "Ange definitionsmängden för $f$.",
             "losning": "$-2 \\le x \\le 4$"},
            {"text": "Ange värdemängden för $f$.",
             "losning": "$-1 \\le f(x) \\le 5$"},
        ],
    }


def test_strackan_las_ur_uppgiftens_text():
    """Facit säger −2 ≤ x ≤ 4: sträckan ritas där, och fönstret tar med
    båda ändarna och y-axeln. Förut −1 ≤ x ≤ 7, och (−2, 5) klipptes bort."""
    fig = exam_figures.linjar_ur_text(_uppg9())["figur"]
    assert fig["stracka"] == [-2, 4]
    assert fig["fonster"][0] < -2 and fig["fonster"][1] > 4
    f = exam_spec.FigLinjar(**fig)
    tikz = exam_figures.render_figur(f)
    # Två fyllda ändpunkter, i kurvans färg.
    assert tikz.count(r"\fill[blue]") == 2
    _xs, _ys, pts = _tikz_ticks(tikz)
    # Kurvan börjar och slutar i ändpunkterna, inte i rutans kant.
    x0 = exam_figures.BOXW / (f.fonster[1] - f.fonster[0])
    assert pts[0][0] == pytest.approx((-2 - f.fonster[0]) * x0, abs=1e-3)
    assert pts[-1][0] == pytest.approx((4 - f.fonster[0]) * x0, abs=1e-3)


def test_strikt_olikhet_ger_inga_fyllda_andar():
    u = _uppg9()
    u["deluppgifter"][0]["losning"] = "$-2 < x \\le 4$"
    fig = exam_figures.linjar_ur_text(u)["figur"]
    assert "stracka" not in fig
    assert fig["fonster"][0] <= -3          # punkten (−2, 5) syns ändå


def test_punkterna_vidgar_fonstret_utan_strackan():
    fig = exam_figures.linjar_fonster(
        {"typ": "linjar", "k": 2, "m": 1},
        ["Visa att punkten $(9,\\ 19)$ ligger på linjen."])
    assert fig == {"typ": "linjar", "k": 2, "m": 1, "fonster": [-1, 10]}


def test_linje_utan_intervall_och_punkter_ar_orord():
    """Byte för byte som förut: inget fält läggs till, och pappret ritar
    samma −1 ≤ x ≤ 7."""
    fig = {"typ": "linjar", "k": 2, "m": 1}
    assert exam_figures.linjar_fonster(fig, ["Rita grafen till $y = 2x + 1$."]) \
        is fig
    assert exam_figures.linjar_fonster(
        fig, ["Punkten $(3,\\ 7)$ ligger på linjen."]) is fig


def test_satt_fonster_rors_inte():
    fig = {"typ": "linjar", "k": 1, "m": 0, "fonster": [-5, 5]}
    assert exam_figures.linjar_fonster(fig, ["$0 \\le x \\le 2$"]) is fig


def test_modellsvaret_far_strackan_nar_det_lases():
    """exam_gen._parse_exam är vägen varje modellsvar går (generering,
    reparation, omskrivning)."""
    from app import exam_gen
    raw = json.dumps({"titel": "t", "uppgifter": [_uppg9()]})
    fig = exam_gen._parse_exam(raw)["uppgifter"][0]["figur"]
    assert fig["stracka"] == [-2, 4]


def test_strackan_star_inte_i_grammatiken():
    """Schemat ligger 269 tecken under taket på ett tjugouppgifts 1b-prov.
    Fälten sätts av appen och får inte kosta grammatiken ett tecken."""
    sk = exam_spec.balanced_skeleton(10, "arbetsblad")
    schema = json.dumps(exam_spec.to_response_format(10, sk))
    assert '"stracka"' not in schema and '"fonster"' not in schema
    assert '"linjar"' in schema


def test_skarmen_ritar_strackans_andpunkter():
    fig = exam_figures.linjar_ur_text(_uppg9())["figur"]
    k = _node("process.stdout.write(JSON.stringify(F.kalla(data)))", fig)
    assert k.count("fill: blue") == 2


def test_triangeln_skuggas_ocksa_pa_skarmen():
    fig = {"typ": "linjar", "k": -1, "m": 6, "namn": "f", "triangel": "x",
           "fler": [{"k": 2, "m": 0, "namn": "g"}]}
    k = _node("process.stdout.write(JSON.stringify(F.kalla(data)))", fig)
    assert "close: true" in k and "[triangeln]" in k
    assert k.index("close: true") < k.index("paint: rgb") or "paint: violet" in k
