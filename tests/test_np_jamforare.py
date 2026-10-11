"""NP-jämföraren (app/np_jamforare): provets poäng mot nationella provets.

Rickard 2026-10-10, BA26B prov 2: jämförelsen med NP uppgift för uppgift ska
göras i generatorn, inte för hand efteråt."""
from app import np_jamforare


NP = [{"id": "NpMa1a vt22 C18a", "poang": [2, 0, 0], "niva": "E",
       "vad": "lös linjär ekvation med parentes, x på båda sidor"},
      {"id": "NpMa1a vt17 D18b", "poang": [1, 1, 0], "niva": "C",
       "vad": "lös ut variabel ur given formel med insatt värde"}]


def _dom(np, poang):
    return {"np": np, "poang": poang, "motivering": ""}


def test_profilen_har_kursens_np_enheter():
    enheter = np_jamforare.np_enheter("Matematik, nivå 1a")
    assert len(enheter) > 50
    assert all(e["id"].startswith("NpMa1a ") for e in enheter)
    assert np_jamforare.np_enheter("Matematik, nivå 3c") == []


def test_annan_niva_och_annan_fordelning_faller_men_inte_annat_antal():
    enheter = [{"nr": "3b", "niva": "C", "poang": [0, 1, 0]},     # NP: E
               {"nr": "6", "niva": "E", "poang": [1, 0, 0]},      # NP: E+C
               {"nr": "11", "niva": "C", "poang": [0, 2, 0]},     # NP: 1/1/0
               {"nr": "9", "niva": "E", "poang": [1, 0, 0]},      # NP: 2 E
               {"nr": "4", "niva": "E", "poang": [1, 0, 0]}]      # samma
    domar = {"3b": _dom("NpMa1a vt22 C18a", [1, 0, 0]),
             "6": _dom("NpMa1a vt17 D18b", [1, 1, 0]),
             "11": _dom("NpMa1a vt17 D18b", [1, 1, 0]),
             "9": _dom("NpMa1a vt22 C18a", [2, 0, 0]),
             "4": _dom("NpMa1a vt22 C18a", [1, 0, 0])}
    fynd = np_jamforare.npj_fynd(enheter, domar, NP)
    assert [f["nr"] for f in fynd] == ["3b", "6", "11"]
    assert fynd[0]["domd"] == "E" and fynd[0]["pastadd"] == "C"
    assert "NpMa1a vt22 C18a" in fynd[0]["message"]


def test_ingen_tystnad_och_paharttat_id_faller_aldrig():
    enheter = [{"nr": "1", "niva": "C", "poang": [0, 1, 0]},
               {"nr": "2", "niva": "C", "poang": [0, 1, 0]},
               {"nr": "3", "niva": "C", "poang": [0, 1, 0]}]
    domar = {"1": _dom("ingen", [0, 0, 0]),
             "2": _dom("NpMa1a vt99 B1", [1, 0, 0])}
    assert np_jamforare.npj_fynd(enheter, domar, NP) == []


def test_trasigt_svar_ger_ingen_dom():
    assert np_jamforare.parse_npj("inte json") == {}


def test_bladet_byter_uppgift_i_stallet_for_poang():
    enheter = [{"nr": "11", "niva": "C", "poang": [0, 1, 0]},
               {"nr": "12", "niva": "C", "poang": [0, 2, 0]}]
    domar = {"11": _dom("NpMa1a vt22 C18a", [1, 0, 0]),
             "12": _dom("NpMa1a vt17 D18b", [1, 1, 0])}       # samma nivå
    fynd = np_jamforare.npj_fynd(enheter, domar, NP, "arbetsblad")
    assert [f["nr"] for f in fynd] == ["11"]
    assert "byt uppgiften" in fynd[0]["message"]


def test_a_bladets_uppgift_utan_np_tvilling_faller():
    enheter = [{"nr": "3", "niva": "A", "poang": [0, 0, 1]},
               {"nr": "4", "niva": "C", "poang": [0, 1, 0]}]
    domar = {"3": _dom("ingen", [0, 0, 0]), "4": _dom("ingen", [0, 0, 0])}
    assert [f["nr"] for f in np_jamforare.npj_fynd(enheter, domar, NP, "arbetsblad")] == ["3"]
    assert np_jamforare.npj_fynd(enheter, domar, NP, "prov") == []


def test_olikheter_ar_utanfor_kurs_1a_ocksa_pa_bladet():
    from app import exam_gen
    exam = {"kurs": "Matematik, nivå 1a", "uppgifter": [
        {"text": "Undersök för vilka rörlängder $L$ Hugo har rätt.", "poang": [0, 0, 2],
         "typ": "problem", "losning": "$L > 6$"},
        {"text": "Lös ekvationen $2x + 3 = 11$.", "poang": [1, 0, 0], "typ": "rutin",
         "losning": "$x = 4$"}]}
    fynd = [f for f in exam_gen.bladets_npvakter(exam) if f["code"] == "kursvakt"]
    assert [f["path"] for f in fynd] == ["uppgift 1"]
    assert "olikheter" in fynd[0]["message"]


