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

import re
from pathlib import Path

import pytest

from app import exam_gen, exam_latex, exam_pdf, exam_spec

UI = Path(__file__).resolve().parent.parent / "app" / "web" / "ui"


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
    # EN elevlösning är giltig sedan 2026-08-23: en enpoängsuppgift har exakt
    # ett lägre poängsteg. Noll är det som inte är det — då utelämnas fältet.
    ({"elevlosningar": []}, "ett tomt elevlösningsfält"),
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
    for falt in ("tabell", "svarsrutor", "stegtabell", "elevlosningar", "enhet",
                 "svarsfalt", "nyckelfraga"):
        assert falt in text, f"{falt} nås inte av grammatiken"


def test_ifyllnadsraderna_finns_pa_bade_uppgift_och_deluppgift():
    """Förlagans rader hör till den fråga som ska besvaras — och när gruppens
    uppgift är delad i a/b är det deluppgiften som ställer frågan."""
    doc = _doc(_uppgift(svarsfalt=["Ekvation", "Svar i ord"]),
               {"del": None, "formaga": "PL", "typ": "problem",
                "poang": [0, 0, 0], "text": "En sten släpps från en bro.",
                "losning": "", "bedomning": "", "deluppgifter": [
                    {"poang": [2, 0, 0], "text": "Lös algebraiskt.",
                     "losning": "3,0 s", "bedomning": "+2 E",
                     "svarsfalt": ["Ekvation"]},
                    {"poang": [0, 2, 0], "text": "Lös grafiskt.",
                     "losning": "Skärningen.", "bedomning": "+2 C"}]})
    assert doc.uppgifter[0].svarsfalt == ["Ekvation", "Svar i ord"]
    assert doc.uppgifter[1].deluppgifter[0].svarsfalt == ["Ekvation"]
    assert doc.uppgifter[1].deluppgifter[1].svarsfalt is None
    # Raderna sätts i ALLA elevmallar — en form som finns på flera ställen
    # glider isär på ett av dem. Bedömningen har ingen svarsplats: där står
    # lösningen, precis som den inte får en svarsrad.
    tex = _alla_tex(doc)
    # PROVET sätter raden som förlagans \svarsrad — samma linje som «Svar:»,
    # men namngiven, och flera på samma rad delar bredden lika. Arbetsbladet
    # har kvar sin egen \svarsfaltrad. Samma fält, två papper, två former.
    assert r"\svarsrad{Ekvation:}" in tex["prov"], "provet saknar raden"
    assert r"\svarsfaltrad{Ekvation}" in tex["arbetsblad"], "arbetsbladet saknar raden"
    # (Makrot självt står i den delade preamblen — det är ANROPET som räknas,
    # precis som för \svarsradmed.)
    assert r"\svarsfaltrad{Ekvation}" not in tex["bedomning"]
    assert r"\svarsrad{Ekvation:}" not in tex["bedomning"]
    # Uppgift 2 är ett PROBLEM och redovisas på lösblad. På provet får den
    # därför ingen svarsrad alls, inte ens en namngiven — kravet avgör
    # (lärarens dom 2026-08-22). Arbetsbladet har inte den regeln och sätter
    # sin egen rad som förut; det är två papper med två former.
    assert tex["prov"].count(r"\svarsrad{Ekvation:}") == 1, \
        "deluppgiften i redovisningsuppgiften fick en svarsrad på provet"
    assert tex["arbetsblad"].count(r"\svarsfaltrad{Ekvation}") == 2


