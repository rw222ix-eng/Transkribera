"""Figurrecept (PR 4): ren TikZ-sträng + riktig kompilering."""
from pathlib import Path

import pytest

from app import exam_figures, exam_pdf, exam_spec


def _kompilera(tikz: str) -> bool:
    """Wrappa TikZ i ett minimalt dokument och kompilera med riktig motor.
    Använder newtxtext/newtxmath (INTE default Computer Modern) — seeden
    cachar bara newtx-fonterna, så en bar `article` skulle krascha på cmr12
    under --only-cached på en rent seedad maskin. \\pagestyle{empty} slipper
    sidnummer-fonten."""
    doc = (r"\documentclass[12pt,a4paper]{article}"
           r"\usepackage[T1]{fontenc}\usepackage{newtxtext,newtxmath}"
           r"\usepackage{tikz}\usetikzlibrary{angles,quotes}\pagestyle{empty}"
           r"\begin{document}" + tikz + r"\end{document}")
    pdf, _logg = exam_pdf.compile_pdf(doc, Path("_figkontroll"), "fig")
    return pdf is not None


from pydantic import TypeAdapter

_FIG = TypeAdapter(exam_spec.Figur)


def _bygg(d: dict):
    """Validera en figur-dict fristående till rätt figurmodell (diskriminerad
    union) — ingen ExamItem/cross-test-import behövs."""
    return _FIG.validate_python(d)


def test_linjar_ger_tikz():
    tikz = exam_figures.render_figur(_bygg({"typ": "linjar", "k": 0.8, "m": 1}))
    assert tikz.startswith(r"\begin{tikzpicture}")
    assert tikz.rstrip().endswith(r"\end{tikzpicture}")
    assert r"plot(\x,{0.8*\x+1})" in tikz


def test_andragrad_ger_tikz():
    tikz = exam_figures.render_figur(
        _bygg({"typ": "andragrad", "a": 1, "b": -4, "c": 3}))
    assert r"plot(\x,{1*\x*\x+-4*\x+3})" in tikz


def test_exponential_anvander_exp_ln():
    tikz = exam_figures.render_figur(
        _bygg({"typ": "exponential", "C": 1, "bas": 2}))
    # bas^x skrivs exp(x*ln(bas)) — TikZ saknar ^-operator för variabel exponent
    assert r"exp(\x*ln(2))" in tikz


def test_normalfordelning_markerar_mu():
    tikz = exam_figures.render_figur(
        _bygg({"typ": "normalfordelning", "mu": 0, "sigma": 1}))
    assert r"$\mu$" in tikz


@pytest.mark.parametrize("d", [
    {"typ": "linjar", "k": 0.8, "m": 1},
    {"typ": "andragrad", "a": 1, "b": -4, "c": 3},
    {"typ": "exponential", "C": 1, "bas": 2},
    {"typ": "normalfordelning", "mu": 0, "sigma": 1},
])
def test_funktionsgrafer_kompilerar(d):
    if not exam_pdf.engine_available():
        pytest.skip("Tectonic saknas")
    try:
        assert _kompilera(exam_figures.render_figur(_bygg(d))), f"{d['typ']} kompilerar inte"
    finally:
        import shutil
        shutil.rmtree("_figkontroll", ignore_errors=True)


def _sidantal(tikz: str):
    """Antal PDF-sidor för en figur (None om fitz saknas)."""
    try:
        import fitz
    except ImportError:
        return None
    doc = (r"\documentclass[12pt,a4paper]{article}"
           r"\usepackage[T1]{fontenc}\usepackage{newtxtext,newtxmath}"
           r"\usepackage{tikz}\usetikzlibrary{angles,quotes}\pagestyle{empty}"
           r"\begin{document}" + tikz + r"\end{document}")
    pdf, _ = exam_pdf.compile_pdf(doc, Path("_figsid"), "sid")
    try:
        if pdf is None:
            return -1
        d = fitz.open(pdf); n = d.page_count; d.close(); return n
    finally:
        import shutil
        shutil.rmtree("_figsid", ignore_errors=True)


@pytest.mark.parametrize("d", [
    {"typ": "exponential", "C": 5, "bas": 0.5},   # avtagande — sprängde förr rutan
    {"typ": "andragrad", "a": -1, "b": 4, "c": -3},   # nedåtvänd parabel
    {"typ": "linjar", "k": -1.5, "m": -2},            # brant negativ linje
])
def test_extrema_parametrar_ryms_pa_en_sida(d):
    if not exam_pdf.engine_available():
        pytest.skip("Tectonic saknas")
    tikz = exam_figures.render_figur(_bygg(d))
    try:
        assert _kompilera(tikz), f"{d['typ']} kompilerar inte"
    finally:
        import shutil
        shutil.rmtree("_figkontroll", ignore_errors=True)
    n = _sidantal(tikz)
    if n is not None:
        assert n == 1, f"{d['typ']} blev {n} sidor — kurvan klipps inte mot rutan"
