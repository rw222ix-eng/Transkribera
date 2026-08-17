"""Lektionstavlor: promptbygge och reparationsloop med stubbat LLM."""
import copy
import json

from app import lesson_board as lb
from app import whiteboard_spec as ws


def _valid_doc() -> dict:
    return copy.deepcopy(lb.FEW_SHOTS[0][1])


def _broken_doc() -> dict:
    """Giltigt schema men ett regelfel (punkt utanför range)."""
    doc = _valid_doc()
    doc["boards"][0]["sections"] = [
        {"kind": "graph", "width": 400, "height": 300,
         "xRange": [-1, 5], "yRange": [-1, 5],
         "points": [{"x": 99, "y": 0, "label": "A"}]},
    ]
    return doc


def _stub_llm(responses: list[str]):
    """Returnerar (llm, calls) — llm poppar svaren i tur och ordning."""
    calls: list[dict] = []

    def llm(model, prompt, system=None, options=None, response_format=None,
            max_tokens=None, token_cb=None):
        calls.append({"model": model, "prompt": prompt, "system": system,
                      "options": options, "response_format": response_format,
                      "max_tokens": max_tokens})
        return responses[min(len(calls) - 1, len(responses) - 1)]

    return llm, calls


# ---------------------------------------------------------------- few-shots --

def test_few_shots_are_valid_wb_json():
    for uppdrag, doc in lb.FEW_SHOTS:
        parsed, errors = ws.validate_board_json(doc)
        assert parsed is not None, uppdrag
        assert errors == [], (uppdrag, errors)


def test_en_few_shot_visar_sammanfattningstabellen():
    """Lärarens tavla (docs/forlagor/) samlar lektionens fall i EN tabell som
    fylls i tillsammans med klassen — det är genomgångens mål. Formen fanns i
    schemat men i ingen shot, och en form modellen aldrig SETT skriver den
    inte."""
    tabeller = [s for _u, doc in lb.FEW_SHOTS
                for b in doc["boards"]
                for flow in ([b.get("sections") or []]
                             + [c["sections"] for c in b.get("columns") or []])
                for s in flow if s.get("kind") == "table"]
    assert tabeller, "ingen few-shot visar en table-sektion"
    for t in tabeller:
        # Bredden räknas ur innehållet — en satt cellW ger likbreda kolumner,
        # och en sammanfattning har inte likbreda kolumner.
        assert "cellW" not in t, "sammanfattningstabellen ska inte låsa cellW"
        assert all(len(rad) == len(t["headers"]) for rad in t["rows"])


def _vanstersektioner(doc: dict) -> list[dict]:
    return doc["boards"][0]["sections"]


def _alla_sektioner(doc: dict):
    """Varje sektion i dokumentet, ned genom row/col/callout."""
    def ned(flode):
        for sek in flode or []:
            yield sek
            yield from ned(sek.get("children"))
    for b in doc["boards"]:
        yield from ned(b.get("sections") or [])
        for kol in b.get("columns") or []:
            yield from ned(kol.get("sections") or [])


