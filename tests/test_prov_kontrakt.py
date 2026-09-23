"""Prov och arbetsblad — kontraktet mot frontendens ark (Etapp 0.4).

Två saker prövas här som ingen annan svit prövar:

1. **Namnvägen.** Frontenden känner klass och kurs vid NAMN, och Gy25-punkterna
   är dess egna korta texter (app/web/ui/gy.js) — inte kursregistrets rader.
   Går de inte fram når provet aldrig servern.
2. **Facitlägena.** Backenden har `typ='arbetsblad'` men ingenting har hittills
   låst att utdatan faktiskt SKILJER sig från provets: arbetsbladet får facit i
   samma dokument och ingen bedömningsanvisning, provet tvärtom.
"""
import copy
import json

import pytest

from app import exam_gen, exam_latex, exam_pdf, exam_spec


def _events(resp):
    return [json.loads(line[len("data:"):])
            for line in resp.text.splitlines() if line.startswith("data:")]


def _done(resp):
    evs = [e for e in _events(resp) if e["type"] == "done"]
    assert evs, _events(resp)
    return evs[0]["result"]


def _exam_doc():
    from tests.test_exam import _exam
    return _exam()


@pytest.fixture
def client(llm_ready):
    """Allt i den här sviten genererar — arbitern måste svara.
    Basfixturen bor i conftest.py."""
    return llm_ready


def _stub(monkeypatch, exam=None):
    calls = []

    def fake(kurs, klass, punkter, *, model, antal=10, tid_min=120, delar=True,
             memory="", teman="", referens="", bilder="", utfall="", bok="",
             profil="prov", koder=None, grupp=None,
             llm=None, max_rounds=exam_gen.MAX_ROUNDS, log_cb=None, **_kw):
        calls.append({"kurs": kurs, "klass": klass, "punkter": punkter,
                      "antal": antal, "tid_min": tid_min, "delar": delar,
                      "utfall": utfall, "bok": bok, "profil": profil,
                      "koder": koder})
        return {"exam": exam or _exam_doc(), "errors": [], "rounds": 1}
    monkeypatch.setattr(exam_gen, "generate_exam", fake)
    return calls


# ------------------------------------------------------------- namnvägen --

def test_kurs_och_klass_som_namn_racker(client, monkeypatch):
    calls = _stub(monkeypatch)
    r = client.post("/api/exams/generate", json={
        "kurs": "Matematik, nivå 2c", "klass": "NA25",
        "punkter_text": ["Derivatans definition", "Deriveringsregler"],
        "antal": 8, "tid_min": 90, "delar": True})
    assert r.status_code == 200
    _done(r)
    assert calls[0]["kurs"] == "Matematik, nivå 2c"
    assert calls[0]["klass"] == "NA25"
    assert calls[0]["punkter"] == ["Derivatans definition", "Deriveringsregler"]
    assert calls[0]["antal"] == 8 and calls[0]["tid_min"] == 90
    assert "NA25" in [g["namn"] for g in client.get("/api/groups").json()]


def test_nivafel_foljer_med_svaret_till_klienten(client, monkeypatch):
    """Grindens fynd (exam_gen._niva_grind) ska nå skärmen. Ligger de bara i
    generatorns svar ser läraren ingenting — panelen och canvasen läser
    `nivafel` (api.js nivafelText)."""
    fynd = [{"nr": "7", "pastadd": "E", "domd": "C", "skal": "kräver kvadrering"}]

    def fake(*a, **kw):
        return {"exam": _exam_doc(), "errors": [], "rounds": 1, "nivafel": fynd}

    monkeypatch.setattr(exam_gen, "generate_exam", fake)
    r = client.post("/api/exams/generate", json={
        "kurs": "Matematik, nivå 2c", "klass": "NA25", "punkter_text": ["x"]})
    assert _done(r)["nivafel"] == fynd


def test_nivafel_ar_alltid_en_lista(client, monkeypatch):
    """Ett papper utan fynd svarar med tom lista och inte med null: klienten ska
    inte behöva skilja «inga fynd» från «ingen kontroll»."""
    _stub(monkeypatch)
    r = client.post("/api/exams/generate", json={
        "kurs": "Matematik, nivå 2c", "klass": "NA25", "punkter_text": ["x"]})
    assert _done(r)["nivafel"] == []


def test_utan_kurs_ar_det_400(client, monkeypatch):
    _stub(monkeypatch)
    assert client.post("/api/exams/generate", json={"klass": "NA25"}).status_code == 400


