"""Anteckningarna — stilen, sidan, prompten, mallen och rutterna.

Det som prövas här är i första hand SPRÅKET, och det är ovanligt: de andra
dokumenttyperna valideras på struktur (balans, poäng, schema) medan
anteckningarnas krav är att de går att läsa i en blick. Tankstrecken, längden
och rubrikerna mäts därför i kod (app/notes_gen.py), och sviten håller de
mätningarna mot det som faktiskt kommer ut ur mallen.

Radbudgeten är den känsligaste av dem: den är kalibrerad mot en kompilerad PDF
och inte gissad, så testet som binder den till mallen (test_sidbudgeten_*)
kompilerar på riktigt. Ändras marginalen, radavståndet eller \\anrubrik faller
det testet — och då ska talen i notes_gen mätas om, inte skruvas.
"""
from __future__ import annotations

import copy
import json

import pytest

from app import exam_latex, exam_pdf, notes_gen
from app.web import routes_anteckningar


# ── Ett giltigt papper att utgå från ────────────────────────────────────────

def _anteckningar() -> dict:
    return {
        "titel": "Första lektionen: kursupplägg",
        "datum": "2026-08-18",
        "klass": "NA25",
        "sektioner": [
            {"rubrik": "Boken",
             "stycken": ["Vi arbetar i Matematik 5000+ 3c. Alla får ett eget "
                         "exemplar idag och skriver numret på insidan."]},
            {"rubrik": "Så räknar vi",
             "stycken": ["Du räknar i din egen takt. Jag går runt och hjälper."],
             "punkter": ["Blå uppgifter först", "Röda när du känner dig säker"]},
            {"rubrik": "Prov och rättning",
             "stycken": ["Första provet ligger i vecka 42. Du får veta "
                         "resultatet inom en vecka."]},
        ],
        "kom_ihag": ["Ta med boken på fredag"],
    }


def _utan_fel(doc: dict) -> None:
    _d, fel = notes_gen.validate_notes_json(doc)
    assert fel == [], fel


# ── Stilkontraktet ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("tecken", ["–", "—"])
def test_tankstreck_falls(tecken):
    """Lärarens uttryckliga krav: inga tankstreck. Prompten kan BE om det;
    bara en kontroll kan garantera det."""
    doc = _anteckningar()
    doc["sektioner"][0]["stycken"][0] = f"Vi arbetar i boken {tecken} alla får ett exemplar."
    _d, fel = notes_gen.validate_notes_json(doc)
    assert [f["code"] for f in fel] == ["tankstreck"]
    assert "sektion 1.stycke 1" in fel[0]["path"]
    # Beskedet ska säga vad som ska GÖRAS, inte bara vad som är fel.
    assert "utan tankstreck" in fel[0]["message"]


def test_bindestreck_ar_fritt():
    """Ett bindestreck i en sammansättning är ett annat tecken än ett
    tankstreck, och regeln får inte svälja det: «kurs-PM» ska stå kvar."""
    doc = _anteckningar()
    doc["sektioner"][0]["stycken"][0] = "Läs kurs-PM:et och e-postadressen på tavlan."
    _utan_fel(doc)


def test_tankstreck_fangas_var_det_an_star():
    """Titeln, rubriken, punkten och kom ihåg-raden är också text läraren
    läser — regeln gäller hela pappret, inte bara styckena."""
    for vag in (("titel",), ("kom_ihag", 0)):
        doc = _anteckningar()
        if vag[0] == "titel":
            doc["titel"] = "Första lektionen — upplägget"
        else:
            doc["kom_ihag"][0] = "Ta med boken — den behövs"
        _d, fel = notes_gen.validate_notes_json(doc)
        assert [f["code"] for f in fel] == ["tankstreck"], vag
    doc = _anteckningar()
    doc["sektioner"][1]["punkter"][0] = "Blå uppgifter – först"
    _d, fel = notes_gen.validate_notes_json(doc)
    assert [f["code"] for f in fel] == ["tankstreck"]


def test_rubriken_ar_en_vagvisare_inte_en_mening():
    doc = _anteckningar()
    doc["sektioner"][0]["rubrik"] = ("Det här handlar om vilken bok vi ska ha "
                                     "under kursen och varför")
    _d, fel = notes_gen.validate_notes_json(doc)
    assert [f["code"] for f in fel] == ["rubrik"]


