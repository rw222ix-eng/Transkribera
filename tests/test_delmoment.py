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
    svar = json.dumps({"saknas": [], "utanfor": [{"nr": "2",
                                                  "metod": "olikheter"}]})
    llm, anrop = _stub_llm([svar])
    fel = exam_gen.doma_delmoment(_prov(), _delmoment(), model="m", llm=llm)
    assert len(anrop) == 1 and "delmomentsdomare" in anrop[0]["prompt"]
    assert [f["code"] for f in fel] == ["delmomenttackning"]
    assert "olikheter" in fel[0]["message"] and fel[0]["path"] == "uppgift 2"
    # Ordern är BYT UT — inte «lägg till» och inte «skriv om provet».
    assert "Byt UT den" in fel[0]["message"]


def test_domaren_domer_inte_langre_om_tackningen():
    """Fynd 1, den skarpa körningen 2026-09-13: läsaren rapporterade noll
    luckor på ett prov som saknade ett helt delmoment. Frågan är en RÄKNING
    och har flyttat till delmomenttackning — svarar ett gammalt band ändå om
    «saknas» ska det ignoreras, annars står samma lucka två gånger."""
    svar = json.dumps({"saknas": [{"delmoment": "Kubikrötter", "byt": "2"},
                                  {"delmoment": "Uttryck"}], "utanfor": []})
    llm, anrop = _stub_llm([svar])
    assert exam_gen.doma_delmoment(_prov(), _delmoment(), model="m",
                                   llm=llm) == []
    assert "TÄCKNINGEN" not in anrop[0]["prompt"]
    assert "METODER UTANFÖR" in anrop[0]["prompt"]


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
    dom = {"utanfor": [{"nr": str(n), "metod": "olikheter"}
                       for n in range(1, 10)]}
    assert len(exam_gen.metodfynd(dom)) == exam_gen.DELMOMENT_MAX_FYND


# ── täckningen: RÄKNAD, inte läst ────────────────────────────────────────

def _prov_som_tacker(utom: str = "") -> dict:
    """Ett prov med en uppgift per undervisat delmoment — utom ett."""
    return {"titel": "Prov: Kapitel 1", "uppgifter": [
        {"del": "B", "poang": [1, 0, 0], "text": f"En uppgift om {n}.",
         "losning": "…", "delmoment": n}
        for n in (d["delmoment"] for d in _delmoment()) if n != utom]}


def test_delmomentet_utan_en_enda_uppgift_falls():
    """FYND 1 ur den skarpa körningen 2026-09-13 (exam 82): «Exponenter som
    inte är heltal» (s. 16–18) prövades inte av någon uppgift, och LÄSAREN
    rapporterade noll fynd. Räkningen ser det, varje gång och utan anrop."""
    fel = exam_gen.delmomenttackning(
        _prov_som_tacker("Exponenter som inte är heltal"), _delmoment())
    assert len(fel) == 1 and fel[0]["code"] == "delmomenttackning"
    m = fel[0]["message"]
    assert "Exponenter som inte är heltal (s. 16–18)" in m
    # Ordern är BYT UT ur det delmoment som har flest — inte «lägg till».
    # Flest har «Grundpotensform», som räknas två gånger därför att rubriken
    # står som delsträng i «Grundpotensform, prefix och enheter»: hellre en
    # lucka för lite än en falsk, för en falsk lucka byter ut en bra uppgift.
    assert "Grundpotensform har 2" in m and "Lägg INTE till" in m
    # Fältnamnet står i klartext, så reparationsgrammatiken behåller fältet
    # (exam_gen._delmoment_i_grammatiken läser prompten).
    assert '"delmoment"' in m
    # Ett prov som täcker allt fälls inte.
    assert exam_gen.delmomenttackning(_prov_som_tacker(), _delmoment()) == []


def test_en_uppgift_far_tacka_tva_delmoment():
    """Blocket tillåter det när uppgifterna inte räcker till, och då ska båda
    räknas: semikolon, eller modellens egna ord runt rubrikerna."""
    exam = _prov_som_tacker("Kubikrötter")
    exam["uppgifter"][0]["delmoment"] = "Kvadratrötter; Kubikrötter"
    assert exam_gen.delmomenttackning(exam, _delmoment()) == []
    exam["uppgifter"][0]["delmoment"] = "Kvadratrötter och Kubikrötter"
    assert exam_gen.delmomenttackning(exam, _delmoment()) == []


