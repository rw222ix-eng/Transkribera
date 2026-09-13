"""Delmomenttäckningen (spår 4, 2026-09-13).

Kapitelramen sprider provet över AVSNITTEN. Prov 44 (TE26A, Ma 1c, 16/9) var
nöjt på den nivån — 2/5/5 uppgifter över 1.1/1.2/1.3 — och missade ändå
faktorisering och förkortning, prefix och enheter och kubikrötterna, alltså
tre av de tolv lektioner klassen faktiskt hade haft. Dessutom krävde två
uppgifter metoder ur kapitel 2 och 3.

Testerna prövar de tre delarna var för sig: listan ur basen (ren logik),
promptblocket (och att prompten är BYTE-IDENTISK utan delmoment) och domaren
med stubbad llm. Inga skarpa modellanrop.
"""
import copy
import json

from app import db, exam_gen
from app.web import routes_planning


# TE26A:s riktiga kalenderrader för Ma 1c, kapitel 1 (s. 2–40), som de står i
# lektionsinnehall. Bara de fält delmomenten läser — datum, sidor, rubrik och
# delar. Två rader ligger EFTER provet (21/9, 22/9) och två utanför spannet:
# båda sorterna ska falla bort.
LEKTIONER = [
    {"datum": "2026-08-24", "fran": 2, "till": 4, "rubrik": "Kvadratrötter",
     "delar": [{"fran": 2, "till": 4, "uppg": "1101–1103"}]},
    {"datum": "2026-08-25", "fran": 5, "till": 9,
     "rubrik": "Kubikrötter. Potenser",
     "delar": [{"fran": 5, "till": 6, "rubrik": "Kubikrötter"},
               {"fran": 7, "till": 9, "rubrik": "Potenser"}]},
    {"datum": "2026-08-26", "fran": 10, "till": 11, "rubrik": "Potenslagar",
     "delar": [{"fran": 10, "till": 11}]},
    {"datum": "2026-08-28", "fran": 12, "till": 13,
     "rubrik": "Grundpotensform", "delar": [{"fran": 12, "till": 13}]},
    {"datum": "2026-08-31", "fran": 14, "till": 15,
     "rubrik": "Grundpotensform, prefix och enheter",
     "delar": [{"fran": 14, "till": 15}]},
    {"datum": "2026-09-01", "fran": 16, "till": 18,
     "rubrik": "Exponenter som inte är heltal",
     "delar": [{"fran": 16, "till": 18}]},
    {"datum": "2026-09-02", "fran": 19, "till": 21,
     "rubrik": "Programmering och kalkylblad i GeoGebra",
     "delar": [{"fran": 19, "till": 21}, {"fran": 21, "till": 21}]},
    {"datum": "2026-09-04", "fran": 22, "till": 25, "rubrik": "Uttryck",
     "delar": [{"fran": 22, "till": 25}]},
    {"datum": "2026-09-07", "fran": 26, "till": 30,
     "rubrik": "Förenkling av uttryck och parenteser",
     "delar": [{"fran": 26, "till": 30}]},
    {"datum": "2026-09-08", "fran": 31, "till": 34,
     "rubrik": "Faktorisering och förkortning",
     "delar": [{"fran": 31, "till": 34}]},
    {"datum": "2026-09-09", "fran": 36, "till": 38,
     "rubrik": "Repetition kap 1 – blandade uppgifter",
     "delar": [{"fran": 36, "till": 38}]},
    {"datum": "2026-09-11", "fran": 39, "till": 40,
     "rubrik": "Repetition kap 1 – kapiteltest",
     "delar": [{"fran": 39, "till": 40}]},
    {"datum": "2026-09-21", "fran": 42, "till": 45,
     "rubrik": "Ekvationer och balansmetoden",
     "delar": [{"fran": 42, "till": 45}]},
    {"datum": "2026-09-22", "fran": 46, "till": 49,
     "rubrik": "Ekvationer med parenteser och bråk",
     "delar": [{"fran": 46, "till": 49}]},
]

