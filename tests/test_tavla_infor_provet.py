"""«Inför provet» för tavlan (2026-09-27).

Lärarens princip: tavlan förklarar och visar exempel så att klassen klarar
PROVET i första hand, bokens uppgifter i andra. Arbetsbladet har haft läget
sedan 2026-09-19 (tests/test_infor_provet.py).

Allt utan skarpa modellanrop: blocken (och att prompterna är byte-identiska
utan dem), urvalet ur provet, provkopievakten, randfallsgrinden och rutten.
"""
import copy
import json

import pytest

from app import db as appdb
from app import lesson_board

from tests.test_exam import _exam
from tests.test_routes_exam import _done


RADER = [
    {"nr": 1, "niva": "E", "del": "B", "sort": "förenklar uttryck",
     "delmoment": "Algebraiska uttryck (s. 8–11)"},
    {"nr": 3, "niva": "A", "del": "B",
     "sort": "bestämmer en konstant så att en andragradsekvation får exakt "
             "en lösning", "delmoment": "pq-formeln (s. 45–48)"},
    {"nr": 6, "niva": "C", "del": "B",
     "sort": "utvecklar en produkt av binom och löser ekvationen",
     "delmoment": "pq-formeln (s. 45–48); Uttryck av andra graden (s. 27–30)"},
    {"nr": 7, "niva": "A", "del": "B", "sort": "ställer upp en ekvation",
     "delmoment": "Problemlösning med andragradsekvationer (s. 49–52)"},
    {"nr": 12, "niva": "A", "del": "C", "sort": "problemlösning",
     "delmoment": "Problemlösning med andragradsekvationer"},
]


# ─────────────────────────────── urvalet ────────────────────────────────


def test_lektionens_sidor_valjer_provets_uppgifter():
    valda = lesson_board.valj_provrader(RADER, [], sidor=[(45, 48)],
                                        rubriker=["pq-formeln"])
    assert [r["nr"] for r in valda] == [3, 6]


def test_uppgift_utan_sidor_valjs_pa_momentets_ord():
    valda = lesson_board.valj_provrader(
        RADER, [], sidor=[], rubriker=["Problemlösning med andragradsekvationer"])
    assert [r["nr"] for r in valda] == [7, 12]


def test_lararens_nummer_gar_fore():
    valda = lesson_board.valj_provrader(RADER, [12, 1], sidor=[(45, 48)])
    assert [r["nr"] for r in valda] == [1, 12]


def test_inget_i_provet_ger_tom_lista():
    assert lesson_board.valj_provrader(RADER, [], sidor=[(90, 97)],
                                       rubriker=["Statistik"]) == []


def test_sorten_ur_forebilden_utan_np_prefixet():
    u = {"forebild": {"nr": 1, "sort": "ingen NP-typ för intervall på "
                      "E-nivå: eleven skriver en dubbelolikhet som ett "
                      "intervall"}, "delmoment": "Intervall"}
    assert lesson_board.provsort(u) == ("eleven skriver en dubbelolikhet som "
                                        "ett intervall")
    assert lesson_board.provsort({"delmoment": "Olikheter"}) == "Olikheter"


# ─────────────────────────────── blocken ────────────────────────────────


def test_blocket_bar_sorterna_och_ordern():
    block = lesson_board.build_infor_prov(RADER[1:3], "Andragrad", "2026-10-20")
    assert block.startswith(lesson_board.PROVMARKOR)
    assert "provets uppgift 3 (A-nivå, utan räknare)" in block
    assert "PROVET FÖRST, BOKEN I ANDRA HAND" in block
    assert "ALDRIG SAMMA UPPGIFT" in block
    assert "2026-10-20" in block


def test_utan_prov_ar_prompterna_byte_identiska():
    """Kassetteregeln: utan valt prov ska skrivningens och domarens prompter
    vara de som gick i väg innan läget fanns."""
    assert lesson_board.build_infor_prov([]) == ""
    assert lesson_board.build_infor_prov_dom([]) == ""
    args = ("Matematik 2a", "IndA", "pq-formeln", "minne", "", "", "BOK")
    assert (lesson_board.build_prompt(*args)
            == lesson_board.build_prompt(*args, prov=""))
    tavla = {"schema": "wb-json-v1", "boards": []}
    assert (lesson_board.build_tackning_prompt(tavla, "BOK", "DELAR")
            == lesson_board.build_tackning_prompt(tavla, "BOK", "DELAR",
                                                  prov=""))


def test_provet_star_efter_boken_i_bada_prompterna():
    block = lesson_board.build_infor_prov(RADER[1:2])
    p = lesson_board.build_prompt("Matematik 2a", "IndA", "pq", bok="BOKBLOCK",
                                  forlaga="", prov=block)
    assert p.index("BOKBLOCK") < p.index(lesson_board.PROVMARKOR)
    dom = lesson_board.build_infor_prov_dom(RADER[1:2])
    d = lesson_board.build_tackning_prompt({"boards": []}, "BOKBLOCK", "",
                                           prov=dom)
    assert d.index("BOKBLOCK") < d.index("Pröva PROVET FÖRST")


# ───────────────────────────── vakterna ────────────────────────────────