def test_sektion_utan_rubrik_falls():
    doc = _anteckningar()
    doc["sektioner"][0]["rubrik"] = "   "
    _d, fel = notes_gen.validate_notes_json(doc)
    assert [f["code"] for f in fel] == ["rubrik"]


def test_sektion_utan_loptext_falls():
    """En sektion som bara är en punktlista är en checklista, inte något att
    tala utifrån. Schemat kräver minst ett stycke; det här håller kravet även
    när stycket finns men är tomt."""
    doc = _anteckningar()
    doc["sektioner"][1]["stycken"] = ["   "]
    _d, fel = notes_gen.validate_notes_json(doc)
    assert "loptext" in [f["code"] for f in fel]


def test_max_en_punktlista_per_sektion_ar_strukturellt():
    """Regeln behöver ingen validator: `punkter` ÄR en lista, inte en lista av
    listor. Två listor i en sektion går alltså inte att uttrycka — och det som
    inte går att uttrycka kan ingen glömma att kontrollera."""
    doc = _anteckningar()
    doc["sektioner"][1]["punkter"] = [["a"], ["b"]]
    _d, fel = notes_gen.validate_notes_json(doc)
    assert [f["code"] for f in fel] == ["schema"] * len(fel) and fel


def test_for_manga_sektioner_falls():
    doc = _anteckningar()
    doc["sektioner"] = doc["sektioner"] * 3            # nio stycken
    _d, fel = notes_gen.validate_notes_json(doc)
    assert "antal" in [f["code"] for f in fel]


def test_for_lang_sektion_falls():
    """En sektion som är en vägg av text är oläsbar även om HELA pappret ryms
    på sidan — därför ett eget tak per sektion, skilt från sidbudgeten."""
    doc = _anteckningar()
    doc["sektioner"][0]["stycken"] = ["Ord. " * 150]      # 750 tecken
    _d, fel = notes_gen.validate_notes_json(doc)
    assert [f["code"] for f in fel] == ["langd"]
    assert notes_gen.rader(notes_gen.NoteDoc.model_validate(doc)) \
        <= notes_gen.RADER_PA_SIDAN, "sidan var inte full — då är det bara sektionstaket som fäller"


def test_kom_ihag_raderna_ska_lasas_i_en_blick():
    doc = _anteckningar()
    doc["kom_ihag"] = ["K" * (notes_gen.KOM_IHAG_TAK + 1)]
    _d, fel = notes_gen.validate_notes_json(doc)
    assert [f["code"] for f in fel] == ["langd"]
    doc = _anteckningar()
    doc["kom_ihag"] = ["Ett", "Två", "Tre", "Fyra"]
    _d, fel = notes_gen.validate_notes_json(doc)
    assert "antal" in [f["code"] for f in fel]


def test_matematik_far_finnas_men_kravs_inte():
    doc = _anteckningar()
    doc["sektioner"][2]["stycken"] = ["Formeln $a^2 + b^2 = c^2$ står på formelbladet."]
    _utan_fel(doc)


# ── Sidan ───────────────────────────────────────────────────────────────────

def test_radbudgeten_raknar_rubriker_och_listor_inte_bara_tecken():
    """Kärnan i varför taket inte är ett teckentak: samma mängd text kostar
    olika mycket sida beroende på hur den är uppdelad."""
    fa = {"titel": "T", "sektioner": [
        {"rubrik": "En", "stycken": ["x" * 900]},
        {"rubrik": "Två", "stycken": ["x" * 900]},
        {"rubrik": "Tre", "stycken": ["x" * 900]}]}
    manga = {"titel": "T", "sektioner": [
        {"rubrik": f"Nr {i}", "stycken": ["x" * 340],
         "punkter": ["Punkt ett", "Punkt två"]} for i in range(6)]}
    assert notes_gen.tecken(notes_gen.NoteDoc.model_validate(manga)) < \
        notes_gen.tecken(notes_gen.NoteDoc.model_validate(fa))
    assert notes_gen.rader(notes_gen.NoteDoc.model_validate(manga)) > \
        notes_gen.rader(notes_gen.NoteDoc.model_validate(fa)), \
        "sex rubriker och sex listor kostar mer sida än tre långa stycken"


