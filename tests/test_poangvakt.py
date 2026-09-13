"""Poängvakten (spår 7, 2026-09-13).

Prov 81, uppgift 8: «Teckna ett uttryck för hur mycket kaféet sparar per år
med flergångsmuggar och beräkna besparingen då x = 50 000.» Ett poäng, och
bedömningsraden «+1 C rätt uttryck och besparingen 51 700 kr» — två
prestationer på en poäng. Läraren: «Hur kan den missa denna uppenbara sak?»

Testerna prövar de tre delarna var för sig: räkningen (ren logik, inga anrop),
fixrundan (samma runda som täckningarna, med stubbad llm) och omskrivningens
poängpass (mål-låset som släpper just poängen när kraven blivit fler).
"""
import copy
import json

from app import exam_gen, exam_spec


# Uppgift 8 ordagrant ur prov 81, med poängen och bedömningsraden den fick.
UPPG8 = {
    "del": "C", "typ": "problem", "formaga": "PL", "poang": [0, 1, 0],
    "text": "Ett kafé serverar $x$ koppar kaffe per dag. Engångsmuggar "
            "kostar $0{,}80$ kr styck och flergångsmuggar $0{,}20$ kr "
            "styck.\nTeckna ett uttryck för hur mycket kaféet sparar per år "
            "med flergångsmuggar och beräkna besparingen då $x = 50\\,000$.",
    "losning": "$0{,}60x \\cdot 365 = 219x$; $x = 50\\,000$ ger 51 700 kr.",
    "bedomning": "+1 C rätt uttryck och besparingen 51 700 kr",
}


def _prov(*uppgifter: dict) -> dict:
    return {"titel": "Prov: Tal och uttryck", "hjalpmedel": "Formelblad.",
            "uppgifter": [copy.deepcopy(u) for u in uppgifter]}


def _stub_llm(svar: list[str]):
    anrop: list[dict] = []

    def llm(model, prompt, system=None, options=None, response_format=None,
            max_tokens=None, token_cb=None):
        anrop.append({"prompt": prompt, "system": system})
        return svar[min(len(anrop) - 1, len(svar) - 1)]

    return llm, anrop


# ── räkningen av uppmaningar ─────────────────────────────────────────────

def test_uppmaningarna_raknas_bara_forst_i_satsen():
    """«och» delar satsen — det är samordningen som bär den andra
    prestationen. Ett verb inne i en bisats är ingen uppmaning."""
    assert exam_gen.uppmaningar(UPPG8["text"]) == ["teckna", "beräkna"]
    assert exam_gen.uppmaningar("Beräkna arean av rektangeln.") == ["beräkna"]
    # Bisatsen: samma verb, men det står inte först i sin sats.
    assert exam_gen.uppmaningar(
        "Hur mycket sparar kaféet om vi beräknar med flergångsmuggar?") == []
    assert exam_gen.uppmaningar("Du ska bestämma $x$.") == []
    # Deluppgiftsmarkören framför uppmaningen räknas ändå.
    assert exam_gen.uppmaningar("a) Förenkla $x^2 \\cdot x^5$.") == ["förenkla"]


def test_np_svansen_motivera_ar_ingen_egen_prestation():
    """«Avgör om han har rätt. Motivera.» är EN C-poäng i nationella provets
    form, och står ordagrant i det inspelade bandet (uppgift 5b). Räknades
    svansen som en andra sak kostade varje resonemangsuppgift en runda."""
    assert exam_gen.uppmaningar(
        "Avgör om han har rätt. Motivera.") == ["avgör"]
    assert exam_gen.uppmaningar("Bestäm $x$. Motivera ditt svar.") == ["bestäm"]
    # Men en svans som ber om något eget är en egen sak att göra.
    assert exam_gen.uppmaningar(
        "Bestäm $x$. Förklara varför metoden fungerar.") == \
        ["bestäm", "förklara"]


def test_redovisningssvansen_ar_ingen_egen_prestation():
    """«… och svara i grundpotensform» säger hur svaret skrivs, inte att
    något mer ska räknas ut."""
    assert exam_gen.uppmaningar(
        "Förenkla uttrycket och skriv svaret i grundpotensform.") == \
        ["förenkla"]
    assert exam_gen.uppmaningar(
        "Beräkna volymen och ange svaret med två decimaler.") == ["beräkna"]


# ── regeln: en poäng per sak uppgiften ber om ────────────────────────────

