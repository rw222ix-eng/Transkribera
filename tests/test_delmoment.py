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

# ══════════════════════════════════════════════════════════════════════════
# SPÅR 5 (2026-09-13): domarna släppte igenom uppgifter som inte hörde till
# kapitlet och som var otydligt skrivna.
#
# Prov 81 genererades MED delmomenten aktiva (spår 4) och hade ändå kvar:
#   uppgift 9   ren aritmetik i fyra steg, ingen variabel, inget uttryck, och
#               två rimliga läsningar med olika svar. Godkänd som «Uttryck».
#   uppgift 11  a) en potensekvation (kapitel 2, s. 50–52, lektionen 23/9,
#               alltså efter provet), b) procentuell förändring (kap 3).
# Läraren: «hur kan det ens hända att provet genererar uppgifter som inte är
# ur kapitel ett alls? … otydligt skrivna, väldigt mycket information, man vet
# inte riktigt vad man ska göra.»
# ══════════════════════════════════════════════════════════════════════════

def _forbjudna():
    return exam_gen.rensa_forbjudna(
        exam_gen.forbjudna_ur_lektioner(LEKTIONER, till=40,
                                        provdatum="2026-09-16"),
        _delmoment())


# ── förbudslistan ur basen ───────────────────────────────────────────────

def test_forbudet_ar_lektionerna_efter_provet_pa_senare_sidor():
    """Precis det prov 81 krävde utan att ha gått igenom."""
    assert [(f["metod"], f["sidor"]) for f in _forbjudna()] == [
        ("Ekvationer och balansmetoden", "42–45"),
        ("Ekvationer med parenteser och bråk", "46–49")]


def test_en_lektion_klassen_hunnit_med_ar_inte_forbjuden():
    """Två villkor, inte ett: sidorna efter spannet OCH datumet efter provet.
    Hann klassen med kapitel 2 innan provet är metoden undervisad."""
    tidigt = [dict(r, datum="2026-09-01") for r in LEKTIONER]
    assert exam_gen.forbjudna_ur_lektioner(tidigt, till=40,
                                           provdatum="2026-09-16") == []
    # Och en repetition av kapitel 1 EFTER provdagen är ingen ny metod:
    # sidorna ligger i spannet.
    sent = [{"datum": "2026-09-20", "fran": 2, "till": 40,
             "rubrik": "Kvadratrötter"}]
    assert exam_gen.forbjudna_ur_lektioner(sent, till=40,
                                           provdatum="2026-09-16") == []


def test_samma_rubrik_kan_inte_bade_kravas_och_vara_forbjuden():
    """«Grundpotensform» står både som lektion i kapitel 1 och längre fram i
    boken. Stod den i båda listorna skulle prompten säga två saker om samma
    sak, och modellen fick välja."""
    krock = [{"metod": "Grundpotensform", "sidor": "80–82"},
             {"metod": "Olikheter", "sidor": "58–63"}]
    assert exam_gen.rensa_forbjudna(krock, _delmoment()) == \
        [{"metod": "Olikheter", "sidor": "58–63"}]


def test_forbudet_kapas_vid_taket_i_bokens_ordning():
    """Resten av boken är fem kapitel. De närmaste är de som läcker in."""
    manga = [{"datum": "2026-10-01", "fran": 40 + i, "till": 40 + i,
              "rubrik": f"Metod {i}"} for i in range(1, 40)]
    ut = exam_gen.forbjudna_ur_lektioner(manga, till=40,
                                         provdatum="2026-09-16")
    assert len(ut) == 39
    kapat = exam_gen.rensa_forbjudna(ut)
    assert len(kapat) == exam_gen.FORBJUDET_TAK
    assert kapat[0]["metod"] == "Metod 1"


