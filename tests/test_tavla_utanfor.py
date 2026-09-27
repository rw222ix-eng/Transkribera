"""Tavlan känner kursens gränser, som proven (förslag 5, veckoanalysen 27/9).

TE26A:s tavla om tecken och intervall (Ma 1c, 2026-09-27) fick rader om
implikation ⇒ och ekvivalens ⇔, och läraren strök dem för hand. Proven har
haft listan ur app/ci_utanfor.py i prompten, hos domarna och i en vakt sedan
17/9. Nu har tavlan samma tre: blocket i skrivningen och omskrivningen,
blocket hos täckningsdomaren och utanforvakten före reparationsrundan. Och
⇔ blir «betyder», inte «ger»: «m ∈ ]0, 800] ger 0 < m ≤ 800» stod på samma
tavla, och där ges ingenting.
"""
import copy
import json

import pytest

from app import ci_utanfor, lesson_board as lb, whiteboard_spec as ws

KURS1C = "Matematik, nivå 1c"
UTAN_LISTA = ("Matematik 3c", "Matematik, nivå 2c", "Ma3c")


def _doc() -> dict:
    return copy.deepcopy(lb.FEW_SHOTS[0][1])


def _med_rad(doc: dict, sektion: dict) -> dict:
    doc["boards"][0]["sections"].append(sektion)
    return doc


def _stub(svar: list[str]):
    anrop: list[dict] = []

    def llm(model, prompt, system=None, options=None, response_format=None,
            max_tokens=None, token_cb=None):
        anrop.append({"prompt": prompt, "system": system})
        return svar[min(len(anrop) - 1, len(svar) - 1)]
    return llm, anrop


# ── Kassettregeln: kurs utan lista ger prompten byte för byte ───────────────

@pytest.mark.parametrize("kurs", UTAN_LISTA)
def test_kurs_utan_lista_ger_den_gamla_skrivprompten(kurs):
    assert lb.build_utanfor_tavla(kurs) == ""
    assert lb.build_utanfor_dom(kurs) == ""
    p = lb.build_prompt(kurs, "NA25", "Derivatans definition")
    assert p == (f"{lb.INSTRUCTION}\n{lb._few_shot_block()}\n\n"
                 f"Uppdrag: skriv lektionstavlan för {kurs}, klass NA25 — "
                 "Derivatans definition.\nSvara med enbart JSON.")


def test_kassettbandets_prompt_ar_orord():
    """tests/kassetter/tavla.json är inspelad mot Matematik 3c."""
    assert "UTANFÖR KURSEN" not in lb.build_prompt(
        "Matematik 3c", "NA25", "Derivatans definition")


@pytest.mark.parametrize("kurs", UTAN_LISTA)
def test_kurs_utan_lista_ger_samma_domar_och_omskrivningsprompt(kurs):
    doc = _doc()
    assert lb.build_tackning_prompt(doc, "BOK", utanfor=lb.build_utanfor_dom(
        kurs)) == lb.build_tackning_prompt(doc, "BOK")
    assert lb.build_refine_prompt(doc, "kortare", bok="BOK", utanfor=
                                  lb.build_utanfor_tavla(kurs)) \
        == lb.build_refine_prompt(doc, "kortare", bok="BOK")


# ── Blocket i 1c ─────────────────────────────────────────────────────────────

def test_1c_far_blocket_i_skrivningen_fore_kallorna():
    p = lb.build_prompt(KURS1C, "TE26A", "Tecken och intervall",
                        bok="UR LÄROBOKEN, s. 55")
    assert "UTANFÖR KURSEN" in p and "implikation och ekvivalens" in p
    assert "på tavlan" in p and "pappret" not in p.split("UTANFÖR KURSEN")[1][:300]
    assert "«betyder»" in p
    assert p.index("UTANFÖR KURSEN") < p.index("UR LÄROBOKEN")


def test_domaren_far_blocket_och_fyndordet():
    dom = lb.build_utanfor_dom(KURS1C)
    p = lb.build_tackning_prompt(_doc(), "KALLAN_X", utanfor=dom)
    assert "UTANFÖR KURSEN" in p and lb.UTANFOR_FYND in p
    assert p.index("UTANFÖR KURSEN") < p.index("KALLAN_X") < p.index("Tavlan:")


def test_omskrivningen_far_blocket():
    blk = lb.build_utanfor_tavla(KURS1C)
    p = lb.build_refine_prompt(_doc(), "kortare", bok="KALLAN_X", utanfor=blk)
    assert blk in p and p.index(blk) < p.index("KALLAN_X")
    m = lb.build_mallapp_prompt(_doc(), "kortare", [("Rubrik", "title")],
                                bok="KALLAN_X", utanfor=blk)
    assert blk in m