def test_uppgift_8_i_prov_81_falls():
    """Fyndet som beställde hela spåret. Två uppmaningar, en poäng."""
    fel = exam_gen.poangvakt(_prov(UPPG8))
    assert len(fel) == 1 and fel[0]["code"] == "poangvakt"
    m = fel[0]["message"]
    assert "uppgift 1 kräver två saker (teckna, beräkna) men ger 1 p" in m
    # Felraden säger vad modellen ska GÖRA, och att den ska hålla sig i delen.
    assert "Ge den 2 p inom SAMMA del" in m
    assert "bedömningsrad per prestation" in m
    assert "Byt inte ut uppgiften" in m
    # Och samma uppgift med två poäng passerar.
    lagad = copy.deepcopy(UPPG8)
    lagad["poang"] = [0, 2, 0]
    lagad["bedomning"] = ("+1 C tecknar uttrycket $219x$\n"
                          "+1 C beräknar besparingen 51 700 kr")
    assert exam_gen.poangvakt(_prov(lagad)) == []


def test_enpoangaren_med_en_uppmaning_passerar():
    """En sak, en poäng: det är formen provet ska ha, och den ska inte kosta
    en reparationsrunda."""
    rutin = {"del": "B", "typ": "rutin", "formaga": "P", "poang": [1, 0, 0],
             "text": "Beräkna $\\sqrt{49}$.", "losning": "7",
             "bedomning": "+1 E korrekt svar"}
    assert exam_gen.poangvakt(_prov(rutin)) == []
    # … men en 1-poängare som ber om två saker fälls också som rutin: en enda
    # poäng går inte att dela, hur uppgiften än är märkt.
    tva = copy.deepcopy(rutin)
    tva["text"] = "Förenkla $x^2 \\cdot x^5$ och avgör om svaret är ett heltal."
    assert len(exam_gen.poangvakt(_prov(tva))) == 1


def test_anvisningens_ord_raknas_inte():
    """«Visa hur du räknar och förklara varför» står i provets anvisning
    (blad.js) och i instruktionsbandet, aldrig i uppgiftstexten. Räkningen
    läser uppgifterna och bara dem."""
    # Orden bär en uppmaning när de står i en uppgiftstext («förklara varför»
    # är den nakna resonemangssvansen och räknas inte, se nedan) …
    assert exam_gen.uppmaningar("Visa hur du räknar och förklara varför.") == \
        ["visa"]
    # … men anvisningen är ingen uppgift, och pappret ska passera.
    exam = _prov({"del": "B", "typ": "rutin", "formaga": "P",
                  "poang": [1, 0, 0], "text": "Beräkna $12 \\cdot 8$.",
                  "losning": "96", "bedomning": "+1 E korrekt svar"})
    exam["instruktion"] = ("Uppgifter märkta «Fullständig lösning krävs» "
                           "redovisas på lösblad. Visa hur du räknar och "
                           "förklara varför.")
    exam["hjalpmedel"] = "Visa hur du räknar och förklara varför."
    assert exam_gen.poangvakt(exam) == []


def test_deluppgiften_raknas_pa_sin_egen_text():
    """Stammen är gemensam för a) och b): räknades den per deluppgift hade
    varje stam med en uppmaning fällt ett papper där ingenting är fel."""
    exam = _prov({"del": "C", "typ": "problem", "formaga": "PL",
                  "poang": [0, 0, 0],
                  "text": "Bestäm sidan i kuben nedan.",
                  "deluppgifter": [
                      {"poang": [1, 0, 0], "text": "Beräkna volymen.",
                       "losning": "8", "bedomning": "+1 E korrekt svar"},
                      {"poang": [0, 1, 0],
                       "text": "Teckna ett uttryck för arean och beräkna den.",
                       "losning": "24", "bedomning": "+1 C korrekt svar"}]})
    fel = exam_gen.poangvakt(exam)
    assert [f["nr"] for f in fel] == ["1b"]
    assert "uppgift 1b kräver två saker" in fel[0]["message"]


def test_bedomningsraden_med_tva_prestationer_falls():
    """Andra måttet: raden delar ut EN poäng för två prestationer. Fälls
    oavsett hur uppgiftstexten är skriven."""
    u = {"del": "C", "typ": "problem", "formaga": "PL", "poang": [0, 2, 0],
         "text": "Bestäm hur mycket kaféet sparar per år.",
         "losning": "51 700 kr",
         "bedomning": ("+1 C rätt uttryck och besparingen 51 700 kr\n"
                       "+1 C korrekt svar med enhet")}
    fel = exam_gen.poangvakt(_prov(u))
    assert len(fel) == 1 and fel[0]["nr"] == "1"
    m = fel[0]["message"]
    assert "ger EN poäng för två prestationer" in m
    assert "rätt uttryck och besparingen" in m
    assert "en rad per prestation" in m


