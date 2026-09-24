"""Bladet inför provet får provets vakter (2026-09-24 kväll).

Rickard var nöjd med proven och inte med de femton bladen som byggdes ur dem
24/9. Felen var provets gamla fel, sådana som provets vakter redan fångar, och
skälet var vägen: bladet gick aldrig genom täckningspasset eller slutgrinden.
Sviten prövar varje fel från den kvällen mot den uppgift som bar det:

* kvadrerings- och konjugatreglerna i 1c (blad 134, 136, 142, 143, 147),
* räknarraden som inte följde provets del (134, 135, 137, 138, 139, 141),
* fyrsiffriga tal under «Utan räknare» (134 uppgift 4),
* uppgifter som hängde på en målad figur (147 uppgift 6),
* kvadratkomplettering och största värde i 2a:s kapitel 1 (144, 141),
* och att bladet bär provkopplingen genom GET och omskrivning.
Allt utan skarpa modellanrop.
"""
import copy
import json

import pytest

from app import ci_utanfor, exam_gen, exam_spec
from app.web import routes_exam

from tests.test_exam import _exam
from tests.test_routes_exam import _done, _godkant_prov, _stub_generate

KURS1C = "Matematik, nivå 1c"


@pytest.fixture
def client(llm_ready):
    return llm_ready


def _u(text, losning="$x = 1$", **k):
    return {"text": text, "losning": losning, **k}


def _papper(*uppgifter, kurs=KURS1C, **extra):
    d = {"titel": "Inför provet", "kurs": kurs, "hjalpmedel": "",
         "uppgifter": [dict(u) for u in uppgifter]}
    d.update(extra)
    return d


# ───────────── kvadrerings- och konjugatreglerna i nivå 1 ─────────────

# Uppgifterna som rättades för hand 24/9, i den form de hade.
KVADRERING = [
    _u("Förenkla $\\dfrac{(a + b)^2 - (a - b)^2}{4}$."),
    _u("Faktorisera uttrycket $4x^2 - (x + 3)^2$."),
    _u("Visa att $x^2 + 12x + 36$ kan skrivas som en kvadrat.",
       "$(x+6)^2 = x^2 + 6x + 6x + 36 = x^2 + 12x + 36$."),
    _u("Förenkla $(3 - x)(3 + x)$."),
    _u("Nils påstår att $(x+3)^2 = x^2 + 9$ för alla tal $x$."),
    _u("Använd konjugatregeln och beräkna $51 \\cdot 49$."),
]
# Det som ska stå kvar: en formel att räkna ut, parenteser term för term,
# en potens av en produkt och en uträkning med bara tal.
TILLATET = [
    _u("Djupet är $h = (12 - 0{,}5t)^2$ cm. Beräkna djupet när $t = 4$."),
    _u("Multiplicera $(x + 2)(x + 3)$."),
    _u("Förenkla $(2x)^2 \\cdot 3x$."),
    _u("Beräkna $(12 - 2 \\cdot 3)^2$."),
    _u("Bryt ut den gemensamma faktorn i $6x^2 + 9x$."),
]


@pytest.mark.parametrize("uppgift", KVADRERING)
def test_kvadreringsreglerna_falls_pa_bladet_i_1c(uppgift):
    fel = ci_utanfor.ci_vakt(_papper(uppgift), KURS1C, "arbetsblad")
    assert [f["path"] for f in fel] == ["uppgift 1"], uppgift["text"]
    assert "kvadrerings- och konjugatreglerna" in fel[0]["message"]
    assert "term för term" in fel[0]["message"]


@pytest.mark.parametrize("uppgift", TILLATET)
def test_det_som_ingar_i_1c_star_kvar(uppgift):
    assert ci_utanfor.ci_vakt(_papper(uppgift), KURS1C, "arbetsblad") == []


def test_ma_1a_far_samma_regel_men_inte_nivå_2():
    papper = _papper(KVADRERING[1])
    assert ci_utanfor.ci_vakt(papper, "Matematik, nivå 1a", "arbetsblad")
    assert ci_utanfor.ci_vakt(papper, "Matematik, nivå 2a", "arbetsblad") == []
    assert ci_utanfor.ci_vakt(papper, "Matematik, nivå 2c", "arbetsblad") == []