def test_alla_few_shots_foljer_dramaturgin():
    """Leonard-principen: tavlan ska gå att gå igenom uppifrån och ned som en
    berättelse. Shotarna ÄR den ordningen — prompttext utan few-shot-stöd följs
    dåligt, så det är här kravet faktiskt bor."""
    for uppdrag, doc in lb.FEW_SHOTS:
        s = _vanstersektioner(doc)
        arter = [sek["kind"] for sek in s]
        assert arter == ["heading", "list", "divider", "heading", "text", "row"], \
            f"{uppdrag}: {arter}"
        # Rubriken och agendan står mitt på tavlan — så skriver läraren dem.
        assert s[0].get("align") == "center" and s[1].get("align") == "center", uppdrag
        # Agendan: 3–4 korta punkter i vardaglig svenska, och boksidorna.
        assert 3 <= len(s[1]["items"]) <= 4, uppdrag
        assert all(len(p.split()) <= 5 for p in s[1]["items"]), uppdrag
        assert any("boken s." in p for p in s[1]["items"]), uppdrag
        # Öppningsfrågan är en fråga till klassen, inte en definition — och en
        # rubrik, inte en ruta. Utan färg: färgen betyder något annat nu.
        assert s[3]["text"].endswith("?") and "color" not in s[3], uppdrag
        # Högst EN mening vardagsspråk innan matematiken tar över.
        assert arter.count("text") == 1, uppdrag
        # Raden sist: figuren (eller den generiska uppställningen) till vänster,
        # formlerna i en col till höger — annars blir tavlan en smal remsa.
        rad = s[-1]["children"]
        assert len(rad) == 2 and rad[1]["kind"] == "col", uppdrag
        assert rad[0]["kind"] in ("shape", "graph", "col"), uppdrag
        spalt = [c["kind"] for c in rad[1]["children"]]
        assert spalt[0] == "math", uppdrag
        # Vanligt fel sist i spalten: röd rubrik + understrykning, ingen ruta.
        rubrik = next(c for c in rad[1]["children"]
                      if c.get("text", "").startswith("Vanligt fel:"))
        i = rad[1]["children"].index(rubrik)
        assert rubrik["color"] == "red" and rubrik["kind"] == "text", uppdrag
        assert rad[1]["children"][i + 1]["kind"] == "underline", uppdrag
        # Tiden lägger systemet dit (satt_tid) — aldrig modellen.
        assert not any(lb._TID_RE.match(sek.get("text", "")) for sek in s), uppdrag


def test_ingen_few_shot_ritar_rutor():
    """«Alla de här blå och röda rutorna, inringande liksom — det ser ganska
    fult ut. Det gör jag inte på tavlan själv.» Shotarna lär ut det de visar,
    så en enda kvarglömd callout hade lärt ut rutan igen."""
    for uppdrag, doc in lb.FEW_SHOTS:
        assert not [s for s in _alla_sektioner(doc) if s["kind"] == "callout"], \
            uppdrag


def test_few_shotarna_ar_svarta_utom_dar_fargen_betyder_nagot():
    """«Massa blåa färger och röda färger — det känns lite inkonsekvent. Vi
    tonar ner på det här. Drastiskt.» Kvar är två ställen: rött för det som
    varnar, och färg inne i figurer för att skilja linjer och vinklar åt."""
    for uppdrag, doc in lb.FEW_SHOTS:
        for sek in _alla_sektioner(doc):
            if sek["kind"] == "graph":
                continue                 # figurens färger skiljer linjer åt
            assert sek.get("color") in (None, "red"), (uppdrag, sek)
            strecket = sek.get("underline")
            if isinstance(strecket, dict):
                assert strecket.get("color") in (None, "red"), (uppdrag, sek)


def test_exemplen_ar_utgangspunkter_inte_losningar():
    """«Jag kommer ju göra själva uträkningarna. Det räcker med en stark
    utgångspunkt jag kan utgå ifrån, och sen kan det bara stå rent generellt
    vad jag ska göra.» Alltså: ingen färdig lösning, inget facit på tavlan."""
    for uppdrag, doc in lb.FEW_SHOTS:
        texter = [s.get("text", "") for s in _alla_sektioner(doc)]
        assert not [t for t in texter if t.startswith("Svar")], uppdrag


def test_few_shotarna_haller_exempeltaket():
    """«Ett enkelt exempel, eller flera enkla — max tre.» Fler än så är för
    mycket att hinna med, och shotarna får inte visa något annat."""
    for uppdrag, doc in lb.FEW_SHOTS:
        rubriker = [s.get("text", "") for s in _alla_sektioner(doc)
                    if s["kind"] == "heading" and s.get("text", "").startswith("Exempel")]
        assert len(rubriker) <= 3, (uppdrag, rubriker)


def test_few_shotarna_haller_textbudgeten():
    """Shotarna ÄR budgeten: en modell härmar det den ser, och en shot som
    ligger över taket lär ut det taket förbjuder."""
    for uppdrag, doc in lb.FEW_SHOTS:
        parsed, _fel = ws.validate_board_json(doc)
        for i, board in enumerate(parsed.boards):
            flows = ([board.sections or []]
                     + [c.sections for c in board.columns or []])
            volym = sum(ws._text_volym(f) for f in flows)
            assert volym <= ws._MAX_BOARD_TEXT, f"{uppdrag}, tavla {i}: {volym}"


# ------------------------------------------------------------------ prompt --

