"""FÖRLAGANS MÅTT — provets form som mätbara tal.

Läraren lämnade in sitt eget Overleaf-prov (Ma 2c, kapitel 2, NA25) och sa:
«Typ exakt så här vill jag att mina prov ska se ut. Inte innehållet — formen.
Lika mycket mellanrum mellan uppgifterna. Tänk på hur mycket text det är. Tänk
på hur jag har strukturerat deluppgifterna. Och var poängen står.»

Formen är alltså ett KRAV, och ett krav som inte mäts glider. Måtten nedan är
avlästa ur hennes PDF med PyMuPDF — textspannens x och y i punkter — och de
prövas här mot appens egen rendering av samma uppgifter. Ett test som bara
letade efter \\question hade passerat även när uppgifterna hamnat 8 mm för
långt isär, och det är precis det hon skulle se.

Två slags mått:

  * SIDANS — satsytans kanter och poängspalten. De följer av preamblen och
    ändras bara om någon rör geometry eller \\pointsinrightmargin.
  * RYTMENS — avståndet mellan två uppgifter, mellan två deluppgifter, mellan
    frågan och svarslinjen. De följer av \\questionshook/\\partshook och av
    \\svarsrad, och det är de som avgör om pappret KÄNNS som hennes.

Testerna kräver Tectonic (markören `tectonic`, samma grind som
test_pdf_kontrakt) och PyMuPDF, som redan finns för bokinläsningen.
"""
from __future__ import annotations

import pytest

from app import exam_latex, exam_pdf, exam_spec

EPOK = 1_767_225_600          # samma fasta tidsstämpel som test_pdf_kontrakt

# ── MÄTT I LÄRARENS PDF (punkter, A4 = 595,28 × 841,89) ────────────────
# Satsytan: 25 mm runt om.
SATSYTA_VANSTER = 70.9
SATSYTA_HOGER = 524.4
# Poängspalten. «1 p» börjar på x = 551,8 och slutar på 568,1 — samma spalt för
# uppgift och deluppgift, för poängen är sidans och inte styckets.
POANGSPALT_X = 551.8
# Uppgiftens hängande nummer och deluppgiftens «(a)».
UPPGIFT_TEXT_X = 91.7
DELUPPGIFT_TEXT_X = 116.4
# Rytmen, mätt mellan baslinjer.
UPPGIFT_TILL_UPPGIFT = 42.1
DELUPPGIFT_TILL_DELUPPGIFT = 28.3
FRAGA_TILL_SVARSRAD = 22.6
FORSTA_RADEN_TILL_STYCKET = 19.4
# Sidhuvudets linje och delrubrikens linje.
HUVUDLINJE_Y = 55.7
DELRUBRIKLINJE_Y = 105.0
# Hur mycket ett mått får glida innan pappret inte längre är hennes. En halv
# punkt är under en tiondels millimeter — det är sättningens eget brus.
TAL = 0.8


def _prov() -> dict:
    """Två delar, kortsvar med deluppgifter först och en redovisningsuppgift
    sist — förlagans egen form, med appens minsta möjliga innehåll."""
    def kort(text, p=1):
        return {"poang": [p, 0, 0], "text": text, "losning": "Svar.",
                "bedomning": "+1 E."}
    return {
        "titel": "Prov Kapitel 2", "kurs": "Matematik 2c", "klass": "NA25",
        "tid_min": 90,
        "hjalpmedel": "Del B utan räknare. Del C med räknare.",
        "uppgifter": [
            {"del": "B", "formaga": "P", "typ": "rutin", "poang": [0, 0, 0],
             "text": "", "deluppgifter": [
                 kort("Lös ekvationen $x^2 - 10x + 21 = 0$."),
                 kort("Beräkna $\\lg 2 + \\lg 5$."),
                 kort("Lös ekvationen $5^{x+1} = 125$.")]},
            {"del": "B", "formaga": "B", "typ": "rutin", "poang": [2, 0, 0],
             "text": "Bestäm värdet av $c$ så att ekvationen "
                     "$x^2 - 8x + c = 0$ bara har en lösning.",
             "losning": "$c = 16$.", "bedomning": "+2 E."},
            {"del": "C", "formaga": "PL", "typ": "problem", "poang": [1, 2, 0],
             "text": "En rektangel har omkretsen 24 cm.\n"
                     "Bestäm den största möjliga arean.",
             "losning": "36 cm$^2$.", "bedomning": "+1 E, +2 C."},
        ],
    }