def test_provet_ror_vi_inte_forran_rickard_sagt_ja():
    """BARA_OVNING: proven är granskade och godkända, och en ny vakt på dem är
    lärarens beslut. Förvalet är provet, så varje gammal anropare är orörd."""
    papper = _papper(KVADRERING[1])
    assert ci_utanfor.ci_vakt(papper, KURS1C) == []
    assert ci_utanfor.ci_vakt(papper, KURS1C, "prov") == []
    # Promptraden för provet är byte för byte den gamla.
    assert ci_utanfor.build_utanfor(KURS1C) == \
        ci_utanfor.build_utanfor(KURS1C, "prov")
    assert "kvadrerings" not in ci_utanfor.build_utanfor(KURS1C)
    blad = ci_utanfor.build_utanfor(KURS1C, "arbetsblad")
    assert "kvadrerings- och konjugatreglerna" in blad
    assert "talföljder" in blad
    # 1a har bara den nya raden, och då ingen mening om talföljder.
    rad_1a = ci_utanfor.build_utanfor("Matematik, nivå 1a", "arbetsblad")
    assert "kvadrerings" in rad_1a and "talföljder" not in rad_1a
    assert ci_utanfor.build_utanfor("Matematik, nivå 1a") == ""


def test_efterkontrollen_visar_det_pa_bladet_men_inte_pa_provet():
    papper = _papper(KVADRERING[0])
    assert [f["kod"] for f in routes_exam._cifynd(papper, "arbetsblad")] == \
        ["utanforci"]
    assert routes_exam._cifynd(papper, "prov") == []


# ──────────────── räknarraden ur provets delar ────────────────


def _prov(dels=("B", "B", "C", "C")):
    return {"titel": "Prov 1", "kurs": KURS1C,
            "hjalpmedel": "Del B utan räknare. Del C med räknare.",
            "uppgifter": [_u(f"Uppgift {i}.", del_=d) for i, d in
                          enumerate(dels, 1)]}


def _fixa_del(prov):
    for u in prov["uppgifter"]:
        u["del"] = u.pop("del_")
    return prov


def test_raknarraden_foljer_provets_del_via_drillar():
    """Blad 134 hade «Räknare är inte tillåten.» på allt, fast fem av dess
    uppgifter övade provets räknardel."""
    prov = _fixa_del(_prov())
    blad = _papper(*[_u(f"Blad {i}.", drillar=d)
                     for i, d in enumerate([1, 3, 2, 4], 1)],
                   hjalpmedel="Räknare är inte tillåten.")
    assert exam_gen.raknarbeslut_ur_provet(blad, prov) == \
        {1: False, 2: True, 3: False, 4: True}
    assert exam_gen.satt_raknarrad_ur_provet(blad, prov)
    assert blad["hjalpmedel"] == ("Räknare får användas på uppgift 2 och 4, "
                                  "men inte på uppgift 1 och 3.")
    # Raden läses tillbaka till samma beslut, och markeringarna följer.
    assert exam_gen.tolka_raknarrad(blad["hjalpmedel"], 4) == \
        {1: False, 2: True, 3: False, 4: True}
    exam_gen.ovningspappret_stadat(blad, "arbetsblad")
    assert blad["uppgifter"][0]["text"].startswith("Utan räknare.")
    assert blad["uppgifter"][1]["text"].startswith("Räknare tillåten.")