def test_ett_papper_som_spiller_over_falls_med_atgard():
    doc = _anteckningar()
    doc["sektioner"] = [{"rubrik": f"Rubrik {i}", "stycken": ["Ord. " * 60],
                         "punkter": ["Punkt ett", "Punkt två"]} for i in range(6)]
    _d, fel = notes_gen.validate_notes_json(doc)
    sidfel = [f for f in fel if f["code"] == "sidan"]
    assert sidfel, fel
    assert "ETT A4" in sidfel[0]["message"]
    assert "ta bort en sektion" in sidfel[0]["message"]


@pytest.mark.tectonic
def test_sidbudgeten_haller_mot_den_riktiga_mallen(tmp_path):
    """Radmodellen är MÄTT mot mallen, inte gissad. Det här testet binder de
    två: ett papper som precis ryms i budgeten ska kompilera till EN sida.

    Faller det har mallen ändrats (marginal, radavstånd, \\anrubrik) och då ska
    konstanterna i notes_gen mätas om — det är hela poängen med att sidtaket
    bor i valideringen och inte i mallen."""
    if not exam_pdf.engine_available():
        pytest.skip("Tectonic saknas")
    # Ett fullt papper: sex sektioner, en punktlista, tre kom ihåg-rader —
    # och precis under radtaket.
    doc = {"titel": "Ett fullt papper som ändå ryms",
           "datum": "2026-08-18", "klass": "NA25",
           "sektioner": [{"rubrik": f"Rubrik nummer {i}",
                          "stycken": ["Det här är en mening som fyller sin "
                                      "sektion med löptext och fortsätter en "
                                      "bit till. " * 2]} for i in range(4)],
           "kom_ihag": ["Ta med boken", "Lämna in blanketten"]}
    doc["sektioner"][1]["punkter"] = ["Blå uppgifter först", "Röda sedan"]
    d, fel = notes_gen.validate_notes_json(doc)
    assert fel == [], fel
    assert d is not None and notes_gen.rader(d) > 30, \
        "testpappret måste ligga NÄRA taket för att bevisa något"
    pdf, logg = exam_pdf.compile_pdf(exam_latex.render_anteckningar(d),
                                     tmp_path, "anteckningar")
    assert pdf is not None, logg
    import pypdfium2 as pdfium
    fil = pdfium.PdfDocument(str(pdf))
    try:
        assert len(fil) == 1, "ett godkänt papper blev två sidor"
    finally:
        fil.close()


@pytest.mark.tectonic
def test_seedens_anteckningar_kompilerar(tmp_path):
    """Sondpappret ska gå igenom den riktiga motorn — det är det som seedar
    cachen med mallens fontmetriker, punktlistan och den tonade rutan."""
    if not exam_pdf.engine_available():
        pytest.skip("Tectonic saknas")
    from tools import seed_tectonic_cache
    tex = exam_latex.render_anteckningar(
        seed_tectonic_cache._representativa_anteckningar())
    pdf, logg = exam_pdf.compile_pdf(tex, tmp_path, "sond-anteckningar")
    assert pdf is not None, logg


def test_seeden_kompilerar_anteckningsmallen():
    """Tom cache är den tysta kraschen: en mall cachen aldrig sett kan inte
    hämtas i efterhand under --only-cached. Att varje render_* har ett jobb i
    seeden vaktas generellt i test_tectonic_seed; här hålls anteckningarna
    fast vid namn, för det var just den nya mallen som riskerade att glömmas."""
    import inspect
    from tools import seed_tectonic_cache
    kalla = inspect.getsource(seed_tectonic_cache.seed)
    assert "exam_latex.render_anteckningar(" in kalla


def test_sondpappret_bar_alla_tre_formerna():
    """Löptext, punktlista och kom ihåg-ruta — alla tre måste kompileras under
    seedningen, annars saknas deras sättning i cachen."""
    from tools import seed_tectonic_cache
    doc = seed_tectonic_cache._representativa_anteckningar()
    assert any(s.punkter for s in doc.sektioner), "ingen punktlista i sonden"
    assert doc.kom_ihag, "ingen kom ihåg-ruta i sonden"
    assert any("$" in p for s in doc.sektioner for p in s.stycken), \
        "ingen matte i sonden — $…$ är tillåtet i fältet och måste seedas"


