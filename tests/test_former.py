"""De fem formerna: tabellen, kryssrutorna, stegtabellen, enheten och de
kommenterade elevlösningarna.

Formgranskningen mot designdokumentet «Arbetsblad prov och tavlor — femton
former» slutade i en lista över former appen kunde RITA men aldrig
PRODUCERA: stilbladen hade reglerna, men schemat hade inga fält, så modellen
kunde inte skriva ett papper som bar dem. Det här är fälten — och det som
prövas är att de går hela vägen: schema → prompt → LaTeX → PDF, och att det
som bara läraren ska se stannar på lärarens papper.

Den sista punkten är den viktigaste. Stegtabellens svar («första felet står i
steg 2»), kryssrutornas rätta val och elevlösningarna är facit. Hamnar de på
elevens ark är provet förstört, och det syns inte förrän tjugotvå elever har
det i handen.
"""
from __future__ import annotations

import pytest

from app import exam_gen, exam_latex, exam_pdf, exam_spec


def _uppgift(**extra) -> dict:
    return {"del": None, "formaga": "P", "typ": "rutin", "poang": [2, 0, 0],
            "text": "Bestäm värdet.", "losning": "42", "bedomning": "+2 E",
            **extra}


def _dok(*uppgifter, **extra) -> dict:
    return {"titel": "Prov · former", "kurs": "Matematik, nivå 2c",
            "klass": "NA25", "hjalpmedel": "Räknare.",
            "uppgifter": list(uppgifter), **extra}


def _doc(*uppgifter, profil="arbetsblad", **extra):
    doc, fel = exam_spec.validate_exam_json(_dok(*uppgifter, **extra), profil)
    assert doc is not None, fel
    return doc


TABELL = {"rubriker": ["År", "2020", "2023"],
          "rader": [["Antal", "5 400", "12 600"]]}
RUTOR = {"etikett": "Sats", "val": ["Randvinkelsatsen", "Kordasatsen"], "ratt": 0}
STEG = {"kolumner": ["Alvas lösning"],
        "steg": [{"celler": ["$3^{x+1} = 7 \\cdot 3^{x-2}$"]},
                 {"celler": ["$3^{3} = 7$"]},
                 {"celler": ["$27 = 7$"]}],
        "forsta_fel": 1}
ELEVER = [
    {"etikett": "Elevlösning A",
     "partier": [{"rader": ["$f'(x) = 3x^2$"], "poang": [0, 0, 0],
                  "dom": "Derivatan är fel."}]},
    {"etikett": "Elevlösning B",
     "partier": [{"rader": ["$f'(x) = 3x^2 + 3 = 0$"], "poang": [1, 0, 0],
                  "dom": "Godtagbar ansats."},
                 {"rader": ["$x^2 = -1$ saknar reell lösning."], "poang": [0, 1, 0],
                  "dom": "Godtagbart resonemang."}]},
]


# ═════════════════════════════════ schemat ═══════════════════════════════

def test_alla_fem_formerna_ryms_i_schemat():
    doc = _doc(_uppgift(enhet="laddpunkter/år", tabell=TABELL),
               _uppgift(svarsrutor=RUTOR),
               _uppgift(poang=[0, 1, 1], typ="resonemang", formaga="R",
                        stegtabell=STEG, elevlosningar=ELEVER))
    u = doc.uppgifter
    assert u[0].enhet == "laddpunkter/år" and u[0].tabell.rubriker[0] == "År"
    assert u[1].svarsrutor.val[1] == "Kordasatsen"
    assert u[2].stegtabell.forsta_fel == 1
    assert [e.poang for e in u[2].elevlosningar] == [0, 2]


def test_en_deluppgift_kan_ocksa_bara_formerna():
    doc = _doc({"del": None, "formaga": "PL", "typ": "problem",
                "poang": [0, 0, 0], "text": "En kub.", "losning": "",
                "bedomning": "", "deluppgifter": [
                    {"poang": [2, 0, 0], "text": "Kantens längd?",
                     "losning": "1,66", "bedomning": "+2 E", "enhet": "dm"},
                    {"poang": [0, 2, 0], "text": "Rimligt?", "losning": "ja",
                     "bedomning": "+2 C", "svarsrutor": {
                         "etikett": "Rimligt?", "val": ["Ja", "Nej"], "ratt": 0}}]})
    d = doc.uppgifter[0].deluppgifter
    assert d[0].enhet == "dm" and d[1].svarsrutor.etikett == "Rimligt?"