def test_raknarraden_hela_bladet_och_utan_besked():
    prov = _fixa_del(_prov(("B", "B")))
    blad = _papper(_u("A.", drillar=1), _u("B.", drillar=2))
    exam_gen.satt_raknarrad_ur_provet(blad, prov)
    assert blad["hjalpmedel"] == "Utan räknare."
    prov = _fixa_del(_prov(("C", "D")))
    exam_gen.satt_raknarrad_ur_provet(blad, prov)
    assert blad["hjalpmedel"] == "Räknare får användas på alla uppgifter."
    # En uppgift utan drillar och utan modellens besked: raden rörs inte.
    blad = _papper(_u("A.", drillar=1), _u("B."), hjalpmedel="Lycka till.")
    assert not exam_gen.satt_raknarrad_ur_provet(blad, prov)
    assert blad["hjalpmedel"] == "Lycka till."
    # Med modellens besked för den uppgiften: provet först, modellen sedan.
    blad["hjalpmedel"] = "Utan räknare."
    assert exam_gen.satt_raknarrad_ur_provet(blad, prov)
    assert blad["hjalpmedel"] == ("Räknare får användas på uppgift 1, men "
                                  "inte på uppgift 2.")


def test_prov_utan_delar_laser_provets_egen_rad():
    prov = {"hjalpmedel": "Räknare på uppgift 2, inte på 1.",
            "uppgifter": [_u("Ett."), _u("Två.")]}
    blad = _papper(_u("A.", drillar=2), _u("B.", drillar=1))
    assert exam_gen.raknarbeslut_ur_provet(blad, prov) == {1: True, 2: False}


def test_promptraden_sager_provets_del_och_reglerna():
    prov = _exam()
    block = exam_gen.build_infor_prov(exam_gen.provslots(prov), [], 7)
    assert "provets uppgift 1: utan räknare, rutin" in block
    assert "provets uppgift 3: med räknare, redovisning" in block
    assert "RÄKNAREN FÖLJER PROVETS DEL" in block
    assert "aldrig 4 668 kr" in block
    assert "BILDEN BÄR ALDRIG MATEMATIKEN PÅ BLADET" in block
    assert "FÖRDJUPNING" not in block
    # Ett prov utan delar får ingen räknarregel.
    utan = copy.deepcopy(prov)
    for u in utan["uppgifter"]:
        u.pop("del")
    assert "RÄKNAREN FÖLJER" not in exam_gen.build_infor_prov(
        exam_gen.provslots(utan), [], 7)
    # Fördjupningen, när den finns.
    block = exam_gen.build_infor_prov(
        exam_gen.provslots(prov), [], 7,
        fordjupning=[{"metod": "Kvadratkomplettering", "sidor": "52–55"}])
    assert "FÖRDJUPNING ÖVAS INTE" in block
    assert "Kvadratkomplettering (s. 52–55)" in block


# ──────────────── utan räknare ska gå att räkna för hand ────────────────

BLAD_134_4 = _u(
    "Utan räknare. En familj betalar en fast avgift per år för elen.\n"
    "Ett år använde de 3 500 kWh och betalade 4 668 kr.\n"
    "Året efter använde de 4 500 kWh och betalade 5 868 kr.\n"
    "Skriv en formel för familjens elkostnad $K$ kr för ett år.",
    "$K = 468 + 1{,}2E$\n$\\dfrac{5\\,868 - 4\\,668}{1\\,000} = 1{,}2$\n"
    "$4\\,668 - 1{,}2 \\cdot 3\\,500 = 468$")


def _utan(*uppgifter):
    return _papper(*uppgifter, hjalpmedel="Utan räknare.")


def test_fyrsiffriga_belopp_utan_raknare_falls():
    fel = exam_gen.raknarfri_talvakt(_utan(BLAD_134_4))
    assert [f["code"] for f in fel] == ["raknarfri"]
    assert "4668" in fel[0]["message"] and "5868" in fel[0]["message"]


