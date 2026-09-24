"""Lärarens dom 2026-09-24 över exam 131 (BA26B, Ma 1a, MATTETEST 1 7/10),
som kod.

  2  Bilden stod mellan frågan och svarslinjen.
  3  Frågan och svarslinjen hamnade överst på nästa sida, och språket var för
     avancerat («räknas som förorenad över», «Bestäm gränsen i procent»).
     Sedan «I 1 kg»: bokstaven och siffran går inte att skilja åt.
  4  Uttrycket i a) stod centrerat under en tom etikettrad, och b) fick ingen
     svarslinje: a) var endast svar, b) redovisning.
  6  «Hugo ska tvätta en altan» och en kvinna på bilden.
  7  För svår för E, sedan delad med «1 mm på 1 m²» som förvirrade: a) takets
     area, b) litrarna, båda på takets egna mått.
  8  «Butik B säljer bara hela rullar» läses som att uppgiften inte går.
     Sedan: rullen och priset i en mening, «kostnaden per meter», och
     radtaket blir pappret (80 tecken).
  9  Sandkornen i 40 säckar: ingen räknar så i verkligheten.
  10 Tabellen stod under bilden, efter frågan. Och «Firma B tar samma pris
     per dag» var sant om firma A också.
"""
from pathlib import Path

from app import exam_gen, exam_latex


def test_deluppgiftens_uttryck_star_direkt_efter_etiketten():
    st = exam_latex._stycken("$3 + 4{,}5 \\cdot 100 - 2 \\cdot (8 - 5)$",
                             luft=True, forst_i_raden=True)
    assert [s["formel"] for s in st] == [False]
    assert st[0]["text"].startswith("\\(3 + 4")
    # Ett uttryck efter en textrad står kvar som displayformel.
    st = exam_latex._stycken("Förenkla.\n$2(x + 1)$", forst_i_raden=True)
    assert [s["formel"] for s in st] == [False, True]
    # Uppgiftens egen text rörs inte: där är formeln förlagans.
    assert exam_latex._stycken("$2(x + 1)$")[0]["formel"] is True


def test_varje_uppgift_begar_sin_hojd():
    mall = Path("app/templates/prov.tex.j2").read_text(encoding="utf-8")
    assert "\\pfbehov{((( u.behov_mm )))mm}" in mall
    assert "\\pfbehov{92mm}" not in mall
    kort = {"stycken": exam_latex._stycken(
        "Jord.\nOlja.\n\nHur många procent?", luft=True),
        "endast_svar": True}
    mm = exam_latex._behov_mm(kort)
    assert 35 <= mm <= 50, mm
    med_bild = dict(kort, bild_fil="egen-03.png")
    assert exam_latex._behov_mm(med_bild) - mm == exam_latex._MM_BILD
    delad = {"stycken": exam_latex._stycken("Beräkna."), "endast_svar": False,
             "deluppgifter": [kort, kort, kort, kort, kort, kort, kort]}
    assert exam_latex._behov_mm(delad) == exam_latex.BEHOV_TAK_MM


def _u(typer, typ="redovisning"):
    return {"typ": typ, "text": "Beräkna.",
            "deluppgifter": [{"typ": t, "text": "$1 + 1$"} for t in typer]}


