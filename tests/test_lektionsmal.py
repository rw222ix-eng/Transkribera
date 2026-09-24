"""Lektionsmålen: det tavlan lovade klassen ska provet pröva.

Lärarens dom 2026-09-24 kväll över exam 126 (NA26F): provet bar en uppgift
per delmoment, men ingen E-poäng för att lösa en linjär ekvation, ingen
olikhet där tecknet vänds, ingen kvadratrot, och mönstret bara på A-nivå.
«Vi behöver lösa det så att vi slipper hålla på såhär fram och tillbaka.»
Se exam_gen, avsnittet LEKTIONSMÅLEN.
"""
from __future__ import annotations

import json

from app import exam_gen


def _tavla(datum, titel, punkter, id_=1):
    return {"datum": datum, "titel": titel, "board": {"boards": [
        {"name": "vanster", "sections": [
            {"kind": "heading", "text": titel},
            {"kind": "list", "items": punkter},
            {"kind": "list", "items": ["Väg 1", "Väg 2"]}]}]}}


def test_malen_ar_forsta_punktlistan_utan_bokens_rader():
    mal = exam_gen.lektionsmal_ur_tavlor([_tavla(
        "2026-09-11", "Olikheter",
        ["Läsa olikheter på tallinjen", "Lösa och vända tecknet",
         "Boken s. 58–63, uppg. 2401–2403"])])
    assert mal == [{"datum": "2026-09-11", "lektion": "Olikheter",
                    "mal": ["Läsa olikheter på tallinjen",
                            "Lösa och vända tecknet"]}]


def test_senaste_tavlan_samma_dag_galler_och_exempel_ar_inga_mal():
    mal = exam_gen.lektionsmal_ur_tavlor([
        _tavla("2026-08-24", "Kvadratrötter", ["Gammalt mål"]),
        _tavla("2026-08-24", "Kvadratrötter och kubikrötter",
               ["Vad en rot betyder", "Två exempel tillsammans",
                "Mest utan miniräknare", "Arbetar i boken s. 2–6"])])
    assert mal == [{"datum": "2026-08-24",
                    "lektion": "Kvadratrötter och kubikrötter",
                    "mal": ["Vad en rot betyder"]}]


def test_digitala_mal_faller_bort_utan_digital_del():
    """Tavlan 10/9 hade «Digitalt när talet blir fult», och klassen gick
    aldrig igenom GeoGebra (läraren 24/9). Provet har ingen datordel."""
    tavla = _tavla("2026-09-10", "Potensekvationer",
                   ["Hur många rötter finns?", "Digitalt när talet blir fult"])
    utan = exam_gen.lektionsmal_ur_tavlor([tavla], digital=False)
    med = exam_gen.lektionsmal_ur_tavlor([tavla], digital=True)
    assert utan[0]["mal"] == ["Hur många rötter finns?"]
    assert "Digitalt när talet blir fult" in med[0]["mal"]


def test_repetition_ger_inga_mal():
    assert exam_gen.lektionsmal_ur_tavlor([_tavla(
        "2026-09-22", "Potenslagarna",
        ["Blandade uppgifter, sedan kapiteltest"])]) == []


def test_har_digital_del():
    assert not exam_gen.har_digital_del(
        {"hjalpmedel": "Formelblad på hela provet, räknare bara på del C."})
    assert not exam_gen.har_digital_del(
        {"hjalpmedel": "Del B utan hjälpmedel. Ingen datordel."})
    assert exam_gen.har_digital_del(
        {"hjalpmedel": "Digitala verktyg och formelblad."})


def test_blocket_ar_tomt_utan_mal_och_bar_malen_annars():
    assert exam_gen.build_lektionsmal([]) == ""
    block = exam_gen.build_lektionsmal(
        [{"datum": "2026-09-11", "lektion": "Olikheter",
          "mal": ["Lösa och vända tecknet"]}], digital=False)
    assert "2026-09-11 Olikheter: Lösa och vända tecknet" in block
    assert "E-poäng" in block and "ingen digital del" in block


def _prov(*uppgifter):
    return {"uppgifter": list(uppgifter)}


def _u(delmoment, poang, **extra):
    return {"del": "B", "formaga": "P", "typ": "rutin", "poang": poang,
            "text": "x", "losning": "1", "bedomning": "+1",
            "delmoment": delmoment, **extra}


DELMOMENT = [{"delmoment": "Mönster och generella samband", "sidor": "85–88"},
             {"delmoment": "Olikheter", "sidor": "58–63"}]


def test_delmoment_bara_pa_a_niva_ar_ett_fynd():
    """Exam 126 uppgift 7: mönstret 0/0/2, så den som läser för E eller C
    prövades aldrig i det."""
    prov = _prov(_u("Mönster och generella samband", [0, 0, 2]),
                 _u("Olikheter", [1, 0, 0]))
    fel = exam_gen.delmomentniva(prov, DELMOMENT)
    assert len(fel) == 1 and fel[0]["code"] == "delmomentniva"
    assert "Mönster och generella samband" in fel[0]["message"]
    assert fel[0]["path"] == "uppgift 1"


