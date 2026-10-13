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
import json
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
    assert "\\facitsvar{225~kr}" in facit or "\\facitsvar{225 kr}" in facit
    assert "\\noindent \\(P = 45 + 180\\)\\par" in facit
    assert "\\facitsvar{a)\\enspace \\(\\pmb{x = 4}\\)}" in facit
    assert "\\facitsvar{b)\\enspace \\(\\pmb{x = 2}\\)}" in facit
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
    assert ".lobed[data-facit]>tbody{display:grid" in css
    # Svaret i en ruta (Rickard 2026-10-13), på skärmen och i LaTeX.
    assert "lofacitsvar" in js and ".lofacitsvar{" in css
    assert "\\facitsvar{" in facit and "\\newcommand{\\facitsvar}" in tex
    # Prompten.
    assert "FACIT FÖR ELEVERNA" in exam_gen.BLAD_FACIT
    assert "högst FYRA ord" in exam_gen.BLAD_FACIT


# ─────────────────── facitpasset (Rickard 2026-10-13) ───────────────────

GAMLA = ["$x = -2$",
         "Multiplicera alla termer med 12: $4(2x + 1) = 3x + 12$",
         "$2x + 10 = 3x + 12$ ger $x = -2$",
         "$10A = 480$ ← $A$ är hela takets area i m$^2$"]


def test_bladfacit_fynd_ser_langa_forklaringar_och_tva_steg():
    fynd = exam_gen.bladfacit_fynd("\n".join(GAMLA))
    assert any("två steg" in f for f in fynd)
    assert any("fler än 4 ord" in f for f in fynd)
    assert exam_gen.bladfacit_fynd("$x = 6$\n$3x = 18$ ← dela med 3") == []
    # Konkret, inte allmänt (Rickard 2026-10-13).
    assert any("inget tal" in f for f in exam_gen.bladfacit_fynd("$x = 6$\n$3x = 18$ ← flytta över"))
    assert not exam_gen.vag_not("stryk tvåorna") and exam_gen.vag_not("förkorta")


def test_bladfacit_haller_svaret_och_matten_orort():
    nya = ["$x = -2$",
           "$4(2x + 1) = 3x + 12$ ← gånger 12",
           "$2x + 10 = 3x + 12$",
           "$x = -2$ ← dra bort $2x$",
           "$10A = 480$ ← $A$ = takets area"]
    assert exam_gen.bladfacit_haller(GAMLA, nya)
    # Svaret ändrat.
    assert not exam_gen.bladfacit_haller(GAMLA, ["$x = -2,0$"] + nya[1:])
    # Ett räknesteg borta.
    assert not exam_gen.bladfacit_haller(GAMLA, nya[:2] + nya[3:])
    # Ny matte.
    assert not exam_gen.bladfacit_haller(GAMLA, nya + ["$x + 2 = 0$"])
    # För lång förklaring.
    assert not exam_gen.bladfacit_haller(
        GAMLA, nya[:4] + ["$10A = 480$ ← $A$ är hela takets area"])