def test_punkter_ur_registret_vinner_over_fritexten(client, monkeypatch):
    """Skickar frontenden KODER går de före — texten är reservvägen.

    Koden är innehållspunktens identitet hela vägen (se course_data), så det
    som når prompten ska vara Skolverkets ordagranna text, med koden först."""
    calls = _stub(monkeypatch)
    kurs = next(c for c in client.get("/api/courses").json()
                if c["namn"] == "Matematik, nivå 2c")
    punkter = client.get(f"/api/exams/content-status?course_id={kurs['id']}").json()
    koder = [p["kod"] for p in punkter["punkter"][:2]]
    _done(client.post("/api/exams/generate", json={
        "course_id": kurs["id"], "punkter": koder,
        "punkter_text": ["ska inte användas"]}))
    assert len(calls[0]["punkter"]) == 2
    assert "ska inte användas" not in calls[0]["punkter"]
    assert all(rad.startswith(kod) for kod, rad in zip(koder, calls[0]["punkter"]))
    # … och koderna följer med som grammatiklås på uppgifternas innehall.
    assert calls[0]["koder"] == koder


def test_okand_kod_faller_tillbaka_pa_etiketterna(client, monkeypatch):
    """En kod som inte finns i registret får inte tysta ner innehållet helt —
    då står planeringen kvar med sina korta etiketter, som förut."""
    calls = _stub(monkeypatch)
    _done(client.post("/api/exams/generate", json={
        "kurs": "Matematik, nivå 2c", "punkter": ["G25-FINNS-INTE-1"],
        "punkter_text": ["Andragradsekvationer"]}))
    assert calls[0]["punkter"] == ["Andragradsekvationer"]
    assert calls[0]["koder"] == []


def test_arbetsblad_gar_pa_samma_rutt_med_egen_profil(client, monkeypatch):
    calls = _stub(monkeypatch)
    r = _done(client.post("/api/exams/generate", json={
        "kurs": "Matematik, nivå 1c", "punkter_text": ["Enhetscirkeln"],
        "typ": "arbetsblad", "antal": 4}))
    assert calls[0]["profil"] == "arbetsblad"
    assert r["typ"] == "arbetsblad"


# ------------------------------------------------------------ facitlägena --

def test_arbetsbladet_bar_sitt_facit_provet_inte():
    """Arbetsbladets facit ligger i SAMMA dokument — eleven rättar sig själv.
    Provets lösningar hör hemma i bedömningsanvisningen, som är ett eget
    dokument läraren har för sig själv."""
    doc, fel = exam_spec.validate_exam_json(_exam_doc())
    assert doc is not None, fel
    ark = exam_latex.render_arbetsblad(doc)
    prov = exam_latex.render_prov(doc)
    bedomning = exam_latex.render_bedomning(doc)

    # Mallarna sätter matematiken som \(…\); jämför i den formen.
    import re
    losning = re.sub(r"\$([^$]*)\$", r"\\(\1\\)", doc.uppgifter[0].losning).strip()
    assert losning in ark, "arbetsbladet ska bära sitt facit"
    assert losning not in prov, "provet får aldrig innehålla lösningarna"
    # Bedömningsanvisningen bär svaret fett, med formlerna i \pmb (NP:s form,
    # lärarens dom 2026-09-23; cachen har ingen fet matematik).
    fet = re.sub(r"\$([^$]*)\$", r"\\(\\pmb{\1}\\)", doc.uppgifter[0].losning).strip()
    assert f"\\bedsvar{{{fet}}}" in bedomning, \
        "bedömningsanvisningen bär provets lösningar"
    # Och bedömningsanvisningen — lärarens eget papper — hör inte till eleven.
    # Anvisningen står som en rad per poäng på pappret (ett \bedkrav per
    # poäng, se exam_spec.bedomningsrader), inte som fältets råa sträng: därför
    # jämförs kriterierna rad för rad, som meningar med NP:s märke.
    for rad in exam_spec.bedomningsrader(doc.uppgifter[0].bedomning):
        assert rad["krav"] not in ark
        mening = rad["krav"][0].upper() + rad["krav"][1:] + "."
        assert f"\\bedkrav{{{mening}}}{{+{rad['niva']}}}" in bedomning
    # «Separat facit»: elevbladet släcker bandet, lösningarna finns då bara på
    # lärarens separata blad (only_facit). Utan flaggan fick eleverna dem
    # dubbelt — en gång i bladet, en gång i facit-PDF:en.
    utan = exam_latex.render_arbetsblad(doc, utan_facit=True)
    assert losning not in utan
    assert losning in exam_latex.render_arbetsblad(doc, only_facit=True)