def test_sondpappret_bryter_inte_mot_sin_egen_stilregel():
    from tools import seed_tectonic_cache
    doc = seed_tectonic_cache._representativa_anteckningar()
    assert notes_gen.validate_notes(doc) == []


# ── Prompten ────────────────────────────────────────────────────────────────

def test_stilkontraktet_star_i_prompten():
    p = notes_gen.build_prompt("Matematik 3c", "NA25", "Första lektionen")
    for krav in ("INGA tankstreck", "Enkelt och tillgängligt språk",
                 "på en sekund", "ETT A4"):
        assert krav in p, krav


def test_exemplet_i_prompten_bryter_inte_mot_regeln():
    """Ett stilexempel som självt bär ett tankstreck lär modellen att regeln
    inte gäller. Regeln SJÄLV måste förstås visa tecknen den förbjuder — det
    är bara JSON-exemplet som ska vara rent, och det är det som prövas."""
    exempel = notes_gen.INSTRUCTION[notes_gen.INSTRUCTION.index('{"titel"'):]
    assert "–" not in exempel and "—" not in exempel
    doc, fel = notes_gen.validate_notes_json(json.loads(exempel.strip()))
    assert doc is not None and [f["code"] for f in fel] == ["antal"], \
        "exemplet ska vara ett giltigt papper så när som på att det är kortat"


def test_lararens_ruta_star_narmast_uppdraget():
    """Källordningen är en rangordning: det läraren själv skrev är uppdraget,
    och det ska inte tappas bakom ett möte eller ett minne."""
    p = notes_gen.build_prompt(
        "Matematik 3c", "NA25", "Första lektionen",
        onskemal="Boken, upplägget och rutinerna",
        transkript=notes_gen.build_transkript([("Möte 1", "vi pratade om boken")]),
        memory="Klassen arbetade med derivator")
    assert p.index("Klassen arbetade") < p.index("vi pratade om boken") \
        < p.index("Boken, upplägget och rutinerna") < p.index("Uppdrag:")


def test_transkriptblocket_sager_vad_texten_ar():
    """Utan den raden skriver modellen ett referat av mötet i stället för
    anteckningar inför lektionen."""
    block = notes_gen.build_transkript([("Kursstart · 2026-08-15", "vi pratade")])
    assert "TRANSKRIBERADE MÖTEN" in block
    assert "Kursstart · 2026-08-15" in block
    assert "Referera inte mötet" in block


def test_tomma_transkript_ger_inget_block():
    assert notes_gen.build_transkript([]) == ""
    assert notes_gen.build_transkript([("Möte", "   ")]) == ""


# ── Loopen ──────────────────────────────────────────────────────────────────

def _svarare(*svar):
    """En stubbad modell som svarar i tur och ordning."""
    kvar = list(svar)

    def llm(_model, _prompt, **_kw):
        return kvar.pop(0) if kvar else json.dumps(_anteckningar(), ensure_ascii=False)
    return llm


def test_ett_tankstreck_kostar_en_reparationsrunda():
    trasigt = _anteckningar()
    trasigt["sektioner"][0]["stycken"][0] = "Boken – den nya upplagan."
    res = notes_gen.generate_notes(
        "Matematik 3c", "NA25", "Första lektionen", model="",
        onskemal="Boken", llm=_svarare(json.dumps(trasigt, ensure_ascii=False),
                                       json.dumps(_anteckningar(), ensure_ascii=False)))
    assert res["errors"] == []
    assert res["rounds"] == 2, "reparationsrundan kördes aldrig"


def test_kvarstaende_fel_redovisas_arligt():
    """Rundorna kan ta slut. Då visas felen för läraren i stället för att
    döljas — samma regel som tavlan och provet följer."""
    trasigt = json.dumps(
        {**_anteckningar(),
         "sektioner": [{"rubrik": "En", "stycken": ["Ett – två."]}] * 3},
        ensure_ascii=False)
    res = notes_gen.generate_notes(
        "Matematik 3c", "NA25", "Moment", model="", onskemal="x",
        llm=_svarare(trasigt, trasigt, trasigt))
    assert res["rounds"] == notes_gen.MAX_ROUNDS
    assert [f["code"] for f in res["errors"]] == ["tankstreck"] * 3