def test_tackningen_ar_fail_open_utan_lista_och_utan_falt():
    """Kassetterna och varje papper i basen skrevs innan fältet fanns, och
    taket kan knuffa ut det ur grammatiken. Att fälla då vore att fälla ett
    papper för att appen blivit klokare."""
    assert exam_gen.delmomenttackning(_prov_som_tacker(), []) == []
    assert exam_gen.delmomenttackning(_prov(), _delmoment()) == []
    assert exam_gen.delmomenttackning({}, _delmoment()) == []


def test_taket_haller_ocksa_den_raknade_tackningen():
    """Fler luckor än så är ingen lucka utan ett annat prov."""
    exam = {"uppgifter": [{"delmoment": "Kvadratrötter"}]}
    assert len(exam_gen.delmomenttackning(exam, _delmoment())) == \
        exam_gen.DELMOMENT_MAX_FYND


# ── fältet i grammatiken ─────────────────────────────────────────────────

def test_faltet_star_i_grammatiken_nar_prompten_ber_om_det():
    """Samma regel som förebildens: fältet finns exakt när det som skickas
    nämner det — uppdraget som ber om det, eller pappret som redan bär det."""
    assert exam_gen._delmoment_i_grammatiken(
        exam_gen.build_delmoment(_delmoment(), 12))
    assert not exam_gen._delmoment_i_grammatiken(
        exam_gen.build_prompt(kurs="Ma1c", klass="TE26A",
                              punkter=["potenser"], antal=12))
    # Reparationsprompten bäddar in dokumentet: bär det fältet ska
    # grammatiken behålla det, annars faller märkningen bort tyst.
    assert exam_gen._delmoment_i_grammatiken(
        exam_gen.build_repair_prompt(_prov_som_tacker(), [], "prov"))


def test_faltet_ryms_pa_kommandoraden_och_offras_sist():
    """Mätt, inte gissat. Tolv uppgifter med alla Ma 1c:s punkter: 23 350
    tecken med förebilden, 23 866 med båda fälten. Vid tjugo uppgifter ligger
    schemat på 29 022 UTAN dem, och då ska BÅDA falla bort — men förebilden
    först, för delmomentet är det täckningen räknas på."""
    from app import claude_code, course_data, exam_spec
    koder = [p["kod"] for p in course_data._kursens_punkter("Matematik 1c")]
    for antal, vantat in ((12, True), (20, False)):
        sk = exam_spec.balanced_skeleton(antal, "prov", delar=True,
                                         kurs="Matematik 1c")
        schema = exam_spec.to_response_format(
            antal, sk, koder, forebild=True,
            delmoment=True)["json_schema"]["schema"]
        assert ('"delmoment"' in json.dumps(schema)) is vantat
        assert claude_code.schemalangd(schema) <= claude_code.SCHEMA_TAK_EXE
    # Rangordningen: ryms bara ett av fälten är det delmomentet som stannar.
    sk = exam_spec.balanced_skeleton(12, "prov", delar=True, kurs="Matematik 1c")
    ensam = exam_spec.to_response_format(12, sk, koder, forebild=False,
                                         delmoment=True)["json_schema"]["schema"]
    assert '"delmoment"' in json.dumps(ensam)
    # Arbetsbladet och gruppuppgiften ser aldrig fältet: ingen av dem får
    # listan, och ett fält modellen ser är ett fält modellen fyller i.
    for rf in (exam_spec.to_response_format(12, sk, koder),
               exam_spec.to_response_format(6, None, None, forebild=True)):
        assert '"delmoment"' not in json.dumps(rf["json_schema"]["schema"])


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
    dom = json.dumps({"utanfor": []})
    lagat = copy.deepcopy(_prov_med_avsnitt(["1.1", "1.2"]))
    trasigt = _prov_med_avsnitt(["1.1", "1.1"])
    # Båda uppgifterna prövar samma delmoment: nio luckor, och den räknade
    # täckningen ska lägga sina fynd i SAMMA prompt som avsnittsluckan.
    for u in trasigt["uppgifter"]:
        u["delmoment"] = "Kvadratrötter"
    llm, anrop = _stub_llm([dom, json.dumps(lagat)])
    res = exam_gen._tackning_pass(trasigt, [], model="m", llm=llm,
                                  profil="prov", antal=2,
                                  skeleton=None, avsnitt=_avsnitt(),
                                  delmoment=_delmoment(), rounds_used=1,
                                  max_rounds=4)
    assert len(anrop) == 2
    reparationen = anrop[1]["prompt"]
    assert "1.2 Uttryck" in reparationen and "Kubikrötter" in reparationen
    assert res["rounds"] == 2


