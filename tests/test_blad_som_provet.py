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
    facit = tex[tex.index("\\bfseries Facit"):]
    assert "\\facitsvar{225~kr}" in facit or "\\facitsvar{225 kr}" in facit
    assert "\\noindent \\(P = 45 + 180\\)\\par" in facit
    assert "\\facitsvar{a)\\enspace \\(\\pmb{x = 4}\\)}" in facit
    assert "\\facitsvar{b)\\enspace \\(\\pmb{x = 2}\\)}" in facit
    # En linje mellan uppgifterna, ingen över den första.
    assert facit.count("\\bedlinje") == 1
    # Mallen tål en äldre vy utan fältet (servern har Python i minnet).
    text = (MALLAR / "arbetsblad.tex.j2").read_text(encoding="utf-8")
    assert "u.facit is defined" in text and "d.facit is defined" in text


def test_skarmens_facit_ar_speglingen():
    js = (UI / "blad-bygg.js").read_text(encoding="utf-8")
    assert "function bladfacit(" in js and "function facitGrupper(" in js
    assert "if (v.typ === 'Arbetsblad' || v.typ === 'Gruppuppgift') return bladfacit(v, uppgifter);" in js
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
    facit = tex[tex.index("\\bfseries Facit"):]
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
    # En likhet utan $…$ är ett ord, som med (NA26F 312, 13/10).
    assert exam_gen._notord("sätt in x = 3") == 3 == exam_gen._notord("sätt in $x = 3$")
    assert exam_gen.bladfacit_fynd("$x = 6$\n$2x = 12$ ← sätt in x = 6") == []


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


def test_bladfacit_ny_svarsrad_nar_forsta_raden_inte_svarar():
    # BA26B dok 333 uppg 1, TE26A dok 325 12b (13/10): halva svaret i rutan.
    gamla = ["900 kr är priset för varje timme han gräver.",
             "1 500 kr är en fast avgift, samma oavsett antal timmar."]
    ny = ["900 kr är timpriset och 1 500 kr den fasta avgiften."] + gamla
    assert exam_gen.bladfacit_hinder(gamla, ny).startswith("svaret")
    assert exam_gen.bladfacit_hinder(gamla, ny, True) == ""
    # Ett gammalt steg får inte försvinna, inte heller med ny svarsrad.
    steg = ["Bara gränsen kan vara gemensam.", "$a + 3 = 1$ ger $a = -2$"]
    assert "försvann" in exam_gen.bladfacit_hinder(steg, ["Bara $a = -2$ fungerar.", steg[0]], True)

    def llm(_m, _p, **_k):
        return json.dumps({"facit": [{"id": "1", "rader": ny, "ny_svarsrad": True}]})
    exam = {"uppgifter": [{"text": "Vad betyder talen?", "losning": "\n".join(gamla)}]}
    assert exam_gen.bladfacitpass(exam, model="m", llm=llm) == 1
    assert exam["uppgifter"][0]["losning"].startswith("900 kr är timpriset")


def test_bladfacit_stryker_rader_som_upprepar_delsvaren():
    # Rickard 13/10: «sluta upprepa delsvaren under rutan» (271/1, 268/4).
    svar = "Rad 1: $10^{9}$, Rad 2: $2^{16}$, Rad 3: $2^{15}$"
    gamla = [svar, "Rad 1: $10^{9}$", "Rad 2: $2^{16}$ ← $2^{10} \\cdot 2^{6}$",
             "Rad 3: $2^{15}$"]
    fynd = exam_gen.bladfacit_fynd("\n".join(gamla))
    assert sum("upprepar ett delsvar" in f for f in fynd) == 2
    # Raderna utan pil får strykas, raden med pil står kvar.
    assert exam_gen.bladfacit_hinder(gamla, gamla[:1] + gamla[2:3]) == ""
    assert "försvann" in exam_gen.bladfacit_hinder(gamla, gamla[:2] + gamla[3:])
    # En rad med räkning utöver delsvaret upprepar inte.
    assert exam_gen.bladfacit_fynd("$x = 5$, $y = 2$\n$2x = 10$\n$x = 5$ ← dela med 2") == []
    # En räknerad som är ett stegs resultat står kvar (NA26F 312/10).
    assert exam_gen.bladfacit_fynd(
        "Noah har fel: $f(x) = x$ och $f(x) = -x + 4$\n$k > 0$: $f(0) = 0$\n$f(x) = x$") == []
    assert "försvann" in exam_gen.bladfacit_hinder(
        ["$f(x) = x$, $g = 2$", "$k > 0$: $f(0) = 0$", "$f(x) = x$"],
        ["$f(x) = x$, $g = 2$", "$k > 0$: $f(0) = 0$"])