def test_parentes_som_gemensam_faktor_ar_utanfor_kurs_1a():
    from app import exam_gen
    exam = {"kurs": "Matematik, nivå 1a", "uppgifter": [
        {"text": "Faktorisera uttrycket $x(x - 4) - 3(4 - x)$ så långt det går.",
         "poang": [0, 0, 1], "typ": "rutin", "losning": "$(x + 3)(x - 4)$"},
        {"text": "Faktorisera $8x^2 - 12x$ genom att bryta ut största möjliga faktor.",
         "poang": [0, 1, 0], "typ": "rutin", "losning": "$4x(2x - 3)$"},
        {"text": "Skriv utan parenteser: $3(x + 2) - 2(x - 1)$", "poang": [1, 0, 0],
         "typ": "rutin", "losning": "$x + 8$"}]}
    fynd = [f for f in exam_gen.bladets_npvakter(exam) if f["code"] == "kursvakt"]
    assert [f["path"] for f in fynd] == ["uppgift 1"]
    assert "parentes som gemensam faktor" in fynd[0]["message"]


def test_generaliseringen_laser_inte_ordets_forsta_bokstav():
    from app import exam_gen
    exam = {"kurs": "Matematik, nivå 1a", "uppgifter": [
        {"text": "Elias får lika mycket för varje timme övertid. Hur stor är månadslönen?",
         "poang": [0, 1, 0], "typ": "problem", "losning": "24 600"},
        {"text": "Varje takstol kostar 900 kr. Vad kostar det för alla takstolar?",
         "poang": [0, 1, 0], "typ": "problem", "losning": "9 900"},
        {"text": "Liam påstår att ekvationen $3(x + 2) - x = 2x + c$ saknar lösning, "
                 "vilket tal $c$ än är. Avgör om Liam har rätt.",
         "poang": [0, 2, 0], "typ": "problem", "losning": "Nej"},
        {"text": "Visa att uttrycket blir 3 för alla $a$.", "poang": [0, 0, 1],
         "typ": "problem", "losning": "3"}]}
    fynd = [f for f in exam_gen.bladets_npvakter(exam) if f["code"] == "kursvakt"]
    assert [f["path"] for f in fynd] == ["uppgift 3", "uppgift 4"]


def test_omprovet_behaller_originalets_poang_och_byter_uppgift():
    """NA26F:s omprov (exam 211, 2026-10-11): poängen är låsta mot
    originalet, så «sätt poängen till …» gick inte att följa och tolv
    nivåfynd stod kvar efter alla rundor."""
    enheter = [{"nr": "1", "niva": "E", "poang": [1, 0, 0]}]
    domar = {"1": _dom("NpMa1a vt17 D18b", [1, 1, 0])}
    vanligt = np_jamforare.npj_fynd(enheter, domar, NP, "prov")
    omprov = np_jamforare.npj_fynd(enheter, domar, NP, "prov", poang_last=True)
    assert "Sätt poängen till" in vanligt[0]["message"]
    assert "Sätt poängen till" not in omprov[0]["message"]
    assert "behåll poängen och byt uppgiften" in omprov[0]["message"]


def test_bladets_fynd_star_bara_nar_samma_uppgift_falls_igen(monkeypatch):
    """Rickard 2026-10-11 (blad 220): på bladet räknas ett NP-fynd först när
    samma uppgift fälls i ett andra anrop, och det anropet ser bara de
    fällda uppgifterna."""
    import json
    monkeypatch.setattr(np_jamforare, "np_enheter", lambda _k: NP)
    enheter = [{"nr": "3", "niva": "C", "poang": [0, 1, 0]},
               {"nr": "5b", "niva": "C", "poang": [0, 1, 0]},
               {"nr": "8", "niva": "C", "poang": [0, 1, 0]}]
    svar = [{"3": "NpMa1a vt22 C18a", "5b": "NpMa1a vt22 C18a",
             "8": "NpMa1a vt17 D18b"},
            {"3": "NpMa1a vt17 D18b", "5b": "NpMa1a vt22 C18a"}]
    sedda = []

    def llm(_m, prompt, **_k):
        d = svar[len(sedda)]
        sedda.append([nr for nr in ("3", "5b", "8") if f'"{nr}"' in prompt])
        return json.dumps({"jamforelser": [
            {"nr": nr, "np": np, "poang": [1, 0, 0] if "C18a" in np
             else [0, 1, 0], "motivering": ""} for nr, np in d.items()]})

    ex = {"kurs": "Matematik, nivå 1a"}
    fynd = np_jamforare.doma_np(ex, enheter, model="m", llm=llm,
                                profil="arbetsblad", upprepa=True)
    assert [f["nr"] for f in fynd] == ["5b"]
    assert len(sedda) == 2 and "8" not in sedda[1]
    sedda.clear()
    utan = np_jamforare.doma_np(ex, enheter, model="m", llm=llm,
                                profil="arbetsblad")
    assert [f["nr"] for f in utan] == ["3", "5b"] and len(sedda) == 1