def test_bedomningsanvisning_skrivs_bara_for_prov(client, monkeypatch):
    """Ett arbetsblad ska inte lämna en bedömningsanvisning efter sig."""
    monkeypatch.setattr(exam_pdf, "engine_available", lambda: False)

    def artefakter(typ):
        _stub(monkeypatch)
        ex = _done(client.post("/api/exams/generate", json={
            "kurs": "Matematik, nivå 2c", "punkter_text": ["Derivator"],
            "typ": typ}))
        _done(client.post(f"/api/exams/{ex['id']}/approve", json={}))
        return sorted(p.name for p in client.base_dir.rglob("*.tex"))

    prov = artefakter("prov")
    assert any(n.endswith(" - bedomning.tex") for n in prov), prov
    for p in client.base_dir.rglob("*.tex"):
        p.unlink()
    ark = artefakter("arbetsblad")
    assert ark and not any(n.endswith(" - bedomning.tex") for n in ark), ark


def test_godkannandet_stamplar_kravgranserna_i_dokumentet(client, monkeypatch):
    """Godkännandet är stunden pappret blir ett papper: gränserna skrivs in i
    prov-JSON:en i stället för att räknas om vid varje framtida tryck.

    Utan stämpeln bar ett återtryck DAGENS regel — och NP-kalibreringen
    2026-08-22 flyttade C-gränsen nio procentenheter. Ett prov från i maj hade
    tryckts om i juni med andra gränser än klassen skrev det med."""
    monkeypatch.setattr(exam_pdf, "engine_available", lambda: False)
    _stub(monkeypatch)
    ex = _done(client.post("/api/exams/generate", json={
        "kurs": "Matematik, nivå 2c", "punkter_text": ["Derivator"]}))
    assert ex["exam"].get("granser") is None      # inte modellens fält
    r = _done(client.post(f"/api/exams/{ex['id']}/approve", json={}))
    g = r["exam"]["granser"]
    assert g["total"] == 20 and g["E"]["minst"] == 6 and g["C"]["minst"] == 11
    assert g["regel"] and r["granser"] == g
    # Stämpeln är en anteckning, inte en ändring: inget nytt varv i ångra-
    # historiken, och pekaren står kvar där läraren lämnade den.
    assert len(r["versions"]) == len(ex["versions"])
    assert r["current_version"] == ex["current_version"]

    # Regeln görs om — det godkända pappret bryr sig inte.
    monkeypatch.setitem(exam_spec.KRAV_DEFAULT, "e_andel", 0.90)
    r2 = _done(client.post(f"/api/exams/{ex['id']}/approve", json={}))
    assert r2["exam"]["granser"] == g and r2["granser"]["E"]["minst"] == 6


# ----------------------------------------------- formen frontenden läser --

def test_svaret_bar_det_arket_behover(client, monkeypatch):
    """Frontendens ark läser nr, poäng, text, nivå, svarsyta och facit. Allt
    det härleds ur prov-JSON:en — och kravgränserna kommer färdigräknade."""
    _stub(monkeypatch)
    r = _done(client.post("/api/exams/generate", json={
        "kurs": "Matematik, nivå 2c", "punkter_text": ["Derivator"]}))
    assert r["granser"] and {"E", "C", "A"} <= set(r["granser"])
    assert r["summor"]
    for u in r["exam"]["uppgifter"]:
        assert u["text"] and u["formaga"] and u["typ"]
        assert len(u["poang"]) == 3
        # Nivån syns i poängvektorn — arket behöver ingen egen etikett.
        assert u.get("deluppgifter") or (u["losning"] and u["bedomning"])


def test_uppgift_med_deluppgifter_har_poangen_bara_pa_delarna():
    """Frontendens ark summerar deluppgifternas poäng till uppgiftens. Låg
    poängen på båda ställena räknades den dubbelt — schemat förbjuder det."""
    doc = copy.deepcopy(_exam_doc())
    doc["uppgifter"][0] = {
        "del": "B", "formaga": "P", "typ": "rutin", "poang": [0, 0, 0],
        "text": "Lös ekvationerna.",
        "deluppgifter": [
            {"poang": [2, 0, 0], "text": "$x^2 = 9$", "losning": "$x = \\pm 3$",
             "bedomning": "+2 E"},
            {"poang": [0, 2, 0], "text": "$x^2 + x = 6$", "losning": "$x = 2$ eller $x = -3$",
             "bedomning": "+2 C"},
        ],
    }
    ok, _ = exam_spec.validate_exam_json(copy.deepcopy(doc))
    assert ok is not None

    doc["uppgifter"][0]["poang"] = [1, 0, 0]        # poäng på båda ställena
    trasig, fel = exam_spec.validate_exam_json(doc)
    assert trasig is None and fel


