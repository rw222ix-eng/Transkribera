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
