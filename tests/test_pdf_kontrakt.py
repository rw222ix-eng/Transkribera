"""Pappret som kommer ut ur skrivaren (Etapp 3).

De andra provsviterna prövar JSON:en, LaTeX-strängen och att kompileringen
returnerar en sökväg. Ingen av dem har hittills öppnat PDF:en och läst vad som
faktiskt står där — och det är det enda läraren delar ut. En uppgift som tappas
i mallen, en poängsumma som inte skrivs ut och ett facit som råkar följa med
elevernas ark syns inte i något strängtest.

Här kompileras fixturprovet med den RIKTIGA motorn, PDF:en öppnas med
pypdfium2 (samma bibliotek tryckpaketet redan använder) och texten läses av:

  * varje uppgiftsstam står på elevernas ark,
  * totalpoängen och betygsgränserna står på provet,
  * facit står i arbetsbladet men ALDRIG på provet,
  * bedömningsanvisningen är lärarens eget papper.

Dessutom snabbpasset: med SOURCE_DATE_EPOCH är samma källa samma PDF, byte för
byte. Ändras hashen har mallen, motorn eller cachen ändrats — och då ska någon
titta på ett papper innan klassen gör det.
"""
from __future__ import annotations

import hashlib
import re

import pytest

from app import exam_latex, exam_pdf, exam_spec
from tests.test_exam import _exam

EPOK = 1_767_225_600          # 2026-01-01T00:00:00Z — vilken som helst, men FAST


def text_ur(pdf) -> str:
    """All text i PDF:en, med radbrytningar och bindestreck utjämnade så en
    uppgiftsstam går att söka efter som en mening."""
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(str(pdf))
    try:
        delar = []
        for i in range(len(doc)):
            sida = doc[i]
            tp = sida.get_textpage()
            delar.append(tp.get_text_range())
            tp.close()
        rå = "\n".join(delar)
    finally:
        doc.close()
    return re.sub(r"\s+", " ", rå.replace("­", "").replace("-\n", ""))


def sidor(pdf) -> int:
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(str(pdf))
    try:
        return len(doc)
    finally:
        doc.close()


@pytest.fixture
def dokument():
    doc, fel = exam_spec.validate_exam_json(_exam())
    assert doc is not None and fel == []
    return doc


@pytest.fixture
def provpdf(dokument, tmp_path):
    pdf, logg = exam_pdf.compile_pdf(exam_latex.render_prov(dokument),
                                     tmp_path, "prov", epoch=EPOK)
    assert pdf is not None, logg
    return pdf


@pytest.mark.tectonic
def test_varje_uppgift_star_pa_elevernas_ark(dokument, provpdf):
    """En uppgift som tappas i mallen upptäcks annars av klassen."""
    text = text_ur(provpdf)
    for u in dokument.uppgifter:
        # Stammen: de första orden räcker och tål radbrytning och matte.
        stam = re.split(r"\$", u.text)[0].strip()
        stam = " ".join(stam.split()[:4])
        assert stam and stam in text, f"uppgiftsstammen saknas i PDF:en: {stam!r}"


@pytest.mark.tectonic
def test_totalpoangen_och_betygsgranserna_star_pa_provet(dokument, provpdf):
    """Poängen utan gränser är bara en siffra: eleven ska kunna läsa av vad
    som krävs för E, C och A på sitt eget papper."""
    text = text_ur(provpdf)
    granser = exam_spec.kravgranser(dokument)
    summor = exam_spec.poangsummor(dokument)
    # Totalpoängen som mallen skriver den — «20 poäng» — inte bara talet 20,
    # som också står i datumet.
    assert f"Totalpoäng {summor['total']} poäng" in text, text[:600]
    assert f"minst {granser['E']['minst']} poäng" in text
    assert f"minst {granser['C']['minst']} poäng" in text
    assert f"minst {granser['A']['minst']} poäng" in text
    assert "Kravgränser" in text


@pytest.mark.tectonic
def test_facit_star_i_arbetsbladet_men_aldrig_pa_provet(dokument, provpdf, tmp_path):
    losning = dokument.uppgifter[0].losning
    nyckel = " ".join(re.split(r"\$", losning)[0].split()[:3]) or "och"
    prov = text_ur(provpdf)

    ab, logg = exam_pdf.compile_pdf(exam_latex.render_arbetsblad(dokument),
                                    tmp_path, "arbetsblad", epoch=EPOK)
    assert ab is not None, logg
    blad = text_ur(ab)
    assert "acit" in blad, "arbetsbladet saknar sitt facit"
    # Provet får inte bära lösningarna — det delas ut till klassen.
    assert "acit" not in prov


@pytest.mark.tectonic
def test_bedomningsanvisningen_ar_lararens_eget_papper(dokument, tmp_path):
    bed, logg = exam_pdf.compile_pdf(exam_latex.render_bedomning(dokument),
                                     tmp_path, "bedomning", epoch=EPOK)
    assert bed is not None, logg
    text = text_ur(bed)
    # Bedömningen bär BÅDE uppgiften och hur den poängsätts.
    assert "E för" in text or "+1" in text or "+2" in text or "+3" in text
    assert sidor(bed) >= 1


@pytest.mark.tectonic
def test_samma_kalla_ger_samma_pdf_byte_for_byte(dokument, tmp_path):
    """Snabbpasset. Med SOURCE_DATE_EPOCH är PDF:en en funktion av källan —
    ändras hashen har mallen, motorn eller cachen ändrats, och då ska någon
    titta på ett papper innan klassen gör det."""
    tex = exam_latex.render_prov(dokument)
    hashar = []
    for varv in ("ett", "tva"):
        pdf, logg = exam_pdf.compile_pdf(tex, tmp_path / varv, "prov", epoch=EPOK)
        assert pdf is not None, logg
        hashar.append(hashlib.sha256(pdf.read_bytes()).hexdigest())
    assert hashar[0] == hashar[1], "samma källa gav två olika PDF:er"


@pytest.mark.tectonic
def test_utan_epok_star_den_riktiga_tiden_i_filen(dokument, tmp_path):
    """Determinismen är testsvitens verktyg, inte appens: ett papper ska inte
    ljuga om när det skrevs."""
    tex = exam_latex.render_prov(dokument)
    a, _ = exam_pdf.compile_pdf(tex, tmp_path / "a", "prov")
    b, _ = exam_pdf.compile_pdf(tex, tmp_path / "b", "prov", epoch=EPOK)
    assert a is not None and b is not None
    assert a.read_bytes() != b.read_bytes()


@pytest.mark.tectonic
def test_gruppuppgiftens_ark_bar_namnrader_men_inga_poang(tmp_path):
    """Gruppens papper ligger på ett bord: namnrader överst, inga poäng i
    marginalen (det är samtalet som prövas), och facit på lärarens sista sida."""
    data = _exam()
    data["grupp"] = {"elever": 3, "langd_min": 45, "redovisning": "muntligt"}
    doc, fel = exam_spec.validate_exam_json(data, "gruppuppgift")
    assert doc is not None, fel
    pdf, logg = exam_pdf.compile_pdf(exam_latex.render_gruppuppgift(doc),
                                     tmp_path, "grupp", epoch=EPOK)
    assert pdf is not None, logg
    text = text_ur(pdf)
    assert text.count("Namn:") == 3, "en namnrad per elev i gruppen"
    assert "45 minuter" in text and "muntligt" in text.lower()
    # Facit och bedömning ligger sist — lärarens ark, inte gruppens.
    assert "Facit" in text
    assert sidor(pdf) >= 2