# ── EFTERKONTROLLEN (granskningen 2026-09-19) ────────────────────────────────
#
# Genereringens vakter kör EN gång. Sedan öppnar läraren canvasen, skriver om
# pappret och godkänner, och mellan de två punkterna tittade ingen. Prov 85
# tappade sin balans i ett varv; prov 86 fick ett avsnitt («2.6») som inte finns
# i boken, förebilder på sidor utanför sina avsnitt och en plåt som visar en fyr
# på en uppgift om ett tryckeri.
#
# Kontrollen hänger i `_exam_result`, alltså i alla fyra svaren (GET, generate,
# refine, approve), och prövas här på funktionen direkt: den är ren och tar
# bokens register som ett argument, så ingen av raderna behöver en databas.

_BOK = {"namn": "Liber Ma 1c", "avsnitt": [
    {"nr": "1.1", "fran": 2, "till": 6},
    {"nr": "1.2", "fran": 7, "till": 21},
    {"nr": "2.3", "fran": 56, "till": 57},
    {"nr": "2.5", "fran": 64, "till": 99},
]}
# nr → sida, som routes_exam._bokunderlag bygger den ur bok_uppgifter.
_SIDOR = {1101: 3, 1253: 14, 2320: 56, 2601: 70}


def _vy(exam, **extra):
    return dict({"id": 1, "typ": "prov", "status": "utkast", "versions": 1,
                 "current_version": 1, "exam": exam}, **extra)


def _kontroll(exam, **kw):
    from app.web import routes_exam
    doc, fel = exam_spec.validate_exam_json(copy.deepcopy(exam))
    assert doc is not None, fel
    summor = exam_spec.poangsummor(doc)
    return routes_exam.efterkontroll(_vy(exam), doc, summor, **kw)


def _ovriga_med_forebild(exam):
    """Förebild på alla uppgifter utom den första, som testet självt sätter.
    Utan den fäller förebildsvakten (kod «utanbok») de andra uppgifterna så
    fort den första får en förebild. Numren är olika och okända för boken:
    samma sort överallt är en modellfamilj (familjvakten), och ett känt
    nummer utan avsnitt säger ingenting mer."""
    for i, u in enumerate(exam["uppgifter"][1:], 1):
        u["forebild"] = {"nr": 5000 + i, "sort": f"sort nummer {i}"}
    return exam


def _koder(fynd):
    return sorted({f["kod"] for f in fynd})


def test_efterkontrollen_tiger_om_ett_helt_papper():
    """Fail-open överallt: utan bok, utan avsnittsfält och utan plåt ska ett
    balanserat prov inte bära en enda varning. En kontroll som alltid säger
    något är en kontroll man slutar läsa."""
    assert _kontroll(_exam_doc()) == []


def test_efterkontrollen_faller_balansen_efter_en_omskrivning():
    """Prov 85: en riktad omskrivning flyttade en poäng från A till C, och
    ingen räknade om. Samma linjal som reparationsloopen (validate_balance)."""
    exam = copy.deepcopy(_exam_doc())
    # All poäng till E: nivåbanden kan inte hålla, och det ska synas.
    for u in exam["uppgifter"]:
        if not u.get("deluppgifter"):
            u["poang"] = [sum(u["poang"]), 0, 0]
    fynd = _kontroll(exam)
    assert "balans" in _koder(fynd)
    assert any("%" in f["text"] for f in fynd)


def test_efterkontrollen_mater_provet_mot_sin_egen_kurs():
    """Lärarens dom 2026-09-22 (exam 118): nivåkontrollen ska följa kursens
    nationella prov, inte hela materialets breda band. Samma papper, 20 p
    med E 9 / C 6 / A 5 (45/30/25 %): inom 2a:s band (E 40–42 % med
    marginal), men 1c:s nationella prov bär C och har E på 29–31 %."""
    exam = copy.deepcopy(_exam_doc())
    exam["kurs"] = "Matematik, nivå 2a"
    assert "balans" not in _koder(_kontroll(exam))
    exam["kurs"] = "Matematik, nivå 1c"
    fynd = [f for f in _kontroll(exam) if f["kod"] == "balans"]
    assert fynd and any("E-poängen är 45%" in f["text"] for f in fynd)
    assert all("kurs 1c" in f["text"] for f in fynd
               if "poängen är" in f["text"] and "av totalen" in f["text"])
    # En kurs utan mätning (fixturens Ma2b) står kvar på det breda bandet.
    assert _kontroll(_exam_doc()) == []


