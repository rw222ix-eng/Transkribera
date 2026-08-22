"""Figurrecept (PR 4): ren TikZ-sträng + riktig kompilering.

VIKTIGT om grinden: de kompilerande testerna (kraschskyddet mot "Dimension
too large", en-sida-kontrollerna, escapning-i-praktiken) bär
``@pytest.mark.tectonic``. Utan motorn hoppas de över lokalt — men med
KRAV_TECTONIC=1 (som i CI) FALLER de i stället. På en maskin utan seedad
Tectonic gick sviten annars grön utan att ett enda figurpåstående prövats, och
en grön svit som inte bevisar något är värre än en röd. Grinden bor i
tests/conftest.py."""
from pathlib import Path

import pytest

from app import exam_figures, exam_pdf, exam_spec


def _wrap(tikz: str) -> str:
    """Minimalt kompilerbart dokument runt en TikZ-figur. newtxtext/newtxmath
    (INTE default Computer Modern) — seeden cachar bara newtx-fonterna, så en
    bar `article` skulle krascha på cmr12 under --only-cached på en rent seedad
    maskin. \\pagestyle{empty} slipper sidnummer-fonten."""
    return (r"\documentclass[12pt,a4paper]{article}"
            r"\usepackage[T1]{fontenc}\usepackage{newtxtext,newtxmath}"
            r"\usepackage{tikz}\usetikzlibrary{angles,quotes}\pagestyle{empty}"
            r"\begin{document}" + tikz + r"\end{document}")


def _kompilera(tikz: str, base: Path) -> bool:
    """Kompilera en figur i en per-test tmp-katalog (base) — inga relativa
    kataloger i repo-roten som kan läcka in i arbetsträdet vid avbrott eller
    krocka mellan parametriserade fall under pytest -n."""
    pdf, _logg = exam_pdf.compile_pdf(_wrap(tikz), base / "figkontroll", "fig")
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


def test_funktionsgraf_foljer_forlagans_axelrecept():
    """Lärarens egen förlaga sätter grafen som `width = 10cm, height = 8cm,
    grid = both, axis lines = center` och UTAN kurvetikett. Receptet är hennes
    och gäller alla funktionsgrafer: tydligt rutnät (minor- + majorlinjer, inte
    den gamla svaga gray!30-ramen), ingen låda runt rutnätet, ingen $y=f(x)$."""
    tikz = exam_figures.render_figur(_bygg({"typ": "linjar", "k": 1, "m": 0}))
    assert "black!50" in tikz              # majorlinjer, klart synliga
    assert "black!30" in tikz              # minorlinjer, klart synliga
    assert "gray!30" not in tikz           # den gamla svaga ramen är borta
    # axis lines = center: ingen ram runt rutnätet, bara axlarna genom origo
    assert "rectangle" not in tikz.split(r"\begin{scope}")[0]
    assert "--(10.3," in tikz               # x-axelns pil, 10 cm bred ruta
    assert ",8.3)" in tikz                  # y-axelns pil, 8 cm hög ruta
    # kurvetiketten är borta — uppgiftstexten säger redan vilken funktion det är
    assert "$y=f(x)$" not in tikz
    assert (10.0, 8.0) == (exam_figures.BOXW, exam_figures.BOXH)


def test_ickekoordinatfigur_saknar_rutnat():
    """Figurer utan koordinatsystem (triangel, enhetscirkel, lådagram) ska INTE
    ha rutnät — rutnätet hör bara till funktionsgraferna."""
    for d in ({"typ": "triangel", "a": 5, "b": 4, "c": 3},
              {"typ": "enhetscirkel", "vinkel": 40},
              {"typ": "ladagram", "min": 2, "q1": 5, "median": 8, "q3": 11, "max": 14}):
        tikz = exam_figures.render_figur(_bygg(d))
        assert "black!50" not in tikz and "black!30" not in tikz


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
    # exakt mu-etiketten, inte bara delsträngen "12" (som kunde matcha en koord)
    assert r"node[below]{\footnotesize 12}" in tikz


def test_axeletiketter_utan_e_notation_och_med_svenskt_komma():
    """Axel-ETIKETTER (inte koordinater) får aldrig hamna i vetenskaplig
    notation (1e+06) för stora tal, och decimaler ska ha svenskt komma."""
    # mu±2·sigma = 3 000 000 → gamla _f/{:g} gav "3e+06" i etiketten
    stor = exam_figures.render_figur(
        _bygg({"typ": "normalfordelning", "mu": 2000000, "sigma": 500000}))
    assert "e+" not in stor and "e-" not in stor
    # mu±sigma = ±0,5 → svenskt decimalkomma, aldrig "0.5"
    dec = exam_figures.render_figur(
        _bygg({"typ": "normalfordelning", "mu": 0, "sigma": 0.5}))
    assert "0,5" in dec
    assert "0.5" not in dec