def test_provets_rad_ar_orord():
    """Tavelflaggan får inte ändra provets rad."""
    assert "pappret" in ci_utanfor.build_utanfor(KURS1C)
    assert "betyder" not in ci_utanfor.build_utanfor(KURS1C)


# ── Vakten ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("sektion", [
    {"kind": "text", "text": "Ekvivalens: båda leden säger samma sak"},
    {"kind": "text", "text": "Implikation: om p så q"},
    {"kind": "math", "latex": "x > 2 \\Leftarrow x > 3"},
    {"kind": "list", "items": ["x = 2 ⇐ 2x = 4"]},
    {"kind": "text", "text": "Median: mittersta värdet"},
])
def test_vakten_faller_1c_raden(sektion):
    fel = lb.utanforvakt(_med_rad(_doc(), sektion), KURS1C)
    assert len(fel) == 1 and fel[0]["code"] == ci_utanfor.KOD
    assert fel[0]["path"].startswith("boards[0].sections[")


def test_vakten_tiger_i_2c_och_2b_och_utan_kurs():
    doc = _med_rad(_doc(), {"kind": "text", "text": "Ekvivalens: p ⇔ q"})
    for kurs in ("Matematik, nivå 2c", "Matematik 2b", "Matematik 3c", ""):
        assert lb.utanforvakt(doc, kurs) == []


def test_roda_traden_och_ger_ar_inga_fynd():
    doc = _med_rad(_doc(), {"kind": "math", "latex": "\\Downarrow"})
    _med_rad(doc, {"kind": "math", "latex": "x^2 = 64 \\text{ ger } x = \\pm 8"})
    _med_rad(doc, {"kind": "math",
                   "latex": "m \\in ]0, 800] \\text{ betyder } 0 < m \\le 800"})
    assert lb.utanforvakt(doc, KURS1C) == []


def test_fynden_ar_kortade_till_provets_tak():
    doc = _doc()
    for i in range(10):
        _med_rad(doc, {"kind": "text", "text": f"Implikation {i}"})
    assert len(lb.utanforvakt(doc, KURS1C)) == ci_utanfor.CI_MAX_FYND


def test_bara_nya_fynd_i_omskrivningen():
    fore = _med_rad(_doc(), {"kind": "text", "text": "Implikation: gammal"})
    efter = _med_rad(copy.deepcopy(fore),
                     {"kind": "text", "text": "Ekvivalens: ny"})
    nya = lb._nya_utanfor(fore, efter, KURS1C)
    assert len(nya) == 1 and "Ekvivalens: ny" in nya[0]["message"]
    # Pilarna räknas inte: rutten byter dem gratis efter varvet.
    pil = _med_rad(copy.deepcopy(fore), {"kind": "math", "latex": "a \\iff b"})
    assert lb._nya_utanfor(fore, pil, KURS1C) == []


# ── Genereringen: vakten driver reparationsrundan ───────────────────────────

def test_generate_reparerar_ekvivalensraden_i_1c():
    smutsig = _med_rad(_doc(), {"kind": "text",
                                "text": "Ekvivalens: samma villkor"})
    llm, anrop = _stub([json.dumps(smutsig), json.dumps(_doc())])
    res = lb.generate_board(KURS1C, "TE26A", "Tecken", model="m", llm=llm,
                            doma=False)
    assert "UTANFÖR KURSEN" in anrop[0]["prompt"]
    assert len(anrop) == 2 and "Ekvivalens" in anrop[1]["prompt"]
    assert res["errors"] == [] and "Ekvivalens" not in json.dumps(
        res["board"], ensure_ascii=False)


def test_generate_i_3c_later_raden_sta():
    rad = _med_rad(_doc(), {"kind": "text", "text": "Ekvivalens: samma"})
    llm, anrop = _stub([json.dumps(rad)])
    res = lb.generate_board("Matematik 3c", "NA25", "x", model="m", llm=llm,
                            doma=False)
    assert len(anrop) == 1 and res["errors"] == []


def test_kvarstaende_fynd_redovisas():
    smutsig = _med_rad(_doc(), {"kind": "text", "text": "Implikation: p"})
    llm, _anrop = _stub([json.dumps(smutsig)])
    res = lb.generate_board(KURS1C, "TE26A", "x", model="m", llm=llm,
                            doma=False)
    assert any(f["code"] == ci_utanfor.KOD for f in res["errors"])