def test_svar_utan_json_ger_ett_arligt_fel():
    res = notes_gen.generate_notes(
        "Matematik 3c", "NA25", "Moment", model="", onskemal="x",
        llm=_svarare("Jag kan tyvärr inte", "inte heller", "nej"))
    assert res["notes"] is None
    assert res["errors"][0]["code"] == "json"


def test_json_i_en_mening_plockas_ut():
    """Modellen ramar gärna in svaret. Objektet ska ändå hittas — samma
    robusthet som exam_gen och lesson_board har."""
    inbaddat = "Här är pappret:\n" + json.dumps(_anteckningar(), ensure_ascii=False) + "\nHoppas det duger!"
    res = notes_gen.generate_notes("Matematik 3c", "NA25", "Moment", model="",
                                   onskemal="x", llm=_svarare(inbaddat))
    assert res["errors"] == [] and res["notes"]["titel"]


def test_pahittade_toppfalt_stads_bort_utan_reparationsrunda():
    """Utan grammatiktvång lägger modellen gärna till fält den tycker hör hemma
    på ett papper. Ett sådant ord ska inte kosta en hel ny generering."""
    med_extra = {**_anteckningar(), "sidfot": "Läraren", "antal_sektioner": 3}
    res = notes_gen.generate_notes(
        "Matematik 3c", "NA25", "Moment", model="", onskemal="x",
        llm=_svarare(json.dumps(med_extra, ensure_ascii=False)))
    assert res["rounds"] == 1 and res["errors"] == []
    assert "sidfot" not in res["notes"]


def test_refine_kor_onskemalet_och_validerar():
    nytt = _anteckningar()
    nytt["sektioner"][2]["stycken"].append("Miniräknaren får användas på del B.")
    res = notes_gen.refine_notes(
        _anteckningar(), "lägg till en rad om miniräknarna", model="",
        llm=_svarare(json.dumps(nytt, ensure_ascii=False)))
    assert res["errors"] == []
    assert "miniräknaren" in json.dumps(res["notes"], ensure_ascii=False).lower()


def test_refine_som_bryter_stilen_repareras():
    trasigt = _anteckningar()
    trasigt["sektioner"][0]["stycken"][0] = "Boken — den nya upplagan."
    res = notes_gen.refine_notes(
        _anteckningar(), "skriv om första stycket", model="",
        llm=_svarare(json.dumps(trasigt, ensure_ascii=False),
                     json.dumps(_anteckningar(), ensure_ascii=False)))
    assert res["errors"] == [] and res["rounds"] == 2


# ── Mallen ──────────────────────────────────────────────────────────────────

def test_mallen_satter_rubriker_stycken_punkter_och_rutan():
    doc, _fel = notes_gen.validate_notes_json(_anteckningar())
    tex = exam_latex.render_anteckningar(doc)
    assert r"\anrubrik{Boken}" in tex
    assert "Vi arbetar i Matematik 5000+ 3c." in tex
    assert r"\begin{itemize}" in tex and "Blå uppgifter först" in tex
    assert r"\komihag{" in tex and "Ta med boken på fredag" in tex
    assert tex.count(r"\anrubrik{") == 3


def test_mallen_escapar_text_men_bevarar_matte():
    doc, _fel = notes_gen.validate_notes_json({
        **_anteckningar(),
        "sektioner": [{"rubrik": "Kostnad & tid",
                       "stycken": ["50 % av tiden. Formeln $a^2+b^2=c^2$ gäller."]},
                      {"rubrik": "Två", "stycken": ["Text."]},
                      {"rubrik": "Tre", "stycken": ["Text."]}]})
    tex = exam_latex.render_anteckningar(doc)
    assert r"Kostnad \& tid" in tex
    assert r"50~\% av tiden" in tex
    assert r"\(a^2+b^2=c^2\)" in tex


def test_mallen_utelamnar_rutan_nar_det_inte_finns_nagot_att_saga():
    doc, _fel = notes_gen.validate_notes_json(
        {k: v for k, v in _anteckningar().items() if k != "kom_ihag"})
    assert r"\komihag{" not in exam_latex.render_anteckningar(doc)