# Precis det läraren räknade upp: de undervisade delmomenten i bokens ordning,
# utan programmeringslektionen och utan de två repetitionerna.
VANTADE = [
    ("Kvadratrötter", "2–4"),
    ("Kubikrötter", "5–6"),
    ("Potenser", "7–9"),
    ("Potenslagar", "10–11"),
    ("Grundpotensform", "12–13"),
    ("Grundpotensform, prefix och enheter", "14–15"),
    ("Exponenter som inte är heltal", "16–18"),
    ("Uttryck", "22–25"),
    ("Förenkling av uttryck och parenteser", "26–30"),
    ("Faktorisering och förkortning", "31–34"),
]


def _delmoment():
    return exam_gen.delmoment_ur_lektioner(LEKTIONER, fran=2, till=40,
                                           provdatum="2026-09-16")


def _stub_llm(svar: list[str]):
    anrop: list[dict] = []

    def llm(model, prompt, system=None, options=None, response_format=None,
            max_tokens=None, token_cb=None):
        anrop.append({"prompt": prompt, "system": system})
        return svar[min(len(anrop) - 1, len(svar) - 1)]

    return llm, anrop


# ── listan ur basen ──────────────────────────────────────────────────────

def test_delmomenten_for_te26a_ar_lektionerna_fore_provet_i_spannet():
    assert [(d["delmoment"], d["sidor"]) for d in _delmoment()] == VANTADE


def test_lektionen_efter_provdagen_ar_inte_undervisad():
    """En lektion som ligger efter provet har inte hållits, och ett prov får
    aldrig kräva den. 21/9 är balansmetoden — precis den sorts metod prov 44
    krävde utan att ha gått igenom."""
    namn = [d["delmoment"] for d in _delmoment()]
    assert "Ekvationer och balansmetoden" not in namn
    # Utan provdatum finns ingen gräns — men sidspannet håller ändå ute kap 2.
    fritt = exam_gen.delmoment_ur_lektioner(LEKTIONER, fran=2, till=40)
    assert "Ekvationer och balansmetoden" not in \
        [d["delmoment"] for d in fritt]
    vitt = exam_gen.delmoment_ur_lektioner(LEKTIONER, fran=2, till=99)
    assert "Ekvationer och balansmetoden" in [d["delmoment"] for d in vitt]


def test_delarnas_egna_rubriker_vinner_over_lektionens():
    """25/8 heter «Kubikrötter. Potenser» i kalendern men är två delmoment med
    var sitt sidspann — och det är de två läraren undervisade."""
    namn = [d["delmoment"] for d in _delmoment()]
    assert "Kubikrötter. Potenser" not in namn
    assert namn.index("Kubikrötter") + 1 == namn.index("Potenser")


def test_det_som_inte_gar_att_prova_pa_papper_faller_bort():
    namn = [d["delmoment"] for d in _delmoment()]
    assert not [n for n in namn if "Programmering" in n or "Repetition" in n]
    assert exam_gen.delmoment_ur_lektioner(
        [{"datum": "2026-09-01", "fran": 2, "till": 3,
          "rubrik": "Kapiteltest kap 1"}], fran=2, till=40) == []


def test_samma_rubrik_tva_dagar_ar_ett_delmoment_med_hela_spannet():
    """En lektion som fortsatte dagen efter är ETT delmoment — annars hade
    prompten bett om två uppgifter på samma sak."""
    rader = [{"datum": "2026-09-01", "fran": 4, "till": 5, "rubrik": "Potenser"},
             {"datum": "2026-09-02", "fran": 6, "till": 8, "rubrik": "potenser"}]
    assert exam_gen.delmoment_ur_lektioner(rader, fran=2, till=40) == \
        [{"delmoment": "Potenser", "sidor": "4–8"}]


def test_raderna_utan_delar_och_med_trasiga_sidor_bar_anda_sitt_moment():
    """Kalendern är inte städad: en rad kan sakna `delar` helt, och en del kan
    sakna sidor. Raden är ändå sann i lektionens eget spann."""
    rader = [{"datum": "2026-09-01", "fran": 12, "till": 12,
              "rubrik": "Grundpotensform"},
             {"datum": "2026-09-02", "fran": 13, "till": 14,
              "rubrik": "Prefix", "delar": [{"rubrik": "Prefix"}]},
             {"datum": "2026-09-03", "fran": 15, "till": 15, "rubrik": "",
              "delar": [{"fran": "x", "till": "y"}]}]
    assert exam_gen.delmoment_ur_lektioner(rader, fran=2, till=40) == [
        {"delmoment": "Grundpotensform", "sidor": "12"},
        {"delmoment": "Prefix", "sidor": "13–14"}]