def test_bokens_egna_avsnitt_ar_reserven():
    """Utan synkad kalender vet boken ändå vad som kommer efter kapitlet."""
    avsnitt = [{"nr": "1.3", "titel": "Uttryck", "fran": 22, "till": 41},
               {"nr": "2.1", "titel": "Ekvationer", "fran": 42, "till": 52},
               {"nr": "2.4", "titel": "Olikheter", "fran": 58, "till": 63}]
    assert exam_gen.forbjudna_ur_avsnitt(avsnitt, till=41) == [
        {"metod": "Ekvationer", "sidor": "42–52"},
        {"metod": "Olikheter", "sidor": "58–63"}]
    assert exam_gen.forbjudna_ur_avsnitt([], till=41) == []


# ── förbudet i prompten och i domen ──────────────────────────────────────

def test_forbudsblocket_fragar_efter_LOSNINGEN_inte_amnet():
    """Uppgift 11 a) handlade om potenser, alltså rätt ämne, och gick ändå
    bara att lösa med en potensekvation. Frågan måste vara «vad krävs för att
    komma i mål», inte «vad handlar den om»."""
    r = exam_gen.build_forbjudet(_forbjudna())
    assert "Ekvationer och balansmetoden (s. 42–45)" in r
    assert "HELT UTAN" in r and "ETT steg" in r


def test_prompten_ar_byteidentisk_utan_forbud_och_utan_forebild():
    """Kassettregeln, en gång till: tomma listor ska ge exakt den prompt som
    gick i väg innan spår 5 fanns."""
    assert exam_gen.build_forbjudet([]) == ""
    assert exam_gen.build_forebild_prov([]) == ""
    argument = dict(kurs="Ma1c", klass="TE26A", punkter=["potenser"], antal=12)
    utan = exam_gen.build_prompt(**argument)
    assert exam_gen.build_prompt(**argument, forbjudet="", forebild="") == utan
    med = exam_gen.build_prompt(**argument,
                                forbjudet=exam_gen.build_forbjudet(
                                    _forbjudna()))
    assert med != utan and "Ekvationer och balansmetoden" in med


def test_domaren_far_samma_forbudslista_som_skrivningen():
    """En domare som bara vet vad som ÄR undervisat måste gissa var gränsen
    går åt andra hållet, och prov 81 visar vad gissningen kostar."""
    svar = json.dumps({"saknas": [],
                       "utanfor": [{"nr": "11", "metod": "potensekvation"}]})
    llm, anrop = _stub_llm([svar])
    fel = exam_gen.doma_delmoment(_prov(), _delmoment(), model="m",
                                  forbjudna=_forbjudna(), llm=llm)
    assert "Ekvationer och balansmetoden (s. 42–45)" in anrop[0]["prompt"]
    assert "FÖRBJUDNA METODER" in anrop[0]["prompt"]
    assert len(fel) == 1 and "potensekvation" in fel[0]["message"]
    # Utan listan står prompten kvar som den var, byte för byte.
    llm2, anrop2 = _stub_llm([svar])
    exam_gen.doma_delmoment(_prov(), _delmoment(), model="m", llm=llm2)
    assert "FÖRBJUDNA METODER" not in anrop2[0]["prompt"]


# ── provets bokförebild ──────────────────────────────────────────────────

def _bokuppgifter():
    return [{"nr": 1112, "sida": 4, "niva": 2, "text": "Lotte påstår att …"},
            {"nr": 34, "sida": 38, "niva": 2, "text": "Bestäm två heltal …"}]


def test_provet_far_kapitlets_uppgifter_som_forebilder():
    r = exam_gen.build_forebild_prov(_bokuppgifter())
    assert "1112" in r and '"sida"' in r      # numren krockar utan sidan
    assert "FÖREBILD" in r and "forebild" in r
    # Provets block är inte gruppuppgiftens: ingen rad om lärarens remsa, och
    # ingen FOREBILD_UTAN_BOK när listan är tom.
    assert "remsa" not in r