def test_mallen_ar_en_sida_utan_uppgiftsmaskineri():
    """Anteckningarna delar preamble med proven men ska inte dra in deras
    maskineri: ingen graphicx, ingen svarsrad, inga uppgiftsmiljöer."""
    doc, _fel = notes_gen.validate_notes_json(_anteckningar())
    tex = exam_latex.render_anteckningar(doc)
    assert r"\usepackage{graphicx}" not in tex
    assert r"\newcommand{\svarsrad}" not in tex
    assert r"\begin{uppgift}" not in tex
    assert r"\newpage" not in tex, "ett stödpapper har EN sida"


# ── Rutterna ────────────────────────────────────────────────────────────────

def _events(resp):
    return [json.loads(rad[len("data:"):])
            for rad in resp.text.splitlines() if rad.startswith("data:")]


def _done(resp):
    klara = [e for e in _events(resp) if e["type"] == "done"]
    assert klara, _events(resp)
    return klara[0]["result"]


@pytest.fixture
def client(llm_ready):
    return llm_ready


def _stubba(monkeypatch, notes=None, errors=None):
    """Stubba generatorn — rutten prövas, inte modellen."""
    anrop = []

    def fake(kurs, klass, moment, *, model, onskemal="", transkript="",
             memory="", datum="", llm=None, max_rounds=3, log_cb=None,
             token_cb=None):
        anrop.append({"kurs": kurs, "klass": klass, "moment": moment,
                      "onskemal": onskemal, "transkript": transkript,
                      "memory": memory, "datum": datum})
        if log_cb:
            log_cb("Skriver anteckningarna …")
        return {"notes": copy.deepcopy(notes or _anteckningar()),
                "errors": errors or [], "rounds": 1}
    monkeypatch.setattr(routes_anteckningar.notes_gen, "generate_notes", fake)
    return anrop


def test_generate_kraver_en_kalla(client):
    r = client.post("/api/anteckningar/generate", json={"kurs": "Matematik 3c"})
    assert r.status_code == 400
    assert "eller välj ett möte" in r.json()["error"]


def test_generate_skriver_och_sparar(client, monkeypatch):
    anrop = _stubba(monkeypatch)
    r = client.post("/api/anteckningar/generate", json={
        "kurs": "Matematik 3c", "klass": "NA25", "moment": "Första lektionen",
        "datum": "2026-08-18", "onskemal": "Boken och rutinerna"})
    res = _done(r)
    assert res["id"] and res["errors"] == []
    assert res["anteckningar"]["titel"]
    # Radbudgeten följer med ut: förhandsvisningen ska kunna säga hur full
    # sidan är innan läraren godkänner.
    assert 0 < res["rader"] <= res["radtak"]
    assert anrop[0]["onskemal"] == "Boken och rutinerna"
    assert anrop[0]["moment"] == "Första lektionen"


def test_pappret_hamnar_i_samma_hog_som_proven(client, monkeypatch):
    """Anteckningarna lagras i exams-tabellen med typ='anteckningar'. Det är
    inte kosmetiskt: versionering, artefakter och tryckpaketets exam-gren
    hänger på det."""
    _stubba(monkeypatch)
    r = client.post("/api/anteckningar/generate",
                    json={"onskemal": "x", "kurs": "Matematik 3c"})
    res = _done(r)
    lista = client.get("/api/exams").json()["exams"]
    rad = next(e for e in lista if e["id"] == res["id"])
    assert rad["typ"] == "anteckningar"
    assert rad["titel"] == res["anteckningar"]["titel"]


def test_refine_ger_en_ny_version(client, monkeypatch):
    _stubba(monkeypatch)
    res = _done(client.post("/api/anteckningar/generate",
                            json={"onskemal": "x", "kurs": "Matematik 3c"}))
    nytt = _anteckningar()
    nytt["sektioner"][0]["stycken"][0] = "Vi arbetar i den nya upplagan."
    monkeypatch.setattr(
        routes_anteckningar.notes_gen, "refine_notes",
        lambda notes, message, **kw: {"notes": nytt, "errors": [], "rounds": 1})
    r = client.post(f"/api/anteckningar/{res['id']}/refine",
                    json={"message": "byt till nya upplagan"})
    ny = _done(r)
    assert len(ny["versions"]) == 2
    assert "nya upplagan" in ny["anteckningar"]["sektioner"][0]["stycken"][0]


def test_refine_kraver_ett_onskemal(client, monkeypatch):
    _stubba(monkeypatch)
    res = _done(client.post("/api/anteckningar/generate",
                            json={"onskemal": "x", "kurs": "Matematik 3c"}))
    r = client.post(f"/api/anteckningar/{res['id']}/refine", json={"message": "  "})
    assert r.status_code == 400


