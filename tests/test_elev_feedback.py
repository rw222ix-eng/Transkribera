"""Feedbacken till eleven: prompten, språket och namnen som aldrig går ut.

Det viktigaste testet i filen är `test_inget_elevnamn_nar_modellen`. Regeln är
lärarens och den är hård — modellen får «Elev 1», aldrig ett namn — och den
enda platsen den kan brytas på är vägen mellan databasen och prompten. Därför
körs den hela vägen genom rutten, med den riktiga prompten fångad.
"""
import json

import pytest

from app import elev_feedback, rattning

UPPGIFTER = [
    {"nr": 1, "t": "Beräkna arean.", "p": 2, "peca": [2, 0, 0]},
    {"nr": 2, "t": "Undersök sambandet.", "p": 6,
     "del": ["ställ upp", "visa att det gäller generellt"],
     "delpeca": [[1, 2, 0], [0, 0, 3]]},
    {"nr": 3, "t": "Avgör om påståendet är sant.", "p": 3, "peca": [0, 2, 1]},
]
RADER = rattning.bygg(UPPGIFTER)
GRANSER = rattning.granser(RADER)


def _elev(varden, betyg="E"):
    s = rattning.elevsummor(RADER, varden)
    return {"summor": s, "betyg": betyg, "varden": varden}


FULLT = {"1": [2, None, None], "2a": [1, 2, None], "2b": [None, None, 3],
         "3": [None, 2, 1]}
HALVT = {"1": [2, None, None], "2a": [1, 0, None], "2b": [None, None, 0],
         "3": [None, 0, 0]}

OK_TEXT = ("Ekvationerna sitter fint. Det som fattas är uppgifterna där du ska "
           "motivera varför ett svar stämmer. Träna på att skriva ner hur du "
           "tänkte, inte bara vad du räknade.")


def _svar(*texter):
    return json.dumps({"feedback": [{"elev": i + 1, "text": t}
                                    for i, t in enumerate(texter)]},
                      ensure_ascii=False)


def _svarare(*svar):
    """En stubbad modell som svarar i tur och ordning."""
    kvar = list(svar)

    def llm(_model, _prompt, **_kw):
        return kvar.pop(0) if kvar else _svar(OK_TEXT)
    return llm


# ── Prompten ────────────────────────────────────────────────────────────────

def test_prompten_bar_uppgifterna_med_nivapoang():
    txt = elev_feedback.build_prompt(RADER, [_elev(FULLT, "A")], GRANSER)
    assert "1: Beräkna arean. (2 p på E" in txt
    assert "2b: visa att det gäller generellt (3 p på A" in txt


def test_prompten_bar_kravgranserna():
    txt = elev_feedback.build_granser(GRANSER)
    assert "Provet är 11 p" in txt and "E från 3 p" in txt
    assert "C från 5 p varav 3 p" in txt and "A från 8 p varav 2 p" in txt


def test_prompten_bar_klassens_utfall():
    """Det som föll för alla är inte elevens egen brist. Utan blocket skriver
    modellen «du missade 2b» till halva klassen som ett personligt problem."""
    txt = elev_feedback.build_klassen(RADER, [_elev(FULLT), _elev(HALVT)])
    assert "2b: klassen tog 50 %" in txt


def test_eleven_ar_ett_nummer_och_avstandet_star_i_poang():
    txt = elev_feedback.build_elever(RADER, [_elev(HALVT, "E")], GRANSER)
    assert txt.startswith("ELEVERNA")
    assert "Elev 1 (betyg E, 3 av 11 p" in txt
    assert "2 p till och 3 p till på C- eller A-nivå för C" in txt
    assert "2a: 1/1 E + 0/2 C" in txt


def test_a_eleven_har_inget_avstand_kvar():
    txt = elev_feedback.build_elever(RADER, [_elev(FULLT, "A")], GRANSER)
    assert " — " not in txt.split("\n")[1]


def test_stilkontraktet_star_i_prompten():
    txt = elev_feedback.build_prompt(RADER, [_elev(FULLT)], GRANSER)
    assert elev_feedback.STIL in txt


def test_exemplet_i_prompten_bryter_inte_mot_sin_egen_regel():
    """Ett exempel som bryter mot regeln ovanför lär modellen att regeln inte
    gäller (samma kontroll som anteckningarna har)."""
    exempel = json.loads(elev_feedback.INSTRUKTION.split("Exempel på formen:\n")[1])
    svar = elev_feedback.FeedbackSvar.model_validate(exempel)
    assert elev_feedback.validate_feedback(svar, 1) == []


# ── Valideringen ────────────────────────────────────────────────────────────