def test_forebildsfaltet_star_i_grammatiken_nar_prompten_ber_om_det():
    """Regeln är promptens egen: fältet ska finnas exakt när det som skickas
    nämner det. Antingen uppdraget som ber om en förebild, eller pappret som
    redan bär
    en (reparation, omskrivning, latexfix)."""
    assert exam_gen._forebild_i_grammatiken(
        exam_gen.build_forebild_prov(_bokuppgifter()), "prov")
    assert not exam_gen._forebild_i_grammatiken("skriv ett prov", "prov")
    assert exam_gen._forebild_i_grammatiken("skriv ett prov", "gruppuppgift")
    # Reparationsprompten bäddar in dokumentet: bär det en förebild ska
    # grammatiken behålla fältet, annars faller pekningen bort tyst.
    doc = copy.deepcopy(_prov())
    doc["uppgifter"][0]["forebild"] = {"nr": 1112, "sort": "samma sort"}
    assert exam_gen._forebild_i_grammatiken(
        exam_gen.build_repair_prompt(doc, [], "prov"), "prov")


def test_taket_vinner_over_forebilden_pa_ett_stort_prov():
    """Fältet kostar en kopia per uppgift. Spricker kommandoradens tak går
    HELA schemat i prompten och grammatiktvånget tappas för varje uppgift.
    En pekning på boken är inte värd den bytesaffären."""
    from app import claude_code, course_data, exam_spec
    koder = [p["kod"] for p in course_data._kursens_punkter("Matematik 1c")]
    for antal, vantat in ((12, True), (20, False)):
        sk = exam_spec.balanced_skeleton(antal, "prov", delar=True,
                                         kurs="Matematik 1c")
        schema = exam_spec.to_response_format(antal, sk, koder,
                                              forebild=True)["json_schema"]["schema"]
        assert ('"forebild"' in json.dumps(schema)) is vantat
        assert claude_code.schemalangd(schema) <= claude_code.SCHEMA_TAK_EXE


# ── provets text: begripligheten ─────────────────────────────────────────

def _kafe():
    """Uppgift 9 ur prov 81, ordagrant. Trettioåtta ord förutsättning innan
    frågan kommer, och två rimliga läsningar: räknas inköpet det första året,
    och är det en diskning per kopp?"""
    return {"titel": "Prov", "uppgifter": [{
        "del": "C", "poang": [0, 1, 0],
        "text": ("Ett kafé serverar $185$ koppar kaffe per dag, $6$ dagar i "
                 "veckan och $48$ veckor per år. En engångsmugg kostar "
                 "$1{,}35$ kr. Flergångsmuggar kostar $4\\,800$ kr att köpa "
                 "in och $0{,}22$ kr per diskning. Bestäm hur mycket kaféet "
                 "sparar under ett år."),
        "losning": "…"}]}


def _stenhuggeri():
    """Uppgift 11 a) ur prov 81, ordagrant. Fyrtiotvå ord förutsättning innan
    frågan kommer, och det står inte vad eleven ska göra förrän i sista
    raden."""
    return {"titel": "Prov", "uppgifter": [{
        "del": "C", "poang": [0, 0, 0],
        "text": ("Ett stenhuggeri tillverkar kuber av granit. Massan $m$ gram "
                 "ges av $m = 2{,}7s^{3}$ där $s$ cm är kubens sida."),
        "deluppgifter": [{
            "poang": [0, 1, 0],
            "text": ("Två kuber väger tillsammans $3{,}0$ kg. Den ena kubens "
                     "sida är dubbelt så lång som den andras. Bestäm den "
                     "mindre kubens sida."),
            "losning": "…"}]}]}