@pytest.mark.parametrize("d", [
    {"typ": "linjar", "k": 0.8, "m": 1},
    {"typ": "andragrad", "a": 1, "b": -4, "c": 3},
    {"typ": "exponential", "C": 1, "bas": 2},
    {"typ": "normalfordelning", "mu": 0, "sigma": 1},
])
@pytest.mark.tectonic
def test_funktionsgrafer_kompilerar(d, tmp_path):
    assert _kompilera(exam_figures.render_figur(_bygg(d)), tmp_path), \
        f"{d['typ']} kompilerar inte"


def test_triangel_ger_tikz_och_hornmarkeringar():
    tikz = exam_figures.render_figur(_bygg({"typ": "triangel", "a": 5, "b": 4, "c": 3}))
    assert r"--cycle" in tikz
    assert "$A$" in tikz and "$B$" in tikz and "$C$" in tikz


def test_triangel_etikett_utan_e_notation():
    """Triangelns c-etikett visar verkligt värde utan e-notation (via _flabel),
    konsekvent med axeletiketterna — även för stora sidor (t.ex. meter)."""
    tikz = exam_figures.render_figur(_bygg(
        {"typ": "triangel", "a": 1200000, "b": 1300000, "c": 1500000}))
    assert "e+" not in tikz
    assert "1500000" in tikz


def test_enhetscirkel_har_vinkelbage():
    tikz = exam_figures.render_figur(_bygg({"typ": "enhetscirkel", "vinkel": 40}))
    assert r"\pic" in tikz and "angle=" in tikz
    assert "circle (1)" in tikz
    # punkten P härleds ur vinkeln — annars kunde vinkeln ignoreras tyst
    assert "cos(40)" in tikz and "sin(40)" in tikz


def test_stapeldiagram_en_stapel_per_kategori():
    tikz = exam_figures.render_figur(_bygg(
        {"typ": "stapeldiagram", "kategorier": ["A", "B", "C"], "varden": [3, 5, 2]}))
    assert tikz.count("rectangle") == 3


def test_stapeldiagram_avvisar_noll_och_negativa_varden():
    """Ett stapeldiagram av bara nollor (division med noll i receptet) eller
    negativa antal ska avvisas av schemat — inte krascha renderingen."""
    from pydantic import ValidationError
    for varden in ([0, 0, 0], [3, -1, 2]):
        with pytest.raises(ValidationError):
            _bygg({"typ": "stapeldiagram", "kategorier": ["A", "B", "C"],
                   "varden": varden})


def test_stapeldiagram_recept_kraschar_inte_pa_noll():
    """Försvar på djupet: även om ett all-noll-värde nådde receptet får det
    inte ge ZeroDivisionError. Anropa den privata receptfunktionen direkt."""
    from types import SimpleNamespace
    fig = SimpleNamespace(kategorier=["A", "B"], varden=[0, 0])
    assert r"\begin{tikzpicture}" in exam_figures._stapeldiagram(fig)


@pytest.mark.parametrize("bad", [float("inf"), float("-inf"), float("nan")])
def test_figur_avvisar_inf_och_nan(bad):
    """inf/NaN (via json '1e400'/'Infinity'/'NaN' — json.loads accepterar dem)
    får inte passera schemat: annars kraschar _build_view med ett OFÅNGAT
    OverflowError/ValueError FÖRE LaTeX-reparationsloopen och SSE-jobbet dör
    tyst utan PDF."""
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        _bygg({"typ": "linjar", "k": bad, "m": 0})


@pytest.mark.parametrize("bad", [0, 360])
def test_enhetscirkel_avvisar_degenererad_vinkel(bad):
    """vinkel 0/360 ger en degenererad \\pic-vinkel (P sammanfaller med X på
    axeln) och nollånga hjälplinjer — en meningslös figur. Schemat avvisar
    dem (gt=0, lt=360); räta/trubbiga vinklar mellan är fortsatt giltiga."""
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        _bygg({"typ": "enhetscirkel", "vinkel": bad})


def test_exponential_avvisar_orimligt_stor_bas():
    """En orimligt stor bas skulle ge OverflowError i receptet (bas^3 över
    domänen [-3,3]) — schemat begränsar basen till ett rimligt intervall."""
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        _bygg({"typ": "exponential", "C": 1, "bas": 1e200})


