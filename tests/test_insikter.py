"""Insikterna ur lektionen — och namnen som aldrig får skrivas ut (Etapp 3).

Efter en transkribering läser modellen igenom lektionen och plockar ut det
läraren behöver minnas: prov som nämndes, vad klassen hade svårt för, vad hon
lovade ta med. Utdatan är ett schema, och två saker måste hålla.

**Schemat.** Fem insiktsslag plus innehållspunkterna, varje post med text och
valfritt datum/referens. Ett svar som inte följer det får inte krascha
extraktionen och inte heller smyga in halva poster i databasen.

**Namnen.** Ett klassrumstranskript är fullt av elevnamn. Prompten säger åt
modellen att bara skriva initialer — men en instruktion är inte en spärr, och
det som skrivs ner här hamnar i databasen, i lektionsminnet och i varje
framtida prompt. Spärren är postprocess.initialisera, och den prövas här.
"""
from __future__ import annotations

import json

import pytest

from app import postprocess


# ── Namnen ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("in_, ut", [
    ("Anna Lindqvist behöver extra tid", "A.L. behöver extra tid"),
    ("Erik Svensson och Maja Berg satt i grupprummet",
     "E.S. och M.B. satt i grupprummet"),
    ("Prata med Mohamed Ali om provet", "Prata med M.A. om provet"),
    ("Åsa Öberg var borta", "Å.Ö. var borta"),
    # Sammansatt förnamn: matchas bara halva står «Anna-L.E.» kvar, alltså
    # precis det som skulle bort.
    ("Anna-Lena Ek räknade fel", "A-L.E. räknade fel"),
    ("Erik Svensson-Berg satt kvar", "E.S. satt kvar"),
])
def test_fullstandiga_namn_kortas_till_initialer(in_, ut):
    assert postprocess.initialisera(in_) == ut


@pytest.mark.parametrize("text", [
    "A.L. behöver extra tid",                      # redan initialer
    "Anna räknade fel på uppgift 4",               # ensamt förnamn rörs inte
    "Pythagoras sats och Eulers formel",           # matematik, inte elever
    "Repetera Kapitel 4 till Fredag",              # versaler som inte är namn
    "Google Kalender krånglade",
    "Klassen hann till s. 214",
    "",
])
def test_det_som_inte_ar_ett_elevnamn_lamnas_i_fred(text):
    assert postprocess.initialisera(text) == text


def test_regeln_star_kvar_i_prompten():
    """Spärren är nätet under — prompten är fortfarande första försvaret, och
    tas den bort får modellen inget skäl att låta bli."""
    for text in (postprocess.EXTRACT_SYSTEM, postprocess.EXTRACT_INSTRUCTION):
        assert "initialer" in text.lower()
    assert "ALDRIG" in postprocess.EXTRACT_SYSTEM


# ── Vägen in i databasen ─────────────────────────────────────────────────

def _svar(monkeypatch, kropp: dict):
    monkeypatch.setattr(postprocess.llm_client, "generate",
                        lambda *a, **k: json.dumps(kropp, ensure_ascii=False))


def test_ett_namn_i_modellsvaret_nar_aldrig_insikten(monkeypatch):
    """Modellen bröt mot instruktionen. Det som sparas är ändå initialer."""
    _svar(monkeypatch, {
        "kalender": [{"text": "Prov i Ma3c 12 maj", "due_date": "2026-05-12"}],
        "svarigheter": [{"text": "Anna Lindqvist fastnade på kedjeregeln",
                         "ref": "Erik Svensson satt bredvid"}],
        "atgarder": [], "grupprum": [], "material": [],
        "innehall": [{"text": "kedjeregeln enligt Maja Berg"}],
    })
    insikter, innehall = postprocess._extract_one("transkript", "modell")
    texter = " ".join(i["text"] + " " + (i["ref"] or "") for i in insikter)
    assert "Lindqvist" not in texter and "Svensson" not in texter
    assert "A.L." in texter and "E.S." in texter
    assert innehall == ["kedjeregeln enligt M.B."]
    # Det som INTE är namn ska överleva orört.
    assert any(i["due_date"] == "2026-05-12" for i in insikter)


def test_extraktionens_schema_haller_svaret_i_form(monkeypatch):
    """Ett svar med fel form ska ge tomma listor, aldrig halva poster."""
    for kropp in ({"svarigheter": "en sträng, inte en lista"},
                  {"svarigheter": [{"ref": "utan text"}]},
                  {}):
        _svar(monkeypatch, kropp)
        insikter, innehall = postprocess._extract_one("transkript", "modell")
        assert insikter == [] and innehall == []


def test_trasig_json_ger_tom_extraktion_inte_ett_undantag(monkeypatch):
    monkeypatch.setattr(postprocess.llm_client, "generate",
                        lambda *a, **k: "det här är inte JSON alls")
    assert postprocess._extract_one("transkript", "modell") == ([], [])


def test_json_i_ett_kodblock_plockas_anda_ut(monkeypatch):
    """Modeller lägger gärna svaret i ```json … ``` — schemat säger nej, men
    en extraktion som faller på ett kodblock är ett tapp för läraren."""
    monkeypatch.setattr(
        postprocess.llm_client, "generate",
        lambda *a, **k: '```json\n{"material": [{"text": "kopiera bladet"}], '
                        '"kalender": [], "svarigheter": [], "atgarder": [], '
                        '"grupprum": [], "innehall": []}\n```')
    insikter, _ = postprocess._extract_one("transkript", "modell")
    assert [i["text"] for i in insikter] == ["kopiera bladet"]
    assert insikter[0]["typ"] == "material"


def test_varje_insiktsslag_far_sin_typ(monkeypatch):
    _svar(monkeypatch, {
        "kalender": [{"text": "prov"}], "svarigheter": [{"text": "bråk"}],
        "atgarder": [{"text": "sluta tidigare"}], "grupprum": [{"text": "två elever"}],
        "material": [{"text": "arbetsblad"}], "innehall": [{"text": "bråk"}],
    })
    insikter, innehall = postprocess._extract_one("transkript", "modell")
    assert {i["typ"] for i in insikter} == {
        "kalender", "svårighet", "åtgärd", "grupprum", "material"}
    assert innehall == ["bråk"]        # innehåll är INTE en insikt