def test_domarens_utanforfynd_passerar_randfallsgrinden():
    bok = ("LÄRARENS URVAL: klassen ska räkna uppg. 2112–2114 på de här "
           "sidorna.")
    fynd = [{"message": f"{lb.UTANFOR_FYND} raden «p ⇔ q» under Att tänka "
                        "på. Stryk raden.",
             "uppgifter": []},
            {"message": "Randfallet (x + 2)² saknas under Att tänka på",
             "uppgifter": []}]
    kvar = lb._hittat_randfall(fynd, bok)
    assert kvar == fynd[:1]


def test_domen_ger_stryk_inte_lagg_till():
    svar = json.dumps({"saknas": [{"uppgifter": [], "vad":
                                   f"{lb.UTANFOR_FYND} «Implikation: p»",
                                   "forslag": "stryk raden"}]})
    llm, anrop = _stub([svar])
    fynd = lb.doma_tackning(_doc(), model="m", llm=llm, bok="BOK",
                            utanfor=lb.build_utanfor_dom(KURS1C))
    assert "stryk eller skriv om: stryk raden" in fynd[0]["message"]
    assert "lägg till" not in fynd[0]["message"]
    assert "UTANFÖR KURSEN" in anrop[0]["prompt"]


# ── Omskrivningen ───────────────────────────────────────────────────────────

def test_refine_reparerar_det_varvet_skrev_i_1c():
    fore = _doc()
    ny = _med_rad(_doc(), {"kind": "text", "text": "Implikation: om p så q"})
    llm, anrop = _stub([json.dumps(ny), json.dumps(_doc())])
    res = lb.refine_board(fore, "lägg till en rad", model="m", llm=llm,
                          kurs=KURS1C)
    assert "UTANFÖR KURSEN" in anrop[0]["prompt"]
    assert len(anrop) == 2 and "Implikation" in anrop[1]["prompt"]
    assert "Implikation" not in json.dumps(res["board"], ensure_ascii=False)


def test_refine_utan_kurs_ar_som_forut():
    ny = _med_rad(_doc(), {"kind": "text", "text": "Implikation: om p så q"})
    llm, anrop = _stub([json.dumps(ny)])
    lb.refine_board(_doc(), "lägg till en rad", model="m", llm=llm)
    assert len(anrop) == 1
    assert anrop[0]["prompt"] == lb.build_refine_prompt(_doc(),
                                                        "lägg till en rad")


# ── pilar_till_ger: ⇒ ger, ⇔ betyder ────────────────────────────────────────

def _tavla(*sektioner):
    return {"title": "Intervall", "boards": [{"sections": list(sektioner)}]}


@pytest.mark.parametrize("kurs", ["Matematik, nivå 1c", "Matematik, nivå 1a",
                                  "Matematik, nivå 1b", "Matematik 2a"])
def test_ekvivalens_blir_betyder_och_implikation_ger(kurs):
    t = _tavla(
        {"kind": "math", "latex": "m \\in ]0, 800] \\Leftrightarrow 0 < m \\le 800"},
        {"kind": "math", "latex": "a \\iff b"},
        {"kind": "math", "latex": "x^2 = 64 \\Rightarrow x = \\pm 8"},
        {"kind": "text", "text": "m ∈ ]0, 800] ⇔ 0 < m ≤ 800"},
        {"kind": "text", "text": "Båda ⇒ 64"})
    rader = [s.get("latex") or s.get("text")
             for s in lb.pilar_till_ger(t, kurs)["boards"][0]["sections"]]
    assert rader == [
        "m \\in ]0, 800] \\text{ betyder } 0 < m \\le 800",
        "a \\text{ betyder } b",
        "x^2 = 64 \\text{ ger } x = \\pm 8",
        "m ∈ ]0, 800] betyder 0 < m ≤ 800",
        "Båda ger 64"]


@pytest.mark.parametrize("kurs", ["Matematik, nivå 2c", "Matematik 2b"])
def test_pilarna_star_kvar_dar_kursen_har_dem(kurs):
    t = _tavla({"kind": "math", "latex": "p \\Leftrightarrow q"})
    assert lb.pilar_till_ger(t, kurs) == t


def test_siffervakten_laser_betyder_som_ekvivalenspilen():
    assert ws._ar_utrakning("2x = 10 \\Leftrightarrow x = 5")
    assert ws._ar_utrakning("2x = 10 \\text{ betyder } x = 5")