def test_bokens_underrubriker_ar_reserven():
    """Utan synkad kalender vet boken ändå vad kapitlet består av."""
    sidor = [{"sida": 2, "rubrik": "Kvadratrötter"},
             {"sida": 3, "rubrik": "Kvadratrötter"},
             {"sida": 4, "rubrik": ""},                # oläst: hoppas över
             {"sida": 5, "rubrik": "Kubikrötter"},
             {"sida": 19, "rubrik": "Programmering i GeoGebra"}]
    assert exam_gen.delmoment_ur_sidor(sidor) == [
        {"delmoment": "Kvadratrötter", "sidor": "2–3"},
        {"delmoment": "Kubikrötter", "sidor": "5"}]
    assert exam_gen.delmoment_ur_sidor([]) == []


# ── promptblocket ────────────────────────────────────────────────────────

def test_blocket_kraver_bade_tackning_och_ingen_metod_utanfor():
    r = exam_gen.build_delmoment(_delmoment(), 12)
    assert "Faktorisering och förkortning (s. 31–34)" in r
    assert "MINST EN uppgift" in r and "12" in r
    assert "UTANFÖR" in r and "olikheter" in r
    # Den beskurna listan får inte läsas som «resten ska prövas ändå».
    assert "programmering" in r and "Det betyder INTE" in r


def test_prompten_ar_byteidentisk_nar_delmoment_saknas():
    """Kassettregeln. Tom lista ska ge exakt den prompt som gick i väg innan
    blocket fanns — annars är varje inspelat band omspelningsmoget."""
    assert exam_gen.build_delmoment([], 12) == ""
    argument = dict(kurs="Ma1c", klass="TE26A", punkter=["potenser"],
                    antal=12)
    utan = exam_gen.build_prompt(**argument)
    tomt = exam_gen.build_prompt(**argument, delmoment="")
    assert utan == tomt
    med = exam_gen.build_prompt(**argument,
                                delmoment=exam_gen.build_delmoment(
                                    _delmoment(), 12))
    assert med != utan and "Kubikrötter" in med


# ── domaren ──────────────────────────────────────────────────────────────

def _prov() -> dict:
    return {"titel": "Prov: Kapitel 1", "uppgifter": [
        {"del": "A", "poang": [2, 0, 0], "text": "Beräkna $\\sqrt{49}$.",
         "losning": "7"},
        {"del": "B", "poang": [0, 3, 0], "text": "Förenkla $x^2 \\cdot x^5$.",
         "losning": "$x^7$"}]}


def test_domaren_ger_fynd_i_samma_form_som_avsnittstackningen():
    svar = json.dumps({"saknas": [{"delmoment": "Kubikrötter", "byt": "2"},
                                  {"delmoment": "Uttryck"}],
                       "utanfor": [{"nr": "2", "metod": "olikheter"}]})
    llm, anrop = _stub_llm([svar])
    fel = exam_gen.doma_delmoment(_prov(), _delmoment(), model="m", llm=llm)
    assert len(anrop) == 1 and "delmomentsdomare" in anrop[0]["prompt"]
    assert [f["code"] for f in fel] == ["delmomenttackning"] * 3
    # Sidspannet står i fyndet, och ordern är BYT UT — inte «lägg till».
    assert "Kubikrötter (s. 5–6)" in fel[0]["message"]
    assert "Byt UT uppgift 2" in fel[0]["message"]
    assert "Lägg INTE till" in fel[0]["message"]
    assert "flest" in fel[1]["message"]        # utan «byt» i domen
    assert "olikheter" in fel[2]["message"] and fel[2]["path"] == "uppgift 2"


def test_domaren_hittar_inte_pa_ett_delmoment_som_ingen_lektion_hade():
    llm, _ = _stub_llm([json.dumps({"saknas": [{"delmoment": "Derivata"}]})])
    assert exam_gen.doma_delmoment(_prov(), _delmoment(), model="m",
                                   llm=llm) == []