def _fel(text, antal=1):
    svar = elev_feedback.FeedbackSvar.model_validate(
        {"feedback": [{"elev": 1, "text": text}]})
    return elev_feedback.validate_feedback(svar, antal)


def test_sex_meningar_falls():
    fel = _fel("Ett. Två. Tre. Fyra. Fem. Sex.")
    assert [f["code"] for f in fel] == ["langd"]
    assert "6 meningar" in fel[0]["message"]


def test_fem_meningar_gar_igenom():
    assert _fel("Ett. Två. Tre. Fyra. Fem.") == []


def test_forkortningar_raknas_inte_som_meningsslut():
    """«t.ex.» är inte tre meningar. Utan den regeln fälls fullgoda texter."""
    assert _fel("Träna på ekvationer, t.ex. de med x på båda sidor. Kör på.") == []


@pytest.mark.parametrize("text", [
    "Du behöver utveckla din procedurförmåga.",
    "Din förmåga att resonera är god.",
    "Lösningen är i huvudsak fungerande.",
    "Du löser uppgifter med viss säkerhet.",
    "Resultatet är tillfredsställande.",
    "Se kunskapskraven för C.",
    "Kolla bedömningsmatrisen.",
])
def test_jargongen_falls(text):
    fel = _fel(text)
    assert [f["code"] for f in fel] == ["jargong"], text


def test_klartext_gar_igenom():
    assert _fel("Träna på att lösa ekvationer där x finns på båda sidor.") == []


def test_betyget_far_namnas():
    assert _fel("Du är två poäng från C. Ta uppgifterna där du ska motivera.") == []


def test_saknad_elev_falls():
    fel = _fel(OK_TEXT, antal=3)
    assert [f["code"] for f in fel] == ["antal"]
    assert "elev 2, 3" in fel[0]["message"]


def test_okant_elevnummer_falls():
    svar = elev_feedback.FeedbackSvar.model_validate(
        {"feedback": [{"elev": 1, "text": OK_TEXT},
                      {"elev": 9, "text": OK_TEXT}]})
    assert [f["code"] for f in elev_feedback.validate_feedback(svar, 1)] == ["elev"]


def test_dubbel_kommentar_falls():
    svar = elev_feedback.FeedbackSvar.model_validate(
        {"feedback": [{"elev": 1, "text": OK_TEXT},
                      {"elev": 1, "text": OK_TEXT}]})
    assert [f["code"] for f in elev_feedback.validate_feedback(svar, 1)] == ["elev"]


# ── Loopen ──────────────────────────────────────────────────────────────────

def test_jargong_kostar_en_reparationsrunda():
    res = elev_feedback.generate_feedback(
        RADER, [_elev(FULLT, "A")], granser=GRANSER,
        llm=_svarare(_svar("Utveckla din procedurförmåga."), _svar(OK_TEXT)))
    assert res["errors"] == [] and res["rounds"] == 2
    assert res["feedback"] == {0: OK_TEXT}


def test_kvarstaende_fel_redovisas_arligt():
    trasigt = _svar("Din förmåga är god.")
    res = elev_feedback.generate_feedback(
        RADER, [_elev(FULLT, "A")], granser=GRANSER,
        llm=_svarare(trasigt, trasigt, trasigt))
    assert [f["code"] for f in res["errors"]] == ["jargong"]
    assert res["rounds"] == elev_feedback.MAX_ROUNDS


def test_svar_utan_json_ger_ett_arligt_fel():
    res = elev_feedback.generate_feedback(
        RADER, [_elev(FULLT)], granser=GRANSER,
        llm=_svarare("hej", "hej", "hej"))
    assert res["feedback"] == {} and res["errors"][0]["code"] == "json"


def test_json_i_en_mening_plockas_ut():
    res = elev_feedback.generate_feedback(
        RADER, [_elev(FULLT)], granser=GRANSER,
        llm=_svarare("Här är svaret: " + _svar(OK_TEXT) + " Hoppas det hjälper!"))
    assert res["feedback"] == {0: OK_TEXT}


def test_indexet_ar_nollbaserat_och_pekar_in_i_listan():
    """Rutten håller mappningen index→elev. Blir den ett steg fel får halva
    klassen någon annans kommentar."""
    res = elev_feedback.generate_feedback(
        RADER, [_elev(FULLT, "A"), _elev(HALVT, "E")], granser=GRANSER,
        llm=_svarare(_svar("Allt satt. Bra jobbat.", "Räkningen sitter. "
                           "Träna på att motivera dina svar.")))
    assert set(res["feedback"]) == {0, 1}
    assert res["feedback"][1].startswith("Räkningen sitter")