def test_build_prompt_contains_conventions_and_task():
    p = lb.build_prompt("Ma3c", "NA23", "derivatans definition",
                        memory="Förra lektionen: gränsvärden.")
    assert "decimalkomma" in p.lower() or "Decimalkomma" in p
    assert "derivatans definition" in p
    assert "NA23" in p and "Ma3c" in p
    assert "Förra lektionen: gränsvärden." in p
    assert "Pythagoras sats" in p          # few-shot 1
    assert "x^2 - 4*x + 3" in p            # few-shot 2 (expr-mönstret)
    # few-shot 3: tabellen som fylls i tillsammans med klassen
    assert "Fyller vi i tillsammans" in p


def test_prompten_bar_dramaturgin():
    """Kraven ur Leonards genomgång: agenda, streck, öppningsfråga, figur före
    formel — och att modellen INTE ska skriva lektionstiden."""
    p = lb.build_prompt("Ma2c", "TE24", "randvinkelsatsen")
    assert "Dramaturgi" in p
    assert "Agenda" in p and "divider-sektion" in p
    assert "Öppningsfrågan" in p
    assert "EFTER figuren (till höger om den), aldrig före" in p
    assert "Skriv INTE någon lektionstid" in p
    assert "Fallgalleri" in p


def test_prompten_forbjuder_rutor_och_kraver_bredden():
    """Lärarens två invändningar mot den första skarpa tavlan: rutorna, och
    att tavlan stod i en smal remsa med tomt utrymme till höger."""
    p = lb.build_prompt("Ma1b", "9A", "pythagoras sats")
    assert "Rita ALDRIG rutor" in p
    assert "callout-sektioner är förbjudna" in p
    assert "SIDA VID SIDA i en row" in p
    assert "Arbetar i boken s." in p          # agendan bär boksidorna


def test_prompten_bar_exempelkraven():
    """«Ett enkelt exempel — max tre — med bra siffror, som speglar bokens
    uppgifter, och där man lätt kan visa ett vanligt fel. Men egna exempel.»"""
    p = lb.build_prompt("Ma1b", "9A", "pythagoras sats")
    assert "1–3 exempel, aldrig fler" in p
    assert "GÅR JÄMNT UT" in p
    assert "TYP och NIVÅ" in p
    assert "skriv ALLTID egna uppgifter" in p
    assert "det felaktiga ledet i rött bredvid det rätta" in p
    assert "Väg 1" in p and "Väg 2" in p
    # Utgångspunkt, inte facit — läraren räknar på plats.
    assert "UTGÅNGSPUNKT, inte en färdig lösning" in p
    assert "Räkna INTE ut svaret" in p
    # Och när boken är källan: tavlan ska räcka för sidornas alla uppgifter.
    assert "SAMTLIGA uppgifter på just de" in p


def test_prompten_tonar_ner_fargerna():
    """Färg är ett verktyg, inte dekoration: rött varnar, figurens färger
    skiljer linjer åt, allt annat är svart."""
    p = lb.build_prompt("Ma1b", "9A", "pythagoras sats")
    assert "tavlan skrivs i SVART" in p
    assert "skilja kurvor, linjer och vinklar åt" in p


def test_build_prompt_bar_fallgalleriet():
    """Fjärde shoten: högertavlans andra form, med färdiga figurer i stället
    för uträkningar."""
    p = lb.build_prompt("Ma2c", "TE24", "randvinkelsatsen")
    assert "Randvinkelsatsen" in p
    assert "Tre fall" in p
    assert "Exempel 4 — uppdrag:" in p


def test_prompten_ar_inte_orimligt_lang():
    """Fyra kompletta few-shots (varav en med tre cirkelpolygoner) — prompten
    ska ändå rymmas med marginal i kontexten."""
    assert len(lb.build_prompt("Ma1b", "9A", "procent")) < 40_000


def test_prompten_bar_textbudgeten():
    """Lärarens fjärde dom: tavlan ska bära det som SKRIVS, inte allt som sägs.
    Kravet måste stå i prompten — valideringen kan bara fälla efteråt, och en
    fällning kostar en reparationsrunda."""
    p = lb.build_prompt("Ma3c", "NA25", "logaritmer")
    assert "Textbudget" in p
    assert "löpande prosa" in p
    assert "table-sektion" in p