def test_svar_i_fall_delas_inte_vid_punkten():
    # TE26A A-bladet dok 275, 13/10: rutan visade bara första fallet.
    rad = "$0 < a < 1$: $\\sqrt{a}$ är större. $a = 1$: lika. $a > 1$: $a$ är större."
    assert exam_latex._dela_svaret(rad) == (rad, "")
    assert exam_latex._dela_svaret("Nej, Leo har fel. Papperet är tunt.") == (
        "Nej, Leo har fel", "Papperet är tunt.")


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


def test_en_etikett_med_formel_star_pa_egen_rad():
    """Exam 266 uppg 2: «Fjäder A: $y = 3x + 10$» flöt ihop med nästa fjäder."""
    assert exam_latex._ihop(
        ["Tre fjädrar töjs.", "Fjäder A: $y = 3x + 10$",
         "Fjäder B: $y = 4x + 10$", "Linjen L har ekvationen: $y = 3x - 4$.",
         "Bestäm k."], False) == [
        "Tre fjädrar töjs.", "Fjäder A: $y = 3x + 10$",
        "Fjäder B: $y = 4x + 10$",
        "Linjen L har ekvationen: $y = 3x - 4$. Bestäm k."]
    js = (UI / "blad-bygg.js").read_text(encoding="utf-8")
    assert "EKVRAD.test(r) || ETIKETTRAD.test(r)" in js
    # Tabellhuvudet är matematik som cellerna (exam 266 visade «$K$»).
    assert "`<th>${mat(r)}</th>`" in js


# ───────────────── bladet i provets LaTeX-mall (2026-10-22) ─────────────────
# Rickard 2026-10-22: bladen ska se ut som provet, utan försättsblad och
# poäng och med facit.


def test_bladet_satts_i_provets_mall_utan_forsattsblad_och_poang():
    _exam, doc = _blad({"text": "Beräkna $3 + 4$.", "losning": "$7$"},
                       {"text": "Visa att $2 + 2 = 4$.", "typ": "redovisning",
                        "poang": [0, 2, 0], "losning": "$4$"})
    tex = exam_latex.render_arbetsblad(doc)
    kropp = tex.split(r"\begin{document}", 1)[1]
    assert r"\documentclass[12pt, a4paper, addpoints]{exam}" in tex
    assert r"\question \pfkrav{Skriv bara svaret.}" in kropp
    assert r"\question \pfkrav{Visa hur du räknar.}" in kropp
    assert r"\question[" not in kropp and "Provtid" not in kropp
    assert "Betyg" not in kropp and r"\textbf{Namn:}" not in kropp
    # Svarsraden under kortsvaret, ingen under redovisningen (lösblad).
    assert kropp.count(r"\svarsrad{Svar:}") == 1
    assert r"\bfseries Facit" in kropp


