"""Figurrecept (PR 4): ren TikZ-sträng + riktig kompilering.

VIKTIGT om grinden: de kompilerande testerna (kraschskyddet mot "Dimension
too large", en-sida-kontrollerna, escapning-i-praktiken) bär
``@pytest.mark.tectonic``. Utan motorn hoppas de över lokalt — men med
KRAV_TECTONIC=1 (som i CI) FALLER de i stället. På en maskin utan seedad
Tectonic gick sviten annars grön utan att ett enda figurpåstående prövats, och
en grön svit som inte bevisar något är värre än en röd. Grinden bor i
tests/conftest.py."""
import re
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


def test_kort_axel_far_en_rutlinje_per_heltal():
    """IndA prov 2 uppg 5a (exam 215): skärningen (2, 1) måste gå att läsa av."""
    tex = exam_figures._funktionsgraf(lambda x: -2 * x + 5, -1, 7)
    tunna = [r for r in tex.splitlines() if r.startswith(r"\draw[black!30")]
    # 9 x-heltal (−1…7) och y från −9 till 7, minus huvudlinjerna.
    assert len(tunna) > 15
    # En lång axel faller tillbaka på halva tickavståndet.
    lang = exam_figures._funktionsgraf(lambda x: 100 * x, -1, 7)
    assert len([r for r in lang.splitlines() if r.startswith(r"\draw[black!30")]) < 20


def test_ekvationssystemets_rader_star_var_for_sig():
    from app import exam_latex
    t = ("Försäljningen beskrivs av ekvationssystemet:\n(1) $x + y = 96$\n"
         "(2) $55x + 85y = 6\\,180$\n\nBestäm hur många sallader kaféet sålde.")
    for st in (exam_latex._ihop_stycken(exam_latex._stycken(t, luft=True)),
               exam_latex._stycken(t, ihop=True)):
        assert [s["text"][:3] for s in st] == ["För", "\\be", "Bes"]
        system = st[1]
        assert system["formel"]
        # Klammer till vänster och numret till höger (Rickard 2026-10-22).
        assert system["text"].startswith("\\begin{cases}")
        assert "x + y = 96 & (1)" in system["text"]
        assert "& (2)" in system["text"]


def test_en_ensam_ekvationsrad_far_ingen_klammer():
    """Prov 215 uppg 14: ett påbörjat system, «(1) $u + n = 12$»."""
    from app import exam_latex
    t = "Ekvationssystemet är påbörjat:\n(1) $u + n = 12$\n\nBestäm tiden."
    st = exam_latex._stycken(t, luft=True)
    assert [s["text"][:3] for s in st] == ["Ekv", "(1)", "Bes"]
    assert "cases" not in "".join(s["text"] for s in st)


def test_linjens_ekvation_ur_texten():
    le = exam_figures.linjens_ekvation
    assert le("2x + y = 5") == (-2.0, 5.0)
    assert le("x - 2y = 6") == (0.5, -3.0)
    assert le("y = 4 − 2x") == (-2.0, 4.0)
    assert le("y = \\frac{1}{2}x - 1") == (0.5, -1.0)
    assert le("y = 0{,}5x + 3") == (0.5, 3.0)
    assert le("6x + ay = b") is None
    assert le("x = 3") is None


def test_namngivna_linjer_i_figuren():
    """Rickard 2026-10-22, prov 215 uppg 12: linjerna heter något i en
    mening och syns i figuren med namn. Uppg 5a: linjen eleven ska rita
    ritas inte."""
    u = {"text": "Linjen $f$ har ekvationen $x + y = 6$ och linjen $g$ har "
                 "ekvationen $2x - y = 0$.\nFiguren visar linjerna $f$ och $g$.",
         "figur": {"typ": "linjar", "k": -1, "m": 6}}
    exam_figures.linjar_ur_text(u)
    assert u["figur"]["namn"] == "f"
    assert u["figur"]["fler"] == [{"k": 2.0, "m": 0.0, "namn": "g"}]
    tex = exam_figures.render_figur(exam_spec.FigLinjar.model_validate(u["figur"]))
    assert "\\draw[violet,very thick]" in tex and "green!60!black" in tex
    assert "{$f$}" in tex and "{$g$}" in tex and "scale=1.5" in tex
    u5 = {"text": "Linjen $f$ har ekvationen $2x + y = 5$.",
          "deluppgifter": [{"text": "Figuren visar linjen $f$.\nLinjen $g$ har "
                                    "ekvationen $y = x - 1$. Rita linjen $g$.",
                            "figur": {"typ": "linjar", "k": -2, "m": 5}}]}
    exam_figures.linjar_ur_text(u5)
    assert u5["deluppgifter"][0]["figur"] == {"typ": "linjar", "k": -2, "m": 5,
                                              "namn": "f"}