def test_efterkontrollen_faller_avsnitt_som_inte_finns_i_boken():
    """Prov 86:s uppgift 12 stod märkt «2.6». Liber Ma 1c slutar på 2.5."""
    exam = copy.deepcopy(_exam_doc())
    exam["uppgifter"][0]["avsnitt"] = "2.6"
    fynd = _kontroll(exam, bok=_BOK, sidor=_SIDOR)
    assert [f["kod"] for f in fynd] == ["avsnitt"]
    assert fynd[0]["nr"] == 1 and fynd[0]["el"] == "uppg1"
    assert "2.6" in fynd[0]["text"] and "Liber Ma 1c" in fynd[0]["text"]
    # …och ett avsnitt boken HAR säger ingenting.
    exam["uppgifter"][0]["avsnitt"] = "1.2"
    assert _kontroll(exam, bok=_BOK, sidor=_SIDOR) == []


def test_efterkontrollen_faller_forebild_utanfor_avsnittets_sidspann():
    """Prov 86:s uppgift 3: märkt 2.5 (s. 64–99), bygger på bokuppgift 1253
    som står på s. 14. Antingen är etiketten fel eller förebilden, och
    täckningen räknar på etiketten, så felet döljer en lucka."""
    exam = _ovriga_med_forebild(copy.deepcopy(_exam_doc()))
    exam["uppgifter"][0]["avsnitt"] = "2.5"
    exam["uppgifter"][0]["forebild"] = {"nr": 1253, "sort": "samma sort: rötter"}
    fynd = _kontroll(exam, bok=_BOK, sidor=_SIDOR)
    assert [f["kod"] for f in fynd] == ["forebild"]
    assert "1253" in fynd[0]["text"] and "s. 14" in fynd[0]["text"]
    # Förebilden INNE i spannet, och en förebild boken inte känner: tyst.
    exam["uppgifter"][0]["forebild"] = {"nr": 2601, "sort": "samma sort"}
    assert _kontroll(exam, bok=_BOK, sidor=_SIDOR) == []
    exam["uppgifter"][0]["forebild"] = {"nr": 9999, "sort": "samma sort"}
    assert _kontroll(exam, bok=_BOK, sidor=_SIDOR) == []


def test_efterkontrollen_godtar_forebild_i_den_andra_rubrikens_spann():
    """Prov 86:s uppgift 8 (2026-09-19): märkt 2.4 (olikheter) med en andra
    rubrik «Faktorisering och förkortning (s. 31–34)» och förebild 1338 på
    s. 14 i testboken. Uppgiften prövar båda med flit, så förebilden får
    ligga i vilket som helst av etikettens spann."""
    exam = _ovriga_med_forebild(copy.deepcopy(_exam_doc()))
    exam["uppgifter"][0]["avsnitt"] = "2.5"
    exam["uppgifter"][0]["forebild"] = {"nr": 1253, "sort": "samma sort: rötter"}
    exam["uppgifter"][0]["delmoment"] = ("Formler (s. 64–68); "
                                         "Rötter (s. 12–16)")
    assert [f["kod"] for f in _kontroll(exam, bok=_BOK, sidor=_SIDOR)] == []


def test_efterkontrollen_tiger_om_forebild_ur_blandade_uppgifter():
    """Bokens blandade uppgifter och kapiteltest numreras 1, 2, 3 … per
    kapitel. Prov 86:s uppgift 5 pekade på «34», som finns på flera sidor i
    samma bok. Ett tal under 100 säger inget om avsnittet och ska inte
    larma."""
    exam = _ovriga_med_forebild(copy.deepcopy(_exam_doc()))
    exam["uppgifter"][0]["avsnitt"] = "2.5"
    exam["uppgifter"][0]["forebild"] = {"nr": 34, "sort": "samma sort"}
    sidor = dict(_SIDOR)
    sidor[34] = 14
    assert _kontroll(exam, bok=_BOK, sidor=sidor) == []


def test_efterkontrollen_faller_provuppgift_utan_forebild():
    """Prov 119 (2026-09-23): uppgift 5 och 7 stod utan avsnitt, 7 utan
    förebild, och de andra frågorna tiger utan avsnitt. Läraren fällde båda:
    «det är inte något vi har gått igenom på lektionen»."""
    exam = _ovriga_med_forebild(copy.deepcopy(_exam_doc()))
    fynd = _kontroll(exam, bok=_BOK, sidor=_SIDOR)
    assert [f["kod"] for f in fynd] == ["utanbok"]
    assert fynd[0]["nr"] == 1
    assert "Uppgift 1 saknar förebild" in fynd[0]["text"]
    assert "nationella provets uppgiftstyper" in fynd[0]["text"]
    assert "inte märkt med något avsnitt" in fynd[0]["text"]
    # Laga-knappen byter ut uppgiften, den tänjer inte förebilden.
    from app.web import routes_exam
    assert "nationella provets uppgiftstyper för kursen" in \
        routes_exam.efterkontroll_instruktion(fynd)
    # Med förebild: tyst.
    exam["uppgifter"][0]["forebild"] = {"nr": 2601, "sort": "samma sort"}
    assert _kontroll(exam, bok=_BOK, sidor=_SIDOR) == []
    # Ett papper där INGEN uppgift har förebild skrevs utan fältet: tyst.
    assert _kontroll(copy.deepcopy(_exam_doc()), bok=_BOK, sidor=_SIDOR) == []
    # Arbetsbladet har ingen sådan regel.
    from app import exam_spec as es
    blad = copy.deepcopy(_exam_doc())
    blad["uppgifter"][1]["forebild"] = {"nr": 2601, "sort": "samma sort"}
    doc, _ = es.validate_exam_json(copy.deepcopy(blad))
    assert not [f for f in routes_exam._bokfynd(doc, _BOK, _SIDOR, "arbetsblad")
                if f["kod"] == "utanbok"]