def test_raknarbeskedet_blir_provets_delrubrik():
    _exam, doc = _blad(
        {"text": "Utan räknare. Beräkna $3 + 4$.", "losning": "$7$"},
        {"text": "Utan räknare. Beräkna $5 + 4$.", "losning": "$9$"},
        {"text": "Räknare tillåten. Beräkna $3{,}7 \\cdot 4{,}1$.",
         "losning": "$15{,}17$"})
    tex = exam_latex.render_arbetsblad(doc)
    assert "Del A: Räknare är inte tillåten" in tex
    assert "Del B: Räknare är tillåten" in tex
    assert "Utan räknare." not in tex and "Räknare tillåten." not in tex
    # Numreringen löper vidare över delarna, som på provet.
    assert r"\setcounter{question}{2}" in tex
    # En enda grupp får rubriken utan delnamn.
    _exam, doc = _blad({"text": "Utan räknare. Beräkna $3 + 4$.",
                        "losning": "$7$"})
    tex = exam_latex.render_arbetsblad(doc)
    assert "{\\Large\\bfseries Räknare är inte tillåten" in tex
    assert "Del A" not in tex


def test_raknarbeskedet_star_kvar_nar_ordningen_inte_ar_provets():
    """Med räknare före utan hade numreringen på pappret blivit en annan än
    på skärmen och i facit."""
    _exam, doc = _blad(
        {"text": "Räknare tillåten. Beräkna $3{,}7 \\cdot 4{,}1$.",
         "losning": "$15{,}17$"},
        {"text": "Utan räknare. Beräkna $3 + 4$.", "losning": "$7$"})
    tex = exam_latex.render_arbetsblad(doc)
    assert "Del A" not in tex
    # Beskedet står i kursivraden under numret, inte i uppgiftstexten.
    assert r"\pfkrav{Räknare tillåten. Skriv bara svaret.}" in tex
    assert r"\pfkrav{Utan räknare. Skriv bara svaret.}" in tex
    assert "Räknare tillåten. Beräkna" not in tex


def test_nya_blad_ordnas_utan_raknare_forst():
    """Vid genereringen (exam_gen.ordna_raknardelar): stegringen står kvar
    inom varje grupp, och räknarraden räknas om efter den nya ordningen."""
    prov = {"uppgifter": [
        {"del": "B", "typ": "rutin", "poang": [1, 0, 0], "text": "a"},
        {"del": "C", "typ": "rutin", "poang": [1, 0, 0], "text": "b"}]}
    exam = {"hjalpmedel": "", "uppgifter": [
        {"text": "u1", "drillar": 1}, {"text": "u2", "drillar": 2},
        {"text": "u3", "drillar": 1}, {"text": "u4", "drillar": 2}]}
    assert exam_gen.ordna_raknardelar(exam, prov)
    assert [u["text"] for u in exam["uppgifter"]] == ["u1", "u3", "u2", "u4"]
    assert not exam_gen.ordna_raknardelar(exam, prov)
    assert exam_gen.satt_raknarrad_ur_provet(exam, prov)
    assert exam["hjalpmedel"] == ("Räknare får användas på uppgift 3 och 4, "
                                  "men inte på uppgift 1 och 2.")


def test_bladmallen_tal_en_aldre_vy():
    """Servern läser mallen från disk men har Python i minnet: mallen ska
    sättas med vyn som den byggdes före 2026-10-22, utan delrubrikerna."""
    _exam, doc = _blad({"text": "Utan räknare. Beräkna $3 + 4$.",
                        "losning": "$7$"})
    tex = exam_latex._environment().get_template("arbetsblad.tex.j2").render(
        visa_poang=False, dokumentkod="", only_facit=False, utan_facit=False,
        med_facitfigur=False, **exam_latex._build_view(doc, None))
    assert r"\begin{questions}" in tex and "Utan räknare." in tex