@pytest.mark.parametrize("uppgift", [
    # Jämna tiotal räknas för hand (blad 146 uppgift 4).
    _u("I januari använde de 900 kWh och betalade 1 590 kr. I maj 400 kWh "
       "och 840 kr. Hur stor är den fasta avgiften?",
       "240\n$(1\\,590 - 840)/500 = 1{,}5$\n$840 - 400 \\cdot 1{,}5 = 240$"),
    # En jämförelse med två decimaler (blad 137 uppgift 5).
    _u("Öppningen är 2,1 m till närmaste decimeter. Dörren är 2,08 m. "
       "Får dörren plats?", "Nej, det går inte att veta."),
    # Tiopotenser: decimalerna är saken (blad 137 uppgift 1).
    _u("Ange talet i rutan: $0{,}006 \\cdot 10^{\\square} = 60$.",
       "$4$\n$0{,}35 \\cdot 10^{-4} \\cdot 10^{2} = 0{,}0035$"),
    # Ett ungefärligt mellanled när svaret är exakt (blad 146 uppgift 8).
    _u("En hiss bär högst 630 kg. Hur många turer behövs?",
       "3\n$70/31 \\approx 2{,}3$"),
])
def test_handraknat_star_kvar(uppgift):
    assert exam_gen.raknarfri_talvakt(_utan(uppgift)) == []


def test_tva_decimaler_att_multiplicera_och_ungefarligt_svar_falls():
    fel = exam_gen.raknarfri_talvakt(_utan(
        _u("Ett rep är 2,45 m. Hur långt är 3,6 rep?",
           "$2{,}45 \\cdot 3{,}6 = 8{,}82$"),
        _u("Hur lång är sidan?", "Ungefär 7 cm\n$\\sqrt{50}$")))
    assert [f["path"] for f in fel] == ["uppgift 1", "uppgift 2"]


def test_med_raknare_far_stora_tal():
    blad = _papper(BLAD_134_4, hjalpmedel="Räknare får användas.")
    assert exam_gen.raknarfri_talvakt(blad) == []


# ──────────────── bilden bär aldrig matematiken på bladet ────────────────

def _scen(text):
    return {"begrepp": "mönster", "filnamn": "a-06-monster",
            "scene": f"SCENE. {text}\nIntended use: mönster."}


def test_figurerna_nedan_och_antal_i_scenen_falls():
    """Blad 147 uppgift 6 och säckarna på 135."""
    fel = exam_gen.bildfigurvakt(_papper(
        _u("Figurerna nedan är byggda av klinkerplattor. Hur många plattor "
           "har figur 10?", scen=_scen("A tiled floor seen from above.")),
        _u("Ali lastar 24 säckar på släpet.",
           scen=_scen("A trailer loaded with 24 sacks of gravel.")),
        _u("Bygg figurer av stickor.",
           scen=_scen("On a table lie exactly twelve matchsticks."))))
    assert [f["path"] for f in fel] == ["uppgift 1", "uppgift 2",
                                        "uppgift 3"]
    assert "figurerna nedan" in fel[0]["message"].lower()
    assert "«24 s" in fel[1]["message"]


@pytest.mark.parametrize("scen", [
    "A father and a boy of about six stand side by side.",
    "Two kayaks lie on the grass beside the jetty.",
    "Four colleagues walk towards a small car.",
    "A house seen exactly from the side, 16 meters wide.",
])
def test_smatt_antal_alder_och_matt_star_kvar(scen):
    assert exam_gen.bildfigurvakt(_papper(
        _u("En uppgift om något.", scen=_scen(scen)))) == []


def test_appens_egen_figur_far_pekas_pa():
    u = _u("Grafen nedan visar funktionen. Ange nollstället.",
           scen=_scen("A calm meadow."),
           figur={"typ": "linjar", "k": 2, "m": -4})
    assert exam_gen.bildfigurvakt(_papper(u)) == []


# ──────────────── provets förbud, fördjupningen, största värde ────────────

LEKTIONER_INDA = [
    {"datum": "2026-09-28", "fran": 45, "till": 48, "rubrik": "pq-formeln"},
    {"datum": "2026-10-05", "fran": 52, "till": 55,
     "rubrik": "Kvadratkomplettering. Fördjupning. Dessutom problemlösning"},
    {"datum": "2027-01-25", "fran": 155, "till": 159,
     "rubrik": "Bestämma största eller minsta värde"},
]