def test_utan_elever_anropas_ingen_modell():
    def sprickan(*_a, **_k):
        raise AssertionError("modellen anropades utan elever")
    res = elev_feedback.generate_feedback(RADER, [], granser=GRANSER,
                                          llm=sprickan)
    assert res == {"feedback": {}, "errors": [], "rounds": 0}


# ── Hela vägen ──────────────────────────────────────────────────────────────

def _spara(client, dokument):
    return client.post("/api/dokument",
                       json={"dokument": dokument, "status": "godkant"}).json()["id"]


def _events(resp):
    return [json.loads(rad[len("data:"):])
            for rad in resp.text.splitlines() if rad.startswith("data:")]


def _done(resp):
    evs = [e for e in _events(resp) if e["type"] == "done"]
    assert evs, _events(resp)
    return evs[0]["result"]


NAMN = ["Alva Nyström", "Elis Hedlund"]


@pytest.fixture
def rattat_prov(llm_ready):
    """Ett prov med två rättade elever — och en fångad prompt."""
    client = llm_ready
    did = _spara(client, {"typ": "Prov", "moment": "derivata", "klass": "NA25",
                          "kurs": "Matematik, nivå 2c", "uppgifter": UPPGIFTER})
    gid = client.get(f"/api/dokument/{did}/elevresultat").json()["group_id"]
    elever = client.put(f"/api/groups/{gid}/elever",
                        json={"namn": NAMN}).json()["elever"]
    client.put(f"/api/dokument/{did}/elevresultat",
               json={"resultat": {elever[0]["id"]: FULLT,
                                  elever[1]["id"]: HALVT}})
    return client, did, elever


def _fanga(monkeypatch, *svar):
    """Kör den RIKTIGA generatorn med en stubbad modell och spara prompten."""
    fangat = {}
    riktig = elev_feedback.generate_feedback

    def wrapper(rader, elever, **kw):
        def llm(_model, prompt, **_kw):
            fangat.setdefault("prompter", []).append(prompt)
            return svar[min(len(fangat["prompter"]) - 1, len(svar) - 1)]
        return riktig(rader, elever, llm=llm, **kw)

    monkeypatch.setattr(elev_feedback, "generate_feedback", wrapper)
    return fangat


def test_inget_elevnamn_nar_modellen(rattat_prov, monkeypatch):
    """Lärarens hårda regel. Modellen ser «Elev 1» och «Elev 2» — inget mer."""
    client, did, _elever = rattat_prov
    fangat = _fanga(monkeypatch, _svar(OK_TEXT, OK_TEXT))
    _done(client.post(f"/api/dokument/{did}/elevfeedback", json={}))
    prompt = "\n".join(fangat["prompter"])
    for namn in NAMN:
        assert namn not in prompt
        for del_ in namn.split():
            assert del_ not in prompt
    assert "Elev 1 (betyg A" in prompt and "Elev 2 (betyg E" in prompt


def test_texten_namnkopplas_forst_i_databasen(rattat_prov, monkeypatch):
    client, did, elever = rattat_prov
    _fanga(monkeypatch, _svar("Allt satt. Bra jobbat.",
                              "Räkningen sitter. Träna på att motivera."))
    res = _done(client.post(f"/api/dokument/{did}/elevfeedback", json={}))
    assert res["feedback"] == {str(elever[0]["id"]): "Allt satt. Bra jobbat.",
                               str(elever[1]["id"]):
                                   "Räkningen sitter. Träna på att motivera."}
    # Och den ligger kvar på provet.
    igen = client.get(f"/api/dokument/{did}/elevresultat").json()["feedback"]
    assert igen == res["feedback"]


def test_elev_utan_poang_utelamnas_ur_prompten(llm_ready, monkeypatch):
    """«Skrev inte provet» — då finns hon inte att skriva om."""
    client = llm_ready
    did = _spara(client, {"typ": "Prov", "moment": "derivata", "klass": "NA25",
                          "uppgifter": UPPGIFTER})
    gid = client.get(f"/api/dokument/{did}/elevresultat").json()["group_id"]
    elever = client.put(f"/api/groups/{gid}/elever",
                        json={"namn": NAMN}).json()["elever"]
    client.put(f"/api/dokument/{did}/elevresultat",
               json={"resultat": {elever[0]["id"]: FULLT, elever[1]["id"]: {}}})
    fangat = _fanga(monkeypatch, _svar(OK_TEXT))
    res = _done(client.post(f"/api/dokument/{did}/elevfeedback", json={}))
    assert "Elev 2" not in fangat["prompter"][0]
    assert list(res["feedback"]) == [str(elever[0]["id"])]
