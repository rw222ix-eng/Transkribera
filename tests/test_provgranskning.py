"""Lärarens tre granskningar 2026-09-19 (prov 85, 86 och 87).

Hon genererade tre prov i appen och skrev ändå om dem för hand efteråt. Felen
hon hittade var av samma sort i alla tre, och samma sort som generatorn borde
ha fångat själv: täckningen räknade uppgifter och inte poäng, A-poängen bar
tryckta tips, omprovet var lättare än sitt original, och provet var längre än
passet.

Varje vakt nedan prövas DETERMINISTISKT, inga modellanrop, inga kassetter.
Det är hela poängen med dem: de kostar ingenting och svarar likadant varje
gång. De två sakerna som kräver en modell (kräver lösningen en metod utanför
kapitlet, är uppgiften begriplig) låg redan hos domarna och prövas där.
"""
from __future__ import annotations

import copy

from app import course_data, exam_gen, exam_spec, niva_rubrik


# ── underlag ─────────────────────────────────────────────────────────────

def _u(text="Beräkna $\\sqrt{49}$.", poang=(1, 0, 0), **extra) -> dict:
    """En uppgift med det vakterna läser och ingenting mer."""
    rad = {"del": "B", "typ": "rutin", "formaga": "B", "poang": list(poang),
           "text": text, "losning": "7", "bedomning": "+1 E för 7"}
    rad.update(extra)
    return rad


def _prov(uppgifter: list[dict], **extra) -> dict:
    return {"titel": "Prov: Kapitel 1", "kurs": "Matematik 1c",
            "uppgifter": uppgifter, **extra}


DELMOMENT = [
    {"delmoment": "Kvadratrötter", "sidor": "2–4", "lektioner": 1},
    {"delmoment": "Potenslagar", "sidor": "10–13", "lektioner": 4},
]

AVSNITT = [
    {"avsnitt": "1.1", "etikett": "1.1 Tal i potensform", "fran": 2,
     "till": 20, "sidor": 19},
    {"avsnitt": "1.2", "etikett": "1.2 Ekvationer", "fran": 21, "till": 30,
     "sidor": 10},
]


def _koder(kod: str) -> list[str]:
    return [k for k in course_data.kodtexter() if k == kod]


# ── 1. VIKTEN: poäng per delmoment mot undervisningstid ──────────────────

def test_delmomentet_med_en_lektion_far_inte_bara_halva_provet():
    """Prov 86: 2.5 bar 9 poäng på två lektioner medan kapitel 1 bar 5 på sex.
    Täckningen var nöjd, båda hade uppgifter, för den räknar uppgifter och
    inte vad de är värda."""
    uppgifter = [_u(poang=(3, 0, 0), delmoment="Kvadratrötter")
                 for _ in range(2)]
    uppgifter += [_u(poang=(1, 0, 0), delmoment="Potenslagar")
                  for _ in range(4)]
    fel = exam_gen.delmomentvikt(_prov(uppgifter), DELMOMENT)
    assert [f["code"] for f in fel] == ["delmomentvikt"]
    assert "Kvadratrötter" in fel[0]["message"]
    # Och den säger VAD som ska göras, inte bara att det är fel.
    assert "Flytta poäng" in fel[0]["message"]


def test_ratt_fordelat_prov_ger_inga_viktfynd():
    uppgifter = [_u(poang=(1, 0, 0), delmoment="Kvadratrötter")]
    uppgifter += [_u(poang=(1, 0, 0), delmoment="Potenslagar")
                  for _ in range(5)]
    assert exam_gen.delmomentvikt(_prov(uppgifter), DELMOMENT) == []


def test_delmomentet_med_en_uppgift_utan_poang_falls():
    """Etiketten satt rätt, uppgiften gav noll poäng: delmomentet är oprövat
    fast räkningen såg en uppgift."""
    uppgifter = [_u(poang=(0, 0, 0), delmoment="Kvadratrötter",
                    deluppgifter=[])]
    uppgifter += [_u(poang=(1, 0, 0), delmoment="Potenslagar")
                  for _ in range(5)]
    fel = exam_gen.delmomentvikt(_prov(uppgifter), DELMOMENT)
    assert [f["code"] for f in fel] == ["delmomentvikt"]
    assert "NOLL poäng" in fel[0]["message"]