def test_kvalitetsorden_ar_ingen_andra_prestation():
    """«med godtagbart svar och korrekt enhet» är EN prestation med två krav
    på hur den ska se ut. Fälldes den hade halva NP-formen blivit ett fynd."""
    u = {"del": "B", "typ": "redovisning", "formaga": "P", "poang": [2, 0, 0],
         "text": "Bestäm arean.", "losning": "12",
         "bedomning": ("+1 E lösning med godtagbart svar och korrekt enhet\n"
                       "+1 E svaret angivet med rätt enhet och rimligt")}
    assert exam_gen.poangvakt(_prov(u)) == []
    assert len(exam_gen._prestationsled(
        "rätt uttryck och besparingen 51 700 kr")) == 2
    assert len(exam_gen._prestationsled(
        "lösning med godtagbart svar och korrekt enhet")) == 1
    # Två egenskaper hos SAMMA objekt är inte två prestationer: ledet före
    # «och» har inget eget huvudord. Raden står i det inspelade bandet.
    assert len(exam_gen._prestationsled(
        "korrekt uppställd och förenklad differenskvot")) == 1
    # Och nationella provets A-prosa döms inte alls: den beskriver EN
    # prestation i trettio ord, och att fälla den vore att gissa.
    assert exam_gen._prestationsled(
        "för en lösning där ekvationen löses med redovisat digitalt verktyg "
        "och derivatan används vid rätt tidpunkt") == []


def test_vakten_ar_provets_och_bara_provets():
    """Arbetsbladet drillar samma sak i flera led och gruppuppgiften bygger
    ett resonemang över fyra deluppgifter. Provets regel mätt på dem hade
    fällt lärarens egna papper."""
    for profil in ("arbetsblad", "gruppuppgift"):
        assert exam_gen.poangvakt(_prov(UPPG8), profil) == []


def test_taket_haller_reparationen_till_en_runda():
    """Fler fynd än så är ingen undervärderad uppgift utan ett papper som ska
    skrivas om. Samma tak och samma skäl som delmomentens."""
    exam = _prov(*([UPPG8] * 9))
    assert len(exam_gen.poangvakt(exam)) == exam_gen.POANG_MAX_FYND


def test_raknade_fynden_gar_fore_de_lasta_raderna():
    """Räkningen av uppmaningar är det säkra måttet och raderna det svagare.
    En runda som ber om fem höjningar spräcker nivåmixen och kastas i sin
    helhet — och då blir inte ens det uppenbara fyndet lagat."""
    lumpad = {"del": "C", "typ": "problem", "formaga": "PL",
              "poang": [0, 0, 1], "text": "Bestäm konstanten $a$.",
              "losning": "2",
              "bedomning": "+1 A räknar allmänt med $k$ och drar rätt slutsats"}
    fel = exam_gen.poangvakt(_prov(lumpad, lumpad, lumpad, lumpad, UPPG8))
    assert len(fel) == exam_gen.POANGRAD_MAX_FYND + 1
    # Uppgift 8 (räkningen) står FÖRST, de lästa raderna efter.
    assert "kräver två saker" in fel[0]["message"] and fel[0]["nr"] == "5"
    assert all("två prestationer" in f["message"] for f in fel[1:])


def test_fail_open_pa_tomma_falt():
    assert exam_gen.poangvakt({}) == []
    assert exam_gen.poangvakt({"uppgifter": [{"poang": [0, 0, 0]}]}) == []
    assert exam_gen.poangvakt(
        {"uppgifter": [{"poang": [1, 0, 0], "text": ""}]}) == []


# ── fixrundan: samma runda som täckningarna ──────────────────────────────

def test_fixrundan_far_ratt_rad():
    """Fyndet ska stå i SAMMA reparationsprompt som täckningarnas, och rundan
    ska vara en enda: ETT anrop, och det är reparationen (ingen domare körs
    utan delmomentslista)."""
    lagat = copy.deepcopy(UPPG8)
    lagat["poang"] = [0, 2, 0]
    lagat["bedomning"] = ("+1 C tecknar uttrycket $219x$\n"
                          "+1 C beräknar besparingen 51 700 kr")
    llm, anrop = _stub_llm([json.dumps(_prov(lagat))])
    res = exam_gen._tackning_pass(_prov(UPPG8), [], model="m", llm=llm,
                                  profil="prov", antal=1, skeleton=None,
                                  avsnitt=[], delmoment=[], rounds_used=1,
                                  max_rounds=4)
    assert len(anrop) == 1
    assert "kräver två saker (teckna, beräkna) men ger 1 p" in anrop[0]["prompt"]
    assert res["rounds"] == 2