def test_build_prompt_without_memory_omits_memory_block():
    p = lb.build_prompt("Ma1b", "9A", "procent")
    assert "lektionsminnet" not in p


def test_underlaget_ar_niva_och_typ_inte_innehall():
    """Underlagets uppgifter följer med i prompten som text — då måste blocket
    också säga att de inte får skrivas av, inte ens med utbytta tal."""
    p = lb.build_prompt("Ma1b", "9A", "procent",
                        underlag="Bokuppslag s. 12: 1201) Beräkna 25 % av 80.")
    assert "HELT EGNA exempel och uppgifter" in p
    assert "skriv aldrig av underlagets" in p


def test_repair_prompt_lists_problems():
    doc = _valid_doc()
    p = lb.build_repair_prompt(doc, [
        {"path": "boards[0]", "code": "grafbredd", "message": "för bred graf"},
        "[WB] hoger: 2 element-överlapp upptäckt",
    ])
    assert "för bred graf" in p
    assert "element-överlapp" in p
    assert json.dumps(doc, ensure_ascii=False)[:60] in p


# ---------------------------------------------------------------- satt_tid --

def test_tiden_laggs_forst_pa_vanstertavlan():
    """Läraren vill ha lektionstiden litet uppe till vänster. Den sätts
    deterministiskt — och tavlan måste fortfarande validera."""
    ut = lb.satt_tid(_valid_doc(), "08:15")
    forst = ut["boards"][0]["sections"][0]
    assert forst == {"kind": "text", "text": "08:15", "size": 16,
                     "color": "black", "gapAfter": 10}
    parsed, fel = ws.validate_board_json(ut)
    assert parsed is not None and fel == []
    # Högertavlan rörs inte.
    assert ut["boards"][1] == _valid_doc()["boards"][1]


def test_hela_passet_star_pa_tavlan():
    """«Det ska stå starttid och sen bindestreck sluttid.» — och spannet ska
    kunna bytas ut lika idempotent som ett ensamt klockslag."""
    ut = lb.satt_tid(_valid_doc(), "09:10", "10:20")
    assert ut["boards"][0]["sections"][0]["text"] == "09:10–10:20"
    assert ws.validate_board_json(ut)[1] == []
    igen = lb.satt_tid(ut, "09:10", "10:20")
    assert [s.get("text") for s in igen["boards"][0]["sections"][:2]] \
        == ["09:10–10:20", "Pythagoras sats"]
    # Utan sluttid blir det bara starten — aldrig ett gissat klockslag.
    assert lb.satt_tid(ut, "09:10")["boards"][0]["sections"][0]["text"] == "09:10"


def test_tiden_ar_idempotent():
    """refine/repair skriver om HELA tavlan; injektionen görs om efteråt och
    får aldrig ge två klockslag."""
    ut = lb.satt_tid(lb.satt_tid(_valid_doc(), "08:15"), "08:15")
    sektioner = ut["boards"][0]["sections"]
    assert sektioner[0]["text"] == "08:15"
    assert sektioner[1]["kind"] == "heading"
    # Ny tid ersätter den gamla.
    bytt = lb.satt_tid(ut, "13:30")
    assert bytt["boards"][0]["sections"][0]["text"] == "13:30"
    assert bytt["boards"][0]["sections"][1]["kind"] == "heading"


def test_tiden_skrivs_med_kolon():
    """Schemat kan lämna 9.10 — och en punkt mellan siffror fälls av
    decimalkommaregeln i whiteboard_spec."""
    ut = lb.satt_tid(_valid_doc(), "9.10")
    assert ut["boards"][0]["sections"][0]["text"] == "9:10"
    assert ws.validate_board_json(ut)[1] == []


def test_utan_starttid_ingen_tidssektion():
    doc = _valid_doc()
    assert lb.satt_tid(doc, None) == doc
    assert lb.satt_tid(doc, "  ") == doc
    # …och en tid som redan ligger där tas bort igen när starttiden försvinner.
    assert lb.satt_tid(lb.satt_tid(doc, "08:15"), None) == doc


def test_satt_tid_ror_inte_originalet():
    doc = _valid_doc()
    lb.satt_tid(doc, "08:15")
    assert doc["boards"][0]["sections"][0]["kind"] == "heading"