def test_luckan_i_exam_82_falls_och_fixrundan_far_ratt_rad():
    """Hela vägen för FYND 1: provet saknar «Exponenter som inte är heltal»,
    domaren (som inte längre dömer om täckningen) hittar ingenting, och
    reparationsrundan får ändå raden — med ordern att BYTA UT en uppgift ur
    det delmoment som har flest. Räkningen sker oavsett vad läsaren svarar."""
    trasigt = _prov_som_tacker("Exponenter som inte är heltal")
    lagat = _prov_som_tacker()
    llm, anrop = _stub_llm([json.dumps({"utanfor": []}), json.dumps(lagat)])
    res = exam_gen._tackning_pass(trasigt, [], model="m", llm=llm,
                                  profil="prov", antal=len(lagat["uppgifter"]),
                                  skeleton=None, avsnitt=[],
                                  delmoment=_delmoment(), rounds_used=1,
                                  max_rounds=4)
    assert len(anrop) == 2 and "delmomentsdomare" in anrop[0]["prompt"]
    reparationen = anrop[1]["prompt"]
    assert "Inget ur delmomentet Exponenter som inte är heltal (s. 16–18)" \
        in reparationen
    assert "Byt UT en uppgift" in reparationen and "Lägg INTE till" in \
        reparationen
    assert res["rounds"] == 2
    # Och ett papper som täcker allt bär ingen kvarstående varning.
    assert exam_gen.delmomenttackning(lagat, _delmoment()) == []


def test_tackningen_raknas_aven_nar_domandet_ar_avstangt():
    """`doma=False` betyder «inga extra modellanrop», och räkningen är noll
    anrop. Luckan ska alltså synas ändå — det var precis den lucka som gick
    igenom när kontrollen låg hos en läsare."""
    trasigt = _prov_som_tacker("Exponenter som inte är heltal")
    llm, anrop = _stub_llm([json.dumps(_prov_som_tacker())])
    res = exam_gen._tackning_pass(trasigt, [], model="m", llm=llm,
                                  profil="prov", antal=9, skeleton=None,
                                  avsnitt=[], delmoment=_delmoment(),
                                  doma=False, rounds_used=1, max_rounds=4)
    assert len(anrop) == 1              # bara reparationen, ingen domare
    assert "Exponenter som inte är heltal" in anrop[0]["prompt"]
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


# ── den kryssade punkten som drar åt motsatt håll ────────────────────────

# Skolverkets ordagranna text för de punkter läraren kryssade till prov 44,
# skrivna som routes_exam skriver dem i prompten («KOD — område: text»).
PUNKTER = [
    "G25-M1C-ALG-1 — Aritmetik, algebra och funktioner: Hantering av formler "
    "och algebraiska uttryck, däribland faktorisering och multiplicering av "
    "uttryck.",
    "G25-M1C-ALG-8 — Aritmetik, algebra och funktioner: Motivering och "
    "hantering av räkneregler för potenser. Metoder för att lösa "
    "potensekvationer.",
]

# Bokens rubriker för det som kommer EFTER provet, som förbudslistan bär dem.
SENARE = [{"metod": "Potensekvationer och numerisk ekvationslösning",
           "sidor": "50–52"},
          {"metod": "Procentuella förändringar", "sidor": "100–107"}]