def test_approve_bygger_pdf_och_lasar_versionen(client, monkeypatch):
    _stubba(monkeypatch)
    res = _done(client.post("/api/anteckningar/generate",
                            json={"onskemal": "x", "kurs": "Matematik 3c",
                                  "datum": "2026-08-18"}))
    monkeypatch.setattr(exam_pdf, "engine_available", lambda: True)
    byggda = {}

    def fejk_kompilera(tex, ut_dir, jobname, **kw):
        sokvag = ut_dir / f"{jobname}.pdf"
        sokvag.write_bytes(b"%PDF-1.4\n")
        byggda["tex"] = tex
        return sokvag, ""
    monkeypatch.setattr(exam_pdf, "compile_pdf", fejk_kompilera)
    r = client.post(f"/api/anteckningar/{res['id']}/approve", json={})
    d = _done(r)
    assert d["status"] == "godkänt"
    assert d["pdf"] and d["tex"] and d["errors"] == []
    assert r"\anrubrik{Boken}" in byggda["tex"]
    # Samma artefaktrutt som proven — tryckpaketet hämtar PDF:en därifrån.
    assert client.get(f"/api/exams/{res['id']}/pdf").status_code == 200


def test_approve_utan_pdfmotor_sparar_tex_och_sager_det(client, monkeypatch):
    _stubba(monkeypatch)
    res = _done(client.post("/api/anteckningar/generate",
                            json={"onskemal": "x", "kurs": "Matematik 3c"}))
    monkeypatch.setattr(exam_pdf, "engine_available", lambda: False)
    r = client.post(f"/api/anteckningar/{res['id']}/approve", json={})
    d = _done(r)
    assert d["pdf"] is None and d["tex"]
    assert d["status"] == "godkänt"
    assert any("PDF-motorn saknas" in e.get("msg", "")
               for e in _events(r) if e["type"] == "log")


def test_kompileringsfel_pekar_pa_chatten(client, monkeypatch):
    """Det finns ingen LaTeX-fixloop här. Då ska beskedet säga vad läraren kan
    göra i stället — inte lämna henne med en engelsk logg."""
    _stubba(monkeypatch)
    res = _done(client.post("/api/anteckningar/generate",
                            json={"onskemal": "x", "kurs": "Matematik 3c"}))
    monkeypatch.setattr(exam_pdf, "engine_available", lambda: True)
    monkeypatch.setattr(exam_pdf, "compile_pdf",
                        lambda *a, **kw: (None, "! Undefined control sequence."))
    d = _done(client.post(f"/api/anteckningar/{res['id']}/approve", json={}))
    assert d["pdf"] is None and d["tex"]
    fel = [e for e in d["errors"] if e["code"] == "kompilering"]
    assert fel and "chatten" in fel[0]["message"]


def test_okant_papper_ger_404(client):
    assert client.post("/api/anteckningar/9999/refine",
                       json={"message": "x"}).status_code == 404
    assert client.post("/api/anteckningar/9999/approve",
                       json={}).status_code == 404


# ── Transkriptdörren ────────────────────────────────────────────────────────

def _lektion(client, namn, text, datum="2026-08-15"):
    from app import db as appdb
    conn = appdb.connect(client.base_dir / "transkribera.db")
    try:
        rad = appdb.create_lesson(conn, history_id=namn, name=namn, datum=datum,
                                  transcript_text=text)
    finally:
        conn.close()
    return rad["id"]


def test_bara_moten_som_faktiskt_har_text_gar_att_valja(client):
    """En väljare som listar tomma möten är en fälla: läraren väljer tre, får
    ett papper byggt på ett, och märker det aldrig."""
    med = _lektion(client, "Kursstart", "vi pratade om boken")
    _lektion(client, "Tom inspelning", "")
    lista = client.get("/api/anteckningar/transkript").json()["transkript"]
    assert [t["id"] for t in lista] == [med]
    assert lista[0]["tecken"] == len("vi pratade om boken")
    assert lista[0]["refereras"] is False


