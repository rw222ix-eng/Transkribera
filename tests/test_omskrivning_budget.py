"""Lärarens önskemål vinner över textbudgeten i en OMSKRIVNING.

Ekvationstavlan 2026-09-17 (TE26A, Liber s. 42–45): två varv i rad bad hon
om ett bråkexempel och ett kontrollsteg, och båda varven kom tillbaka utan
dem. Ett svar som gjorde det hon bad om bar 345 tecken mot högerns tak 340;
reparationsrundan fick «textbudget» som enda problem och lappen strök det
nyaste på tavlan, alltså beställningen. Loggen sa «1 problem».

Nu hålls budgetfyndet tillbaka i refine_board (REFINE_BEHALL) och redovisas
som varning; generate_board reparerar budgeten som förut."""
import copy
import json

from app import lesson_board as lb
from app import whiteboard_spec as ws

from tests.test_lesson_board import _stub_llm, _valid_doc


def _pratig() -> dict:
    """En giltig tavla vars högertavla spränger budgeten, inget annat."""
    doc = _valid_doc()
    kol = doc["boards"][1]["columns"][0]["sections"]
    for i in range(6):
        kol.append({"kind": "heading", "text": f"Exempel {i + 4}"})
        kol.append({"kind": "list", "bullet": "–",
                    "items": ["Samla: dra bort tre i båda led",
                              "Multiplicera: båda led med fyra"]})
    _p, fel = ws.validate_board_json(doc)
    assert [f["code"] for f in fel] == ["textbudget"], fel
    return doc


def test_omskrivningen_reparerar_inte_bort_budgeten():
    fore = _valid_doc()
    svar = _pratig()
    llm, calls = _stub_llm([json.dumps(svar)])
    res = lb.refine_board(fore, "lägg till ett bråkexempel", model="", llm=llm)
    # Ett anrop: omskrivningen. Ingen reparationsrunda för budgeten.
    assert len(calls) == 1
    assert res["board"] == svar
    assert [f["code"] for f in res["errors"]] == ["textbudget"]
    assert res["rounds"] == 1


def test_andra_fel_repareras_fortfarande_och_budgeten_foljer_med_ut():
    fore = _valid_doc()
    trasig = copy.deepcopy(_pratig())
    trasig["boards"][1]["columns"][0]["sections"].append(
        {"kind": "callout", "children": [{"kind": "text", "text": "ruta"}]})
    lagad = _pratig()
    llm, calls = _stub_llm([json.dumps(trasig), json.dumps(lagad)])
    rader: list[str] = []
    res = lb.refine_board(fore, "lägg till ett bråkexempel", model="",
                          llm=llm, log_cb=rader.append)
    assert len(calls) == 2
    assert [f["code"] for f in res["errors"]] == ["textbudget"]
    # Loggen säger vilket problem rundan rättar, inte bara hur många.
    assert any("1 problem: ruta" in r for r in rader), rader


def test_genereringen_reparerar_budgeten_som_forut():
    svar = _pratig()
    llm, calls = _stub_llm([json.dumps(svar), json.dumps(_valid_doc())])
    res = lb.generate_board("Ma1c", "TE26A", "ekvationer", model="",
                            doma=False, llm=llm)
    assert len(calls) == 2
    assert res["errors"] == []


def test_omskrivningen_behaller_lararens_losningar():
    """«Lösningarna behöver skrivas under varje exempel» (2026-09-17 kväll).
    Facitvakten fäller uträkningar i genereringen; i en omskrivning där hon
    bett om dem redovisas de som varning i stället för att strykas."""
    fore = _valid_doc()
    svar = _valid_doc()
    svar["boards"][1]["columns"][0]["sections"].append(
        {"kind": "math", "latex": "3 \\cdot 3^2 = 3 \\cdot 9 = 27"})
    _p, fel = ws.validate_board_json(svar)
    assert [f["code"] for f in fel] == ["facit"], fel
    llm, calls = _stub_llm([json.dumps(svar)])
    res = lb.refine_board(fore, "skriv lösningen under varje exempel",
                          model="", llm=llm)
    assert len(calls) == 1 and res["board"] == svar
    assert [f["code"] for f in res["errors"]] == ["facit"]
    assert lb.REFINE_BEHALL == ("textbudget", "facit", "siffror_vanster")


def test_omskrivningen_behaller_en_sifferrad_lararen_bett_om():
    """Samma regel, samma skäl (2026-09-20). Vakten undantar ankaret när
    bokstavsformeln står direkt under det, och det löser det vanliga fallet.
    Men ber hon om en sifferrad som INTE har någon formel efter sig fälls den
    fortfarande — och då ska fyndet redovisas i en omskrivning, inte strykas.
    Det var så ankaret hon bad om försvann (jobb 480, event 3)."""
    fore = _valid_doc()
    svar = _valid_doc()
    spalt = svar["boards"][0]["sections"][-1]["children"][1]["children"]
    spalt.append({"kind": "math",
                  "latex": "x^2 = 64 \\Rightarrow x = \\pm 8"})
    _p, fel = ws.validate_board_json(svar)
    assert [f["code"] for f in fel] == ["siffror_vanster"], fel
    llm, calls = _stub_llm([json.dumps(svar)])
    res = lb.refine_board(fore, "lägg till raden med 64 sist i spalten",
                          model="", llm=llm)
    assert len(calls) == 1 and res["board"] == svar
    assert [f["code"] for f in res["errors"]] == ["siffror_vanster"]
