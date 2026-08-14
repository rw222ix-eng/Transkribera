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


def test_alla_few_shots_foljer_dramaturgin():
    """Leonard-principen: tavlan ska gå att gå igenom uppifrån och ned som en
    berättelse. Shotarna ÄR den ordningen — prompttext utan few-shot-stöd följs
    dåligt, så det är här kravet faktiskt bor."""
    for uppdrag, doc in lb.FEW_SHOTS:
        s = _vanstersektioner(doc)
        arter = [sek["kind"] for sek in s]
        assert arter[:5] == ["heading", "list", "divider", "callout", "text"], \
            f"{uppdrag}: {arter}"
        # Agendan: 3–4 korta punkter i vardaglig svenska.
        assert 3 <= len(s[1]["items"]) <= 4, uppdrag
        assert all(len(p.split()) <= 5 for p in s[1]["items"]), uppdrag
        # Öppningsfrågan är en fråga till klassen, inte en definition.
        assert s[3]["children"][0]["text"].endswith("?"), uppdrag
        # Högst EN mening vardagsspråk innan matematiken tar över.
        assert arter.count("text") == 1, uppdrag
        # Figuren (eller den generiska uppställningen) FÖRE första formeln.
        figur = min(i for i, k in enumerate(arter)
                    if k in ("shape", "graph") or (k == "list" and i > 1))
        assert figur < arter.index("math"), uppdrag
        # Och vanligt fel-callouten sist.
        sista = s[-1]
        assert sista["kind"] == "callout" and sista["color"] == "red", uppdrag
        assert sista["children"][0]["text"].startswith("Vanligt fel:"), uppdrag
        # Tiden lägger systemet dit (satt_tid) — aldrig modellen.
        assert not any(lb._TID_RE.match(sek.get("text", "")) for sek in s), uppdrag


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
    assert "Sammanfattning" in p           # few-shot 3 (tabellmönstret)


def test_prompten_bar_dramaturgin():
    """Kraven ur Leonards genomgång: agenda, streck, öppningsfråga, figur före
    formel — och att modellen INTE ska skriva klockslaget."""
    p = lb.build_prompt("Ma2c", "TE24", "randvinkelsatsen")
    assert "Dramaturgi" in p
    assert "Agenda" in p and "divider-sektion" in p
    assert "Öppningsfrågan" in p
    assert "EFTER figuren, aldrig före" in p
    assert "Skriv INTE något klockslag" in p
    assert "Fallgalleri" in p


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
    """Läraren vill ha klockslaget litet uppe till vänster. Det sätts
    deterministiskt — och tavlan måste fortfarande validera."""
    ut = lb.satt_tid(_valid_doc(), "08:15")
    forst = ut["boards"][0]["sections"][0]
    assert forst == {"kind": "text", "text": "08:15", "size": 16,
                     "color": "black", "gapAfter": 10}
    parsed, fel = ws.validate_board_json(ut)
    assert parsed is not None and fel == []
    # Högertavlan rörs inte.
    assert ut["boards"][1] == _valid_doc()["boards"][1]


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


def test_refine_board_autorepairs_invalid_result():
    llm, calls = _stub_llm([json.dumps(_broken_doc()), json.dumps(_valid_doc())])
    res = lb.refine_board(_valid_doc(), "gör om", model="m", llm=llm)
    assert res["errors"] == []
    assert res["rounds"] == 2
