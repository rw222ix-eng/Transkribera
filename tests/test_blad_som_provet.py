"""Bladet inför provet i provets form (Rickard 2026-09-25).

De fem proven var godkända och bladen byggdes om efter dem. Tre saker i
koden följer av beställningen:

* samma disposition som provet: stammens meningar i ett stycke med frågan
  direkt efter, och en rad «a) …» i texten börjar ett nytt stycke,
* facit i bedömningsanvisningens form: svaret först och fett, ett steg per
  rad, luft före nästa deluppgift, en linje mellan uppgifterna,
* provets nya vakter (5e8bae9) också på bladet: dolt krav, avrundning vid
  högsta eller minsta värde, «Endast svar» som bedöms på svaret.
"""
from pathlib import Path

from app import exam_gen, exam_latex, exam_spec

UI = Path(__file__).resolve().parent.parent / "app" / "web" / "ui"
MALLAR = Path(exam_latex.__file__).parent / "templates"


def _blad(*uppgifter):
    exam = {"titel": "Inför provet", "kurs": "Matematik, nivå 1c",
            "klass": "NA26F", "hjalpmedel": "",
            "uppgifter": [dict({"del": None, "formaga": "P", "typ": "rutin",
                                "poang": [1, 0, 0], "bedomning": "+1 E"}, **u)
                          for u in uppgifter]}
    doc, fel = exam_spec.validate_exam_json(exam, "arbetsblad")
    assert doc is not None, fel
    return exam, doc


# ───────────────────────── facit som bedömningen ─────────────────────────


def test_facit_delar_svaret_och_stegen():
    g = exam_latex.facit_grupper(
        "225\n$P = 45 + 12 \\cdot 15 = 225$", "kr")
    assert g == [{"namn": "", "svar": "225 kr",
                  "steg": ["$P = 45 + 12 \\cdot 15 = 225$"]}]
    # Meningsslutet: «Nej» fett, förklaringen som ett steg.
    g = exam_latex.facit_grupper(
        "Nej. Talet framför tiopotensen ska vara minst 1.\n$52 = 5{,}2$")
    assert g[0]["svar"] == "Nej"
    assert g[0]["steg"] == ["Talet framför tiopotensen ska vara minst 1.",
                            "$52 = 5{,}2$"]
    # «, eftersom» börjar ett steg.
    g = exam_latex.facit_grupper(
        "$n = 5$, eftersom $3^{4} = 81$ och $3^{5} = 243$.")
    assert g[0]["svar"] == "$n = 5$"
    assert g[0]["steg"] == ["Eftersom $3^{4} = 81$ och $3^{5} = 243$."]
    # En punkt inne i matematiken och en förkortning delar inte.
    g = exam_latex.facit_grupper("t.ex. $x = 3$. Kontroll: $3 + 1 = 4$")
    assert g[0]["svar"] == "t.ex. $x = 3$"


def test_facit_delar_deluppgifter_ur_texten():
    """Bladen bar länge «a) … b) …» i ett och samma facit."""
    g = exam_latex.facit_grupper(
        "a) $0{,}6$\nb) $5$, eftersom $5 \\cdot 5 \\cdot 5 = 125$\n"
        "c) $x = 9$\n$3x - 12 = x + 6$\n$2x = 18$", "kr")
    assert [x["namn"] for x in g] == ["a)", "b)", "c)"]
    # Enheten hör till hela uppgiften och sätts inte på en deluppgift.
    assert g[0]["svar"] == "$0{,}6$"
    assert g[1]["steg"] == ["Eftersom $5 \\cdot 5 \\cdot 5 = 125$"]
    assert g[2]["steg"] == ["$3x - 12 = x + 6$", "$2x = 18$"]


def test_facit_ledet_och_svar_prefixet():
    assert exam_latex.facit_grupper("$5$", "$n =$")[0]["svar"] == "$n =$ $5$"
    assert exam_latex.facit_grupper("Svar: 3\n$20/8$", "burkar")[0] == {
        "namn": "", "svar": "3 burkar", "steg": ["$20/8$"]}


def test_latexfacit_i_bedomningens_form():
    _exam, doc = _blad(
        {"text": "Beräkna priset.", "losning": "225\n$P = 45 + 180$",
         "enhet": "kr"},
        {"text": "Lös.", "poang": [0, 0, 0], "bedomning": "",
         "deluppgifter": [
             {"text": "Lös $2x = 8$.", "poang": [1, 0, 0],
              "losning": "$x = 4$\n$x = 8/2$", "bedomning": "+1 E"},
             {"text": "Lös $x + 1 = 3$.", "poang": [1, 0, 0],
              "losning": "$x = 2$", "bedomning": "+1 E"}]})
    tex = exam_latex.render_arbetsblad(doc)
    facit = tex[tex.index("\\delprovband{Facit}"):]
    assert "\\bedsvar{225~kr}" in facit or "\\bedsvar{225 kr}" in facit
    assert "\\noindent \\(P = 45 + 180\\)\\par" in facit
    assert "\\bedsvar{a)\\enspace \\(\\pmb{x = 4}\\)}" in facit
    assert "\\bedsvar{b)\\enspace \\(\\pmb{x = 2}\\)}" in facit
    # En linje mellan uppgifterna, ingen över den första.
    assert facit.count("\\rule{\\linewidth}{0.15mm}") == 1
    # Mallen tål en äldre vy utan fältet (servern har Python i minnet).
    text = (MALLAR / "arbetsblad.tex.j2").read_text(encoding="utf-8")
    assert "u.facit is defined" in text and "d.facit is defined" in text