def test_efterkontrollen_faller_tryckta_tips():
    """Prov 88 (2026-09-19): tipsen skrevs bort på uppgift 4 men stod kvar på
    6 och 11, och efterkontrollen sa inget. Nu ett fynd per uppgift."""
    exam = copy.deepcopy(_exam_doc())
    exam["uppgifter"][0]["text"] = (exam["uppgifter"][0].get("text") or "")         + " Tips: sätt in talet i formeln."
    fynd = _kontroll(exam, bok=_BOK, sidor=_SIDOR)
    assert [f["kod"] for f in fynd] == ["tips"]
    assert fynd[0]["nr"] == 1


def test_efterkontrollen_faller_delmomentsetikett_i_ett_annat_avsnitt():
    """Rubriken bär sina sidor («Intervall (s. 56–57)»). Ligger de i ett annat
    avsnitt än uppgiftens etikett är märkningen fel."""
    exam = copy.deepcopy(_exam_doc())
    exam["uppgifter"][0]["avsnitt"] = "2.5"
    exam["uppgifter"][0]["delmoment"] = "Intervall (s. 56–57)"
    fynd = _kontroll(exam, bok=_BOK, sidor=_SIDOR)
    assert [f["kod"] for f in fynd] == ["delmoment"]
    assert fynd[0]["el"] == "uppg1"
    # Två rubriker med semikolon: det räcker att EN rör avsnittet.
    exam["uppgifter"][0]["delmoment"] = \
        "Intervall (s. 56–57); Formler (s. 64–68)"
    assert _kontroll(exam, bok=_BOK, sidor=_SIDOR) == []


def test_efterkontrollen_faller_provtid_som_inte_racker():
    """Prov 85 stod på 70 minuter med ett papper som räknas till 100."""
    exam = copy.deepcopy(_exam_doc())
    exam["tid_min"] = 20
    fynd = _kontroll(exam)
    assert [f["kod"] for f in fynd] == ["tid"]
    assert "20 minuter" in fynd[0]["text"]
    # Tolv procents slack: ett papper med gott om tid tiger.
    exam["tid_min"] = 240
    assert _kontroll(exam) == []


def test_efterkontrollen_faller_plat_som_inte_hor_till_scenen(tmp_path,
                                                              monkeypatch):
    """Prov 86:s uppgift 12: SCENE-stycket beskriver ett tryckeri, plåten
    visar en fyr och en båt i kvällsmörker. Måttet är matchningens eget
    (platar.poang mot MIN_POANG), samma linjal som satte plåten dit."""
    from app import platar
    from app.web import routes_exam
    katalog = [
        {"namn": "a-14-fyr-bat", "spar": "a",
         "motiv": "fyr och båt i kvällsmörker",
         "begrepp": "sinussatsen och cosinussatsen, elevationsvinkel, "
                    "observatorer, trigonometri"},
        {"namn": "a-12-tryckeri", "spar": "a", "motiv": "tryckeri med press",
         "begrepp": "prismodeller tryckeri, linjär kostnad, brytpunkt"},
    ]
    monkeypatch.setattr(platar, "katalog", lambda base=None: katalog)
    scen = {"begrepp": "prismodeller tryckeri",
            "scene": "SCENE. A small print workshop seen straight from the "
                     "front at eye level, with a long flat table and a press "
                     "machine behind it. Intended use: exam task scenario.",
            "filnamn": "a-12-tryckeri"}
    exam = copy.deepcopy(_exam_doc())
    exam["uppgifter"][0]["scen"] = dict(scen, plat="a-14-fyr-bat")

    def kor(e):
        doc, fel = exam_spec.validate_exam_json(copy.deepcopy(e))
        assert doc is not None, fel
        return routes_exam.efterkontroll(_vy(e), doc,
                                         exam_spec.poangsummor(doc),
                                         base=tmp_path)

    fynd = kor(exam)
    assert [f["kod"] for f in fynd] == ["bild"]
    assert fynd[0]["el"] == "uppg1"
    assert "a-14-fyr-bat" in fynd[0]["text"]
    # Rätt plåt: tyst. Okänd plåt: eget fynd, för rutan blir tom i tryck.
    exam["uppgifter"][0]["scen"]["plat"] = "a-12-tryckeri"
    assert kor(exam) == []
    exam["uppgifter"][0]["scen"]["plat"] = "a-99-finns-inte"
    fynd = kor(exam)
    assert [f["kod"] for f in fynd] == ["bild"]
    assert "katalogen" in fynd[0]["text"]