def test_den_kryssade_punkten_markt_med_den_del_som_kommer_senare():
    """FYND 2 ur den skarpa körningen 2026-09-13: punkten ALG-8 heter
    «Potenser och potensekvationer» och är kryssad, medan potensekvationerna
    (s. 50–52) står i förbudslistan. Prompten bad alltså om två motsatta
    saker, och modellen skrev «Lös potensekvationerna»."""
    r = exam_gen.build_ci_forbehall(PUNKTER, SENARE)
    assert "Punkten «G25-M1C-ALG-8» är kryssad" in r
    assert "«Metoder för att lösa potensekvationer»" in r
    assert "Potensekvationer och numerisk ekvationslösning (s. 50–52)" in r
    # Den undervisade halvan står kvar som det som FÅR prövas.
    assert "Motivering och hantering av räkneregler för potenser." in r
    assert "gäller förbudet" in r
    # Punkten som inte krockar märks inte alls: faktoriseringen är undervisad.
    assert "ALG-1" not in r


def test_potenser_ar_inte_potensekvationer():
    """Prefixmatchning, aldrig delsträng. «potenser» och «potensekvationer»
    delar sju tecken, och hade delsträngen fått gälla vore räknereglerna —
    hela kapitel 1 — märkta som något som kommer senare."""
    bara_regler = ["G25-M1C-ALG-8 — Aritmetik: Motivering och hantering av "
                   "räkneregler för potenser."]
    assert exam_gen.build_ci_forbehall(bara_regler, SENARE) == ""
    # Böjningen ska däremot matcha: «olikhet» och «olikheter» är samma sak.
    olikhet = ["G25-M1C-ALG-6 — Aritmetik: Begreppen intervall och linjär "
               "olikhet. Metoder för att lösa linjära olikheter."]
    r = exam_gen.build_ci_forbehall(olikhet, [{"metod": "Linjära olikheter",
                                               "sidor": "58–63"}])
    assert "Ingen del av punkten är undervisad ännu" in r


def test_bestamningarna_i_rubriken_marker_ingenting():
    """Huvudordet matchar, inte bestämningen. «Linjära olikheter» ska märka
    olikheterna och ingenting annat — «linjära» står i var tredje punkt, och
    hade adjektivet fått gälla vore linjära funktioner och linjära ekvationer
    märkta som något klassen inte haft."""
    alla = [f"G25-M1C-ALG-{i} — Aritmetik: {t}" for i, t in (
        (4, "Begreppet linjär funktion och egenskaper hos linjära "
            "funktioner. Räta linjens ekvation."),
        (5, "Metoder för att lösa linjära ekvationer."),
        (6, "Begreppen intervall och linjär olikhet."))]
    r = exam_gen.build_ci_forbehall(alla, [{"metod": "Linjära olikheter",
                                            "sidor": "58–63"}])
    assert "ALG-6" in r and "ALG-4" not in r and "ALG-5" not in r
    # Och prefixet får bara skilja en böjning: «ekvation» är ett prefix av
    # «ekvationslösning», men de är två olika saker.
    assert exam_gen.build_ci_forbehall(
        alla, [{"metod": "Numerisk ekvationslösning", "sidor": "50–52"}]) == ""


def test_forbehallen_ar_tomma_utan_forbud_och_utan_krock():
    """Kassettregeln en tredje gång, och samma villkor som blocken ovan."""
    assert exam_gen.build_ci_forbehall(PUNKTER, []) == ""
    assert exam_gen.build_ci_forbehall([], SENARE) == ""
    assert exam_gen.build_ci_forbehall(["G25-M1C-STA-1 — Sannolikhet: "
                                        "Begreppen oberoende och beroende "
                                        "händelse."], SENARE) == ""
    argument = dict(kurs="Ma1c", klass="TE26A", punkter=["potenser"], antal=12)
    utan = exam_gen.build_prompt(**argument)
    assert exam_gen.build_prompt(**argument, forbehall="") == utan