def test_viktvakten_ar_fail_open():
    """Tom lista, papper utan fältet, och ett papper som är för kort för att
    ha en fördelning alls."""
    sex = [_u(delmoment="Potenslagar") for _ in range(6)]
    assert exam_gen.delmomentvikt(_prov(sex), []) == []
    assert exam_gen.delmomentvikt(_prov([_u() for _ in range(6)]),
                                  DELMOMENT) == []
    kort = [_u(poang=(9, 0, 0), delmoment="Potenslagar")]
    assert exam_gen.delmomentvikt(_prov(kort), DELMOMENT) == []


def test_en_lucka_tystar_overvikten_sa_reparationen_far_en_order():
    """Täckningen säger redan «byt UT en uppgift ur det delmoment som har
    flest». Stod övervikten bredvid skulle samma byte beställas två gånger."""
    uppgifter = [_u(poang=(2, 0, 0), delmoment="Potenslagar")
                 for _ in range(6)]
    prov = _prov(uppgifter)
    assert exam_gen.delmomenttackning(prov, DELMOMENT)      # Kvadratrötter tom
    assert exam_gen.delmomentvikt(prov, DELMOMENT) == []


# ── 1b. NIVÅN: varje avsnitt ska bära en E-poäng ─────────────────────────

def test_avsnittet_med_bara_en_A_uppgift_falls():
    """Prov 86: olikheterna bar en enda A-uppgift och 2.1 Ekvationer noll
    E-poäng. Den elev som läser för E mötte ett avsnitt hon inte kunde visa
    något på."""
    uppgifter = [_u(poang=(1, 0, 0), avsnitt="1.1") for _ in range(5)]
    uppgifter.append(_u(poang=(0, 0, 1), avsnitt="1.2"))
    fel = exam_gen.avsnittsniva(_prov(uppgifter), AVSNITT)
    assert [f["code"] for f in fel] == ["avsnittsniva"]
    assert "1.2 Ekvationer" in fel[0]["message"]
    # En (1, 1, 0) räcker, kravet är en E-POÄNG, inte en E-uppgift.
    uppgifter[-1] = _u(poang=(1, 0, 1), avsnitt="1.2")
    assert exam_gen.avsnittsniva(_prov(uppgifter), AVSNITT) == []


def test_avsnitt_som_inte_finns_i_boken_falls():
    """Prov 86 bar ett avsnitt «2.6». Kapitlet slutar på 2.5."""
    uppgifter = [_u(avsnitt="1.1") for _ in range(5)]
    uppgifter.append(_u(avsnitt="2.6"))
    fel = exam_gen.avsnittsniva(_prov(uppgifter), AVSNITT)
    koder = [f["code"] for f in fel]
    assert "avsnittsmarkning" in koder
    rad = next(f for f in fel if f["code"] == "avsnittsmarkning")
    assert "«2.6»" in rad["message"] and rad["path"] == "uppgift 6"


def test_forebilden_avslojar_fel_avsnittsetikett():
    """Samma mätning som delmomenttäckningen gör: etiketten är modellens
    självrapport, boken vet var uppgiften står."""
    uppgifter = [_u(avsnitt="1.1") for _ in range(5)]
    uppgifter.append(_u(avsnitt="1.1",
                        forebild={"nr": 2320, "sort": "samma sort"}))
    bok = [{"nr": 2320, "sida": 25}]
    fel = exam_gen.avsnittsniva(_prov(uppgifter), AVSNITT, bok)
    rad = next(f for f in fel if f["code"] == "avsnittsmarkning")
    assert "1.2 Ekvationer" in rad["message"]
    # En förebild INNE i avsnittets spann säger ingenting.
    assert not [f for f in exam_gen.avsnittsniva(
        _prov(uppgifter), AVSNITT, [{"nr": 2320, "sida": 5}])
        if f["code"] == "avsnittsmarkning"]


def test_avsnittsvakten_ar_fail_open_utan_ram_och_utan_falt():
    sex = [_u() for _ in range(6)]
    assert exam_gen.avsnittsniva(_prov(sex), AVSNITT) == []
    assert exam_gen.avsnittsniva(_prov([_u(avsnitt="1.1")] * 6),
                                 AVSNITT[:1]) == []


# ── 1c. MÄRKNINGEN: prövar uppgiften det den säger? ──────────────────────

