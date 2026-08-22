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
            # Två namngivna svarsrader på SAMMA uppgift — formen läraren dömde
            # om (se test_ett_svar_per_rad). Typen är «redovisning» och inte
            # «rutin» med flit: _y() sorterar träffarna på y utan att bry sig om
            # sidan, så en tredje «Endast svar krävs» på sida 2 hade flyttat
            # index åt de andra måtten.
            {"del": "C", "formaga": "P", "typ": "redovisning",
             "poang": [2, 0, 0],
             "text": "En andragradsekvation $x^2 + px - 15 = 0$ har lösningen "
                     "$x = 3$.",
             "svarsfalt": ["Svar $p =$", "Svar andra lösningen"],
             "losning": "$p = 2$, $x = -5$.", "bedomning": "+2 E."},
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


@pytest.mark.tectonic
def test_ett_svar_per_rad(rader):
    """«När det står Svar = ___ och sen Svar ___ igen bredvid — så ska det INTE
    se ut. Ett svar per rad; nästa svar på raden under.»

    Förlagans eget \\svarsrad saknar \\par och lägger två svarsrader BREDVID
    varandra på samma rad. Det är ett av hennes småfel — som betygstabellens
    överlappande spann — och rättas i _preamble.tex.j2. Testet låser
    rättelsen: två namngivna svarsrader på samma uppgift ska ha olika y och
    samma x (båda börjar vid satsytans vänsterkant)."""
    rad, _ = rader
    ett = [(x, y) for _s, x, y, txt in rad if txt.startswith("Svar p =")]
    tva = [(x, y) for _s, x, y, txt in rad if txt.startswith("Svar andra")]
    assert len(ett) == 1 and len(tva) == 1, f"{ett} {tva}"
    (x1, y1), (x2, y2) = ett[0], tva[0]
    assert y2 > y1 + 5, f"svarsraderna delar rad (y {y1:.1f} och {y2:.1f})"
    assert abs(x1 - x2) < TAL, (
        f"andra svarsraden börjar på x={x2:.1f}, inte vid vänsterkanten "
        f"{x1:.1f}")


# ── VÄNDMÄRKET ────────────────────────────────────────────────────────
# LÄRARENS BEGÄRAN 2026-08-22: «så eleverna inte gör en sida, tror att de är
# klara och lämnar in». Kursivt «Vänd» plus en tunn pil i nedre högra hörnet,
# på varje sida UTOM den sista i varje del — där lämnar man in.
#
# Måtten: sidfoten sitter på förlagans egen bottenmarginal, och pilen är det
# som når ut i högerkanten. Ordet «Vänd» slutar därför en pilbredd (6 mm plus
# ett tunt mellanrum) innanför satsytans högerkant — det är avsiktligt, och
# därför mäts ordet mot 35 mm och inte mot 25.
VAND_HOGERKANT_MAX = 35 * 72 / 25.4       # ≈ 99 pt: ordet + pilen
VAND_NEDERKANT_MAX = 25 * 72 / 25.4       # ≈ 71 pt: bottenmarginalen


def _langt_prov(delar=("B", "C"), per_del=9):
    """Ett prov som säkert blir flera sidor i varje del — vändmärket säger
    ingenting på ett prov som får plats på ett blad."""
    def uppg(nr, kod):
        return {"del": kod, "formaga": "P", "typ": "redovisning",
                "poang": [1, 1, 0],
                "text": f"Uppgift {nr}. " + "Bestäm konstanten $a$. " * 12,
                "losning": "Svar.", "bedomning": "+1 E, +1 C."}
    uppgifter, nr = [], 1
    for kod in delar:
        for _ in range(per_del):
            uppgifter.append(uppg(nr, kod))
            nr += 1
    return {"titel": "Kapitel 2", "kurs": "Matematik 2c", "klass": "NA25",
            "tid_min": 90, "hjalpmedel": "Formelblad.",
            "uppgifter": uppgifter}


def _vandsidor(spec, tmp_path):
    fitz = pytest.importorskip("fitz")
    doc, fel = exam_spec.validate_exam_json(spec, "prov")
    assert doc is not None, fel
    pdf, logg = exam_pdf.compile_pdf(exam_latex.render_prov(doc), tmp_path,
                                     "vand", epoch=EPOK)
    assert pdf is not None, logg
    d = fitz.open(pdf)
    ut = []
    for sida in d:
        traff = [b for b in sida.get_text("blocks") if "Vänd" in b[4]]
        if not traff:
            ut.append(None)
            continue
        x0, y0, x1, y1 = traff[0][:4]
        ut.append((sida.rect.width - x1, sida.rect.height - y1))
    d.close()
    return ut


@pytest.mark.tectonic
def test_vandmarket_star_pa_alla_sidor_utom_delens_sista(tmp_path):
    """Tvådelsprov på flera sidor per del. Sista sidan i Del A och sista sidan
    i Del B ska sakna märket; alla andra ska ha det i nedre högra hörnet —
    försättsbladet inräknat, för efter det kommer alltid mer."""
    sidor = _vandsidor(_langt_prov(), tmp_path)
    assert len(sidor) >= 4, f"provet blev bara {len(sidor)} sidor"
    # Delarnas sista sidor är de utan märke; de ska vara EXAKT två (en per del)
    # och den sista av dem ska vara dokumentets sista sida.
    utan = [i for i, v in enumerate(sidor) if v is None]
    assert len(utan) == 2, f"märket saknas på sidorna {utan}"
    assert utan[-1] == len(sidor) - 1, "sista sidan bär «Vänd»"
    for i, v in enumerate(sidor):
        if v is None:
            continue
        hoger, nedre = v
        assert hoger < VAND_HOGERKANT_MAX,             f"s.{i + 1}: «Vänd» {hoger:.1f} pt från högerkanten"
        assert nedre < VAND_NEDERKANT_MAX,             f"s.{i + 1}: «Vänd» {nedre:.1f} pt från nederkanten"


@pytest.mark.tectonic
def test_vandmarket_pa_ett_prov_utan_delar(tmp_path):
    """En del: märket på alla sidor utom den sista."""
    spec = _langt_prov(delar=(None,), per_del=14)
    sidor = _vandsidor(spec, tmp_path)
    assert len(sidor) >= 3
    assert sidor[-1] is None, "sista sidan bär «Vänd»"
    assert all(v is not None for v in sidor[:-1]),         f"märket saknas mitt i provet: {[i for i, v in enumerate(sidor) if v is None]}"


@pytest.mark.tectonic
def test_bedomningsanvisningen_har_inget_vandmarke(tmp_path):
    """Bedömningsanvisningen delar preamblen men är LÄRARENS papper — ingen
    elev bläddrar i den, och «Vänd» hör inte hemma där."""
    fitz = pytest.importorskip("fitz")
    doc, fel = exam_spec.validate_exam_json(_langt_prov(), "prov")
    assert doc is not None, fel
    pdf, logg = exam_pdf.compile_pdf(exam_latex.render_bedomning(doc),
                                     tmp_path, "bed", epoch=EPOK)
    assert pdf is not None, logg
    d = fitz.open(pdf)
    assert not any("Vänd" in s.get_text() for s in d)
    d.close()