def test_efterkontrollen_faller_endast_svar_mot_uppgiftstypen():
    """Delraden på försättsbladet härleds ur uppgifterna (exam_latex.delrader,
    blad.js redovisning sedan c4d2469). Säger dokumentets EGEN hjälpmedelsregel
    något annat om samma del lovar pappret två saker om samma uppgift."""
    exam = copy.deepcopy(_exam_doc())
    # Fixturens del B bär bara rutinuppgifter: löftet går att hålla.
    exam["hjalpmedel"] = ("Del B utan räknare, endast svar krävs. "
                          "Del C med räknare och formelblad.")
    assert "delkrav" not in _koder(_kontroll(exam))
    # En redovisningsuppgift flyttas in i del B, och då säger pappret två
    # saker om samma uppgift.
    exam["uppgifter"][2]["del"] = "B"
    fynd = _kontroll(exam)
    assert "delkrav" in _koder(fynd)
    rad = next(f for f in fynd if f["kod"] == "delkrav")
    assert "del B" in rad["text"] and "fullständig lösning" in rad["text"]


def test_efterkontrollen_ar_med_i_varje_svar(client, monkeypatch):
    """Nyckeln finns i generate och i GET, alltid en lista, aldrig None.
    Klienten ska inte behöva skilja «inga fynd» från «ingen kontroll kördes»."""
    exam = copy.deepcopy(_exam_doc())
    exam["tid_min"] = 20                       # ett fynd som säkert fälls
    _stub(monkeypatch, exam)
    # Minuterna ÄR lärarens, inte modellens: rutten skriver dem över dokumentets
    # (se _satt_lararens_datum-grannen i generate), så talet måste komma i
    # begäran för att nå pappret.
    r = _done(client.post("/api/exams/generate", json={
        "kurs": "Matematik, nivå 2c", "punkter_text": ["Derivator"],
        "tid_min": 20}))
    assert [f["kod"] for f in r["efterkontroll"]] == ["tid"]
    hamtat = client.get(f"/api/exams/{r['id']}").json()
    assert [f["kod"] for f in hamtat["efterkontroll"]] == ["tid"]
    # «Laga fynden»-meningen följer med i samma svar. TOM här, för provtiden
    # lagas inte av en omskrivning. Knappen visas då inte (plan.js ritaFynd).
    assert r["efterkontroll_instruktion"] == ""
    assert hamtat["efterkontroll_instruktion"] == ""


# ── «LAGA FYNDEN»: FYNDEN SOM EN INSTRUKTION ─────────────────────
# Meningen knappen skickar byggs på servern (routes_exam
# .efterkontroll_instruktion) just för att den ska vara EN mening: samma knapp
# sitter i förhandsvisningen och på varvets rad i canvasen, och två klienter
# som formulerar om koderna var för sig blir två olika omskrivningar med samma
# namn. Ren funktion in och ut, så den går att pröva utan papper.

def _fynd(kod, nr, text):
    return {"kod": kod, "nr": nr, "el": f"uppg{nr}" if nr else None,
            "text": text}


def test_instruktionen_bar_fyndets_mening_och_en_atgard():
    """Fyndets egen mening står kvar. Den bär talen (vilken bokuppgift, vilket
    sidspann) och är den enda källan till dem. Åtgärden läggs efter som en egen
    mening: fyndet säger vad som är fel, åtgärden vad som får ändras."""
    from app.web import routes_exam
    text = routes_exam.efterkontroll_instruktion([
        _fynd("forebild", 8, "Uppgift 8 är märkt med avsnitt 1.2 (s. 20–30) "
                             "men bygger på bokuppgift 1112, som står på s. 12."),
        _fynd("sprak", None, "Språkvakten fäller uppgift 7."),
    ])
    assert "bokuppgift 1112" in text and "Språkvakten fäller uppgift 7." in text
    # Åtgärderna, en per kod, och de säger vad som INTE får röras.
    assert "Byt förebild" in text and "poäng står kvar" in text
    assert "kortare meningar" in text
    # Numrerad lista, ett fynd per rad.
    rader = [r for r in text.splitlines() if r[:2] in ("1.", "2.")]
    assert len(rader) == 2