def test_langa_moten_markeras_som_refererade(client):
    _lektion(client, "Långt möte", "x" * (routes_anteckningar.RAKTEXT_TAK + 1))
    lista = client.get("/api/anteckningar/transkript").json()["transkript"]
    assert lista[0]["refereras"] is True


def test_kort_mote_gar_in_ordagrant(client, monkeypatch):
    anrop = _stubba(monkeypatch)
    lid = _lektion(client, "Kursstart", "Vi bestämde att boken blir 5000+.")
    _done(client.post("/api/anteckningar/generate",
                      json={"kurs": "Matematik 3c", "lektioner": [lid]}))
    assert "Vi bestämde att boken blir 5000+." in anrop[0]["transkript"]
    assert "Kursstart" in anrop[0]["transkript"]


def test_langt_mote_refereras_innan_det_gar_in_i_prompten(client, monkeypatch):
    """Taket för prompten sätts av referatet, inte av mötets längd."""
    anrop = _stubba(monkeypatch)
    lid = _lektion(client, "Långt möte",
                   "Ord. " * (routes_anteckningar.RAKTEXT_TAK // 2))
    monkeypatch.setattr(routes_anteckningar.postprocess, "run",
                        lambda op, text, model, **kw: "REFERATET")
    r = client.post("/api/anteckningar/generate",
                    json={"kurs": "Matematik 3c", "lektioner": [lid]})
    _done(r)
    assert "REFERATET" in anrop[0]["transkript"]
    assert len(anrop[0]["transkript"]) < routes_anteckningar.RAKTEXT_TAK
    # Väntan ska synas: ett referat är ett modellanrop till.
    assert any("Refererar" in e.get("msg", "")
               for e in _events(r) if e["type"] == "log")


def test_tom_ruta_ar_tillatet_nar_ett_mote_ar_valt(client, monkeypatch):
    _stubba(monkeypatch)
    lid = _lektion(client, "Kursstart", "vi pratade om boken")
    res = _done(client.post("/api/anteckningar/generate",
                            json={"kurs": "Matematik 3c", "lektioner": [lid]}))
    assert res["id"]


def test_antalet_moten_ar_takat(client, monkeypatch):
    """Fler möten är inte en lektion att förbereda utan ett arkiv att söka i —
    och den frågan har appen redan svar på någon annanstans."""
    anrop = _stubba(monkeypatch)
    ids = [_lektion(client, f"Möte {i}", f"innehåll {i}") for i in range(8)]
    _done(client.post("/api/anteckningar/generate",
                      json={"kurs": "Matematik 3c", "lektioner": ids}))
    med = anrop[0]["transkript"]
    assert sum(f"innehåll {i}" in med for i in range(8)) == \
        routes_anteckningar.MAX_TRANSKRIPT


def test_anteckningarna_gar_att_andra_efter_en_omstart(client, monkeypatch):
    """Samma krav som tavlan fick i v20 och provet haft sedan v5: pappret som
    inte blev klart i går ska gå att ändra i dag."""
    from fastapi.testclient import TestClient
    from app.web import server as srv
    _stubba(monkeypatch)
    res = _done(client.post("/api/anteckningar/generate",
                            json={"onskemal": "x", "kurs": "Matematik 3c"}))
    ny = TestClient(srv.create_app(base_dir=client.base_dir))
    monkeypatch.setattr(ny.app.state.arbiter, "ensure_llm",
                        lambda: "http://127.0.0.1:8170")

    nytt = _anteckningar()
    nytt["sektioner"][0]["stycken"][0] = "Efter omstarten."
    sett = {}

    def fake_refine(notes, message, **kw):
        sett["sektioner"] = len(notes.get("sektioner") or [])
        sett["mal"] = kw.get("mal")
        return {"notes": nytt, "errors": [], "rounds": 1}
    monkeypatch.setattr(routes_anteckningar.notes_gen, "refine_notes", fake_refine)

    r = ny.post(f"/api/anteckningar/{res['id']}/refine",
                json={"message": "skriv om den",
                      "mal": {"namn": "Boken", "innehall": "Vi läser s. 2–6."}})
    assert r.status_code == 200
    assert "Efter omstarten." in _done(r)["anteckningar"]["sektioner"][0]["stycken"][0]
    assert sett["sektioner"] == len(_anteckningar()["sektioner"])
    assert sett["mal"] == {"namn": "Boken", "innehall": "Vi läser s. 2–6."}