def test_etiketten_som_ingen_bedomningsrad_bekraftar_falls():
    """Prov 85: delmomentet var pq-formeln, och poängen gavs för «löser med
    digitalt verktyg». Varken texten, facit eller bedömningen nämnde en
    andragradsekvation."""
    delmoment = [{"delmoment": "Andragradsekvationer och pq-formeln",
                  "sidor": "40–46", "lektioner": 3}]
    u = _u(text="Lös ekvationen numeriskt.",
           losning="Grafen skär $x$-axeln i 2,4",
           bedomning="+1 C för svaret 2,4 med redovisat digitalt verktyg",
           delmoment="Andragradsekvationer och pq-formeln")
    fel = exam_gen.delmomentmarkning(_prov([u]), delmoment)
    assert [f["code"] for f in fel] == ["delmomentmarkning"]
    assert fel[0]["path"] == "uppgift 1"


def test_etiketten_som_facit_bekraftar_star_kvar():
    """Kravet är lågt satt med flit: NÅGOT av rubrikens ord ska finnas
    någonstans. En falsk fällning byter ut en bra uppgift."""
    delmoment = [{"delmoment": "Faktorisering och förkortning",
                  "sidor": "31–34", "lektioner": 2}]
    u = _u(text="Förenkla uttrycket.",
           losning="Faktorisera täljaren och förkorta bort $(x-2)$",
           delmoment="Faktorisering och förkortning")
    assert exam_gen.delmomentmarkning(_prov([u]), delmoment) == []


# ── 1d. CENTRALT INNEHÅLL ────────────────────────────────────────────────

def test_den_kryssade_punkten_utan_uppgift_blir_ett_fynd():
    """validate_ci frågar åt ena hållet (bär uppgiften en kod?). Prov 85
    saknade datorlektionens kalkylblad helt, och ingen frågade åt det andra."""
    koder = _koder("G25-M1C-ALG-1") + _koder("G25-M1C-DIG-1")
    assert len(koder) == 2
    u = _u(text="Faktorisera $x^2 - 4$.", innehall=["G25-M1C-ALG-1"],
           losning="$(x-2)(x+2)$")
    fel = exam_gen.ci_tackning(_prov([u]), koder)
    assert [f["code"] for f in fel] == ["citackning"]
    assert "G25-M1C-DIG-1" in fel[0]["message"]
    # Den digitala punkten får sin egen rad, den prövas bara om provet BER
    # om verktyget.
    assert "DIGITALA" in fel[0]["message"]


def test_ci_tackningen_ar_fail_open_utan_kryss_och_utan_taggar():
    u = _u(text="Faktorisera $x^2 - 4$.")
    assert exam_gen.ci_tackning(_prov([u]), None) == []
    assert exam_gen.ci_tackning(_prov([u]), _koder("G25-M1C-ALG-1")) == []


def test_taggen_som_inte_stammer_med_uppgiften_falls():
    """Prov 85: uppgift 1 stod taggad ALG-6 och var en parentesförenkling."""
    koder = _koder("G25-M1C-ALG-6")
    u = _u(text="Förenkla $3(x + 2) - 2x$.", losning="$x + 6$",
           bedomning="+1 E för $x + 6$", innehall=["G25-M1C-ALG-6"])
    fel = exam_gen.ci_taggning(_prov([u]), koder)
    assert [f["code"] for f in fel] == ["citaggning"]
    assert fel[0]["path"] == "uppgift 1"


def test_ratt_taggad_uppgift_gar_igenom():
    koder = _koder("G25-M1C-ALG-6")
    u = _u(text="Lös olikheten $2x + 1 > 7$ och ange svaret som ett intervall.",
           losning="$x > 3$", innehall=["G25-M1C-ALG-6"])
    assert exam_gen.ci_taggning(_prov([u]), koder) == []


# ── 2. A-POÄNGEN ────────────────────────────────────────────────────────

def test_a_poang_med_tryckt_tips_falls():
    """Omprov 87: fem av sju A-poäng bar ett tips som gav bort metoden."""
    u = _u(text="Förenkla $\\frac{800 \\cdot 10^{12}}{800 \\cdot 10^{4}}$. "
                "Tips: förkorta bort 800 och subtrahera exponenterna.",
           poang=(0, 0, 1))
    fel = exam_gen.a_nivavakt(_prov([u]))
    assert [f["code"] for f in fel] == ["anivavakt"]
    assert "Stryk tipset" in fel[0]["message"]