@pytest.fixture(scope="module")
def rader(tmp_path_factory):
    """Varje textrad i provets PDF som (sida, x, y, text)."""
    fitz = pytest.importorskip("fitz")
    doc, fel = exam_spec.validate_exam_json(_prov(), "prov")
    assert doc is not None, fel
    ut = tmp_path_factory.mktemp("forlaga")
    pdf, logg = exam_pdf.compile_pdf(exam_latex.render_prov(doc), ut,
                                     "prov", epoch=EPOK)
    assert pdf is not None, logg
    d = fitz.open(pdf)
    rad = []
    for sida in range(len(d)):
        for b in d[sida].get_text("dict")["blocks"]:
            if b["type"] != 0:
                continue
            for lin in b["lines"]:
                txt = "".join(s["text"] for s in lin["spans"]).strip()
                if txt:
                    rad.append((sida, lin["spans"][0]["bbox"][0],
                                lin["spans"][0]["bbox"][1], txt))
    # Linjerna (sidhuvudets och delrubrikens) ligger som teckningar.
    linjer = [(s, r["rect"].y0) for s in range(len(d))
              for r in d[s].get_drawings()
              if abs(r["rect"].height) < 1.5
              and abs(r["rect"].width - (SATSYTA_HOGER - SATSYTA_VANSTER)) < 1]
    d.close()
    return rad, linjer


def _y(rader, fras, n: int = 0, *, med_forsattsblad: bool = False):
    """y för den n:te raden som bär `fras`, uppifrån räknat.

    Försättsbladet (sida 0) hoppas över: dess instruktionspunkt CITERAR
    «Endast svar krävs», och den citeringen är inte en uppgifts kravrad. Utan
    filtret mätte testet avståndet från en punktlista på sida 1 till en fråga
    på sida 2 och rapporterade 207 pt."""
    traffar = sorted(y for sida, _x, y, txt in rader
                     if fras in txt and (med_forsattsblad or sida > 0))
    assert len(traffar) > n, f"hittade inte {fras!r} (nr {n}) i provet"
    return traffar[n]


def _x(rader, fras):
    for _sida, x, _y, txt in rader:
        if fras in txt:
            return x
    raise AssertionError(f"hittade inte {fras!r} i provet")


@pytest.mark.tectonic
def test_satsytan_ar_forlagans(rader):
    """25 mm runt om: uppgiftsnumret börjar på 76,7 och texten på 91,7."""
    rad, _ = rader
    assert abs(_x(rad, "Bestäm värdet av") - UPPGIFT_TEXT_X) < TAL
    assert abs(_x(rad, "Lös ekvationen") - DELUPPGIFT_TEXT_X) < TAL


@pytest.mark.tectonic
def test_poangen_star_i_hogermarginalen(rader):
    """«Och var poängen står.» I en egen spalt UTANFÖR satsytan, i lod med
    uppgiftens första rad — inte sist på den rad den råkar hamna på.

    Både uppgiftens och deluppgiftens poäng står i SAMMA spalt: poängen är
    sidans, inte styckets."""
    rad, _ = rader
    poang = [(x, y) for _s, x, y, txt in rad if txt.strip() in ("1 p", "2 p", "3 p")]
    assert len(poang) >= 4, f"för få poängmarkörer: {poang}"
    for x, _y in poang:
        assert abs(x - POANGSPALT_X) < TAL, f"poängen står på x={x}, inte i spalten"
        assert x > SATSYTA_HOGER, "poängen ligger inne i satsytan"


