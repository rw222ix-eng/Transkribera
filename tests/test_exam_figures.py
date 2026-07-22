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
    assert "plot coordinates" in tikz


def test_andragrad_ger_tikz():
    tikz = exam_figures.render_figur(
        _bygg({"typ": "andragrad", "a": 1, "b": -4, "c": 3}))
    assert "plot coordinates" in tikz


def test_exponential_ger_tikz_med_samplade_koordinater():
    """Exponentialen ritas nu via samplade koordinater i en fast ritruta
    (skalinvariant) — inget domain/exp(\\x*ln(...))-uttryck i utdatan längre."""
    tikz = exam_figures.render_figur(
        _bygg({"typ": "exponential", "C": 1, "bas": 2}))
    assert "plot coordinates" in tikz
    assert r"exp(\x*ln" not in tikz


def test_normalfordelning_markerar_mu():
    """mu:s VERKLIGA tal ska stå på axeln (ersätter den gamla $\\mu$-noden,
    som inte längre stämmer när mu är ett stort naturligt tal, t.ex. lön)."""
    tikz = exam_figures.render_figur(
        _bygg({"typ": "normalfordelning", "mu": 12, "sigma": 1}))
    assert "12" in tikz


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


def test_triangel_ger_tikz_och_hornmarkeringar():
    tikz = exam_figures.render_figur(_bygg({"typ": "triangel", "a": 5, "b": 4, "c": 3}))
    assert r"--cycle" in tikz
    assert "$A$" in tikz and "$B$" in tikz and "$C$" in tikz


def test_enhetscirkel_har_vinkelbage():
    tikz = exam_figures.render_figur(_bygg({"typ": "enhetscirkel", "vinkel": 40}))
    assert r"\pic" in tikz and "angle=" in tikz
    assert "circle (1)" in tikz


def test_stapeldiagram_en_stapel_per_kategori():
    tikz = exam_figures.render_figur(_bygg(
        {"typ": "stapeldiagram", "kategorier": ["A", "B", "C"], "varden": [3, 5, 2]}))
    assert tikz.count("rectangle") == 3


def test_stapeldiagram_escapar_kategorinamn():
    """Kategorinamn med LaTeX-specialtecken (&, %) måste escapas — annars
    kraschar kompileringen på ett & eller kommenterar bort raden på ett %."""
    tikz = exam_figures.render_figur(_bygg(
        {"typ": "stapeldiagram", "kategorier": ["A&B", "50 %", "C_1"],
         "varden": [3, 5, 2]}))
    assert r"A\&B" in tikz and r"50 \%" in tikz and r"C\_1" in tikz
    assert "A&B" not in tikz            # råa specialtecken får inte läcka


def test_ladagram_har_lada_och_morrhar():
    tikz = exam_figures.render_figur(_bygg(
        {"typ": "ladagram", "min": 2, "q1": 5, "median": 8, "q3": 11, "max": 14}))
    assert "rectangle" in tikz


@pytest.mark.parametrize("d", [
    {"typ": "triangel", "a": 5, "b": 4, "c": 3},
    {"typ": "enhetscirkel", "vinkel": 40},
    {"typ": "stapeldiagram", "kategorier": ["A", "B", "C"], "varden": [3, 5, 2]},
    {"typ": "ladagram", "min": 2, "q1": 5, "median": 8, "q3": 11, "max": 14},
])
def test_geometri_statistik_kompilerar(d):
    if not exam_pdf.engine_available():
        pytest.skip("Tectonic saknas")
    try:
        assert _kompilera(exam_figures.render_figur(_bygg(d)))
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


@pytest.mark.parametrize("d", [
    {"typ": "exponential", "C": 1000, "bas": 1.05},        # ränta-på-ränta
    {"typ": "normalfordelning", "mu": 30000, "sigma": 5000},   # lönefördelning
    {"typ": "stapeldiagram", "kategorier": ["A", "B", "C"], "varden": [900, 1200, 700]},
    {"typ": "andragrad", "a": 30, "b": 0, "c": 0},
    {"typ": "ladagram", "min": 1000, "q1": 2000, "median": 3000, "q3": 4000, "max": 5000},
    {"typ": "ladagram", "min": 5, "q1": 5, "median": 5, "q3": 5, "max": 5},   # alla lika
])
def test_stora_naturliga_tal_kompilerar_pa_en_sida(d):
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
        assert n == 1, f"{d['typ']} blev {n} sidor"