def test_bladet_far_provets_kravradsvakt_och_deluppgiftsvakt():
    exam, _doc = _blad(
        {"text": "Utan räknare. Beräkna $3 + 4$. Motivera ditt svar.",
         "losning": "$7$"},
        {"text": "En skola.", "typ": "problem", "poang": [0, 0, 0],
         "bedomning": "", "losning": "",
         "deluppgifter": [{"poang": [1, 0, 0], "bedomning": "+1 E",
                           "losning": "$4$", "text": " ".join(["ord"] * 31)
                           + " Beräkna antalet."}]})
    koder = {f["code"] for f in exam_gen.ovningsvakter(exam)}
    assert "kravrad" in koder
    assert any(f["code"] == "begriplighet" and "1b" not in f["path"]
               and "2a" in f["path"] for f in exam_gen.ovningsvakter(exam))


def test_bladet_ritar_inga_tips():
    """Rickard 2026-10-22: «Ta bort tipsen». Mallen ritar ingen notis, så att
    äldre blad med en ledtråd byggs utan den, och genereringen tömmer
    fältet (exam_gen.stryk_tips)."""
    exam, doc = _blad({"text": "Utan räknare. Beräkna $3 + 4$.",
                       "losning": "$7$", "notis": "Tips: Räkna på fingrarna."})
    assert "fingrarna" not in exam_latex.render_arbetsblad(doc)
    assert exam_gen.stryk_tips(exam, "arbetsblad")
    assert exam["uppgifter"][0]["notis"] is None


def _kortsvar(text, **extra):
    return dict({"typ": "rutin", "poang": [1, 0, 0], "formaga": "P",
                 "text": text, "losning": "$1$", "bedomning": "+1 E"}, **extra)


def test_lika_kortsvar_samlas_som_provet():
    """Rickard 2026-10-22: «Samla som provet». Kaspers blad (exam 277) hade
    «Förenkla uttrycket: …» som uppgift 1 och 2; provet 268 skriver
    «Lös ekvationerna.» och bara ekvationen i a), b) och c)."""
    exam = {"hjalpmedel": "Räknare får användas på uppgift 4, men inte på "
                          "uppgift 1, 2 och 3.", "uppgifter": [
        _kortsvar("Utan räknare. Förenkla uttrycket: $(x + 3)^2 - x(x + 2)$.",
                  drillar=1, innehall=["A"]),
        _kortsvar("Förenkla uttrycket: $(x - 5)^2 - x(x - 4)$.",
                  drillar=4, innehall=["A", "B"], poang=[2, 0, 0]),
        _kortsvar("Faktorisera uttrycket: $x^2 - 49$."),
        _kortsvar("Förenkla uttrycket: $3x + 2x$.")]}
    assert exam_gen.samla_kortsvar(exam)
    forsta = exam["uppgifter"][0]
    assert forsta["text"] == "Förenkla uttrycken så långt som möjligt."
    assert forsta["poang"] == [0, 0, 0] and forsta["drillar"] == 1
    assert forsta["innehall"] == ["A", "B"]
    assert [d["text"] for d in forsta["deluppgifter"]] == [
        "$(x + 3)^2 - x(x + 2)$", "$(x - 5)^2 - x(x - 4)$"]
    assert forsta["deluppgifter"][1]["poang"] == [2, 0, 0]
    # Faktorisera bryter raden, och uppgift 4 har ett annat räknarbesked.
    assert len(exam["uppgifter"]) == 3
    assert exam["hjalpmedel"] == ("Räknare får användas på uppgift 3, men "
                                  "inte på uppgift 1 och 2.")
    doc, fel = exam_spec.validate_exam_json(
        dict(exam, titel="t", kurs="Matematik, nivå 2a", klass="IndA"),
        "arbetsblad")
    assert doc is not None, fel
    tex = exam_latex.render_arbetsblad(doc)
    assert "Förenkla uttrycken så långt som möjligt." in tex
    assert not exam_gen.samla_kortsvar(exam)