def test_forbehallet_foljer_med_i_genereringens_prompt():
    """Deterministiskt ur de två listor prompten redan bär — inga nya anrop."""
    llm, anrop = _stub_llm([json.dumps(_prov())])
    exam_gen.generate_exam("Ma1c", "TE26A", PUNKTER, model="m", llm=llm,
                           antal=2, delar=False, doma=False,
                           forbjudna=SENARE, max_rounds=2)
    assert "KRYSSAT MEN ÄNNU INTE UNDERVISAT" in anrop[0]["prompt"]
    assert "Punkten «G25-M1C-ALG-8» är kryssad" in anrop[0]["prompt"]


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


def _kvadratsumman():
    """Uppgift 6 ur prov 81, ordagrant — den klassen inte förstod språket i
    (läraren 2026-09-16): räkneord inuti varandra och «på varandra
    följande»."""
    return {"titel": "Prov", "uppgifter": [{
        "del": "B", "poang": [0, 0, 0],
        "text": "Talen $n-1$, $n$ och $n+1$ är tre på varandra följande heltal.",
        "deluppgifter": [{
            "poang": [0, 2, 0],
            "text": ("Teckna och förenkla ett uttryck för summan av de tre "
                     "talens kvadrater."),
            "losning": "…"}]}]}


def test_sprakvakten_faller_rakneord_i_varandra_och_pa_varandra_foljande():
    """Det räknebara i «språket var för svårt»: «summan av … kvadrater» och
    «på varandra följande». Bara på provet, och märkt så att slutgrinden
    räknar om fyndet i stället för att behålla det (_raknas_om)."""
    fel = exam_gen.begriplighetssignaler(_kvadratsumman(), "prov")
    assert [f["code"] for f in fel] == ["begriplighet", "begriplighet"]
    assert "staplar räkneord" in fel[0]["message"]
    assert "summan av de tre talens kvadrater" in fel[0]["message"]
    assert "på varandra följande" in fel[1]["message"]
    assert all(exam_gen._raknas_om(f) for f in fel)
    assert all(exam_gen.SPRAKVAKTENS_MARKE in f["message"] for f in fel)
    # Verbformen går fri, och gruppuppgiften mäts inte så.
    fri = _kvadratsumman()
    fri["uppgifter"][0]["text"] = "Talen är $n-1$, $n$ och $n+1$."
    fri["uppgifter"][0]["deluppgifter"][0]["text"] = (
        "Kvadrera varje tal. Lägg ihop de tre kvadraterna och förenkla.")
    assert exam_gen.begriplighetssignaler(fri, "prov") == []
    assert exam_gen.begriplighetssignaler(_kvadratsumman(), "gruppuppgift") == []
    # Ordvaktens fynd (uppgift 11) står kvar som förut.
    assert len(exam_gen.begriplighetssignaler(_stenhuggeri(), "prov")) == 1


def test_provets_begriplighetsdomare_har_lararens_fem_krav():
    p = exam_gen.build_begriplighet_prompt([{"nr": "1", "text": "x"}], "",
                                           "prov")
    assert "begriplighetsdomare" in p           # bandvalet i tests/fejk.py
    for krav in ("EN SITUATION", "EN FRÅGA", "ALLA TAL SOM BEHÖVS",
                 "ENTYDIG TOLKNING", str(exam_gen.ORD_FORE_FRAGAN),
                 # Det sjätte kravet, lärarens efter prov 81.
                 "ORDEN ÄR ELEVENS", "på varandra följande"):
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
    delmomentdom = json.dumps({"utanfor": [{"nr": "1",
                                            "metod": "potensekvationer"}]})
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
    assert "potensekvationer" in reparationen         # metoden utanför
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


# ── slutgrinden: hålet i fixrundan (spår 9, 2026-09-13) ──────────────────
#
# Prov 82 (TE26A, Ma 1c, «Bara E») genererades med spår 4–8 och levererades
# ändå utan «Grundpotensform, prefix och enheter (s. 14–15)». Jobbloggen visar
# varför: «Delmomenten: 1 fynd mot lektionerna, byter ut uppgifter …» tidigt,
# sedan «Justerar 7 uppgift(er)» och två «Säkrar nivån …». Vakten dömde ett
# mellanläge, en senare runda bytte bort uppgiften igen, och `errors` var TOM.
#
# Ett BALANSERAT papper behövs för de här testerna och inte bara en lista med
# rubriker: efterrundan har samma «rent före, trasigt efter»-grind som varje
# annan runda i filen, så ett papper som redan bryter balansen hade svarat på
# en annan fråga än den som ställs.
_FORMAGA = ["B", "P", "PL", "M", "R", "K", "B", "P", "PL", "M"]
_TYP = ["rutin", "problem", "rutin", "resonemang", "redovisning",
        "rutin", "problem", "rutin", "resonemang", "redovisning"]