def test_blandat_krav_falls():
    fel = exam_gen.blandat_krav_vakt({"uppgifter": [
        _u(["rutin", "redovisning"]), _u(["rutin", "rutin"], "rutin"),
        _u(["redovisning", "resonemang"]), {"typ": "rutin", "text": "x"}]})
    assert [f["code"] for f in fel] == ["blandatkrav"]
    assert "Uppgift 1 blandar endast svar (a) med redovisning (b)" in \
        fel[0]["message"]
    # Deluppgiften utan egen typ ärver uppgiftens.
    u = _u(["", "redovisning"], "rutin")
    assert exam_gen.blandat_krav_vakt({"uppgifter": [u]})
    # NP:s form, a) endast svar och b) «Motivera …», står kvar (129:11).
    np = _u(["rutin", "redovisning"])
    np["deluppgifter"][1]["text"] = "Motivera ditt svar med $1 + 1$."
    assert exam_gen.blandat_krav_vakt({"uppgifter": [np]}) == []
    # Uttrycket först och egen text efter är deluppgiftens egen fråga
    # (exam 129 uppgift 12, godkänt av läraren).
    tecken = _u(["rutin", "redovisning"])
    tecken["deluppgifter"][0]["text"] = "$x = 5$\nSkriv det tecken som passar."
    tecken["deluppgifter"][1]["text"] = "$x > 3$\nSkriv rätt tecken."
    assert exam_gen.blandat_krav_vakt({"uppgifter": [tecken]}) == []
    # Samma uppmaning med sitt eget uttryck (exam 130:s form) är samma sort.
    los = _u(["rutin", "redovisning"])
    for d, ekv in zip(los["deluppgifter"], ("$x^2 = 4$\nSvara exakt.",
                                            "$5x^2 = 30x$")):
        d["text"] = "Lös ekvationen: " + ekv
    assert exam_gen.blandat_krav_vakt({"uppgifter": [los]})


def test_delsidan_sager_bara_delens_hjalpmedel():
    """Del B:s sida bar hela provets mening om del A. «Då borde det ju bara
    stå Hjälpmedel: Räknare och formelblad. Punkt slut.»"""
    h131 = ("Del B utan räknare, formelbladet är tillåtet. Del C med räknare "
            "och formelblad.")
    assert exam_latex._hjalpmedel_i_delen(h131, "C") == \
        "Räknare och formelblad."
    assert exam_latex._hjalpmedel_i_delen(h131, "B") == "Formelblad."
    h126 = "Formelblad på hela provet, räknare bara på del C."
    assert exam_latex._hjalpmedel_i_delen(h126, "C") == \
        "Räknare och formelblad."
    h130 = "Formelblad på hela provet, digitala verktyg bara på del C."
    assert exam_latex._hjalpmedel_i_delen(h130, "C") == \
        "Digitala verktyg och formelblad."
    # Tiger regeln om delen står hela meningen kvar.
    assert exam_latex._hjalpmedel_i_delen("Formelblad.", "C") is None
    # IndA prov 1: «Del 1 görs utan hjälpmedel, del 2 med miniräknare.»
    inda = "Del B utan hjälpmedel. Del C med miniräknare."
    assert exam_latex._digitala_i_delen(inda, "B") is False
    assert exam_latex._hjalpmedel_i_delen(inda, "C") == "Räknare."
    assert exam_latex._hjalpmedel_i_delen(inda, "B") == "Inga."


def test_tabellen_star_dar_den_namns():
    """Uppgift 10: tabellen stod under bilden, efter frågan."""
    st = exam_latex._stycken(
        "Tabellen nedan visar vad det kostar att hyra en minigrävare.\n"
        "Firma B tar samma pris per dag.\n\n"
        "Från hur många dagar är firma A billigast?", luft=True)
    fore, efter = exam_latex._dela_vid_tabellen(st, True)
    assert len(fore) == 1 and fore[0]["par_efter"] is True
    assert efter[-1]["text"].startswith("Från hur många")
    # Nämns tabellen inte står den före frågan.
    st = exam_latex._stycken("Priserna gäller två firmor.\n\nVilken?",
                             luft=True)
    fore, efter = exam_latex._dela_vid_tabellen(st, True)
    assert [s["text"] for s in efter] == ["Vilken?"]
    # Utan tabell rörs ingenting.
    assert exam_latex._dela_vid_tabellen(st, False) == (st, [])
    mall = Path("app/templates/prov.tex.j2").read_text(encoding="utf-8")
    i = mall.index("former.stycken(u.stycken_fore)")
    assert i < mall.index("former.tabellbok(u.tabell)") < mall.index(
        "former.stycken(u.stycken_efter)") < mall.index("u.bild_fil")