def test_ifyllnadsraden_star_efter_fragan_inte_fore():
    """Svarsplatsen kommer efter frågan. Lägger modellen fälten på FÖRÄLDERN
    till en uppgift med deluppgifter — vilket den gjorde i den första skarpa
    inspelningen — hamnade «Valt värde på c:» före den deluppgift som ber om
    värdet, och deluppgiften fick en tom skrivyta i stället."""
    # Typen är «rutin»: svarsplatsen hör till kravet «Endast svar krävs»
    # (lärarens dom 2026-08-22 — se test_forlaga_matt
    # .test_ingen_svarsrad_pa_redovisningsuppgift), och det testet här mäter är
    # VAR raden hamnar, inte vilken uppgift som får ha en.
    doc = _doc({"del": None, "formaga": "PL", "typ": "rutin",
                "poang": [0, 0, 0], "text": "En spelfigurs bana.",
                "losning": "", "bedomning": "",
                "svarsfalt": ["Valt värde", "Motivering"],
                "deluppgifter": [
                    {"poang": [2, 0, 0], "text": "Enas om ett värde.",
                     "losning": "c > 4", "bedomning": "+2 E"},
                    {"poang": [0, 2, 0], "text": "Motivera valet.",
                     "losning": "…", "bedomning": "+2 C"}]})
    tex = _alla_tex(doc)
    # Facit har lösningen och därmed ingen svarsplats. Provet och arbetsbladet
    # sätter raden i var sin form — provet som förlagans \svarsrad, bladet som
    # sin egen \svarsfaltrad — men BÅDA efter frågan.
    assert tex["prov"].index("Enas om ett värde") \
        < tex["prov"].index(r"\svarsrad{Valt värde:}"), \
        "provet sätter svarsplatsen före frågan"
    assert tex["arbetsblad"].index("Enas om ett värde") \
        < tex["arbetsblad"].index(r"\svarsfaltrad{Valt"), \
        "arbetsbladet sätter svarsplatsen före frågan"


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
        assert "Derivatan är fel" not in tex[namn], \
            f"{namn} bär elevlösningarna — de är lärarens"
        assert "\\textbf{\\svarsruteval" not in tex[namn], \
            f"{namn} markerar det rätta krysset"
    assert "Första felet står i steg 2" in tex["bedomning"]
    # Elevlösningarna står som rader i bedömningstabellen: etiketten är
    # poängsteget («0 p»), och kommentaren är skälet.
    assert r"\bedrad{0 p}" in tex["bedomning"]
    assert "Derivatan är fel" in tex["bedomning"]
    assert "\\textbf{\\svarsruteval" in tex["bedomning"]


ELEVER_ORD = [
    {"etikett": "Elevlösning A",
     "partier": [{"rader": ["$600 / 25 = 24$",
                            "Tanken är tom efter 24 minuter."],
                  "poang": [0, 0, 0], "dom": "Påfyllningen används inte."}]},
    {"etikett": "Elevlösning B",
     "partier": [{"rader": ["$y = 600 + (p - 25)x$",
                            "Nettoflödet är $p - 25$ liter per minut."],
                  "poang": [0, 1, 0], "dom": "Korrekt modell."}]},
]


def test_en_elevlosning_som_borjar_med_ord_klistras_inte_fast_i_par():
    """Lärarens skarpa 1a-prov föll här: raderna radas upp med \\par emellan,
    och nästa rad började med en bokstav — «\\parTanken», ett odefinierat
    kommando, och HELA bedömningsanvisningen kompilerade inte. Provet fick sin
    PDF, anvisningen ingen. Samma fel var redan fixat i gruppuppgift.tex.j2;
    det syntes inte här för att elevlösningarnas rader nästan alltid börjar med
    matematik, och \\( avslutar \\par på egen hand."""
    doc = _doc(_uppgift(poang=[0, 1, 1], typ="resonemang", formaga="R",
                        elevlosningar=ELEVER_ORD))
    tex = exam_latex.render_bedomning(doc)
    assert "\\parTanken" not in tex
    # Bara elevraderna: preamblen har \parindent och \parskip, som är egna
    # kommandon och inte ett \par med ett ord fastklistrat. Raderna ligger
    # mellan \bedskilj och nästa \bedskilj (bedomning.tex.j2, elevrad).
    partier = re.findall(r"\\bedskilj(.*?)(?=\\bedskilj|\\end\{uppgift\})",
                         tex, re.S)
    assert partier
    for p in partier:
        assert re.search(r"\\par[A-Za-zÅÄÖåäö]", p) is None, \
            "\\par klistrat mot ett ord — kommandonamnet blir odefinierat"


@pytest.mark.tectonic
def test_bedomningen_med_ordrader_kompilerar(tmp_path):
    doc = _doc(_uppgift(poang=[0, 1, 1], typ="resonemang", formaga="R",
                        elevlosningar=ELEVER_ORD))
    pdf, logg = exam_pdf.compile_pdf(exam_latex.render_bedomning(doc),
                                     tmp_path, "bedomning")
    assert pdf is not None, f"bedömningen föll:\n{logg[-800:]}"


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


# ══════════════════════════ skärmen och papperet ═════════════════════════

def _melvin():
    """Lärarens gruppuppgift 2026-08-26, uppgift 2: en stam med en mättabell,
    och en deluppgift som ber gruppen granska en FÄRDIG uträkning. Uträkningen
    ligger där den frågas om — på deluppgiften."""
    return {"del": None, "formaga": "B", "typ": "redovisning",
            "poang": [0, 0, 0], "losning": "", "bedomning": "",
            "text": "Tabellen visar morgontemperaturen fyra dagar i rad.",
            "tabell": {"rubriker": ["Morgon", "Temperatur"],
                       "rader": [["1", "$-6$"], ["2", "$-2$"]]},
            "deluppgifter": [
                {"poang": [1, 0, 0], "text": "Beräkna skillnaden.",
                 "losning": "$4$", "bedomning": "+1 E", "enhet": "°C"},
                {"poang": [0, 1, 0],
                 "text": "Melvin har beräknat medeltemperaturen. Markera den "
                         "första rad som är fel.",
                 "losning": "Rad 2.", "bedomning": "+1 C",
                 "svarsfalt": ["Första felaktiga raden", "Rätt värde"],
                 "stegtabell": {"kolumner": ["Melvins lösning"],
                                "steg": [{"celler": ["$\\dfrac{-6+(-2)}{2}$"]},
                                         {"celler": ["$= \\dfrac{-6+2}{2}$"]},
                                         {"celler": ["$= -2$"]}],
                                "forsta_fel": 1}}]}