def test_tiden_hittar_vanstertavlan_aven_med_kolumner():
    """Motorn ritar `sections` bara när tavlan saknar `columns` (layout.js) —
    tiden måste hamna där den faktiskt syns."""
    doc = _valid_doc()
    doc["boards"][0] = {"width": 900, "height": 780, "name": "vanster",
                        "columns": [{"weight": 1, "sections": [
                            {"kind": "heading", "text": "Rubrik", "size": 30}]}]}
    ut = lb.satt_tid(doc, "08:15")
    assert ut["boards"][0]["columns"][0]["sections"][0]["text"] == "08:15"


def test_satt_tid_taler_trasig_tavla():
    assert lb.satt_tid(None, "08:15") is None
    assert lb.satt_tid({}, "08:15") == {}
    assert lb.satt_tid({"boards": []}, "08:15") == {"boards": []}


# ---------------------------------------------------------- generate_board --

def test_generate_valid_first_try():
    llm, calls = _stub_llm([json.dumps(_valid_doc())])
    res = lb.generate_board("Ma1b", "9A", "Pythagoras sats", model="m", llm=llm)
    assert res["errors"] == []
    assert res["rounds"] == 1
    assert res["board"]["title"] == "Pythagoras sats"
    # grammatiktvånget skickas med
    assert calls[0]["response_format"]["type"] == "json_schema"
    assert calls[0]["system"] == lb.SYSTEM


def test_generate_passes_token_cb_to_llm():
    """token_cb (live-uppbyggnaden i UI:t) ska nå LLM-anropet i varje runda."""
    seen: list = []

    def llm(model, prompt, system=None, options=None, response_format=None,
            max_tokens=None, token_cb=None):
        seen.append(token_cb)
        if token_cb:
            token_cb('{"title":')
        return json.dumps(_valid_doc())

    cb_tokens: list[str] = []
    cb = cb_tokens.append
    res = lb.generate_board("Ma1b", "9A", "x", model="m", llm=llm, token_cb=cb)
    assert res["errors"] == []
    assert seen and all(c is cb for c in seen)
    assert cb_tokens == ['{"title":']


def test_generate_repairs_rule_error():
    llm, calls = _stub_llm([json.dumps(_broken_doc()), json.dumps(_valid_doc())])
    res = lb.generate_board("Ma1b", "9A", "x", model="m", llm=llm)
    assert res["rounds"] == 2
    assert res["errors"] == []
    # reparationsprompten innehöll det maskinläsbara felet
    assert "utanför" in calls[1]["prompt"]


def test_generate_gives_up_after_max_rounds():
    llm, calls = _stub_llm([json.dumps(_broken_doc())])
    res = lb.generate_board("Ma1b", "9A", "x", model="m", llm=llm)
    assert res["rounds"] == lb.MAX_ROUNDS
    assert len(calls) == lb.MAX_ROUNDS
    assert any(e["code"] == "utanför-range" for e in res["errors"])
    assert res["board"] is not None      # senaste försöket redovisas ärligt


def test_generate_retries_on_invalid_json_then_succeeds():
    # Trunkerat/trasigt svar (bench Fas 2) → omkörning inom rundbudgeten.
    llm, calls = _stub_llm(["det här är inte json", json.dumps(_valid_doc())])
    res = lb.generate_board("Ma1b", "9A", "x", model="m", llm=llm)
    assert res["errors"] == []
    assert res["rounds"] == 2
    assert len(calls) == 2


def test_generate_handles_non_json_all_rounds():
    llm, calls = _stub_llm(["det här är inte json"])
    res = lb.generate_board("Ma1b", "9A", "x", model="m", llm=llm)
    assert res["board"] is None
    assert res["errors"][0]["code"] == "json"
    assert res["rounds"] == lb.MAX_ROUNDS
    assert len(calls) == lb.MAX_ROUNDS


def test_generate_parses_json_with_surrounding_noise():
    llm, _ = _stub_llm(["Här är tavlan:\n" + json.dumps(_valid_doc()) + "\nKlart!"])
    res = lb.generate_board("Ma1b", "9A", "x", model="m", llm=llm)
    assert res["errors"] == []


# ------------------------------------------------------------ repair_board --