def test_vakten_matter_hur_mycket_text_som_star_fore_fragan():
    """Det mätbara i lärarens «väldigt mycket information». Taket är satt så
    att uppgift 11 (42 ord) faller och uppgift 9 (38) klaras av domaren i
    stället: en vakt som fäller halva provet blir en vakt hon slutar tro på."""
    fel = exam_gen.begriplighetssignaler(_stenhuggeri(), "prov")
    assert len(fel) == 1 and fel[0]["code"] == "begriplighet"
    assert f"taket är {exam_gen.ORD_FORE_FRAGAN}" in fel[0]["message"]
    assert exam_gen.begriplighetssignaler(_kafe(), "prov") == []
    # En kort uppgift går fri, och gruppuppgiftens egna mått rörs inte.
    assert exam_gen.begriplighetssignaler(_prov(), "prov") == []
    assert exam_gen.begriplighetssignaler(_stenhuggeri(), "arbetsblad") == []


def test_provets_begriplighetsdomare_har_lararens_fem_krav():
    p = exam_gen.build_begriplighet_prompt([{"nr": "1", "text": "x"}], "",
                                           "prov")
    assert "begriplighetsdomare" in p           # bandvalet i tests/fejk.py
    for krav in ("EN SITUATION", "EN FRÅGA", "ALLA TAL SOM BEHÖVS",
                 "ENTYDIG TOLKNING", str(exam_gen.ORD_FORE_FRAGAN)):
        assert krav in p
    # Gruppuppgiftens prompt är orörd: fyra elever vid ett bord, uppgift 2
    # hårdast. Byte för byte den som spelades in.
    g = exam_gen.build_begriplighet_prompt([{"nr": "1", "text": "x"}])
    assert "Fyra elever" in g and "UPPGIFT 2" in g and "EN SITUATION" not in g


def test_provets_relevansdomare_domer_pa_losningen_inte_amnet():
    p = exam_gen.build_relevans_prompt([{"nr": "1", "text": "x"}],
                                       _bokuppgifter(), profil="prov")
    assert "ett prov i matematik" in p
    assert "Räkna igenom lösningen" in p
    g = exam_gen.build_relevans_prompt([{"nr": "1", "text": "x"}],
                                       _bokuppgifter())
    assert "grupparbetspapper" in g and "Räkna igenom lösningen" not in g


# ── allt i EN reparationsrunda ───────────────────────────────────────────

def test_de_tre_domarna_gar_i_samma_reparationsprompt():
    """Lärarens två klagomål är samma sorts fel: uppgiften ska bytas eller
    skrivas om, inte provet. Tre domaranrop, EN reparation."""
    delmomentdom = json.dumps({"saknas": [{"delmoment": "Kubikrötter",
                                           "byt": "1"}]})
    relevansdom = json.dumps({"domar": [{"nr": "1", "dom": "annan sort",
                                         "battre": "1112",
                                         "skal": "ingen sådan i kapitlet"}]})
    begripdom = json.dumps({"domar": [{"nr": "1", "forstar": "nej",
                                       "stor": "två läsningar"}]})
    llm, anrop = _stub_llm([delmomentdom, relevansdom, begripdom,
                            json.dumps(_stenhuggeri())])
    res = exam_gen._tackning_pass(_stenhuggeri(), [], model="m", llm=llm,
                                  profil="prov", antal=1, skeleton=None,
                                  avsnitt=[], delmoment=_delmoment(),
                                  forbjudna=_forbjudna(),
                                  bokuppgifter=_bokuppgifter(),
                                  rounds_used=1, max_rounds=4)
    assert len(anrop) == 4, [a["prompt"][:40] for a in anrop]
    reparationen = anrop[3]["prompt"]
    assert "Kubikrötter" in reparationen              # delmomentsluckan
    assert "annan sort" in reparationen or "förebild" in reparationen
    assert "ord förutsättning" in reparationen        # den mätta vakten
    assert "två läsningar" in reparationen            # begriplighetsdomen
    assert res["rounds"] == 2


def test_provet_utan_bokdorr_kostar_precis_de_anrop_det_kostade_forut():
    """Kassettregeln. Utan kapitlets uppgifter finns ingen bokgrind, och
    prompten och anropen ska vara exakt de som spelades in."""
    llm, anrop = _stub_llm([json.dumps({"saknas": []})])
    exam_gen._tackning_pass(_stenhuggeri(), [], model="m", llm=llm,
                            profil="prov",
                            antal=1, skeleton=None, avsnitt=[],
                            delmoment=_delmoment(), rounds_used=1,
                            max_rounds=4)
    assert len(anrop) == 1 and "delmomentsdomare" in anrop[0]["prompt"]