def test_fordjupningen_ur_kalendern():
    ut = exam_gen.fordjupningar_ur_lektioner(LEKTIONER_INDA, fran=8, till=55,
                                             provdatum="2026-10-20")
    assert ut == [{"metod": "Kvadratkomplettering", "sidor": "52–55",
                   "fordjupning": True}]
    # Utanför sidorna eller efter provdagen räknas den inte.
    assert exam_gen.fordjupningar_ur_lektioner(
        LEKTIONER_INDA, fran=8, till=50, provdatum="2026-10-20") == []
    assert exam_gen.fordjupningar_ur_lektioner(
        LEKTIONER_INDA, fran=8, till=55, provdatum="2026-10-01") == []


def test_blad_144_uppgift_7_och_9():
    """Kvadratkompletteringen stod bara i facit, och «störst intäkt» sa inte
    ordet värde."""
    blad = _papper(
        _u("Undersök för vilka $a$ uttrycket $x^2 + 2ax + 4a + 5$ är positivt "
           "för alla $x$.",
           "$-1 < a < 5$\n$x^2 + 2ax + 4a + 5 = (x + a)^2 - a^2 + 4a + 5$"),
        _u("Bestäm det pris som ger störst intäkt per vecka.", "$150$ kr"),
        _u("Lös ekvationen $x^2 - 5x + 6 = 0$ med pq-formeln.",
           "$x = 2$ eller $x = 3$"),
        kurs="Matematik, nivå 2a")
    fordj = exam_gen.fordjupningar_ur_lektioner(
        LEKTIONER_INDA, fran=8, till=55, provdatum="2026-10-20")
    forbjudna = [{"metod": "Bestämma största eller minsta värde",
                  "sidor": "155–159"}]
    fel = exam_gen.fordjupningsvakt(blad, fordj)
    assert [f["path"] for f in fel] == ["uppgift 1"]
    assert "fördjupning" in fel[0]["message"]
    fel = exam_gen.extremvardesvakt(blad, forbjudna, [], [])
    assert [f["path"] for f in fel] == ["uppgift 2"]
    # Har klassen haft största och minsta värde är det inget förbud.
    haft = [{"delmoment": "Bestämma största eller minsta värde"}]
    assert exam_gen.extremvardesvakt(blad, forbjudna, haft, []) == []
    assert exam_gen.extremvardesvakt(blad, [], [], []) == []
    # Hela uppsättningen: ett fynd per uppgift, även när två vakter träffar.
    alla = exam_gen.ovningsvakter(blad, forbjudna=forbjudna + fordj)
    alla_ramen = exam_gen.ovningsvakter(
        blad, **exam_gen._ramens_listor({"forbjudna": forbjudna + fordj}))
    forbud = [f["path"] for f in alla_ramen if f["code"] == "forbudsvakt"]
    assert forbud == ["uppgift 1", "uppgift 2"]
    assert len([f for f in alla if f["code"] == "forbudsvakt"]) >= 1


# ──────────────── hela vägen genom genereringen ────────────────


def _prov_1c():
    prov = copy.deepcopy(_exam())
    prov["kurs"] = KURS1C
    prov["uppgifter"][2].update(
        text="Lös ekvationen $3x - 7 = 8$.", innehall=["ekvationer"],
        losning="$x = 5$.", bedomning="+1 E ansats\n+1 C korrekt\n"
                                      "+1 A generell metod")
    return prov


BLADTEXTER = [
    "Ange lösningarna till $(x - 2)(x + 5) = 0$.",
    "Lös ekvationen $x^2 - 9x + 20 = 0$.",
    "Lös ekvationen $2x + 3 = 11$.",
    "En rektangulär rabatt har omkretsen 24 m.\nBestäm måtten.",
    "Ett konto växer med 3 procent per år.\nNär har beloppet ökat med "
    "hälften?",
    "En funktion har $a > 0$.\nHar den ett största värde? Motivera.",
    "Funktionen är $g(x) = x^2 - 4x$.\nFörklara hur symmetrilinjen bestäms.",
]


# Facit som räkneverket godtar (sympy räknar ekvationerna efter).
BLADFACIT = ["$x = 2$ och $x = -5$.", "$x = 4$ eller $x = 5$.", "$x = 4$."]