def test_utan_namn_ar_figuren_som_forut():
    u = {"text": "Figuren visar en rät linje.", "figur": {"typ": "linjar", "k": 0.5, "m": -1}}
    exam_figures.linjar_ur_text(u)
    assert u["figur"] == {"typ": "linjar", "k": 0.5, "m": -1}
    tex = exam_figures.render_figur(exam_spec.FigLinjar.model_validate(u["figur"]))
    assert "\\draw[blue,very thick]" in tex and "scale=1.5" not in tex


def test_axlarna_ar_tjocka_och_siffrorna_star_vid_dem():
    """Rickard 2026-10-22, prov 215 uppg 4, 5, 12: axlarna var lika smala som
    rutnätet, och skalsiffrorna stod vid rutans kant långt från axeln."""
    tex = exam_figures.render_figur(exam_spec.FigLinjar(typ="linjar", k=0.5, m=-1))
    assert tex.count(r"\draw[->,line width=1.2pt]") == 2
    sx = exam_figures.BOXW / 8
    # x = 2 ligger 3 enheter från fönstrets vänsterkant (−1).
    m = re.search(r"\\node\[below,fill=white,inner sep=1pt\] at \(([\d.]+),([-\d.e]+)\) "
                  r"\{\\footnotesize 2\}", tex)
    assert m and float(m.group(1)) == pytest.approx(3 * sx)
    assert float(m.group(2)) > 0          # under x-axeln, inte under rutan
    m = re.search(r"\\node\[left,fill=white,inner sep=1pt\] at \(([-\d.e]+),[\d.]+\) "
                  r"\{\\footnotesize 1\}", tex)
    assert m and float(m.group(1)) == pytest.approx(sx - 0.14)
    # Siffrorna ritas före axlarna och kurvan, så att plattan bara döljer
    # rutnätet.
    assert tex.index("footnotesize 2") < tex.index(r"\draw[->,line width")
    assert tex.index("footnotesize 2") < tex.index("plot coordinates")


def test_linjens_namn_i_texten_har_figurens_farg():
    """Rickard 2026-10-22: «den bokstaven f … ska bli lila», «g ska vara grön»."""
    u = {"text": "Linjen $f$ har ekvationen $x + y = 6$ och linjen $g$ har "
                 "ekvationen $2x - y = 0$.\nFiguren visar linjerna $f$ och $g$.",
         "figur": {"typ": "linjar", "k": -1, "m": 6}}
    exam_figures.linjar_ur_text(u)
    farger = exam_figures.namnfarger(u)
    assert farger == {"f": "violet", "g": "green!60!black"}
    ut = exam_figures.farga_namn("Linjen $f$ och $g$, $f(x)$ och $g = 2$.", farger)
    assert ut == ("Linjen ${\\color{violet}f}$ och ${\\color{green!60!black}g}$, "
                  "$f(x)$ och $g = 2$.")
    # Utan namngivna linjer: texten orörd.
    assert exam_figures.namnfarger({"text": "x", "figur": {"typ": "linjar",
                                                           "k": 1, "m": 0}}) == {}


def test_triangeln_med_axeln_skuggas():
    """Rickard 2026-10-22, prov 215 uppg 12: «det måste tydligare vara markerat
    i koordinatsystemet vilken triangel det är vi pratar om»."""
    u = {"text": "Linjen $f$ har ekvationen $x + y = 6$ och linjen $g$ har "
                 "ekvationen $2x - y = 0$. Linjerna $f$ och $g$ bildar en "
                 "triangel tillsammans med $x$-axeln. Figuren visar linjerna "
                 "$f$ och $g$. Beräkna triangelns area.",
         "figur": {"typ": "linjar", "k": -1, "m": 6}}
    exam_figures.linjar_ur_text(u)
    assert u["figur"]["triangel"] == "x"
    assert exam_figures.triangelhorn((-1, 6), (2, 0), "x") == [
        (2.0, 4.0), (6.0, 0.0), (0.0, 0.0)]
    tex = exam_figures.render_figur(exam_spec.FigLinjar.model_validate(u["figur"]))
    assert r"\fill[yellow!50" in tex and "{triangeln}" in tex
    # Skuggan ligger under linjerna.
    assert tex.index(r"\fill[yellow!50") < tex.index("plot coordinates")
    # Redan namngivna linjer (ett sparat papper) får också sin triangel.
    sparad = {"text": u["text"], "figur": {"typ": "linjar", "k": -1, "m": 6,
                                           "namn": "f", "fler": [
                                               {"k": 2, "m": 0, "namn": "g"}]}}
    exam_figures.linjar_ur_text(sparad)
    assert sparad["figur"]["triangel"] == "x"
    # Parallella linjer bildar ingen triangel.
    assert exam_figures.triangelhorn((2, 1), (2, 5), "x") is None