_POANG = [[2, 0, 0], [1, 1, 0], [1, 1, 0], [1, 1, 0], [1, 1, 0],
          [2, 0, 0], [0, 2, 0], [0, 1, 1], [0, 0, 2], [0, 0, 2]]
# Var uppgift sin egen mening. Variationsvakten byter talen mot # innan den
# jämför, så «uppgift 6» och «uppgift 8» hade varit samma text för den — och
# den bortbytta uppgiften nedan hade fällts för en likhet testet inte handlar
# om.
_STAM = ["Beräkna", "Förenkla", "Avgör", "Bestäm", "Visa",
         "Jämför", "Undersök", "Skriv om", "Motivera", "Ange"]


def _balanserat_prov(tappat: str = "") -> dict:
    """Ett prov som validerar: en uppgift per undervisat delmoment, i balans
    på nivå, förmåga, typ och stegring.

    `tappat` är det delmoment en senare runda skrev bort — uppgiften finns
    kvar och balansen är orörd, precis som efter en nivåsäkring, men uppgiften
    prövar nu samma sak som en annan uppgift redan gör."""
    namnen = [d["delmoment"] for d in _delmoment()]
    uppgifter = []
    for i, namn in enumerate(namnen):
        prover = "Uttryck" if namn == tappat else namn
        uppgifter.append({
            "del": "B" if i < 5 else "C", "poang": _POANG[i],
            "formaga": _FORMAGA[i], "typ": _TYP[i],
            "text": f"{_STAM[i]} talet i {prover}.", "losning": "…",
            "bedomning": "+1 E", "delmoment": prover})
    return {"titel": "Prov: Kapitel 1", "kurs": "Ma1c",
            "hjalpmedel": "Del A utan räknare", "uppgifter": uppgifter}


def _slutgrind(exam, llm, *, errors=None, rundor=1):
    return exam_gen._slutgrind(
        {"exam": exam, "errors": list(errors or []), "rounds": 3},
        model="m", llm=llm, profil="prov", antal=10, skeleton=None,
        koder=None, niva_mal=None, avsnitt=[], delmoment=_delmoment(),
        bokuppgifter=None, max_rounds=rundor)


def test_papperet_haller_som_underlag_for_slutgrinden():
    """Grinden mäter mot balansen; går pappret sönder av sig självt mäter
    testerna nedan något annat än de påstår."""
    assert exam_gen._validate(_balanserat_prov(), "prov", None, None)[1] == []
    assert exam_gen._validate(
        _balanserat_prov("Grundpotensform, prefix och enheter"),
        "prov", None, None)[1] == []


def test_delmomentet_som_nivarundan_bytte_bort_lagas_i_efterrundan():
    """Hela spår 9 i ett test: pappret som lämnar nivåsäkringen saknar
    prefixmomentet, slutgrinden räknar om, efterrundan får RÄTT rad, och det
    lagade pappret är det som levereras."""
    tappat = _balanserat_prov("Grundpotensform, prefix och enheter")
    lagat = _balanserat_prov()
    llm, anrop = _stub_llm([json.dumps(lagat)])
    res = _slutgrind(tappat, llm)
    assert len(anrop) == 1                      # EN efterrunda, inte fler
    prompt = anrop[0]["prompt"]
    assert "Inget ur delmomentet Grundpotensform, prefix och enheter " \
        "(s. 14–15)" in prompt
    assert "Byt UT en uppgift" in prompt and "Lägg INTE till" in prompt
    # Och låset följer med: rundan får inte öppna en ny lucka när den lagar
    # den här.
    assert "BEHÅLL DELMOMENTEN" in prompt
    assert res["exam"] == lagat and res["errors"] == [] and res["rounds"] == 4