# ── vägen från basen ─────────────────────────────────────────────────────

def test_rutten_ger_forbudet_ur_kalendern_och_boken(tmp_path):
    db_file = tmp_path / "t.db"
    conn = db.connect(db_file)
    try:
        bid = db.create_bok(conn, namn="Liber Ma 1c", kurs="Matematik 1c")["id"]
        db.set_bok_register(conn, bid, [
            {"nr": "1.3", "titel": "Uttryck", "fran": 22, "till": 41},
            {"nr": "2.1", "titel": "Ekvationer", "fran": 42, "till": 52},
            {"nr": "2.4", "titel": "Olikheter", "fran": 58, "till": 63}])
        db.replace_lektionsinnehall(conn, [
            dict(r, klass="TE26A", kurs="Matematik 1c") for r in LEKTIONER])
        gid = db.get_or_create_group(conn, "TE26A")
        cid = db.get_or_create_course(conn, "Matematik 1c")
    finally:
        conn.close()
    kropp = {"bok": {"id": bid, "fran": 2, "till": 40}, "datum": "2026-09-16"}
    # Kalendern först: lärarens egna rubriker för det som kommer efter provet.
    assert [f["metod"] for f in routes_planning.forbjudna_metoder(
        db_file, kropp, group_id=gid, course_id=cid,
        undervisade=_delmoment())] == ["Ekvationer och balansmetoden",
                                       "Ekvationer med parenteser och bråk"]
    # Utan kalender: bokens egna avsnitt efter spannet.
    assert [f["metod"] for f in routes_planning.forbjudna_metoder(
        db_file, kropp, group_id=None, course_id=None)] == ["Ekvationer",
                                                            "Olikheter"]
    # Ingen bokdörr: tyst, och prompten är då den gamla.
    assert routes_planning.forbjudna_metoder(
        db_file, {"datum": "2026-09-16"}, group_id=gid, course_id=cid) == []


def test_provets_forebilder_tar_bokens_repetitionssidor_forst(tmp_path):
    """Blandade uppgifter och kapiteltestet är läromedlets eget prov på
    kapitlet, och läraren höll dem som lektion veckan före provet."""
    from app import bok
    sidor = ([{"sida": n, "rubrik": "Uttryck",
               "text": f"## EXEMPEL OCH UPPGIFTER\n13{n:02d} Förenkla."}
              for n in range(22, 35)]
             + [{"sida": 36, "rubrik": "Blandade uppgifter",
                 "text": "## EXEMPEL OCH UPPGIFTER\n15 Förenkla uttrycket."},
                {"sida": 39, "rubrik": "Kapiteltest",
                 "text": "## EXEMPEL OCH UPPGIFTER\n3 Skriv som en potens."}])
    uppg = ([{"nr": 1300 + n, "sida": n, "niva": 1, "exempel": 0}
             for n in range(22, 35)]
            + [{"nr": 15, "sida": 36, "niva": 1, "exempel": 0},
               {"nr": 3, "sida": 39, "niva": 1, "exempel": 0},
               {"nr": 9, "sida": 39, "niva": 1, "exempel": 1}])
    ut = bok.provuppgifter(sidor, uppg, antal=6)
    assert len(ut) == 6
    # Bägge repetitionssidorna med, exemplet bort, och sidan följer med varje
    # rad: numren krockar (nr 3 finns både i kapiteltestet och som 1303).
    assert (36, 15) in [(r["sida"], r["nr"]) for r in ut]
    assert (39, 3) in [(r["sida"], r["nr"]) for r in ut]
    assert 9 not in [r["nr"] for r in ut]
    assert bok.provuppgifter([], [], antal=6) == []
