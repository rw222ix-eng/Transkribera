"""Stammens svarsfält flyttas till deluppgifterna på provet (exam_gen.
svarsfalt_till_delarna). Prov 215 v1388 uppgift 5 hade fyra fält på stammen,
och alla hamnade under b) på pappret. Inga modellanrop."""
from __future__ import annotations

from app import exam_gen


def _uppgift5(falt):
    return {"uppgifter": [{
        "typ": "rutin", "poang": [0, 0, 0], "svarsfalt": falt,
        "text": "Linjen $f$ har ekvationen $3x + y = 7$.",
        "deluppgifter": [
            {"typ": "rutin", "poang": [1, 0, 0], "text": "Var skär linjerna?",
             "losning": "$x = 2$ och $y = 1$"},
            {"typ": "rutin", "poang": [0, 0, 1], "text": "Bestäm a och b.",
             "losning": "$a = 2$ och $b \\neq 14$\nMed $b = 14$ sammanfaller "
                        "linjerna."},
        ]}]}


def test_falten_foljer_variabeln_i_delens_losning():
    e = _uppgift5(["Svar $x =$", "Svar $y =$", "Svar $a =$", "Svar $b$:"])
    assert exam_gen.svarsfalt_till_delarna(e) == []
    u = e["uppgifter"][0]
    assert "svarsfalt" not in u
    assert [d["svarsfalt"] for d in u["deluppgifter"]] == [
        ["Svar $x =$", "Svar $y =$"], ["Svar $a =$", "Svar $b$:"]]


def test_lika_manga_falt_som_delar_ett_per_del():
    e = _uppgift5(["Svar a) Punkten", "Svar b) Villkoren"])
    assert exam_gen.svarsfalt_till_delarna(e) == []
    assert [d["svarsfalt"] for d in e["uppgifter"][0]["deluppgifter"]] == [
        ["Punkten"], ["Villkoren"]]


def test_falt_som_inte_gar_att_placera_blir_ett_fynd():
    e = _uppgift5(["Svar $x =$", "Punkt", "Villkor"])
    fel = exam_gen.svarsfalt_till_delarna(e)
    assert [f["code"] for f in fel] == [exam_gen.SVARSFALTKOD]
    assert e["uppgifter"][0]["svarsfalt"]


def test_del_med_redovisning_eller_egna_falt_ror_inte_stammen():
    e = _uppgift5(["Svar $x =$", "Svar $y =$", "Svar $a =$"])
    e["uppgifter"][0]["deluppgifter"][1]["typ"] = "problem"
    assert exam_gen.svarsfalt_till_delarna(e) == []
    assert len(e["uppgifter"][0]["svarsfalt"]) == 3