def test_repair_board_uses_client_warnings():
    llm, calls = _stub_llm([json.dumps(_valid_doc())])
    res = lb.repair_board(_valid_doc(),
                          ["[WB] hoger: 1 element-överlapp upptäckt"],
                          model="m", llm=llm)
    assert res["errors"] == []
    assert res["rounds"] == 2            # 1 (generering) + 1 (reparation)
    assert "element-överlapp" in calls[0]["prompt"]


def test_repair_board_respects_shared_round_budget():
    llm, calls = _stub_llm([json.dumps(_valid_doc())])
    res = lb.repair_board(_valid_doc(), ["[WB] varning"],
                          model="m", llm=llm, rounds_used=lb.MAX_ROUNDS)
    assert calls == []                   # budgeten redan slut — inget LLM-anrop
    assert res["rounds"] == lb.MAX_ROUNDS
    assert res["errors"] == ["[WB] varning"]


# ------------------------------------------------------------ refine_board --

def test_refine_board_applies_instruction():
    updated = _valid_doc()
    updated["title"] = "Pythagoras sats — repetition"
    llm, calls = _stub_llm([json.dumps(updated)])
    res = lb.refine_board(_valid_doc(), "byt exempel 2 mot ett med decimaltal",
                          model="m", llm=llm)
    assert res["errors"] == []
    assert res["board"]["title"] == "Pythagoras sats — repetition"
    assert "byt exempel 2" in calls[0]["prompt"]


def test_refine_board_bar_elementet_lararen_pekade_pa():
    """Klicket i granskningen fastnade i webbläsaren: bara meningen gick till
    modellen, som fick gissa vilken av tjugo rutor «gör den kortare» gällde.
    Namnet är lärarens etikett och finns inte i JSON:en — innehållet gör det,
    och det är innehållet som pekar ut rutan."""
    llm, calls = _stub_llm([json.dumps(_valid_doc())])
    lb.refine_board(_valid_doc(), "gör den kortare", model="m", llm=llm,
                    mal={"namn": "Formel 3", "innehall": "a^2 + b^2 = c^2"})
    prompt = calls[0]["prompt"]
    assert "PEKADE PÅ «Formel 3»" in prompt
    assert "a^2 + b^2 = c^2" in prompt
    assert "låt allt annat i dokumentet stå oförändrat" in prompt
    # Och utan klick står prompten som förut — ingen rad om något element.
    llm2, calls2 = _stub_llm([json.dumps(_valid_doc())])
    lb.refine_board(_valid_doc(), "gör den kortare", model="m", llm=llm2)
    assert "PEKADE PÅ" not in calls2[0]["prompt"]


def test_refine_board_autorepairs_invalid_result():
    llm, calls = _stub_llm([json.dumps(_broken_doc()), json.dumps(_valid_doc())])
    res = lb.refine_board(_valid_doc(), "gör om", model="m", llm=llm)
    assert res["errors"] == []
    assert res["rounds"] == 2


def test_refine_board_far_bokdorren_med_sig():
    """«Lägg till vilka uppgifter vi ska göra under lektionen» kunde bara bli en
    allmän mening: genereringen fick bokens sidor och lärarens urval, men
    iterationen fick ingenting — numren stod inte i prompten."""
    llm, calls = _stub_llm([json.dumps(_valid_doc())])
    lb.refine_board(_valid_doc(), "lägg till vilka uppgifter vi ska göra",
                    model="m", llm=llm,
                    bok="UR LÄROBOKEN — Liber Ma 1c, s. 2–6.\n\nLÄRARENS URVAL: "
                        "klassen ska räkna uppg. 1101–1103, 1105–1119.")
    prompt = calls[0]["prompt"]
    assert "LÄRARENS URVAL" in prompt and "1101–1103, 1105–1119" in prompt
    # Källan står FÖRE tavlan: det är underlaget, inte något att ändra i.
    assert prompt.index("LÄRARENS URVAL") < prompt.index("nuvarande lektionstavlan")
    # Och utan bok står prompten som förut.
    llm2, calls2 = _stub_llm([json.dumps(_valid_doc())])
    lb.refine_board(_valid_doc(), "gör om", model="m", llm=llm2)
    assert "UR LÄROBOKEN" not in calls2[0]["prompt"]