@pytest.mark.tectonic
def test_lika_mycket_mellanrum_mellan_uppgifterna(rader):
    """«Lika mycket mellanrum mellan uppgifterna.» Förlagan mäter 42,1 pt
    mellan sista raden i en uppgift och första raden i nästa."""
    rad, _ = rader
    # Sista svarslinjen i uppgift 1 (kortsvaren) → kravraden på uppgift 2.
    sista_svaret_i_ett = _y(rad, "Svar:", 2)
    krav_pa_tva = _y(rad, "Endast svar krävs", 1)
    # Svarslinjen lägger 2 mm under sig (förlagans \svarsrad), så avståndet
    # från den till nästa uppgift är rytmen plus den luften.
    matt = krav_pa_tva - sista_svaret_i_ett
    assert abs(matt - (UPPGIFT_TILL_UPPGIFT + 5.7)) < 3, (
        f"uppgift→uppgift mäter {matt:.1f} pt")


@pytest.mark.tectonic
def test_deluppgifternas_rytm_och_svarslinjer(rader):
    """Deluppgift → deluppgift mäter 28,3 pt när ingen svarslinje ligger
    emellan, och frågan → «Svar:» mäter 22,6 pt."""
    rad, _ = rader
    fragor = sorted(y for _s, _x, y, txt in rad if txt.startswith("Lös ekvationen")
                    or txt.startswith("Beräkna"))
    # De tre första svarslinjerna hör till kortsvarens deluppgifter; den
    # fjärde är uppgift 2:s egen.
    svar = sorted(y for _s, _x, y, txt in rad if txt.startswith("Svar:"))[:3]
    assert len(fragor) == 3 and len(svar) == 3
    for f, s in zip(fragor, svar):
        assert abs((s - f) - FRAGA_TILL_SVARSRAD) < TAL, (
            f"fråga→svarslinje mäter {s - f:.1f} pt")
    # Svarslinjen → nästa deluppgift: rytmen plus svarsradens egen luft.
    for s, f in zip(svar, fragor[1:]):
        assert abs((f - s) - (DELUPPGIFT_TILL_DELUPPGIFT + 5.7)) < 3, (
            f"svarslinje→deluppgift mäter {f - s:.1f} pt")


@pytest.mark.tectonic
def test_kravraden_och_forsta_stycket(rader):
    """Kravetiketten står på uppgiftens första rad, och frågan 19,4 pt under
    den — ett styckeavstånd, precis som i förlagan."""
    rad, _ = rader
    # Uppgift 2 — den som bär BÅDE kravrad och egen frågetext.
    krav = _y(rad, "Endast svar krävs", 1)
    forsta = _y(rad, "Bestäm värdet av")
    assert abs((forsta - krav) - FORSTA_RADEN_TILL_STYCKET) < TAL, (
        f"kravrad→fråga mäter {forsta - krav:.1f} pt")


@pytest.mark.tectonic
def test_linjerna_ligger_dar_forlagan_har_dem(rader):
    """Sidhuvudets linje på y = 55,7 och delrubrikens på y = 105,0 — båda
    tvärs över hela satsytan."""
    _rad, linjer = rader
    y_varden = [y for _s, y in linjer]
    assert any(abs(y - HUVUDLINJE_Y) < TAL for y in y_varden), y_varden
    assert any(abs(y - DELRUBRIKLINJE_Y) < TAL for y in y_varden), y_varden


@pytest.mark.tectonic
def test_forsattsbladet_har_forlagans_ordning(rader):
    """Titel, klass, linje, delöversikt, provtid, hjälpmedel, inlämningsregel,
    totalpoäng, betygstabell, instruktioner, namnrader — i den ordningen. Det
    är den läraren känner igen pappret på."""
    rad, _ = rader
    forsta_sidan = [(y, txt) for s, _x, y, txt in rad if s == 0]
    ordning = ["Prov Kapitel 2", "Klass: NA25", "Del A", "Provtid:",
               "Hjälpmedel:", "Du lämnar in", "Provet kan ge totalt",
               "Betyg", "Instruktioner", "Namn:", "Klass:"]
    sedd = -1.0
    for fras in ordning:
        y = min((y for y, txt in forsta_sidan if fras in txt and y > sedd),
                default=None)
        assert y is not None, f"«{fras}» saknas eller står i fel ordning"
        sedd = y
