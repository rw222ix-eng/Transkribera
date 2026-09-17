"""Symbolvakten (lesson_board.symbolvakt): exemplen mot sidorna åt båda håll.

Fallet är ekvationstavlan 2026-09-17 (Liber Ma1c 2.1, s. 42–45, uppg.
2101–2111): exempel 2 vände till en olikhet som inte finns på sidorna, och
bråkekvationerna (2109, 2111) fick inget exempel alls. Domaren hade reglerna
och släppte igenom båda; läraren skrev om tavlan i två varv för hand."""
import json

from app import lesson_board as lb

from tests.test_lesson_board import _stub_llm, _valid_doc

# Bokblockets form är bok.build_bok_block: sidtexten med sin MATEMATIK-lista
# («N. $…$ — i uppgift …»), sedan uppgiftsnumren och lärarens urvalsrad.
BOK = """UR LÄROBOKEN — Liber Ma 1c, s. 42–45. Lektionen SKA bygga på de här sidorna.

## MATEMATIK

1. $=$ — i första brödtextstycket
2. $6x = 2x - 3(2 - x)$ — uppgiftsraden i Exempel 8
3. $\\dfrac{2x + 6}{2} = 4x - 3$ — i uppgift 2104
4. $x - 17 = 3$ — 2106 a
5. $x + \\dfrac{2}{3} = \\dfrac{5}{3}$ — 2106 b
6. $3(2x + 1) = x$ — 2108 b
7. $\\dfrac{y}{5} = -4$ — 2109 a
8. $\\dfrac{2x}{5} = 4$ — 2109 c
9. $2x - 4 = x + 5$ — 2110 c
10. $-15 = \\dfrac{2y}{-3}$ — 2111 d
11. $x^2 = 9$ — 2299 a, en sida läraren INTE valde

Uppgiftsnummer på sidorna: 2104, 2106, 2108, 2109, 2110, 2111, 2299.

LÄRARENS URVAL: klassen ska räkna uppg. 2104–2111 på de här sidorna. Skriv de numren precis så.
"""


def _tavla(*latex: str) -> dict:
    sek = [{"kind": "heading", "text": "Exempel 1"}]
    sek += [{"kind": "math", "latex": x} for x in latex]
    return {"boards": [{"sections": [{"kind": "math", "latex": "ax + b = c"}]},
                       {"columns": [{"sections": sek}]}]}


def test_klasserna_pekar_ut_ett_moment():
    k = lb._klasser
    assert k("5x - 4 < 3x + 6") == {"olikhet"}
    assert k("x \\le 7{,}5") == {"olikhet"}
    assert k("\\frac{x}{4} + 3 = 8") == {"bråk"}
    assert k("x/4 + 3 = 8") == {"bråk"}
    assert k("T = 21 - 21 \\cdot 2^{-t}") == {"variabel i exponenten"}
    assert k("\\sqrt{x + 1} = 3") == {"rot"}
    assert k("\\sin v = 0{,}5") == {"trigonometri"}
    assert k("|x - 2| = 3") == {"absolutbelopp"}
    # Upphöjt till två, parenteser och decimaltal pekar inte ut något.
    assert k("12 - 3(x - 2) = 6") == set()
    assert k("h = 45 - 4{,}9t^2") == set()
    assert k("x^{2} + 5x - 7") == set()


def test_olikheten_pa_ekvationssidorna_falls():
    fynd = lb.symbolvakt(_tavla("3x + 8 = x + 20", "\\frac{x}{4} + 3 = 8",
                                "5x - 4 < 3x + 6"), BOK)
    assert [f["code"] for f in fynd] == ["utanfor_sidorna"], fynd
    assert "olikhet" in fynd[0]["message"]
    assert fynd[0]["path"] == "boards[1].columns[0].sections[3]"


def test_braken_i_urvalet_utan_exempel_falls():
    fynd = lb.symbolvakt(_tavla("3x + 8 = x + 20", "12 - 3(x - 2) = 6"), BOK)
    assert [f["code"] for f in fynd] == ["typ_utan_exempel"], fynd
    assert "bråk" in fynd[0]["message"] and "2109" in fynd[0]["message"]
    # Fem bråkrader i urvalet räknas; raden ur 2299 hör inte till urvalet.
    assert "5 uppgiftsrader" in fynd[0]["message"]


def test_en_tavla_som_speglar_urvalet_gar_fri():
    assert lb.symbolvakt(_tavla("3x + 8 = x + 20", "\\frac{x}{4} + 3 = 8",
                                "12 - 3(x - 2) = 6"), BOK) == []


def test_typ_utanfor_urvalet_kravs_inte():
    """x^2 = 9 står på sidorna men i en uppgift läraren valde bort: ingen
    typ_utan_exempel för den. Och en enstaka rad räcker inte (_TYP_MINSTA)."""
    bok = BOK.replace("2299 a, en sida läraren INTE valde", "2108 c")
    fynd = lb.symbolvakt(_tavla("\\frac{x}{4} + 3 = 8"), bok)
    assert fynd == [], fynd


def test_vakten_tiger_utan_bok_utan_matte_och_utan_urval():
    tavla = _tavla("5x - 4 < 3x + 6")
    assert lb.symbolvakt(tavla, "") == []
    assert lb.symbolvakt(tavla, "UR LÄROBOKEN — bara prosa, inga formler.") == []
    assert lb.symbolvakt(None, BOK) == []
    # Utan urvalsrad döms bara riktningen utåt (olikheten), aldrig luckan.
    utan_urval = BOK.split("LÄRARENS URVAL")[0]
    assert [f["code"] for f in lb.symbolvakt(tavla, utan_urval)] == ["utanfor_sidorna"]
    assert lb.symbolvakt(_tavla("3x + 8 = x + 20"), utan_urval) == []


def test_generate_board_far_symbolvaktens_fynd_att_ratta():
    doc = _valid_doc()
    kol = doc["boards"][1]["columns"][0]["sections"]
    kol.append({"kind": "heading", "text": "Exempel 2"})
    kol.append({"kind": "math", "latex": "5x - 4 < 3x + 6"})
    llm, calls = _stub_llm([json.dumps(doc)])
    res = lb.generate_board("Ma1c", "TE26A", "ekvationer", model="",
                            doma=False, llm=llm, bok=BOK)
    koder = {f.get("code") for f in res["errors"]}
    assert {"utanfor_sidorna", "typ_utan_exempel"} <= koder, res["errors"]
    assert "som inte finns på bokens sidor" in calls[1]["prompt"]
    assert "men inget exempel av den typen" in calls[1]["prompt"]


def test_domarens_fynd_loggas():
    """Ekvationstavlan gick ut med «5 luckor» i loggen och ingenting om vilka.
    Nu står varje fynd som en loggrad."""
    dom = json.dumps({"saknas": [{"uppgifter": [2109], "vad": "bråkekvationer",
                                  "forslag": "ett exempel med x/5"}]})
    llm, _calls = _stub_llm([dom])
    rader: list[str] = []
    fynd = lb.doma_tackning(_valid_doc(), model="", llm=llm, bok=BOK,
                            log_cb=rader.append)
    assert len(fynd) == 1
    assert any(r.startswith("Domaren: bråkekvationer") for r in rader), rader