def test_fyndet_som_star_kvar_efter_efterrundan_blir_lararens_varning():
    """Det som gjorde prov 82 farligt var inte luckan utan tystnaden:
    `errors` var tom. Lagar inte efterrundan fyndet ska det stå kvar där, med
    delmomentets namn."""
    tappat = _balanserat_prov("Grundpotensform, prefix och enheter")
    llm, anrop = _stub_llm([json.dumps(tappat)])
    res = _slutgrind(tappat, llm)
    assert len(anrop) == 1
    kvar = [e for e in res["errors"] if e["code"] == "delmomenttackning"]
    assert len(kvar) == 1 and kvar[0]["path"] == "uppgifter"
    assert "Grundpotensform, prefix och enheter" in kvar[0]["message"]


def test_slutgrinden_kostar_ingenting_pa_ett_papper_som_haller():
    """KASSETTREGELN. Håller pappret ska grinden inte kosta ett enda anrop och
    inte röra rundräknaren — ett prov som satt direkt ska gå exakt de anrop
    det gick i går."""
    llm, anrop = _stub_llm(["{}"])
    res = _slutgrind(_balanserat_prov(), llm)
    assert anrop == [] and res["rounds"] == 3 and res["errors"] == []


def test_slutgrinden_rensar_bort_ett_fynd_som_lagats_pa_vagen():
    """Fixrundans varning gällde ett mellanläge. Lagades luckan senare pekar
    varningen på en uppgift som inte finns längre, och då ska den bort."""
    gammalt = exam_gen.delmomenttackning(
        _balanserat_prov("Kubikrötter"), _delmoment())
    llm, anrop = _stub_llm(["{}"])
    res = _slutgrind(_balanserat_prov(), llm, errors=gammalt)
    assert gammalt and anrop == [] and res["errors"] == []


def test_domarnas_fynd_overlever_slutgrinden():
    """Grinden räknar om det den KAN räkna. Delmomentsdomarens metodfynd
    (samma kod, men path «uppgift 7») kan den inte, och det ska stå kvar
    oavsett vad räkningen säger."""
    domarfynd = exam_gen.metodfynd({"utanfor": [{"nr": "7",
                                                 "metod": "olikheter"}]})
    llm, _ = _stub_llm(["{}"])
    res = _slutgrind(_balanserat_prov(), llm, errors=domarfynd)
    assert res["errors"] == domarfynd


def test_generate_exam_raknar_om_sist_ocksa_utan_domare():
    """`doma=False` betyder «inga extra modellanrop», och RÄKNINGEN är noll
    anrop. Efterrundan uteblir, men luckan ska ändå stå i `errors` när
    pappret lämnar generatorn."""
    tappat = _balanserat_prov("Grundpotensform, prefix och enheter")
    llm, anrop = _stub_llm([json.dumps(tappat)])
    res = exam_gen.generate_exam("Ma1c", "TE26A", ["potenser"], model="m",
                                 llm=llm, antal=10, doma=False,
                                 skeleton=[dict(u) for u in tappat["uppgifter"]],
                                 delmoment=_delmoment(), max_rounds=2)
    kvar = [e for e in res["errors"] if e["code"] == "delmomenttackning"]
    assert len(kvar) == 1 and "Grundpotensform, prefix och enheter" in \
        kvar[0]["message"]
    # Fixrundans egen reparation, och sedan INGET mer: slutgrinden räknar om
    # utan att ringa.
    assert len(anrop) == 2


def test_generate_exam_kostar_samma_anrop_som_forut_utan_fynd():
    """Kassettregeln hela vägen upp: ett prov där vakterna inte fäller något
    ska gå exakt ett anrop, som före spår 9."""
    helt = _balanserat_prov()
    llm, anrop = _stub_llm([json.dumps(helt)])
    res = exam_gen.generate_exam("Ma1c", "TE26A", ["potenser"], model="m",
                                 llm=llm, antal=10, doma=False,
                                 skeleton=[dict(u) for u in helt["uppgifter"]],
                                 delmoment=_delmoment(), max_rounds=2)
    assert len(anrop) == 1 and res["errors"] == []