def test_visa_att_pa_A_falls_bara_nar_provet_saknar_en_oppen_uppgift():
    """«Visa att» är en laglig A-form på ett prov som också kan ställa den
    öppna frågan. Omprov 87 hade inte EN enda."""
    visa = _u(text="Visa att summan alltid är delbar med 3.", poang=(0, 0, 1))
    assert [f["code"] for f in exam_gen.a_nivavakt(_prov([visa]))] \
        == ["anivavakt"]
    oppen = _u(text="Undersök om påståendet gäller för alla heltal.",
               poang=(0, 0, 1))
    assert exam_gen.a_nivavakt(_prov([visa, oppen])) == []


def test_tipset_falls_pa_alla_nivaer_men_sanningsvardet_bara_pa_A():
    """Prov 88 (2026-09-19) bar «Tips: Sätt in x = 3 …» på en C-uppgift.
    Nationella provet trycker aldrig tips, så tipset fälls på E och C också.
    Det givna sanningsvärdet är däremot bara ett A-fynd."""
    u = _u(text="Visa att $2 + 2 = 4$. Tips: räkna.", poang=(1, 1, 0))
    fel = exam_gen.a_nivavakt(_prov([u]))
    assert [f["code"] for f in fel] == ["anivavakt"]
    assert "tips" in fel[0]["message"].lower()
    u2 = _u(text="Visa att $2 + 2 = 4$.", poang=(1, 1, 0))
    assert exam_gen.a_nivavakt(_prov([u2])) == []
    # Tipset i uppgiftens `notis` (prov 88 uppg 6 och 11) räknas också.
    u3 = _u(text="Beräkna arean.", poang=(1, 1, 0))
    u3["notis"] = "Tips: Räkna ut hela ytan och dra bort dammen."
    assert [f["code"] for f in exam_gen.a_nivavakt(_prov([u3]))] == ["anivavakt"]


# ── 3. METODER UR SENARE KAPITEL ────────────────────────────────────────

def test_forbudet_laser_bade_kalendern_och_bokens_register():
    """Omprov 87 uppg 6a krävde en ekvation med obekant i nämnaren, kapitel
    2, på ett kapitel 1-prov. Bokens register hade rubriken, men registret
    lästes bara när kalendern teg, och kalendern teg inte."""
    lektioner = [{"datum": "2026-09-25", "fran": 58, "till": 63,
                  "rubrik": "Olikheter"}]
    bokavsnitt = [{"titel": "Ekvationer med bråk", "fran": 44, "till": 49},
                  {"titel": "Olikheter", "fran": 58, "till": 63}]
    ut = exam_gen.forbjudna_metoder(lektioner, bokavsnitt, till=40,
                                    provdatum="2026-09-20")
    namn = [f["metod"] for f in ut]
    assert namn == ["Ekvationer med bråk", "Olikheter"], namn
    # Samma rubrik ur båda källorna blir EN rad, inte två.
    assert len(ut) == len({f["metod"] for f in ut})


def test_forbudet_drar_bort_det_klassen_faktiskt_haft():
    bokavsnitt = [{"titel": "Potenslagar", "fran": 50, "till": 55}]
    ut = exam_gen.forbjudna_metoder([], bokavsnitt, till=40,
                                    delmoment=DELMOMENT)
    assert ut == []


# ── 4. OMPROVET ─────────────────────────────────────────────────────────

REFERENS = _prov([
    _u(poang=(2, 0, 0), text="Beräkna $\\sqrt{98}$ exakt.",
       losning="$\\sqrt{98} = \\sqrt{49 \\cdot 2} = 7\\sqrt{2}$, "
               "alltså $a = 7$ och $b = 2$"),
    _u(poang=(0, 2, 0), typ="redovisning", formaga="P",
       text="Bestäm uttryckets värde.",
       losning="$a = 3$ ger $b = 12$ och $c = 4$"),
])