def test_poangvakten_kors_ocksa_nar_domandet_ar_avstangt():
    """`doma=False` betyder «inga extra modellanrop», och räkningen är noll
    anrop."""
    llm, anrop = _stub_llm([json.dumps(_prov(UPPG8))])
    exam_gen._tackning_pass(_prov(UPPG8), [], model="m", llm=llm,
                            profil="prov", antal=1, skeleton=None, avsnitt=[],
                            delmoment=[], doma=False, rounds_used=1,
                            max_rounds=4)
    assert len(anrop) == 1 and "kräver två saker" in anrop[0]["prompt"]


def test_en_poangandring_som_spracker_balansen_kastas_utan_loop():
    """Balansvakten prövas som förut på det reparationen skickade tillbaka:
    blir pappret trasigt av lagningen behålls det gamla och fyndet står kvar
    som varning. EN runda, aldrig en loop mellan de två vakterna."""
    trasigt = _prov(UPPG8)
    llm, anrop = _stub_llm([json.dumps({"titel": "Prov", "uppgifter": []})])
    res = exam_gen._tackning_pass(trasigt, [], model="m", llm=llm,
                                  profil="prov", antal=1, skeleton=None,
                                  avsnitt=[], delmoment=[], rounds_used=1,
                                  max_rounds=4)
    assert len(anrop) == 1                    # inte två, inte fyra
    assert res["rounds"] == 2
    assert res["exam"] is trasigt
    assert [f["code"] for f in res["errors"]] == ["poangvakt"]


def test_behall_planen_slapps_bara_pa_den_fallda_uppgiften():
    """Begriplighetsfyndet säger «Behåll uppgiftens poäng» och poängvakten
    ber om en höjning. Står båda i samma prompt lyder modellen den ena
    slumpvis, så låset släpps på DEN uppgiften och står kvar på de andra."""
    fel = [{"path": "uppgift 1", "code": "begriplighet",
            "message": "uppgift 1 är otydlig." + exam_gen.BEHALL_PLANEN},
           {"path": "uppgift 2", "code": "begriplighet",
            "message": "uppgift 2 är otydlig." + exam_gen.BEHALL_PLANEN},
           {"path": "uppgift 1", "code": "poangvakt", "message": "höj till 2 p"}]
    ut = exam_gen._slapp_poanglaset(fel)
    assert exam_gen.BEHALL_PLANEN not in ut[0]["message"]
    assert exam_gen.BEHALL_PLANEN in ut[1]["message"]
    # Utan poängfynd rörs listan inte alls.
    assert exam_gen._slapp_poanglaset(fel[:2]) == fel[:2]


# ── omskrivningen: mål-låset släpper JUST poängen ────────────────────────

# Varierade uppgiftstexter: variationsvakten fäller ett prov där två
# uppgifter är för lika, och den körs i samma _validate som balansen.
_AMNEN = ("arean av rektangeln", "volymen av kuben", "omkretsen av cirkeln",
          "medelvärdet i tabellen", "kvadratroten ur talet", "potensen",
          "uttryckets värde", "vinkeln i triangeln", "sträckan på kartan",
          "hastigheten i backen", "massan i påsen", "priset efter rabatten")


def _balanserat_prov(antal: int = 12) -> dict:
    """Ett prov som validerar: skelettets egen balans, en uppgift per plats."""
    slots = exam_spec.balanced_skeleton(antal, "prov", delar=True)
    return {"titel": "Prov", "kurs": "Matematik 1c", "klass": "TE26A",
            "hjalpmedel": "Formelblad.",
            "uppgifter": [
                {"del": s["del"], "formaga": s["formaga"], "typ": s["typ"],
                 "poang": list(s["poang"]),
                 "text": f"Beräkna {_AMNEN[(i - 1) % len(_AMNEN)]} "
                         f"när talet är ${i * 3}$.", "losning": "svar",
                 "bedomning": "\n".join(
                     f"+1 {n} korrekt svar"
                     for n, p in zip("ECA", s["poang"]) for _ in range(p))}
                for i, s in enumerate(slots, 1)]}