# ── delmomentslåset ──────────────────────────────────────────────────────

def test_laset_namner_bara_den_som_ar_ensam_barare():
    exam = _balanserat_prov("Grundpotensform, prefix och enheter")
    las = exam_gen.delmomentlas(exam, _delmoment())
    # Uppgift 1 är ensam om kvadratrötterna och står i låset.
    assert "- uppgift 1: Kvadratrötter" in las
    # «Uttryck» prövas nu av två uppgifter (den bortbytta och sin egen) och
    # tål att den ena skrivs om — den ska inte stå i låset.
    assert ": Uttryck" not in las
    # Och fältets namn står i klartext, så att det följer med oförändrat.
    assert '"delmoment"' in las and "SAMMA delmoment" in las


def test_laset_galler_bara_de_uppgifter_rundan_far_andra():
    """Nivåsäkringen skriver om en DELMÄNGD. En rad om uppgift 9 i en runda
    som bara får röra uppgift 2 är brus, och brus läses inte."""
    exam = _balanserat_prov()
    las = exam_gen.delmomentlas(exam, _delmoment(), [2])
    assert las.count("- uppgift") == 1 and "- uppgift 2: Kubikrötter" in las
    assert exam_gen.delmomentlas(exam, _delmoment(), [999]) == ""


def test_laset_ar_tomt_utan_lista_och_prompten_da_byteidentisk():
    """Kassettregeln: utan delmomentlista ska reparationsprompten vara byte
    för byte den som gick i väg förut."""
    exam = _balanserat_prov()
    fel = [exam_gen._err("uppgifter", "avsnittstackning", "Inget ur avsnitt")]
    assert exam_gen.delmomentlas(exam, []) == ""
    assert exam_gen.delmomentlas(exam, None) == ""
    assert exam_gen.build_repair_prompt(exam, fel, "prov", "") == \
        exam_gen.build_repair_prompt(exam, fel, "prov")
    assert "BEHÅLL DELMOMENTEN" not in exam_gen.build_repair_prompt(
        exam, fel, "prov")


def test_nivasakringen_far_veta_vad_uppgiften_maste_behalla():
    """Spår 9:s andra halva: nivåsäkringen bytte bort prov 82:s enda
    prefixuppgift. Nu står det i hennes prompt vad uppgiften bär."""
    exam = _balanserat_prov()
    fynd = [{"nr": "6", "pastadd": "E", "domd": "C", "skal": "för svår",
             "message": "uppgift 6 ligger på C men påstår E"}]
    llm, anrop = _stub_llm([json.dumps(exam)])
    exam_gen._niva_grind({"exam": exam, "errors": [], "rounds": 4,
                          "nivafynd": fynd, "nivakoll": True,
                          "nivamatt": True},
                         model="m", llm=llm, profil="prov", skala="",
                         antal=10, skeleton=None, koder=None, niva_mal=None,
                         delmoment=_delmoment())
    assert anrop and "BEHÅLL DELMOMENTEN" in anrop[0]["prompt"]
    assert "- uppgift 6: Grundpotensform, prefix och enheter" in \
        anrop[0]["prompt"]


def test_facitjusteringen_far_samma_las():
    """Samma sak för domarpassets runda — «Justerar 7 uppgift(er)» i prov 82:s
    jobblogg. Den skriver om HELA pappret och ska veta vad det bär."""
    exam = _balanserat_prov()
    llm, anrop = _stub_llm([json.dumps({"domar": []}),
                            json.dumps({"fel": [{"nr": "1",
                                                 "skal": "facit fel"}]}),
                            json.dumps(exam)])
    exam_gen._domar_pass(exam, [], model="m", llm=llm, profil="prov",
                         skala="", antal=10, skeleton=None, rounds_used=1,
                         max_rounds=4, delmoment=_delmoment())
    reparationer = [a["prompt"] for a in anrop
                    if "Problem att åtgärda" in a["prompt"]]
    assert reparationer and "BEHÅLL DELMOMENTEN" in reparationer[0]