def test_omprovsblocket_ar_tomt_utan_referens():
    """Kassettregeln: ett vanligt prov ska få exakt den prompt det fick innan
    omprovsläget fanns."""
    assert exam_gen.build_omprov(None) == ""
    assert exam_gen.build_omprov({"uppgifter": []}) == ""
    argument = dict(kurs="Ma1c", klass="TE26A", punkter=["potenser"], antal=2)
    assert exam_gen.build_prompt(**argument) == \
        exam_gen.build_prompt(**argument, omprov="")


def test_omprovsblocket_ger_planen_men_aldrig_uppgiftstexten():
    """En modell som ser originaluppgiften skriver samma uppgift med nya
    siffror, och eleven som skriver om provet har redan sett den."""
    block = exam_gen.build_omprov(REFERENS)
    assert "OMPROV" in block and "SAMMA SLOT, NY UPPGIFT" in block
    assert "redovisning" in block and "(0, 2, 0)" in block
    assert "98" not in block and "Beräkna" not in block


def test_omprovet_arver_originalets_slots_som_skelett():
    skelett = exam_gen.skelett_ur_prov(REFERENS)
    assert [s["poang"] for s in skelett] == [[2, 0, 0], [0, 2, 0]]
    assert [s["typ"] for s in skelett] == ["rutin", "redovisning"]
    assert exam_gen.skelett_ur_prov({"uppgifter": []}) is None


def test_likvardighetsvakten_faller_den_lattare_sloten():
    """87 var lättare på E och C: √64 mot √72, och en symbolisk uppgift där
    originalet hade en numerisk."""
    lattare = _prov([
        _u(poang=(2, 0, 0), text="Beräkna $\\sqrt{64}$.", losning="8"),
        _u(poang=(0, 1, 0), typ="rutin", formaga="B",
           text="Förenkla.", losning="$2x$"),
    ])
    fel = exam_gen.likvardighetsvakt(lattare, REFERENS)
    koder = {f["code"] for f in fel}
    assert koder == {"likvardighet"}
    rad = next(f for f in fel if f["path"] == "uppgift 2")
    assert "poängen är (0, 1, 0)" in rad["message"]
    assert "typen" in rad["message"]
    # Steget räknas också: originalets facit tog fyra räknesteg, det nya noll.
    rad1 = next(f for f in fel if f["path"] == "uppgift 1")
    assert "räknesteg" in rad1["message"] and "färre" in rad1["message"]


def test_ett_likvardigt_omprov_gar_igenom():
    nytt = copy.deepcopy(REFERENS)
    nytt["uppgifter"][0]["text"] = "Beräkna $\\sqrt{50}$ exakt."
    nytt["uppgifter"][0]["losning"] = ("$\\sqrt{50} = \\sqrt{25 \\cdot 2} = "
                                       "5\\sqrt{2}$, alltså $a = 5$ och $b = 2$")
    assert exam_gen.likvardighetsvakt(nytt, REFERENS) == []


def test_likvardighetsvakten_ar_fail_open_utan_referens():
    assert exam_gen.likvardighetsvakt(REFERENS, None) == []


# ── 5. TIDEN ────────────────────────────────────────────────────────────

def test_provet_som_ar_langre_an_passet_sager_det():
    """Prov 85: tolv uppgifter och 26 poäng på ett pass på 70 minuter, och
    exam_spec säger själv att ett sådant prov tar ungefär 100."""
    fel = exam_spec.tidsvakt(12, 70, "prov", kurs="Ma2a")
    assert [f["code"] for f in fel] == ["tidsvakt"]
    assert "70 minuter" in fel[0]["message"]
    # Den säger också vad som ryms, och att antalet står kvar.
    assert "ryms på tiden" in fel[0]["message"]
    assert "Antalet är ditt eget" in fel[0]["message"]


def test_tidsvakten_tiger_nar_provet_ryms():
    assert exam_spec.tidsvakt(8, 100, "prov", kurs="Ma2a") == []
    # Marginalen: ett prov som ligger inom tio minuter över är inte fel.
    plan = exam_spec.skelettsummor(8, "prov", kurs="Ma2a")
    assert exam_spec.tidsvakt(8, plan["tid"] - exam_spec.TID_MARGINAL_MIN,
                              "prov", kurs="Ma2a") == []


def test_tidsvakten_ar_fail_open_utan_tid():
    assert exam_spec.tidsvakt(12, 0, "prov") == []
    assert exam_spec.tidsvakt(0, 70, "prov") == []


