"""Tavlan skriver «ger», inte ⇒, i kurserna under 2c (Rickard 2026-09-25).

Implikationspilen står bara i Ma 2c:s centrala innehåll (app/ci_utanfor.py).
Ankaret «x^2 = 64 ⇒ x = ±8» stod ändå på tavlorna för 2a och 1c, för prompten
visade det så. Nu visar prompten «ger», genereringen och omskrivningen byter
det som ändå kommer, och siffervakten läser «ger» som den läste pilen.
"""
import copy
import json
import re
from pathlib import Path

import pytest

from app import bok_losning, lesson_board, whiteboard_spec as ws

PIL = re.compile(r"\\(?:Rightarrow|Leftrightarrow|implies|iff)(?![A-Za-z])|[⇒⇔]")
TAVLA = Path(__file__).parent / "tavlor" / "inda-2026-09-21.json"


def _tavla(*sektioner):
    return {"title": "Kvadratrötter",
            "boards": [{"sections": list(sektioner)}]}


def test_ankaret_blir_ger_i_1c():
    t = _tavla({"kind": "math", "latex": "x^2 = 64 \\Rightarrow x = \\pm 8"},
               {"kind": "math", "latex": "x^2 = a \\;\\Rightarrow\\; x = \\pm\\sqrt{a}"},
               {"kind": "text", "text": "Båda ⇒ 64"})
    ny = lesson_board.pilar_till_ger(t, "Matematik, nivå 1c")
    rader = [s.get("latex") or s.get("text") for s in ny["boards"][0]["sections"]]
    assert rader == ["x^2 = 64 \\text{ ger } x = \\pm 8",
                     "x^2 = a \\text{ ger } x = \\pm\\sqrt{a}",
                     "Båda ger 64"]
    assert "Rightarrow" in json.dumps(t)          # originalet är orört


@pytest.mark.parametrize("kurs", ["Matematik, nivå 1a", "Matematik 2a",
                                  "Matematik, nivå 1b"])
def test_ekvivalenspilen_blir_ocksa_ger(kurs):
    t = _tavla({"kind": "math", "latex": "2x = 6 \\Leftrightarrow x = 3"},
               {"kind": "math", "latex": "a \\iff b"})
    ny = lesson_board.pilar_till_ger(t, kurs)
    assert not PIL.search(json.dumps(ny))


def test_2c_och_rodatraden_ar_orda():
    t = _tavla({"kind": "math", "latex": "x = 2 \\Rightarrow x^2 = 4"},
               {"kind": "math", "latex": "\\Downarrow"})
    assert lesson_board.pilar_till_ger(t, "Matematik, nivå 2c") == t
    ny = lesson_board.pilar_till_ger(t, "Matematik, nivå 1c")
    assert ny["boards"][0]["sections"][1]["latex"] == "\\Downarrow"


def test_riktigt_ankare_star_kvar_efter_bytet():
    """IndA:s rottavla 21/9 hade ankaret med pilen. Med «ger» ger validatorn
    samma fynd som förut: ankaret är fortfarande ankaret."""
    tavla = json.loads(TAVLA.read_text(encoding="utf-8"))
    ny = lesson_board.pilar_till_ger(copy.deepcopy(tavla), "Matematik 2a")
    assert "\\text{ ger }" in json.dumps(ny)
    koder = lambda f: sorted((x.get("path"), x.get("code")) for x in f)
    assert koder(ws.validate_board_json(ny)[1]) == \
        koder(ws.validate_board_json(tavla)[1])


def test_siffervakten_laser_ger_som_pilen():
    assert ws._ar_utrakning("y = 4 - 5x \\Rightarrow k = -5")
    assert ws._ar_utrakning("y = 4 - 5x \\text{ ger } k = -5")
    assert not ws._ar_utrakning("x^2 = a \\text{ ger } x = \\pm \\sqrt{a}")


def test_promptexemplen_visar_ger():
    assert not PIL.search(lesson_board.INSTRUCTION)
    assert "x^2 = 64 \\text{ ger } x = \\pm 8" in lesson_board.INSTRUCTION
    p = bok_losning.build_prompt("Liber Matematik 1c", "1.4", [],
                                 [{"nr": 1401, "niva": 1}])
    assert not PIL.search(p) and "«ger»" in p