@pytest.mark.parametrize("fel,vad", [
    ({"tabell": {"rubriker": ["a", "b"], "rader": [["1"]]}},
     "en rad med färre celler än kolumner"),
    ({"stegtabell": {"kolumner": ["x"], "steg": [{"celler": ["a"]},
                                                 {"celler": ["b"]},
                                                 {"celler": ["c"]}],
                     "forsta_fel": 7}},
     "ett felsteg som inte finns"),
    ({"stegtabell": {"kolumner": ["x", "y"], "steg": [{"celler": ["a"]},
                                                      {"celler": ["b", "c"]},
                                                      {"celler": ["d", "e"]}],
                     "forsta_fel": 0}},
     "ett steg med fel antal celler"),
    ({"svarsrutor": {"etikett": "Sats", "val": ["bara ett"]}},
     "en kryssruterad med ett enda val"),
    ({"svarsrutor": {"etikett": "Sats", "val": ["a", "b"], "ratt": 5}},
     "ett rätt svar utanför listan"),
    ({"elevlosningar": ELEVER[:1]},
     "en enda elevlösning — poängen är att visa skillnaden"),
])
def test_trasiga_former_stoppas_med_besked(fel, vad):
    doc, fellista = exam_spec.validate_exam_json(
        _dok(_uppgift(**fel)), "arbetsblad")
    assert doc is None, f"{vad} släpptes igenom"
    assert fellista and fellista[0]["message"], vad


def test_en_elevlosning_kan_inte_ge_mer_an_uppgiften_ar_vard():
    """Bedömningen ska gå ihop: en lösning som ger fyra poäng på en uppgift
    värd två är ett skrivfel som annars når läraren mitt i rättningen."""
    for_mycket = [{"etikett": "A", "partier": [
        {"rader": ["x"], "poang": [5, 0, 0], "dom": "…"}]},
        {"etikett": "B", "partier": [{"rader": ["y"], "poang": [1, 0, 0], "dom": "…"}]}]
    doc, fel = exam_spec.validate_exam_json(
        _dok(_uppgift(elevlosningar=for_mycket)), "arbetsblad")
    assert doc is None
    assert "värd" in fel[0]["message"]


def test_formerna_star_i_prompten_sa_modellen_vet_nar_de_ska_anvandas():
    """Ett fält som finns i schemat men inte i instruktionen används aldrig —
    grammatiken tillåter det, men modellen vet inte att det finns."""
    for ord_ in ("tabell", "svarsrutor", "stegtabell", "elevlosningar", "enhet"):
        assert ord_ in exam_gen.INSTRUCTION, f"{ord_} saknas i instruktionen"
    # …och att facit hör till läraren måste stå där också.
    assert "visas bara för läraren" in exam_gen.INSTRUCTION


def test_grammatiken_slapper_igenom_de_nya_falten():
    schema = exam_spec.to_response_format()
    text = str(schema)
    for falt in ("tabell", "svarsrutor", "stegtabell", "elevlosningar", "enhet"):
        assert falt in text, f"{falt} nås inte av grammatiken"


# ═════════════════════════════════ papperet ══════════════════════════════

def _alla_tex(doc):
    return {
        "prov": exam_latex.render_prov(doc),
        "arbetsblad": exam_latex.render_arbetsblad(doc),
        "bedomning": exam_latex.render_bedomning(doc),
    }


def test_formerna_satts_i_latex():
    doc = _doc(_uppgift(enhet="kr", tabell=TABELL),
               _uppgift(svarsrutor=RUTOR),
               _uppgift(poang=[0, 1, 1], typ="resonemang", formaga="R",
                        stegtabell=STEG))
    tex = _alla_tex(doc)
    for namn, t in tex.items():
        assert "\\begin{tabular}" in t, f"{namn} saknar datatabellen"
        assert "\\begin{tabularx}" in t, f"{namn} saknar stegtabellen"
        assert "\\svarsrutor{" in t, f"{namn} saknar kryssruteraden"
        assert "Randvinkelsatsen" in t and "Kordasatsen" in t
    # Enheten hör till SVARSRADEN, och svarsraden finns bara på elevens ark.
    # (`\svarsradmed` står i preamblen överallt — det är ANROPET som räknas.)
    for namn in ("prov", "arbetsblad"):
        assert "\\svarsradmed{}{" in tex[namn], f"{namn} saknar enheten"
    assert "\\svarsradmed{}{" not in tex["bedomning"], \
        "bedömningen har ingen svarsrad — den har lösningen"