def test_deluppgiftens_stegtabell_star_pa_alla_papper():
    """Uppgiften ska gå att räkna på. Frågar b) om «den första rad som är fel»
    måste raderna stå på samma papper som frågan."""
    doc = _doc(_melvin(), profil="gruppuppgift",
               grupp={"elever": 3, "langd_min": 45,
                      "redovisning": "skriftligt"})
    for namn, tex in (("gruppuppgift", exam_latex.render_gruppuppgift(doc)),
                      ("arbetsblad", exam_latex.render_arbetsblad(doc)),
                      ("prov", exam_latex.render_prov(doc))):
        assert "Melvins lösning" in tex, f"{namn} tappade stegtabellens rubrik"
        assert "-6+2" in tex.replace(" ", ""), f"{namn} tappade Melvins rader"
        # Facit stannar hos läraren: vilket steg som är fel står inte här.
        assert "Första felet står i steg" not in tex, f"{namn} röjde facit"


def test_skarmen_ritar_deluppgiftens_egna_former():
    """SKÄRMEN OCH PAPPRET SÄGER SAMMA SAK. _former.tex.j2 kallar sig «samma
    former som på skärmarket», och mallarna sätter dem på VARJE deluppgift
    (former.kropp(d)) — men skärmen ritade bara `d.text`.

    Det fällde lärarens gruppuppgift 2026-08-26: uppgift 2 b) bad gruppen
    markera den första felaktiga raden i Melvins lösning, och stegtabellen med
    Melvins rader låg på deluppgiften. Förhandsvisningen visade en fråga om en
    uträkning som inte fanns på pappret, uppgiften gick inte att räkna på — och
    ingen omskrivning kunde laga det, för i dokumentets JSON var den komplett."""
    plan = (UI / "plan.js").read_text(encoding="utf-8")
    js = (UI / "blad-bygg.js").read_text(encoding="utf-8")
    css = (UI / "prov.css").read_text(encoding="utf-8")
    # Formerna måste FÖLJA MED från dokumentets JSON, annars finns inget att rita.
    for falt in ("ut.deltabell", "ut.delsteg", "ut.delrutor", "ut.delalt",
                 "ut.delnotis", "ut.delfalt"):
        assert falt in plan, f"{falt} når aldrig arket"
    # …men facit får aldrig följa med. Deluppgiftens stegtabell plockas isär
    # kolumn för kolumn och steg för steg, precis som förälderns — `forsta_fel`
    # och `ratt` kopieras aldrig, och därmed når de aldrig elevens ark.
    assert "steg: (d.stegtabell.steg || []).map(s => ({ celler: s.celler }))" in plan
    assert "ut.delalt = delar.map(d => d.alternativ || null)" in plan
    # Renderarna ritar dem — både gruppuppgiftens kort och provets deluppgift.
    assert "delform" in js and "u.delsteg" in js and "u.deltabell" in js
    assert "u.delfalt" in js, "deluppgiftens namngivna rader ritas inte"
    # Provets deluppgiftsrad är ett rutnät med tre spalter, och varje nytt barn
    # tar nästa ruta — formerna måste spänna textspalten som figuren gör.
    assert ".prdel[data-avdelad]>li>.prdelform" in css
    # Formnyckeln räknar deluppgifternas former också: ett blad vars enda
    # stegtabell sitter på en deluppgift bär ändå tre former och behöver gu6.
    assert "'stegtabell', 'delsteg'" in js
    # STAMMENS former står FÖRE deluppgifterna, på båda papperen. Tabellen är
    # datat a) och b) räknar på, och skärmen lade den under de frågor som
    # använde den — mallarna sätter den före (\begin{deluppgift}, \begin{parts}).
    assert "${alt}${former}${del}" in js
    assert js.count("${alt}${former}${del}") == 3, \
        "något papper sätter fortfarande stammens former efter deluppgifterna"


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
            assert "Derivatan" in text
            assert "steg 2" in text
        else:
            # Enheten står på svarsraden — och svarsraden finns bara här.
            assert "laddpunkter" in text, f"{namn}: enheten saknas"
            assert "Elevlösning" not in text, f"{namn} tryckte lärarens papper"