def test_en_e_poang_i_en_deluppgift_racker():
    prov = _prov(_u("Mönster och generella samband", [0, 0, 0],
                    deluppgifter=[{"poang": [1, 0, 0]}, {"poang": [0, 0, 2]}]),
                 _u("Olikheter", [1, 0, 0]))
    assert exam_gen.delmomentniva(prov, DELMOMENT) == []


def test_niva_3_och_papper_utan_falt_tiger():
    nivatre = [{"delmoment": "Problemlösning nivå 3", "sidor": "56"}]
    assert exam_gen.delmomentniva(
        _prov(_u("Problemlösning nivå 3", [0, 0, 2])), nivatre) == []
    utan = {"uppgifter": [{"poang": [0, 0, 2], "text": "x"}]}
    assert exam_gen.delmomentniva(utan, DELMOMENT) == []


def test_ci_tackningen_kraver_inte_dig_utan_digital_del():
    prov = {"hjalpmedel": "Formelblad, räknare bara på del C.",
            "uppgifter": [{"innehall": ["G25-M1C-ALG-5"]}]}
    koder = ["G25-M1C-ALG-5", "G25-M1C-DIG-2"]
    assert exam_gen.ci_tackning(prov, koder) == []
    prov["hjalpmedel"] = "Digitala verktyg och formelblad."
    fel = exam_gen.ci_tackning(prov, koder)
    assert fel and "DIG-2" in fel[0]["message"]


MAL = [{"datum": "2026-09-11", "lektion": "Olikheter",
        "mal": ["Lösa och vända tecknet"]}]


def test_domaren_ser_poangen_och_malen():
    sett = {}

    def llm(model, prompt, **kw):
        sett["prompt"], sett["kw"] = prompt, kw
        return json.dumps({"saknas": [{
            "datum": "2026-09-11", "mal": "Lösa och vända tecknet",
            "niva": "E", "varfor": "Ingen olikhet delas med ett negativt tal."}]})

    prov = {"hjalpmedel": "Formelblad.", "kurs": "Matematik 1c",
            "uppgifter": [_u("Olikheter", [1, 0, 0], text="Lös $2x < 6$.")]}
    fel = exam_gen.doma_lektionsmal(prov, MAL, model="", llm=llm)
    assert "lektionsmålsdomare" in sett["prompt"]
    # Kursens strykningar följer med: pilarna är inte 1c (Rickard 25/9).
    assert "UTANFÖR KURSEN" in sett["prompt"]
    assert "implikation och ekvivalens" in sett["prompt"]
    assert '"poang_ECA": [1, 0, 0]' in sett["prompt"]
    assert "ingen digital del" in sett["prompt"]
    assert sett["kw"]["response_format"]["json_schema"]["name"] == "lektionsmaldom"
    assert len(fel) == 1 and fel[0]["code"] == "lektionsmal"
    assert "«Lösa och vända tecknet»" in fel[0]["message"]
    assert "E-nivå" in fel[0]["message"]


def test_domaren_kors_inte_utan_mal_och_ar_fail_open():
    def llm(*a, **kw):
        raise AssertionError("ingen tavla, inget anrop")

    prov = {"uppgifter": [_u("Olikheter", [1, 0, 0])]}
    assert exam_gen.doma_lektionsmal(prov, [], model="", llm=llm) == []

    def trasig(*a, **kw):
        raise RuntimeError("nätet borta")

    assert exam_gen.doma_lektionsmal(prov, MAL, model="", llm=trasig) == []
    assert exam_gen.lektionsmalfynd("inte json") == []


def test_rutten_laser_tavlorna_for_provets_lektioner(tmp_path):
    """Samma lektioner som delmomenten: före provdagen, sidor inom spannet,
    den egna klassen."""
    from app import db
    from app.web import routes_planning
    db_file = tmp_path / "t.db"
    conn = db.connect(db_file)
    try:
        bid = db.create_bok(conn, namn="Liber Ma 1c", kurs="Matematik 1c")["id"]
        db.replace_lektionsinnehall(conn, [
            {"datum": "2026-09-11", "fran": 58, "till": 63, "klass": "NA26F",
             "kurs": "Matematik 1c", "rubrik": "Olikheter"},
            {"datum": "2026-10-02", "fran": 272, "till": 275, "klass": "NA26F",
             "kurs": "Matematik 1c", "rubrik": "Trigonometri"}])
        gid = db.get_or_create_group(conn, "NA26F")
        cid = db.get_or_create_course(conn, "Matematik 1c")
        for d, t, p in (("2026-09-11", "Olikheter", ["Lösa och vända tecknet"]),
                        ("2026-10-02", "Trigonometri", ["Sinus"])):
            db.create_planned_lesson(
                conn, titel=t, datum=d, group_id=gid, course_id=cid,
                board_json=json.dumps(_tavla(d, t, p)["board"]))
    finally:
        conn.close()
    ut = routes_planning.undervisade_lektionsmal(
        db_file, {"bok": {"id": bid, "fran": 42, "till": 99},
                  "datum": "2026-10-01"}, group_id=gid, course_id=cid)
    assert ut == [{"datum": "2026-09-11", "lektion": "Olikheter",
                   "mal": ["Lösa och vända tecknet"]}]


def test_generate_utan_mal_ger_samma_prompt_som_forut():
    """Kassetteregeln: utan tavlor är prompten byte för byte densamma."""
    assert exam_gen.build_lektionsmal([], digital=False) == ""