def test_skarmens_facit_ar_speglingen():
    js = (UI / "blad-bygg.js").read_text(encoding="utf-8")
    assert "function bladfacit(" in js and "function facitGrupper(" in js
    assert "if (v.typ === 'Arbetsblad') return bladfacit(v, uppgifter);" in js
    css = (UI / "losning.css").read_text(encoding="utf-8")
    assert '[data-form="fa"] .pruppg' in css and ".lobedsteg" in css


def test_facitets_steg_far_en_forklaring_efter_pilen():
    """Rickard 2026-09-26: «lösningarna är ganska svåra att förstå». Ett steg
    i facit kan bära en kort förklaring, «rad ← not» (exam_spec.ELEVNOT), som
    sätts till höger om steget på samma höjd. Svaret är bara svaret: en pil
    på svarsraden stryks. Prompten ber om formen (exam_gen.BLAD_FACIT)."""
    vy = exam_latex._facit_vy("$\\dfrac{x}{4}$ ← stryk\n"
                              "$x^2 - 6x = x(x - 6)$ ← bryt ut $x$\n"
                              "$36 \\cdot 2 = 72$")
    assert "←" not in vy[0]["svar"] and "stryk" not in vy[0]["svar"]
    assert vy[0]["steg"][0] == {"rad": "\\(x^2 - 6x = x(x - 6)\\)",
                                "not": "bryt ut \\(x\\)"}
    assert vy[0]["steg"][1]["not"] == ""
    _exam, doc = _blad({"text": "Förenkla.",
                        "losning": "$\\dfrac{x}{4}$\n$x^2 - 6x = x(x - 6)$ ← bryt ut $x$\n"
                                   "$36 \\cdot 2 = 72$"})
    tex = exam_latex.render_arbetsblad(doc)
    facit = tex[tex.index("\\delprovband{Facit}"):]
    assert "\\facitsteg{\\(x^2 - 6x = x(x - 6)\\)}{bryt ut \\(x\\)}" in facit
    assert "\\noindent \\(36 \\cdot 2 = 72\\)\\par" in facit
    assert "\\newcommand{\\facitsteg}" in tex
    # Skärmen: samma rad och not.
    js = (UI / "blad-bygg.js").read_text(encoding="utf-8")
    assert "lofacitnot" in js and "elevradDelar(s)" in js
    css = (UI / "losning.css").read_text(encoding="utf-8")
    assert ".lobedsteg[data-not]" in css
    # Prompten.
    assert "FACIT FÖR ELEVERNA" in exam_gen.BLAD_FACIT
    assert "högst SEX ord" in exam_gen.BLAD_FACIT


# ─────────────────────────── stammen i ett stycke ───────────────────────────


def test_stammen_pa_bladet_i_ett_stycke():
    _exam, doc = _blad({
        "text": "Utan räknare. Ella ska bowla.\nPriset i kr ges av "
                "$P = 40 + 55n$.\n\nHur mycket kostar en serie?",
        "losning": "55"})
    vy = exam_latex._build_view(doc)
    u = vy["delar"][0]["uppgifter"][0]
    assert [s["text"] for s in u["stycken_blad"]] == [
        "Utan räknare. Ella ska bowla. Priset i kr ges av \\(P = 40 + 55n\\). "
        "Hur mycket kostar en serie?"]
    tex = exam_latex.render_arbetsblad(doc)
    assert "Ella ska bowla. Priset i kr" in tex


def test_en_rad_med_a_parentes_borjar_ett_nytt_stycke():
    assert exam_latex._ihop(
        ["Ella ska bowla.", "a) Hur mycket?", "b) Hon betalar 205 kr.",
         "Hur många?"], False) == [
        "Ella ska bowla.", "a) Hur mycket?", "b) Hon betalar 205 kr. Hur många?"]
    js = (UI / "blad-bygg.js").read_text(encoding="utf-8")
    assert "const DELRAD = /^[a-h]\\)\\s/;" in js
    # Bara arbetsbladet flödar; gruppuppgiftens text står rad för rad.
    assert "const flod = t => (typ === 'Arbetsblad' ? ihop(t) : t);" in js


# ───────────────────────── provets nya vakter ─────────────────────────


def test_bladet_far_provets_nya_vakter():
    exam, _doc = _blad(
        {"text": "Lös ekvationen $2x = 10$.", "typ": "problem",
         "losning": "$x = 5$",
         "bedomning": "+1 E korrekt svar med godtagbar motivering"},
        {"text": "Bestäm den högsta farten. Avrunda svaret till ett heltal.",
         "typ": "problem", "losning": "33", "bedomning": "+1 E korrekt svar"},
        {"text": "Beräkna $3 \\cdot 4$.", "losning": "12",
         "bedomning": "+1 E beräknar och visar 12"})
    koder = sorted(f["code"] for f in exam_gen.bladets_npvakter(exam))
    assert koder == ["avrundning", "doltkrav", "endastsvar"]
    for k in ("doltkrav", "avrundning", "endastsvar"):
        assert k in exam_gen.OVNINGSKODER
    alla = {f["code"] for f in exam_gen.ovningsvakter(exam, prov=None)}
    assert {"doltkrav", "avrundning", "endastsvar"} <= alla