def test_domaren_ar_fail_open():
    """Ett domarfel fäller aldrig ett papper som redan är skrivet."""
    for svar in ("inte json alls", "{}", json.dumps({"saknas": "trasigt"})):
        llm, _ = _stub_llm([svar])
        assert exam_gen.doma_delmoment(_prov(), _delmoment(), model="m",
                                       llm=llm) == []

    def dor(*a, **k):
        raise RuntimeError("nätet dog")

    rader = []
    assert exam_gen.doma_delmoment(_prov(), _delmoment(), model="m", llm=dor,
                                   log_cb=rader.append) == []
    assert any("kunde inte nås" in r for r in rader)


def test_domaren_kostar_inget_anrop_utan_lista_eller_utan_uppgifter():
    llm, anrop = _stub_llm(["{}"])
    assert exam_gen.doma_delmoment(_prov(), [], model="m", llm=llm) == []
    assert exam_gen.doma_delmoment({}, _delmoment(), model="m", llm=llm) == []
    assert anrop == []


def test_taket_haller_reparationen_till_ett_byte():
    dom = {"saknas": [{"delmoment": d["delmoment"]} for d in _delmoment()]}
    fel = exam_gen.delmomentfynd(_delmoment(), dom)
    assert len(fel) == exam_gen.DELMOMENT_MAX_FYND


# ── fixrundan: samma runda som avsnittstäckningen ────────────────────────

def _avsnitt():
    return [{"avsnitt": "1.1", "etikett": "1.1 Tal", "fran": 2, "till": 20,
             "sidor": 19},
            {"avsnitt": "1.2", "etikett": "1.2 Uttryck", "fran": 21,
             "till": 40, "sidor": 20}]


def _prov_med_avsnitt(koder: list[str]) -> dict:
    exam = _prov()
    for u, a in zip(exam["uppgifter"], koder):
        u["avsnitt"] = a
    return exam


def test_delmomentsfynden_gar_i_samma_reparationsprompt_som_avsnitten():
    """Lärarens krav: modellen ska BYTA UT uppgifter, inte skriva om provet.
    Alltså ETT anrop till domaren, ETT till reparationen — och båda sorternas
    fynd i samma prompt."""
    dom = json.dumps({"saknas": [{"delmoment": "Kubikrötter", "byt": "1"}]})
    lagat = copy.deepcopy(_prov_med_avsnitt(["1.1", "1.2"]))
    llm, anrop = _stub_llm([dom, json.dumps(lagat)])
    res = exam_gen._tackning_pass(_prov_med_avsnitt(["1.1", "1.1"]), [],
                                  model="m", llm=llm, profil="prov", antal=2,
                                  skeleton=None, avsnitt=_avsnitt(),
                                  delmoment=_delmoment(), rounds_used=1,
                                  max_rounds=4)
    assert len(anrop) == 2
    reparationen = anrop[1]["prompt"]
    assert "1.2 Uttryck" in reparationen and "Kubikrötter" in reparationen
    assert res["rounds"] == 2


def test_domaren_kors_inte_nar_domandet_ar_avstangt():
    """`doma=False` betyder «inga extra modellanrop efter att pappret är
    skrivet», och domaren är ett sådant."""
    llm, anrop = _stub_llm(["{}"])
    res = exam_gen._tackning_pass(_prov_med_avsnitt(["1.1", "1.2"]), [],
                                  model="m", llm=llm, profil="prov", antal=2,
                                  skeleton=None, avsnitt=_avsnitt(),
                                  delmoment=_delmoment(), doma=False,
                                  rounds_used=1, max_rounds=4)
    assert anrop == [] and res["errors"] == []


def test_generate_exam_lagger_blocket_i_prompten():
    llm, anrop = _stub_llm([json.dumps(_prov())])
    exam_gen.generate_exam("Ma1c", "TE26A", ["potenser"], model="m", llm=llm,
                           antal=2, delar=False, doma=False,
                           delmoment=_delmoment(), max_rounds=3)
    assert "DELMOMENTEN KLASSEN FAKTISKT HAR UNDERVISATS I" in anrop[0]["prompt"]
    assert "Kubikrötter (s. 5–6)" in anrop[0]["prompt"]
    # `doma=False` betyder «inga extra modellanrop»: bara skrivningen.
    assert not any("delmomentsdomare" in a["prompt"] for a in anrop)