def _blad(texter=BLADTEXTER):
    blad = copy.deepcopy(_prov_1c())
    blad.pop("forsattsbild", None)
    blad["hjalpmedel"] = "Räknare får användas."
    for i, (u, t) in enumerate(zip(blad["uppgifter"], texter), 1):
        u["text"] = t
        u["drillar"] = i
        u.pop("scen", None)
        if i <= len(BLADFACIT):
            u["losning"] = BLADFACIT[i - 1]
    return blad


def test_genereringen_lagar_kvadreringen_i_samma_runda_och_satter_raden():
    prov = _prov_1c()
    smutsigt = _blad([BLADTEXTER[0], "Faktorisera uttrycket $4x^2 - (x + 3)^2$."]
                     + BLADTEXTER[2:])
    rent = _blad()
    prompter = []

    def llm(model, prompt, **k):
        prompter.append(prompt)
        return json.dumps(smutsigt if len(prompter) == 1 else rent)

    res = exam_gen.generate_exam(
        KURS1C, "NA26F", ["Uttryck"], model="", antal=7,
        profil="arbetsblad", inforprov=prov, infor_nummer=[], llm=llm,
        doma=False)
    assert len(prompter) == 2, "en reparationsrunda för fynden"
    assert "kvadrerings- och konjugatreglerna" in prompter[1]
    assert res["exam"]["uppgifter"][1]["text"].endswith(BLADTEXTER[1])
    assert not [e for e in res["errors"] if e["code"] == "utanforci"]
    # Provets del B är uppgift 1 och 2: de görs utan räknare.
    assert res["exam"]["hjalpmedel"] == (
        "Räknare får användas på uppgift 3, 4, 5, 6 och 7, men inte på "
        "uppgift 1 och 2.")
    assert res["exam"]["uppgifter"][0]["text"].startswith("Utan räknare.")
    assert res["exam"]["uppgifter"][2]["text"].startswith("Räknare tillåten.")


def test_blad_utan_prov_gar_som_forut():
    """Utan valt prov: ingen extra runda, bara varningen på slutet."""
    smutsigt = _blad([BLADTEXTER[0], "Faktorisera uttrycket $4x^2 - (x + 3)^2$."]
                     + BLADTEXTER[2:])
    for u in smutsigt["uppgifter"]:
        u.pop("drillar")
    prompter = []

    def llm(model, prompt, **k):
        prompter.append(prompt)
        return json.dumps(smutsigt)

    res = exam_gen.generate_exam(
        KURS1C, "NA26F", ["Uttryck"], model="", antal=7,
        profil="arbetsblad", llm=llm, doma=False)
    assert len(prompter) == 1
    assert "RÄKNAREN FÖLJER" not in prompter[0]
    assert [e["path"] for e in res["errors"] if e["code"] == "utanforci"] == \
        ["uppgift 2"]
    assert res["exam"]["hjalpmedel"] == "Räknare får användas."


# ──────────────── provkopplingen genom GET och omskrivning ────────────────


def test_grammatiken_bar_inte_provkopplingen():
    rf = exam_spec.to_response_format(7, None, None)
    assert "infor_prov" not in rf["json_schema"]["schema"]["properties"]
    doc, fel = exam_spec.validate_exam_json({**_blad(), "infor_prov": 126},
                                            "arbetsblad")
    assert doc is not None and doc.infor_prov == 126, fel


def test_efterkontrollen_sager_raknarraden(client):
    prov = _prov_1c()
    blad = _blad()
    blad["hjalpmedel"] = "Räknare är inte tillåten."
    doc = exam_spec.validate_exam_json(blad, "arbetsblad")[0]
    fynd = routes_exam.efterkontroll({"typ": "arbetsblad", "exam": blad}, doc,
                                     None, infor=prov)
    rad = [f for f in fynd if f["kod"] == "raknarrad"]
    assert rad and "Räknare får användas på uppgift 3, 4, 5, 6 och 7" in \
        rad[0]["text"]
    assert "raknarrad" in routes_exam._ATGARD
    # Utan provet tiger den, som kopiorna.
    fynd = routes_exam.efterkontroll({"typ": "arbetsblad", "exam": blad}, doc,
                                     None)
    assert not [f for f in fynd if f["kod"] == "raknarrad"]