def test_sparat_papper_utan_triangelfalt_trycks_med_triangel():
    """Prov 215 uppg 12 skrevs inte om efter att fältet kom; pappret läser
    triangeln ur texten vid bygget."""
    from app import exam_latex
    it = exam_spec.ExamItem.model_validate({
        "del": "C", "avsnitt": "2.3", "delmoment": "x", "formaga": "PL",
        "typ": "problem", "poang": [1, 1, 0], "innehall": ["G25-M2A-ALG-1"],
        "text": "Linjen $f$ har ekvationen $x + y = 6$ och linjen $g$ har "
                "ekvationen $2x - y = 0$. Linjerna $f$ och $g$ bildar en "
                "triangel tillsammans med $x$-axeln. Figuren visar linjerna "
                "$f$ och $g$. Beräkna triangelns area.",
        "losning": "12", "bedomning": "+1 E a\n+1 C b",
        "figur": {"typ": "linjar", "k": -1, "m": 6, "namn": "f",
                  "fler": [{"k": 2, "m": 0, "namn": "g"}]}})
    assert exam_latex._med_triangel(it).figur.triangel == "x"
    utan = it.model_copy(update={"text": "Figuren visar linjerna $f$ och $g$."})
    assert exam_latex._med_triangel(utan) is utan


def test_skiss_utan_skala():
    """Rickard 2026-10-22, prov 215 uppg 12: med rutnät och skalsiffror läses
    höjden 4 och basen 6 av. En skiss har bara axlar och linjer."""
    u = {"text": "Linjen $f$ har ekvationen $x + y = 6$ och linjen $g$ har "
                 "ekvationen $2x - y = 0$. Linjerna $f$ och $g$ bildar en "
                 "triangel tillsammans med $x$-axeln. Figuren visar en skiss "
                 "av linjerna $f$ och $g$. Beräkna triangelns area.",
         "figur": {"typ": "linjar", "k": -1, "m": 6}}
    exam_figures.linjar_ur_text(u)
    assert u["figur"]["skiss"] is True and u["figur"]["triangel"] == "x"
    tex = exam_figures.render_figur(exam_spec.FigLinjar.model_validate(u["figur"]))
    assert "black!30" not in tex and "black!50" not in tex
    assert "footnotesize" not in tex and "line width=1pt" not in tex
    assert r"\fill[yellow!50" in tex and "plot coordinates" in tex
    # Utan ordet skiss: rutnätet står kvar.
    vanlig = {"text": "Figuren visar linjen.", "figur": {"typ": "linjar", "k": 1, "m": 0}}
    exam_figures.linjar_ur_text(vanlig)
    assert "skiss" not in vanlig["figur"]
    assert "black!30" in exam_figures.render_figur(
        exam_spec.FigLinjar.model_validate(vanlig["figur"]))


def test_linje_med_26_enheter_far_en_linje_per_heltal():
    """Blad 310:11 (2026-10-23): y = 3x − 2 på −1 ≤ x ≤ 7 fick y-linjer på
    2,5, och facits avläsning (0, −2), (1, 1) låg mellan linjerna."""
    tikz = exam_figures._funktionsgraf(lambda x: 3 * x - 2, -1, 7)
    ylinjer = re.findall(r"\\draw\[black!30,thin\] \(0,([\d.]+)\)", tikz)
    # −6 … 20 med luften: en linje per heltal utom de fem märkta.
    assert len(ylinjer) >= 20


def test_koordinatsystemets_hojd_raknas_ur_figuren():
    """Blad 311:11 (2026-10-23): grafen räknades som 60 mm och hamnade ensam
    på sidan efter texten. Ett 8 cm rutnät med axlar behöver minst 90 mm."""
    from app import exam_latex
    tex = exam_figures._funktionsgraf(lambda x: 2.5 * x + 10, -1, 7)
    assert exam_latex._figur_mm(tex) >= 90
    assert exam_latex._figur_mm(r"\begin{tikzpicture}[scale=2](0,0)--(0,1)"
                                r"\end{tikzpicture}") == exam_latex._MM_FIGUR


def test_stapeldiagrammets_langa_etiketter_krockar_inte():
    """Blad 301 uppg. 9 (2026-10-23): «Fotboll» och «Simning» en cm isär
    skrevs ihop. Mitten på grannstaplarna står minst en etikettbredd isär."""
    import re
    from app import exam_figures, exam_spec
    f = exam_spec.FigStapeldiagram(typ="stapeldiagram",
                                   kategorier=["Fotboll", "Simning", "Dans", "Gym"],
                                   varden=[35, 15, 20, 30])
    mitt = [float(x) for x in re.findall(r"\\node\[below\] at \(([\d.]+),0\)",
                                         exam_figures._stapeldiagram(f))]
    assert len(mitt) == 4
    assert min(b - a for a, b in zip(mitt, mitt[1:])) >= 0.17 * 7
    # Korta etiketter står som förut, en cm isär.
    kort = exam_spec.FigStapeldiagram(typ="stapeldiagram", kategorier=["A", "B"],
                                      varden=[1, 2])
    assert "at (1,0)" in exam_figures._stapeldiagram(kort)