def test_generate_exam_domer_delmomenten_aven_utan_kapitelram():
    """Listan är domarens EGET kontrakt: den körs också för ett prov utan
    bokens avsnittsram, för det är lektionerna som är löftet."""
    llm, anrop = _stub_llm([json.dumps(_prov())])
    exam_gen.generate_exam("Ma1c", "TE26A", ["potenser"], model="m", llm=llm,
                           antal=2, delar=False, doma=True, illustration=False,
                           delmoment=_delmoment(), max_rounds=2)
    assert any("delmomentsdomare" in a["prompt"] for a in anrop[1:])


# ── vägen från basen ─────────────────────────────────────────────────────

def test_basen_ger_bara_den_egna_klassens_och_kursens_lektioner(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    try:
        db.replace_lektionsinnehall(conn, [
            dict(r, klass="TE26A", kurs="Matematik 1c") for r in LEKTIONER[:3]
        ] + [{"datum": "2026-09-03", "fran": 5, "till": 6, "klass": "NA26B",
              "kurs": "Matematik 1c", "rubrik": "Annan klass"}])
        gid = db.get_or_create_group(conn, "TE26A")
        cid = db.get_or_create_course(conn, "Matematik 1c")
        rader = db.lektionsinnehall_for_kurs(conn, gid, cid)
    finally:
        conn.close()
    assert [r["rubrik"] for r in rader] == [
        "Kvadratrötter", "Kubikrötter. Potenser", "Potenslagar"]
    assert rader[1]["delar"][0]["rubrik"] == "Kubikrötter"
    assert [d["delmoment"] for d in exam_gen.delmoment_ur_lektioner(
        rader, fran=2, till=40, provdatum="2026-09-16")] == [
        "Kvadratrötter", "Kubikrötter", "Potenser", "Potenslagar"]


def test_rutten_faller_tillbaka_pa_boken_och_tiger_utan_bokdorr(tmp_path):
    db_file = tmp_path / "t.db"
    conn = db.connect(db_file)
    try:
        bid = db.create_bok(conn, namn="Liber Ma 1c", kurs="Matematik 1c")["id"]
        db.save_bok_sida(conn, bid, 2, rubrik="Kvadratrötter", avsnitt="1.1")
        db.save_bok_sida(conn, bid, 3, rubrik="Kubikrötter", avsnitt="1.1")
    finally:
        conn.close()
    kropp = {"bok": {"id": bid, "fran": 2, "till": 40},
             "datum": "2026-09-16"}
    # Ingen kalender: boken bär listan.
    assert routes_planning.undervisade_delmoment(
        db_file, kropp, group_id=None, course_id=None) == [
        {"delmoment": "Kvadratrötter", "sidor": "2"},
        {"delmoment": "Kubikrötter", "sidor": "3"}]
    # Ingen bokdörr: tyst, och prompten är då den gamla.
    assert routes_planning.undervisade_delmoment(
        {}, {"datum": "2026-09-16"}, group_id=1, course_id=1) == []


def test_kalendern_vinner_over_boken(tmp_path):
    db_file = tmp_path / "t.db"
    conn = db.connect(db_file)
    try:
        bid = db.create_bok(conn, namn="Liber Ma 1c", kurs="Matematik 1c")["id"]
        db.save_bok_sida(conn, bid, 2, rubrik="Bokens rubrik", avsnitt="1.1")
        db.replace_lektionsinnehall(conn, [
            dict(r, klass="TE26A", kurs="Matematik 1c") for r in LEKTIONER])
        gid = db.get_or_create_group(conn, "TE26A")
        cid = db.get_or_create_course(conn, "Matematik 1c")
    finally:
        conn.close()
    ut = routes_planning.undervisade_delmoment(
        db_file, {"bok": {"id": bid, "fran": 2, "till": 40},
                  "datum": "2026-09-16"}, group_id=gid, course_id=cid)
    assert [(d["delmoment"], d["sidor"]) for d in ut] == VANTADE