def _tavla(latex):
    return {"schema": "wb-json-v1", "boards": [
        {"columns": [{"sections": []}]},
        {"columns": [{"sections": [
            {"kind": "heading", "text": "Exempel 1"},
            {"kind": "math", "latex": latex}]}]}]}


def test_provkopievakten_faller_provets_uttryck():
    prov = "Bestäm talet $k$ så att ekvationen $x^2 + 6x + k = 0$ har exakt en lösning."
    fynd = lesson_board.provkopior(_tavla("x^2 + 6x + k = 0"), prov)
    assert [f["code"] for f in fynd] == ["provkopia"]
    assert lesson_board.provkopior(_tavla("x^2 - 8x + k = 0"), prov) == []
    assert lesson_board.provkopior(_tavla("x^2 + 6x + k = 0"), "") == []


def test_randfallsgrinden_slapper_provets_fynd():
    bok = "LÄRARENS URVAL: klassen ska räkna uppg. 1330–1346 på lektionen."
    fynd = [{"message": "Att tänka på saknar negativt under roten "
                        "(provets uppgift 11)", "uppgifter": []},
            {"message": "Randfallet parentes i kvadrat saknas", "uppgifter": []}]
    kvar = lesson_board._hittat_randfall(fynd, bok)
    assert [f["message"][:12] for f in kvar] == ["Att tänka på"]


def test_domaren_far_provblocket_och_vakten_texterna():
    fangat = {}

    def llm(model, prompt, **kw):
        fangat.setdefault("prompter", []).append(prompt)
        return '{"saknas": []}'

    tavla = _tavla("x^2 + 2x - 8 = 0")
    lesson_board._tackning_pass(tavla, [], model="m", llm=llm, bok="BOK",
                                prov=lesson_board.build_infor_prov_dom(RADER[1:2]))
    assert "Pröva PROVET FÖRST" in fangat["prompter"][0]


# ─────────────────────────────── rutten ─────────────────────────────────


@pytest.fixture
def client(llm_ready):
    return llm_ready


def _prov_i_basen(client):
    exam = copy.deepcopy(_exam())
    for i, u in enumerate(exam["uppgifter"]):
        u["delmoment"] = "pq-formeln" if i in (1, 2) else "Statistik"
        u["forebild"] = {"nr": 90000 + i, "sort": f"sort nummer {i + 1}"}
    exam["uppgifter"][1]["text"] = "Lös ekvationen $x^2 + 6x + 5 = 0$."
    conn = appdb.connect(client.base_dir / "transkribera.db")
    try:
        gid = appdb.get_or_create_group(conn, "IndA")
        cid = appdb.get_or_create_course(conn, "Matematik, nivå 2a")
        vy = appdb.create_exam(conn, exam=exam, group_id=gid, course_id=cid,
                               datum="2026-10-20", typ="prov")
        appdb.set_exam_status(conn, vy["id"], "godkänt")
    finally:
        conn.close()
    return vy["id"], exam


def _fanga(monkeypatch):
    fangat = {}

    def fake(course, group, moment, *, model, log_cb=None, **kw):
        fangat.update(kw)
        return {"board": {"schema": "wb-json-v1", "title": moment,
                          "boards": []}, "errors": [], "rounds": 1}

    monkeypatch.setattr(lesson_board, "generate_board", fake)
    return fangat


def test_rutten_bygger_blocket_ur_provet(client, monkeypatch):
    eid, exam = _prov_i_basen(client)
    fangat = _fanga(monkeypatch)
    r = client.post("/api/planning/generate", json={
        "moment": "pq-formeln", "infor_prov_id": eid, "infor_nummer": []})
    svar = _done(r)
    assert "provets uppgift 2" in fangat["prov"]
    assert "provets uppgift 3" in fangat["prov"]
    assert "provets uppgift 1 " not in fangat["prov"]
    # Texterna går till vakten, aldrig till prompten.
    assert "x^2 + 6x + 5" in fangat["provtext"]
    assert "x^2 + 6x + 5" not in fangat["prov"]
    assert "Pröva PROVET FÖRST" in fangat["prov_dom"]
    # Numren sparas med planeringen, så att omskrivningen läser samma.
    conn = appdb.connect(client.base_dir / "transkribera.db")
    try:
        rad = conn.execute("SELECT data FROM planeringar WHERE pid = ?",
                           (svar["id"],)).fetchone()
    finally:
        conn.close()
    assert json.loads(rad[0])["infor_prov"]["nummer"] == [2, 3]


def test_utan_prov_far_generatorn_tomma_block(client, monkeypatch):
    fangat = _fanga(monkeypatch)
    _done(client.post("/api/planning/generate", json={"moment": "pq-formeln"}))
    assert fangat["prov"] == fangat["prov_dom"] == fangat["provtext"] == ""


def test_prov_utan_uppgift_pa_lektionen_ger_tomt_block(client, monkeypatch):
    eid, _ = _prov_i_basen(client)
    fangat = _fanga(monkeypatch)
    r = client.post("/api/planning/generate", json={
        "moment": "Geometri", "infor_prov_id": eid})
    _done(r)
    assert fangat["prov"] == ""