def test_kortsvar_med_en_tillagd_mening_samlas_och_meningen_hamnar_i_stammen():
    """Theos blad (exam 285, jobb 2170, 2026-10-22): uppgift 1 hade en mening
    efter uttrycket och uppgift 2 inget kolon, och de stod kvar var för sig.
    Anvisningen gäller alla deluppgifter och står i stammen i plural."""
    exam = {"hjalpmedel": "Räknare får användas på uppgift 3, men inte på "
                          "uppgift 1 och 2.", "uppgifter": [
        _kortsvar("Utan räknare. Förenkla uttrycket $(x + 3)^2 - x(x + 4)$.\n"
                  "Skriv svaret utan parenteser.", poang=[2, 0, 0]),
        _kortsvar("Utan räknare. Förenkla uttrycket $(x - 5)^2 - x(x - 7)$."),
        _kortsvar("Räknare tillåten. Beräkna $3,4^2$.")]}
    assert exam_gen.samla_kortsvar(exam)
    forsta = exam["uppgifter"][0]
    assert forsta["text"] == ("Förenkla uttrycken så långt som möjligt. "
                              "Skriv svaren utan parenteser.")
    assert [d["text"] for d in forsta["deluppgifter"]] == [
        "$(x + 3)^2 - x(x + 4)$", "$(x - 5)^2 - x(x - 7)$"]
    assert [d["poang"] for d in forsta["deluppgifter"]] == [[2, 0, 0], [1, 0, 0]]
    assert len(exam["uppgifter"]) == 2
    assert exam["hjalpmedel"] == ("Räknare får användas på uppgift 2, men "
                                  "inte på uppgift 1.")
    # Samma anvisning på båda står en gång.
    tva = {"hjalpmedel": "", "uppgifter": [
        _kortsvar("Lös ekvationen: $x^2 = 7$. Svara exakt."),
        _kortsvar("Lös ekvationen $x^2 + 6 = 17$.\nSvara exakt.")]}
    assert exam_gen.samla_kortsvar(tva)
    assert tva["uppgifter"][0]["text"] == "Lös ekvationerna. Svara exakt."
    # En mening med tal eller formel är en annan uppgift och hindrar.
    for extra in ("Sätt in $x = 2$.", "Avrunda till 2 decimaler.",
                  "Vad blir svaret om x är negativt?"):
        hinder = {"hjalpmedel": "", "uppgifter": [
            _kortsvar("Förenkla uttrycket: $(x + 1)^2$. " + extra),
            _kortsvar("Förenkla uttrycket: $(x + 2)^2$.")]}
        assert not exam_gen.samla_kortsvar(hinder), extra


def test_kortsvar_med_bild_eller_annan_typ_samlas_inte():
    exam = {"hjalpmedel": "", "uppgifter": [
        _kortsvar("Lös ekvationen: $x^2 = 9$."),
        _kortsvar("Lös ekvationen: $x^2 = 16$.", scen={"begrepp": "x"}),
        _kortsvar("Lös ekvationen: $x^2 = 25$.", typ="redovisning"),
        _kortsvar("Lös ekvationen: $x^2 = 36$.")]}
    assert not exam_gen.samla_kortsvar(exam)


def test_bladets_prompt_har_provets_formuleringsregler():
    """Rickard 2026-10-22 om blad 277: «Har du använt provgeneratorn som mall
    då eller?» E-stegen och provets sätt att ge storheter står i bladets
    prompt, inte i provets."""
    blad = exam_gen.build_prompt("Ma2b", "SA23", [], profil="arbetsblad")
    prov = exam_gen.build_prompt("Ma2b", "SA23", [], profil="prov")
    assert exam_gen.BLAD_SOM_PROVET in blad
    assert exam_gen.BLAD_SOM_PROVET not in prov
    assert "E-STEGEN ÄR TYDLIGA" in blad


