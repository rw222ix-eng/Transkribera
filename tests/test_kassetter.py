"""Kassetterna: hela kedjan EFTER svaret, körd på riktigt (Etapp 3).

Sviten stubbar annars `llm_client.generate` eller generatorn själv — och hoppar
därmed över precis den del som brukar gå sönder: strömtolkningen i
claude_code, JSON-parsningen, schemat, balansreglerna och reparationsrundorna.

En kassett är ETT svar, sparat rad för rad som CLI:t skrev det. Den spelas upp
genom det fejkade `claude`-programmet, alltså genom appens riktiga söm — inte
genom en monkeypatch en nivå in. Det som prövas är därför: när modellen svarar
såhär, vad gör appen?

`inspelad: false` betyder att bandet är byggt ur appens egna exempel — rätt
form, men ingen modell har skrivit det. Byt ut dem mot riktiga svar med
`python -m tools.spela_in_kassett` (kräver inloggning, kostar några ören).
"""
from __future__ import annotations

import json

import pytest

from app import claude_code, exam_gen, lesson_board, postprocess, whiteboard_spec
from tests import fejk


def test_alla_kassetter_har_den_form_uppspelningen_kraver():
    namn = fejk.alla_kassetter()
    assert namn, "inga kassetter — kedjan efter svaret prövas då aldrig"
    for n in namn:
        band = fejk.las_kassett(n)
        assert band["namn"] == n
        assert band["vad"] and isinstance(band["rader"], list) and band["rader"]
        assert isinstance(band["inspelad"], bool)
        # Sista raden är result-raden: utan den vet appen inte att svaret är slut.
        sista = json.loads(band["rader"][-1])
        assert sista["type"] == "result"


def test_ett_band_gar_genom_bryggan_ord_for_ord(fejk_claude):
    """Uppspelningen ska gå genom claude_code.generate — deltan strömmade,
    texten hopsatt, kostnaden avläst — inte förbi den."""
    fejk_claude(kassett="tavla")
    bitar = []
    svar = claude_code.generate("vad som helst", token_cb=bitar.append)
    assert len(bitar) > 1, "svaret kom inte som en ström"
    assert json.loads(svar)["title"] == "Derivatans definition"
    assert claude_code.SENASTE["kostnad"] > 0


def test_tavlan_ur_kassetten_ar_giltig_wb_json(fejk_claude):
    """Hela vägen: CLI → ström → JSON → whiteboard_spec → färdig tavla."""
    fejk_claude(kassett="tavla")
    res = lesson_board.generate_board(
        "Matematik 3c", "NA25", "Derivatans definition", model="")
    assert res["errors"] == []
    assert res["rounds"] == 1
    board = res["board"]
    assert board["title"] == "Derivatans definition"
    # Samma validator som servern kör innan tavlan får skickas till klienten
    # (den tar den tolkade dicten, inte JSON-texten).
    doc, fel = whiteboard_spec.validate_board_json(board)
    assert doc is not None and fel == []


def test_en_trasig_tavla_repareras_i_nasta_runda(fejk_claude):
    """Första bandet bryter mot schemat, andra är rätt. Reparationsrundan ska
    köra på riktigt — det är den som gör att läraren får en tavla i stället för
    ett felmeddelande."""
    lagen = iter(["tavla-trasig", "tavla"])
    riktig = claude_code.generate

    def vaxla(*a, **k):
        fejk_claude(kassett=next(lagen, "tavla"))
        return riktig(*a, **k)
    import app.llm_client as llm_client
    res = lesson_board.generate_board(
        "Matematik 3c", "NA25", "Derivatans definition", model="",
        llm=lambda model, prompt, **kw: vaxla(prompt, system=kw.get("system")))
    assert res["errors"] == [], res["errors"]
    assert res["rounds"] >= 2, "reparationsrundan kördes aldrig"


def test_provet_ur_kassetten_klarar_balansreglerna(fejk_claude):
    """Den skarpa inspelningen bar tre påhittade toppfält (`totalpoang`,
    `instruktion`, `tid_minuter`) — det modellen gör när grammatiktvånget är
    borta. De städas bort vid parsningen i stället för att kosta en hel
    reparationsrunda, och resten ska hålla balansreglerna."""
    fejk_claude(kassett="prov")
    res = exam_gen.generate_exam("Matematik 3c", "NA25",
                                 ["Derivata", "Gränsvärden"], model="", antal=6)
    assert res["errors"] == [], res["errors"]
    exam = res["exam"]
    assert exam["uppgifter"] and exam["titel"]
    from app import exam_spec
    doc, fel = exam_spec.validate_exam_json(exam)
    assert doc is not None and fel == []
    # Städningen tar toppnivån — och bara den.
    assert "totalpoang" not in exam and "instruktion" not in exam
    assert all("del" in u and "poang" in u for u in exam["uppgifter"])


def test_insikterna_ur_den_skarpa_kassetten_bar_inga_namn(fejk_claude):
    """Den riktiga körningen FÖLJDE integritetsregeln — inga fullständiga
    namn kom tillbaka. Det testet vaktar är att det förblir så."""
    fejk_claude(kassett="insikter")
    insikter, innehall = postprocess._extract_one("transkript", "modell")
    assert insikter and innehall
    texter = " ".join(i["text"] + " " + (i["ref"] or "") for i in insikter)
    assert postprocess.initialisera(texter) == texter, \
        "ett fullständigt namn kom tillbaka ur den skarpa inspelningen"
    assert any(i["typ"] == "kalender" for i in insikter)


def test_ett_namn_som_anda_kommer_tillbaka_stoppas(fejk_claude):
    """…och när den INTE följer regeln — det bandet är konstruerat, för det
    ska inte behöva hända på riktigt för att spärren ska vara prövad."""
    fejk_claude(kassett="insikter-med-namn")
    insikter, _ = postprocess._extract_one("transkript", "modell")
    texter = " ".join(i["text"] + " " + (i["ref"] or "") for i in insikter)
    assert "Lindqvist" not in texter and "Svensson" not in texter
    assert "A.L." in texter and "E.S." in texter


def test_en_kassett_som_inte_finns_ar_ett_tydligt_fel(fejk_claude):
    fejk_claude(kassett="finns-inte")
    with pytest.raises(RuntimeError):
        claude_code.generate("x")