def test_instruktionen_lamnar_provtiden_utanfor():
    """Provtiden lagas genom att läraren sätter fler minuter eller stryker
    poäng, och båda är hennes val. En modell som bads «laga» den hade tagit bort
    uppgifter. Ensam ger den tom sträng, alltså ingen knapp."""
    from app.web import routes_exam
    tid = _fynd("tid", None, "Pappret är satt till 70 minuter men uppgifterna "
                             "räknas till 100.")
    assert routes_exam.efterkontroll_instruktion([tid]) == ""
    assert routes_exam.efterkontroll_instruktion([]) == ""
    assert routes_exam.efterkontroll_instruktion(None) == ""
    text = routes_exam.efterkontroll_instruktion(
        [tid, _fynd("avsnitt", 3, "Uppgift 3 är märkt med avsnitt 2.6.")])
    assert "70 minuter" not in text and "avsnitt 2.6" in text
    # …och raden numreras från ett, fast provtiden stod först i listan.
    assert text.splitlines()[-1].startswith("1. Uppgift 3")


def test_instruktionen_samlar_uppgiftsnumren():
    """Numren är klientens lås på omskrivningen (`nummer` i refine-kroppen) och
    står också i meningen. En gång var, i ordning, och provtidens saknade
    nummer räknas inte."""
    from app.web import routes_exam
    fynd = [_fynd("avsnitt", 8, "Uppgift 8 är märkt fel."),
            _fynd("bild", 3, "Uppgift 3 bär fel plåt."),
            _fynd("forebild", 8, "Uppgift 8 pekar på fel bokuppgift."),
            _fynd("tid", None, "Pappret är satt till 70 minuter.")]
    assert routes_exam.efterkontroll_nummer(fynd) == [3, 8]
    assert routes_exam.efterkontroll_nummer([]) == []
    assert "De gäller uppgift 3 och 8." in routes_exam.efterkontroll_instruktion(fynd)
    # Ett enda nummer skrivs utan «och», och ett fynd utan nummer (balansen
    # gäller pappret) ger ingen numrering alls.
    assert "uppgift 3." in routes_exam.efterkontroll_instruktion(fynd[1:2])
    assert "De gäller" not in routes_exam.efterkontroll_instruktion(
        [_fynd("balans", None, "Balansen mot kursens mål stämmer inte.")])


def test_efterkontrollen_saknar_delmoment_ur_kalendern(monkeypatch, tmp_path):
    """Prov 126 (NA26F, 2026-09-23): lagningsrundorna bytte ut
    mönsteruppgiften, och omskrivningen har ingen täckningsvakt. Läraren såg
    det själv. Efterkontrollen frågar nu kalenderns delmoment på varje papper.
    Spannet är hela KAPITLEN provets uppgifter hör till, så ett avsnitt vars
    sista uppgift försvann (2.5 här) räknas ändå."""
    from app.web import routes_exam, routes_planning
    exam = _ovriga_med_forebild(copy.deepcopy(_exam_doc()))
    for u in exam["uppgifter"]:
        u["avsnitt"] = "1.1"
        u["delmoment"] = "Kvadratrötter (s. 2–6)"
    sett = {}

    def fake(db_file, body, *, group_id, course_id):
        sett.update(body["bok"])
        return [{"delmoment": "Kvadratrötter", "sidor": "2–6", "lektioner": 1},
                {"delmoment": "Grundpotensform", "sidor": "12–15",
                 "lektioner": 1}]
    monkeypatch.setattr(routes_planning, "undervisade_delmoment", fake)
    doc, _ = exam_spec.validate_exam_json(copy.deepcopy(exam))
    vy = _vy(exam, group_id=1, course_id=2, datum="2026-10-01")
    fynd = routes_exam._lektionsfynd(vy, doc, dict(_BOK, id=5), tmp_path / "x.db")
    assert [f["kod"] for f in fynd] == ["lektion"]
    assert "Grundpotensform (s. 12–15)" in fynd[0]["text"]
    # Kapitel 1 i testboken: 1.1 och 1.2 (s. 2–21), inte 2.x.
    assert (sett["fran"], sett["till"]) == (2, 21)
    # Arbetsbladet och ett papper utan klass tiger.
    assert routes_exam._lektionsfynd(dict(vy, typ="arbetsblad"), doc,
                                     dict(_BOK, id=5), tmp_path / "x.db") == []
    assert routes_exam._lektionsfynd(dict(vy, group_id=None), doc,
                                     dict(_BOK, id=5), tmp_path / "x.db") == []