# ── 6. SPRÅKET ──────────────────────────────────────────────────────────

def test_2a_provet_utan_ordet_motivera_falls():
    """Prov 85 var ett 2a-prov och saknade ordet helt. RUBRIK_PER_KURS säger
    att formen förekommer upp till sju gånger i kursens nationella prov."""
    prov = _prov([_u(text="Beräkna $2 + 2$.")])
    fel = exam_gen.rubrikordsvakt(prov, "Ma2a")
    assert [f["code"] for f in fel] == ["rubrikord"]
    med = _prov([_u(text="Beräkna $2 + 2$. Motivera ditt svar.")])
    assert exam_gen.rubrikordsvakt(med, "Ma2a") == []


def test_1a_provet_med_fem_motiveringar_falls_at_andra_hallet():
    """I a-spåret av kurs 1 står formen HÖGST en gång i hela provet."""
    prov = _prov([_u(text="Beräkna. Motivera ditt svar.") for _ in range(5)])
    fel = exam_gen.rubrikordsvakt(prov, "Ma1a")
    assert [f["code"] for f in fel] == ["rubrikord"]
    assert exam_gen.rubrikordsvakt(
        _prov([_u(text="Beräkna. Motivera ditt svar.")]), "Ma1a") == []


def test_kurs_utan_matning_provas_inte():
    """1c-raden talar om formellt språk, inte om en frågeform som går att
    räkna, och en siffra som inte är mätt hör inte hemma i rubriken."""
    assert niva_rubrik.kravord("Ma1c") is None
    assert exam_gen.rubrikordsvakt(_prov([_u()]), "Ma1c") == []
    assert exam_gen.rubrikordsvakt(_prov([_u()]), "") == []


def test_rutinuppgift_som_ber_om_motivering_sager_emot_sin_kravrad():
    """Prov 85: uppgifter som krävde redovisning låg i en del vars kravrad
    säger «Endast svar krävs». Kravraden följer typen (exam_latex._krav)."""
    u = _u(typ="rutin", text="Bestäm $k$. Motivera ditt svar.")
    fel = exam_gen.kravradsvakt(_prov([u]))
    assert [f["code"] for f in fel] == ["kravrad"]
    assert "Endast svar krävs" in fel[0]["message"]


def test_redovisningsuppgift_utan_ordet_motivera_ar_inget_fynd():
    """NP skriver «Bestäm f'(x) med hjälp av derivatans definition» utan ett
    ord om redovisning, och kravraden på pappret säger redan «Fullständig
    lösning krävs»."""
    u = _u(typ="redovisning", formaga="P", poang=(0, 2, 0),
           text="Bestäm $f'(x)$ med hjälp av derivatans definition.")
    assert exam_gen.kravradsvakt(_prov([u])) == []


# ── 7. BILDBESTÄLLNINGEN ────────────────────────────────────────────────

def _scen(begrepp: str) -> dict:
    return {"begrepp": begrepp, "filnamn": "a-ny-scen",
            "scene": "SCENE. A small pond in a summer park seen straight "
                     "from the side at eye level, the flat water surface "
                     "running unbroken across the lower third of the frame."}


def test_bilden_som_hor_till_en_annan_uppgift_falls():
    u = _u(text="Beräkna $\\sqrt{49}$.", scen=_scen("algtillväxt damm"))
    fel = exam_gen.scenvakt(_prov([u]))
    assert [f["code"] for f in fel] == ["scenvakt"]


def test_scenvakten_mater_inte_det_engelska_stycket():
    """SCENE-stycket skrivs på engelska och ska klistras in i lärarens
    bildverktyg. Ett svenskt begrepp mot en engelsk text hade fällt varenda
    scen på varje prov."""
    u = _u(text="I en damm växer alger. Arean beskrivs av $A(t)$.",
           losning="$A'(10) = 10$", scen=_scen("algtillväxt damm"))
    assert exam_gen.scenvakt(_prov([u])) == []


# ── kedjan: fynden går i EN reparationsprompt, och räknas om till slut ───