def test_bladfacit_saknad_svarsrad_far_en_som_samlar_delsvaren():
    # TE26A E-bladet dok 272, 13/10: rutan visade första delsvaret som svaret.
    gamla = ["$4^{3} = 64$ ← $4 \\cdot 4 \\cdot 4 = 64$",
             "$\\sqrt[3]{125} = 5$ ← kolla $5 \\cdot 5 \\cdot 5 = 125$"]
    assert exam_gen.saknar_svarsrad(gamla)
    assert any("svarsraden saknas" in f for f in exam_gen.bladfacit_fynd("\n".join(gamla)))
    assert exam_gen.bladfacit_haller(gamla, ["$4^{3} = 64$, $\\sqrt[3]{125} = 5$"] + gamla)
    # Ny matte i svarsraden, en pil på den, eller ett delsvar borta.
    assert not exam_gen.bladfacit_haller(gamla, ["$4^{3} = 65$, $\\sqrt[3]{125} = 5$"] + gamla)
    assert not exam_gen.bladfacit_haller(gamla, ["$4^{3} = 64$ ← räkna"] + gamla)
    assert not exam_gen.bladfacit_haller(gamla, ["$4^{3} = 64$"] + gamla[:1])
    # Kedjans början och slut får stå i svarsraden.
    kedja = ["$100^{1/2} = \\sqrt{100} = 10$ ← halv är roten",
             "$a^{3} \\cdot a^{4} = a^{3 + 4} = a^{7}$"]
    assert exam_gen.bladfacit_haller(
        kedja, ["$100^{1/2} = 10$, $a^{3} \\cdot a^{4} = a^{7}$"] + kedja)
    # Numrerade delsvar.
    delsvar = ["1: Nej. $\\sqrt{9 + 16} = \\sqrt{25} = 5$",
               "2: Ja. $\\sqrt{4 \\cdot 25} = \\sqrt{100} = 10$"]
    assert exam_gen.saknar_svarsrad(delsvar)
    assert exam_gen.bladfacit_haller(delsvar, ["1: Nej, 2: Ja"] + delsvar)
    # Ett vanligt facit och en figurrad först saknar inte svarsrad.
    assert not exam_gen.saknar_svarsrad(GAMLA)
    assert not exam_gen.saknar_svarsrad(["[tallinje start 3 hopp -9] ← minus åt vänster", "$-6$"])
    prompt = exam_gen.build_bladfacit_prompt({}, [("1", {"losning": "\n".join(gamla)})])
    assert '"saknar_svarsrad": true' in prompt
    # «Rad 1: …», «Rad 2: …» (BA26B A-bladet dok 271).
    rad = ["Rad 1: $10^{9}$", "Rad 2: $2^{16}$", "Rad 3: $2^{15}$"]
    assert exam_gen.saknar_svarsrad(rad)
    assert exam_gen.bladfacit_haller(rad, ["Rad 1: $10^{9}$, Rad 2: $2^{16}$, Rad 3: $2^{15}$"] + rad)


def test_bladfacit_hinder_sager_varfor_och_omtaget_far_veta():
    # NA26F 311/312, 13/10: omtaget fick bara fynden och upprepade felet.
    assert "ny matte $t\\vec{v}$" in exam_gen.bladfacit_hinder(
        ["$5$", "$7 - t = 3t$ ger $t = 2$"],
        ["$5$", "$7 - t = 3t$ ← lägg till $t\\vec{v}$", "$t = 2$"])
    assert exam_gen.bladfacit_hinder(
        ["$5$", "$7 - t = 3t$ ger $t = 2$"],
        ["$5$", "$7 - t = 3t$ ← lägg till t·v", "$t = 2$"]) == ""
    prompter = []

    def llm(_m, prompt, **_k):
        prompter.append(prompt)
        return json.dumps({"facit": [{"id": "1", "rader": [
            "$5$", "$7 - t = 3t$ ← lägg till $t\\vec{v}$", "$t = 2$"]}]})
    exam = {"uppgifter": [{"text": "Lös.", "losning": "$5$\n$7 - t = 3t$ ger $t = 2$"}]}
    assert exam_gen.bladfacitpass(exam, model="m", llm=llm) == 0
    assert len(prompter) == 2 and "förra omskrivningen nekades: ny matte" in prompter[1]


def test_bladfacitpass_skriver_bara_det_som_haller():
    exam = {"uppgifter": [
        {"text": "Lös.", "losning": "\n".join(GAMLA)},
        {"text": "Lös.", "losning": "$x = 6$\n$3x = 18$ ← dela båda sidor med tre nu"}]}
    svar = {"facit": [
        {"id": "1", "rader": ["$x = -2$", "$4(2x + 1) = 3x + 12$ ← gånger 12",
                              "$2x + 10 = 3x + 12$", "$x = -2$",
                              "$10A = 480$ ← $A$ = takets area"]},
        {"id": "2", "rader": ["$x = 5$", "$3x = 18$ ← dela med 3"]}]}
    n = exam_gen.bladfacitpass(exam, model="m",
                               llm=lambda *a, **k: json.dumps(svar))
    assert n == 1
    assert exam["uppgifter"][0]["losning"].startswith("$x = -2$\n$4(2x + 1)")
    # Svaret ändrat: uppgift 2 står kvar som den var.
    assert exam["uppgifter"][1]["losning"].endswith("med tre nu")


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