def test_facit_stannar_pa_lararens_papper():
    """Det här är formernas farligaste egenskap: de BÄR svaret. Står svaret på
    elevens ark är provet förstört, och det märks först när klassen sitter med
    det."""
    doc = _doc(_uppgift(svarsrutor=RUTOR),
               _uppgift(poang=[0, 1, 1], typ="resonemang", formaga="R",
                        stegtabell=STEG, elevlosningar=ELEVER))
    tex = _alla_tex(doc)
    for namn in ("prov", "arbetsblad"):
        assert "Första felet står i steg" not in tex[namn], \
            f"{namn} avslöjar vilket steg som är fel"
        assert "Elevlösning A" not in tex[namn], \
            f"{namn} bär elevlösningarna — de är lärarens"
        assert "\\textbf{\\svarsruteval" not in tex[namn], \
            f"{namn} markerar det rätta krysset"
    assert "Första felet står i steg 2" in tex["bedomning"]
    assert "Elevlösning A" in tex["bedomning"]
    assert "\\textbf{\\svarsruteval" in tex["bedomning"]


def test_stegtabellen_har_en_kryssruta_per_steg():
    doc = _doc(_uppgift(poang=[0, 1, 1], typ="resonemang", formaga="R",
                        stegtabell=STEG))
    tex = exam_latex.render_prov(doc)
    # Tre steg → tre rutor att kryssa, och ingen av dem förkryssad.
    assert tex.count("\\kryssruta") >= 3
    assert "\\textbf{X}" not in tex


def test_tva_kolumner_ger_tva_elevers_losningar_sida_vid_sida():
    tva = dict(STEG, kolumner=["Alvas lösning", "Bilals lösning"],
               steg=[{"celler": ["$3^{x+1}$", "$\\lg 3^{x+1}$"]},
                     {"celler": ["$3^3 = 7$", "$(x+1)\\lg 3$"]},
                     {"celler": ["$27 = 7$", "$x \\approx 0{,}77$"]}])
    doc = _doc(_uppgift(poang=[0, 1, 1], typ="resonemang", formaga="R",
                        stegtabell=tva))
    tex = exam_latex.render_prov(doc)
    assert "Alvas lösning" in tex and "Bilals lösning" in tex
    assert "{lXXc}" in tex        # steg + två lösningar + kryssrutekolumn


# ═════════════════════════════════ tryckt ════════════════════════════════

@pytest.mark.tectonic
def test_formerna_kompilerar_och_star_i_pdfen(tmp_path):
    """Formerna finns på papperet — inte bara i LaTeX-källan. En form som
    kompilerar men försvinner i sättningen är värre än en som faller."""
    import pypdfium2

    doc = _doc(_uppgift(enhet="laddpunkter/år", tabell=TABELL),
               _uppgift(svarsrutor=RUTOR),
               _uppgift(poang=[0, 1, 1], typ="resonemang", formaga="R",
                        stegtabell=STEG, elevlosningar=ELEVER))
    for namn, tex in _alla_tex(doc).items():
        pdf, logg = exam_pdf.compile_pdf(tex, tmp_path, namn)
        assert pdf is not None, f"{namn} gick inte att kompilera:\n{logg[-800:]}"
        text = "".join(pypdfium2.PdfDocument(str(pdf))[i].get_textpage().get_text_range()
                       for i in range(len(pypdfium2.PdfDocument(str(pdf)))))
        assert "12 600" in text, f"{namn}: datatabellens siffror saknas"
        assert "Randvinkelsatsen" in text, f"{namn}: kryssrutornas val saknas"
        if namn == "bedomning":
            assert "Elevlösning A" in text
            assert "steg 2" in text
        else:
            # Enheten står på svarsraden — och svarsraden finns bara här.
            assert "laddpunkter" in text, f"{namn}: enheten saknas"
            assert "Elevlösning" not in text, f"{namn} tryckte lärarens papper"