def test_de_nya_fynden_gar_i_samma_reparationsrunda_som_de_gamla():
    """Hela poängen med _raknade_fynd: en lucka, en snedfördelning och en
    felmärkt uppgift ska stå i SAMMA prompt. Modellen ska byta ut uppgifter,
    inte skriva om provet en gång per vakt."""
    uppgifter = [_u(poang=(1, 0, 0), avsnitt="1.1") for _ in range(5)]
    uppgifter.append(_u(poang=(0, 0, 1), avsnitt="1.2",
                        text="Visa att talet alltid är delbart med 3.",
                        delmoment="Kvadratrötter"))
    prov = _prov(uppgifter)
    fel = exam_gen._raknade_fynd(prov, avsnitt=AVSNITT, antal=6,
                                 delmoment=DELMOMENT, profil="prov",
                                 kurs="Ma2a")
    koder = {f["code"] for f in fel}
    assert {"avsnittsniva", "anivavakt", "rubrikord"} <= koder, koder
    # … och arbetsbladet slipper provets egna vakter.
    blad = exam_gen._raknade_fynd(prov, avsnitt=AVSNITT, antal=6,
                                  delmoment=DELMOMENT, profil="arbetsblad",
                                  kurs="Ma2a")
    assert not {"anivavakt", "rubrikord"} & {f["code"] for f in blad}


def test_slutgrinden_raknar_om_varje_ny_vakt():
    """Ett fynd som står kvar i `errors` från en tidig runda pekar på en
    uppgift som kanske inte finns längre. Alla de nya koderna är ENBART
    räknade, ingen domare skriver dem, och ska därför räknas om."""
    for kod in ("avsnittsniva", "avsnittsvikt", "avsnittsmarkning",
                "delmomentvikt", "delmomentmarkning", "citackning",
                "citaggning", "anivavakt", "kravrad", "rubrikord",
                "likvardighet", "scenvakt"):
        assert exam_gen._raknas_om({"code": kod, "path": "uppgifter"}), kod
    # Domarnas fynd står kvar, som förut.
    assert not exam_gen._raknas_om({"code": "relevans", "path": "uppgift 3"})


def test_generate_exam_lagger_omprovsplanen_i_prompten():
    prompter = []

    def llm(model, prompt, **kw):
        prompter.append(prompt)
        return "{}"

    exam_gen.generate_exam("Matematik 1c", "TE26A", ["potenser"], model="m",
                           antal=2, llm=llm, max_rounds=1,
                           referensprov=REFERENS)
    assert "DET HÄR ÄR ETT OMPROV" in prompter[0]
    assert "GÖR DEM INTE ENKLARE" in prompter[0]


def test_poangvakten_hojer_inte_poangen_pa_taket():
    """Exam 116 (2026-09-22): fyra «höj poängen»-fynd tog ett 23-poängspass
    till 27 p. På taket ska vakten be uppgiften om FÄRRE saker i stället."""
    from app import exam_gen
    u = {"del": "B", "formaga": "PL", "typ": "problem", "poang": [0, 1, 0],
         "text": "Teckna ett uttryck för arean. Beräkna arean när sidan är 4.",
         "losning": "x", "bedomning": "+1 C rätt area"}
    exam = {"titel": "t", "kurs": "Matematik 2a", "uppgifter": [u]}
    utan = exam_gen.poangvakt(exam, "prov")
    assert utan and "höj poängtrippeln" in utan[0]["message"]
    # Samma papper på taket (1 p av 1): inte höja, utan stryka en uppmaning.
    pa = exam_gen.poangvakt(exam, "prov", poang_tak=1)
    assert pa and "Höj INTE" in pa[0]["message"]
    assert "stryk en uppmaning" in pa[0]["message"]
    assert "höj poängtrippeln" not in pa[0]["message"]
    # Under taket gäller det gamla rådet.
    under = exam_gen.poangvakt(exam, "prov", poang_tak=5)
    assert "höj poängtrippeln" in under[0]["message"]
    # Utrymmet räknas ned: två fynd på ett papper med EN poäng kvar under
    # taket får ett «höj» och ett «stryk» (exam 117: 22 → 24 p med tak 23).
    u2 = dict(u, text="Teckna uttrycket. Beräkna arean. Avgör om det stämmer.")
    tva = {"titel": "t", "kurs": "Matematik 2a", "uppgifter": [u, u2]}
    fynd = exam_gen.poangvakt(tva, "prov", poang_tak=3)
    assert [("Höj INTE" in f["message"]) for f in fynd] == [False, True]