def test_omskrivningen_far_provet_och_behaller_kopplingen(client, monkeypatch):
    prov_id, gid, cid = _godkant_prov(
        client, titel="Prov 1", datum="2026-10-20", klass="TE27H",
        kurs="Matematik, nivå 2b")
    _stub_generate(monkeypatch, result={"exam": _blad(), "errors": [],
                                        "rounds": 1})
    svar = _done(client.post("/api/exams/generate", json={
        "course_id": cid, "group_id": gid, "antal": 7, "typ": "arbetsblad",
        "infor_prov_id": prov_id}))
    assert svar["exam"]["infor_prov"] == prov_id
    fangat = {}
    nytt = _blad()
    nytt["uppgifter"][0]["text"] = "Ange lösningarna till $(x - 3)(x + 4) = 0$."

    def fake_refine(exam, message, **kw):
        fangat["infor"] = kw.get("infor")
        return {"exam": copy.deepcopy(nytt), "errors": [], "rounds": 1}
    monkeypatch.setattr(exam_gen, "refine_exam", fake_refine)
    res = _done(client.post(f"/api/exams/{svar['id']}/refine",
                            json={"message": "byt uppgift 1", "nummer": 1}))
    assert fangat["infor"] and fangat["infor"]["titel"] == "Prov 1"
    assert res["exam"]["infor_prov"] == prov_id


# ──────────────── facit: ett steg per rad, också i LaTeX ────────────────


def test_latexfacit_har_ett_steg_per_rad():
    """Blad 134 uppgift 4: tre steg på en rad utan skiljetecken. Skärmen
    rättades i losning.css (447baa3), LaTeX-reserven här."""
    from app import exam_latex
    steg = exam_latex.losning_steg(BLAD_134_4["losning"] + "\n\n")
    assert steg.count(r"\newline") == 2
    assert steg.startswith(r"\(K = 468")
    # Mallarna för arbetsblad och gruppuppgift läser den, provets inte.
    from pathlib import Path
    mallar = Path(exam_latex.__file__).parent / "templates"
    for namn in ("arbetsblad.tex.j2", "gruppuppgift.tex.j2"):
        text = (mallar / namn).read_text(encoding="utf-8")
        assert "u.losning_steg" in text and "d.losning_steg" in text
        assert "((( u.losning )))" not in text


# ──────────────── provets egna uttryck (granskningen 24/9 natt) ────────────


def test_provets_uttryck_pa_bladet_falls():
    """Prov 129 uppgift 6 hade «5 − 2x < 11», och blad 145 uppgift 9 fick
    samma olikhet vänd. Prov 130 hade «(x − 3)² = 25», och blad 138 uppgift 11
    «(x − 3)² = 16»."""
    prov = _papper(_u("Lös olikheten $5 - 2x < 11$."),
                   _u("Lös ekvationen: $(x - 3)^2 = 25$."))
    blad = _papper(
        _u("Olikheten är $11 > 5 - 2x$. Avgör om $x = -4$ är en lösning."),
        _u("Lös ekvationen: $(x - 3)^{2} = 16$."),
        # Samma parentes inne i ett längre uttryck är inte provets uttryck.
        _u("Förenkla $(x + 4)(x - 4) - 2(x - 3)^2$."),
        _u("Lös olikheten $7 - 3x < 19$."))
    fel = exam_gen.uttrycksvakt(blad, prov)
    assert [f["path"] for f in fel] == ["uppgift 1", "uppgift 2"]
    assert all(f["code"] == "provuttryck" for f in fel)
    assert "provuttryck" in routes_exam._ATGARD
    # Fail-open utan prov.
    assert exam_gen.uttrycksvakt(blad, None) == []