def test_fragan_star_ovanfor_svarslinjen():
    """Uppgift 2: bilden stod mellan frågan och «Svar: ____»."""
    st = exam_latex._stycken("En regel är 2 m lång.\nHugo kapar bort 1 m.\n\n"
                             "Hur lång är regeln nu?", luft=True)
    fore, efter, fraga = exam_latex._dela_uppgiften(st, False)
    assert [s["text"] for s in fraga] == ["Hur lång är regeln nu?"]
    assert len(fore) == 2 and fore[-1]["par_efter"] is True and efter == []
    # Utan tom rad finns ingen fråga att skilja ut.
    st = exam_latex._stycken("Beräkna $2 + 2$.", luft=True)
    assert exam_latex._dela_uppgiften(st, False)[2] == []
    mall = Path("app/templates/prov.tex.j2").read_text(encoding="utf-8")
    fore_bild = mall.index("u.bild_fil and u.bild_fore_fragan")
    assert mall.index("former.stycken(u.stycken_efter)") < fore_bild < \
        mall.index("former.stycken(u.stycken_fraga)") < \
        mall.index("u.bild_fil and not u.bild_fore_fragan")


def test_tecken_som_gar_att_forvaxla():
    """Uppgift 3: «I 1 kg jord …»."""
    def prov(text):
        return {"uppgifter": [{"text": text}]}
    assert [f["code"] for f in exam_gen.forvaxlingsvakt(prov(
        "I 1 kg jord från en byggtomt finns $2\\,000$ mg olja."))] == \
        ["forvaxling"]
    assert exam_gen.forvaxlingsvakt(prov("Hon häller i 1 l vatten."))
    assert exam_gen.forvaxlingsvakt(prov("I $1$ kg jord finns olja."))
    for ok in ("Varje kilogram jord innehåller 2 000 mg olja.",
               "I 12 kg jord finns olja.", "I 1,5 kg jord finns olja.",
               "Hon häller i 1 liter vatten."):
        assert exam_gen.forvaxlingsvakt(prov(ok)) == [], ok


def test_exponentbraket_och_stegtabellens_luft():
    """Exam 126 uppgift 1 («$64^{\\frac{1}{3}}$» såg ut som 64 · 1/3) och
    uppgift 10 (stegtabellens bråk slog i linjerna), samma dag."""
    assert exam_latex.escape_mixed("Ange värdet av $64^{\\frac{1}{3}}$.") \
        == "Ange värdet av \\(64^{1/3}\\)."
    assert exam_latex._exponentbrak("a^\\dfrac{2}{3} + \\frac{1}{2}") == \
        "a^{2/3} + \\frac{1}{2}"
    st = exam_latex._stycken("$x^{\\frac{1}{2}} = 3$")
    assert st[0]["formel"] and st[0]["text"] == "x^{1/2} = 3"

    class Steg:
        def __init__(self, celler):
            self.celler = celler

    class Tabell:
        kolumner = ["Majas lösning"]
        forsta_fel = 1
        def __init__(self, rader):
            self.steg = [Steg([r]) for r in rader]

    brak = exam_latex._stegtabell_vy(Tabell(["$\\dfrac{x}{4} = 2$", "$x = 8$"]),
                                     facit=False)
    assert brak["stracka"] == "2.1"
    assert exam_latex._stegtabell_vy(Tabell(["$x = 8$"]),
                                     facit=False)["stracka"] == "1.3"
    mall = Path("app/templates/_former.tex.j2").read_text(encoding="utf-8")
    assert "\\renewcommand{\\arraystretch}{((( s.stracka )))}" in mall