@pytest.mark.parametrize("fig", [
    {"typ": "linjar", "k": 1e300, "m": 0},
    {"typ": "linjar", "k": 1, "m": 1e300},
    {"typ": "andragrad", "a": 1e300, "b": 0, "c": 0},
    {"typ": "exponential", "C": 1e300, "bas": 2},
    {"typ": "triangel", "a": 1e300, "b": 1e300, "c": 1e300},
])
def test_figur_avvisar_orimligt_stora_koefficienter(fig):
    """Obundna koefficient-/sidfält som når rå aritmetik (C·bas^x, sida² i
    triangelns cx) kunde spilla över till inf/nan → ofångad krasch i
    _build_view. Schemat begränsar dem till en generös men ändlig storlek."""
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        _bygg(fig)


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
    assert "rectangle" in tikz                       # lådan
    # morrhåren: exakt två vågräta linjer (min–q1 och q3–max), utan rectangle
    morrhar = [r for r in tikz.splitlines()
               if r.startswith(r"\draw[thick]") and ")--(" in r
               and "rectangle" not in r]
    assert len(morrhar) == 2


@pytest.mark.parametrize("d", [
    {"typ": "triangel", "a": 5, "b": 4, "c": 3},
    {"typ": "enhetscirkel", "vinkel": 40},
    {"typ": "stapeldiagram", "kategorier": ["A", "B", "C"], "varden": [3, 5, 2]},
    {"typ": "ladagram", "min": 2, "q1": 5, "median": 8, "q3": 11, "max": 14},
])
@pytest.mark.tectonic
def test_geometri_statistik_kompilerar(d, tmp_path):
    assert _kompilera(exam_figures.render_figur(_bygg(d)), tmp_path)


def _sidantal(tikz: str, base: Path) -> int:
    """Antal PDF-sidor för en figur, kompilerad i en per-test tmp-katalog.

    Räknades förr med fitz (PyMuPDF) — ett paket som varken står i
    requirements eller finns på en ren maskin. Saknades det returnerade
    hjälparen None och en-sida-kravet försvann tyst ur testet: figuren kunde
    spränga sin ruta utan att någon svit blev röd. pypdfium2 är redan ett
    deklarerat beroende (tryckpaketet fogar ihop PDF:er med den)."""
    import pypdfium2 as pdfium
    pdf, _ = exam_pdf.compile_pdf(_wrap(tikz), base / "figsid", "sid")
    if pdf is None:
        return -1
    d = pdfium.PdfDocument(str(pdf))
    try:
        return len(d)
    finally:
        d.close()


@pytest.mark.parametrize("d", [
    {"typ": "exponential", "C": 5, "bas": 0.5},   # avtagande — sprängde förr rutan
    {"typ": "andragrad", "a": -1, "b": 4, "c": -3},   # nedåtvänd parabel
    {"typ": "linjar", "k": -1.5, "m": -2},            # brant negativ linje
])
@pytest.mark.tectonic
def test_extrema_parametrar_ryms_pa_en_sida(d, tmp_path):
    tikz = exam_figures.render_figur(_bygg(d))
    assert _kompilera(tikz, tmp_path), f"{d['typ']} kompilerar inte"
    assert _sidantal(tikz, tmp_path) == 1, \
        f"{d['typ']} blev fler sidor — kurvan klipps inte mot rutan"


@pytest.mark.parametrize("d", [
    {"typ": "exponential", "C": 1000, "bas": 1.05},        # ränta-på-ränta
    {"typ": "normalfordelning", "mu": 30000, "sigma": 5000},   # lönefördelning
    {"typ": "stapeldiagram", "kategorier": ["A", "B", "C"], "varden": [900, 1200, 700]},
    {"typ": "andragrad", "a": 30, "b": 0, "c": 0},
    {"typ": "ladagram", "min": 1000, "q1": 2000, "median": 3000, "q3": 4000, "max": 5000},
    {"typ": "ladagram", "min": 5, "q1": 5, "median": 5, "q3": 5, "max": 5},   # alla lika
    # Stor triangel (t.ex. sidor i meter): råa sidlängder som koordinat
    # sprängde TeX:s maxmått (~576 cm) → "Dimension too large". Receptet
    # måste normalisera in i en fast ritruta precis som funktionsgraferna.
    {"typ": "triangel", "a": 650, "b": 720, "c": 900},
])
@pytest.mark.tectonic
def test_stora_naturliga_tal_kompilerar_pa_en_sida(d, tmp_path):
    tikz = exam_figures.render_figur(_bygg(d))
    assert _kompilera(tikz, tmp_path), f"{d['typ']} kompilerar inte"
    assert _sidantal(tikz, tmp_path) == 1, f"{d['typ']} blev fler sidor"