def test_nivan_star_i_bladets_rubrik():
    """«Jag vet inte vilken nivå det är» (Rickard 2026-10-22): ett blad med
    bara E-poäng heter «Arbetsblad på E-nivå», ett blandat blad får ingen."""
    _exam, doc = _blad({"text": "Beräkna $3 + 4$.", "losning": "$7$"})
    assert "Arbetsblad på E-nivå" in exam_latex.render_arbetsblad(doc)
    _exam, doc = _blad({"text": "Beräkna $3 + 4$.", "losning": "$7$"},
                       {"text": "Beräkna $5 + 4$.", "losning": "$9$",
                        "poang": [0, 1, 0], "bedomning": "+1 C"})
    tex = exam_latex.render_arbetsblad(doc)
    assert "Arbetsblad \\textperiodcentered{}" in tex and "-nivå" not in tex


def test_platen_star_pa_bladet_som_pa_provet():
    """Kaspers blad 277 (2026-10-22): «det finns ju ingen bilder». Lärarens
    bild och plåten (egna_bilder, nycklade på numret) sätts som på provet."""
    _exam, doc = _blad({"text": "Ett fönster. Beräkna $3 + 4$.",
                        "losning": "$7$"})
    tex = exam_latex.render_arbetsblad(doc, egna_bilder={1: "egen-01.png"})
    assert r"\includegraphics[width=0.7\textwidth]{egen-01.png}" in tex


def test_bladet_visar_inget_raknat_exempel():
    """Rickard 2026-10-22, «Ta bort tipsen»: elevläsarens lagning skrev in
    metoden färdigräknad på IndA:s E-blad (exam 287, 290, 292, 293). En
    svarsmall, en lösning att granska, ett påstående med exempel och givna
    data står kvar."""
    def fynd(t):
        exam = {"titel": "t", "kurs": "Matematik, nivå 2a", "uppgifter": [
            {"text": t, "typ": "rutin", "poang": [1, 0, 0], "losning": "x"}]}
        return [f["code"] for f in exam_gen.raknat_exempelvakt(exam)]
    for t in (
        "Skriv uttrycket som två parenteser gånger varandra: $x^2 - 16$.\n"
        "Gör på samma sätt som i exemplet:\n$x^2 - 9 = (x + 3)(x - 3)$",
        "Skriv uttrycket $x^2 - 36$ som två parenteser gånger varandra.\n"
        "Så här ser det ut för ett annat uttryck: $x^2 - 25 = (x + 5)(x - 5)$.",
        "Faktorisera uttrycket med konjugatregeln: $x^2 - 64$.\nDet är samma "
        "form som när du skriver $x^2 + 3x = x(x + 3)$.",
        "Bryt ut så mycket som möjligt ur uttrycket: $14x^2 - 21x$.\nSvaret "
        "ska vara ett tal och $x$ gånger en parentes, så här:\n"
        "$10x^2 + 15x = 5x(2x + 3)$",
        "Exempel: $4x + 8 = 4(x + 2)$\nBryt ut så mycket som möjligt: $6x + 9$.",
    ):
        assert fynd(t) == ["raknat_exempel"], t
    for t in (
        "Skriv $x^2 - 81$ som två parenteser gånger varandra.\n"
        "$x^2 - 81 = (\\ldots)(\\ldots)$",
        "Nora löser ekvationen $3x^2 = 12x$ så här:\n$\\frac{3x^2}{x} = "
        "\\frac{12x}{x}$\n$x = 4$\nAvgör med en beräkning om Nora har rätt.",
        "Han påstår att svaret alltid är delbart med 4.\nExempel: $7 \\cdot 9 "
        "+ 1 = 64 = 16 \\cdot 4$\nUndersök om han har rätt.",
        "Lösningarna till ekvationen kan skrivas så här: $x = 2{,}5 \\pm "
        "\\sqrt{4{,}25}$\nBestäm talet $q$.",
        "Till exempel är $\\vec{a} = (3,\\ 6)$ parallell med $\\vec{w}$.",
    ):
        assert fynd(t) == [], t