def _omskriven(prov: dict) -> dict:
    """Lärarens omskrivning: uppgift 1 ber nu om två saker, poängen står
    kvar."""
    ut = copy.deepcopy(prov)
    ut["uppgifter"][0]["text"] = ("Teckna ett uttryck för kaféets besparing "
                                  "och beräkna den då $x = 50\\,000$.")
    return ut


def test_omskrivningen_far_hoja_poangen_nar_kraven_blev_fler():
    """Läraren skriver om uppgift 1 så att den ber om två saker. Mål-låset
    släpper igenom bara den uppgiften, och poängpasset ger den en runda till
    så att poängtrippeln får följa kraven."""
    fore = _balanserat_prov()
    assert exam_gen._validate(copy.deepcopy(fore), "prov")[1] == []
    efter = _omskriven(fore)
    fynd = exam_gen.poangvakt(efter)
    assert fynd and fynd[0]["nr"] == "1"
    lagat = copy.deepcopy(efter)
    poang = lagat["uppgifter"][0]["poang"]
    niva = next(i for i, p in enumerate(poang) if p)
    poang[niva] += 1
    lagat["uppgifter"][0]["bedomning"] = "\n".join(
        f"+1 {n} steg {k}" for n, p in zip("ECA", poang)
        for k in range(1, p + 1))
    llm, anrop = _stub_llm([json.dumps(lagat)])
    res = exam_gen._poangpass(fore, {"exam": efter, "errors": [], "rounds": 1},
                              model="m", llm=llm, profil="prov",
                              riktning=("uppgift", 1), niva_mal=None,
                              max_rounds=4)
    assert len(anrop) == 1
    assert "kräver två saker (teckna, beräkna)" in anrop[0]["prompt"]
    assert res["rounds"] == 2
    assert res["exam"]["uppgifter"][0]["poang"] == poang
    # Och de andra uppgifterna står orörda: mål-låset gäller fortfarande.
    assert res["exam"]["uppgifter"][1:] == efter["uppgifter"][1:]


def test_omskrivningen_som_inte_andrar_kraven_kostar_ingen_runda():
    """Kassetteregeln i sak: rör varvet inte kraven ska det gå exakt de anrop
    det gick förut."""
    fore = _balanserat_prov()
    efter = copy.deepcopy(fore)
    efter["uppgifter"][0]["text"] = "Beräkna uppgift 1 en gång till."
    llm, anrop = _stub_llm(["{}"])
    res = exam_gen._poangpass(fore, {"exam": efter, "errors": [], "rounds": 1},
                              model="m", llm=llm, profil="prov",
                              riktning=("uppgift", 1), niva_mal=None,
                              max_rounds=4)
    assert anrop == [] and res["rounds"] == 1 and res["exam"] is efter


def test_poangfyndet_pa_en_orord_uppgift_ror_inte_varvet():
    """Ett gammalt fynd på uppgift 3 är inget besked om det önskemål läraren
    just skickade — samma regel som nivågrindens."""
    fore = _balanserat_prov()
    fore["uppgifter"][2]["text"] = ("Teckna ett uttryck och beräkna svaret.")
    efter = copy.deepcopy(fore)
    efter["uppgifter"][0]["text"] = "Beräkna uppgift 1 en gång till."
    llm, anrop = _stub_llm(["{}"])
    res = exam_gen._poangpass(fore, {"exam": efter, "errors": [], "rounds": 1},
                              model="m", llm=llm, profil="prov",
                              riktning=("uppgift", 1), niva_mal=None,
                              max_rounds=4)
    assert anrop == [] and res["exam"] is efter


def test_poangrundan_som_spracker_pappret_kastas_och_varnar():
    """«Rent före, trasigt efter» är en försämring: lärarens omskrivning står
    kvar, och fyndet visas som varning i stället."""
    fore = _balanserat_prov()
    efter = _omskriven(fore)
    llm, anrop = _stub_llm([json.dumps({"titel": "Prov", "uppgifter": []})])
    res = exam_gen._poangpass(fore, {"exam": efter, "errors": [], "rounds": 1},
                              model="m", llm=llm, profil="prov",
                              riktning=("uppgift", 1), niva_mal=None,
                              max_rounds=4)
    assert len(anrop) == 1 and res["rounds"] == 2
    assert res["exam"] is efter
    assert [f["code"] for f in res["errors"]] == ["poangvakt"]