def test_kravraden_galler_hela_uppgiften():
    """Exam 129 uppgift 11: «Fullständig lösning krävs.» och «Svar: ____»
    under a). Lösblad betyder ingen svarsrad, inte heller på en deluppgift."""
    from tests.test_exam import _exam
    from app import exam_spec
    exam = _exam()
    u = exam["uppgifter"][0]
    u.update(typ="redovisning", poang=[0, 0, 0], losning="", bedomning="",
             deluppgifter=[
                 {"poang": [1, 0, 0], "typ": "rutin", "text": "$1 + 1$",
                  "losning": "2", "bedomning": "+1 E rätt"},
                 {"poang": [1, 0, 0], "typ": "redovisning",
                  "text": "Visa att $2 > 1$.", "losning": "x",
                  "bedomning": "+1 E rätt"}])
    doc, fel = exam_spec.validate_exam_json(exam)
    assert doc is not None, fel
    vy = exam_latex._build_view(doc)
    it = next(x for d in vy["delar"] for x in d["uppgifter"]
              if x["har_deluppgifter"])
    assert it["svar_pa_pappret"] is False
    mall = Path("app/templates/prov.tex.j2").read_text(encoding="utf-8")
    assert "((* elif d.endast_svar and u.svar_pa_pappret *))" in mall
    assert "((* elif d.svarsfalt_rad and u.svar_pa_pappret *))" in mall


def _scenuppgift(text, scene):
    return {"uppgifter": [{"text": text, "scen": {"scene": scene}}]}


def test_personen_i_texten_ar_personen_pa_bilden():
    """Uppgift 6: «Hugo ska tvätta en altan.» och en kvinna på bilden."""
    hugo = "Hugo ska tvätta en altan.\nHan blandar altantvätt med vatten."
    figur = ("SCENE. A wooden deck. A small faceless figure in work clothes "
             "kneels at the far right.\nIntended use: det man blandar.")
    fel = exam_gen.personvakt(_scenuppgift(hugo, figur))
    assert [f["code"] for f in fel] == ["person"]
    assert "«a young man»" in fel[0]["message"]
    kvinna = figur.replace("A small faceless figure", "A young woman")
    assert exam_gen.personvakt(_scenuppgift(hugo, kvinna))
    alva = hugo.replace("Hugo", "Alva").replace("Han", "Hon")
    assert exam_gen.personvakt(_scenuppgift(alva, kvinna)) == []
    # Ingen människa i scenen, eller inget namn i texten: inget att fälla.
    assert exam_gen.personvakt(_scenuppgift(
        hugo, "SCENE. A wooden deck with a bucket.")) == []
    assert exam_gen.personvakt(_scenuppgift(
        "En altan ska tvättas.", figur)) == []


def test_domarna_star_i_instruktionen():
    r = exam_gen.INSTRUCTION
    assert "PERSONEN I TEXTEN ÄR PERSONEN PÅ BILDEN" in r
    # Exam 130 uppgift 7, samma dag: grusgången var en smal ram på bilden.
    assert "BILDEN SÄGER INTE EMOT TEXTEN" in r
    assert "SPRÅKET ÄR ELEVERNAS" in r
    assert "«räknas som förorenad över»" in r
    assert "Deluppgifter med samma uppmaning («Beräkna …», «Lös ekvationen" in r
    assert "«I butik B måste man köpa en hel rulle med 50 m kabel, som" in r
    assert "«Tabellen nedan visar …», och pappret" in r
    assert "UPPGIFTEN ÄR NÅGOT ELEVEN HAR NYTTA AV" in r
    assert "Frågan får inte se besvarad ut av texten ovanför" in r
    assert "Inga tecken som går att förväxla" in r
    assert "räknar varje deluppgift på uppgiftens egna tal" in r
    assert "Villkoret som frågan gäller står i frågan" in r
    assert "«kostnaden per meter är mindre där», aldrig «metern kostar" in r
    assert "en hel rulle med 50 m kabel, som kostar 620 kr.»" in r
    assert "högst 80 tecken" in r
    assert "«Hos firma B betalar man bara ett pris per dag.», aldrig" in r
