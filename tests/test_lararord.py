"""Lärarens egna ord — «Vad var svårt?» och «Vad ska väga tyngst?».

Två rutor i steg 3, två sätt att inte nå fram:

  1. `#svart` fanns inte alls. Appen kunde bara säga vad klassen hade svårt för
     om lektionen SPELATS IN — «Svårighet att följa upp» kommer ur transkriptet
     via db.next_prep — och en lektion utan mikrofon lämnade tavlan utan det
     enda läraren säkert visste.
  2. `#fokus` fanns, sparades på pappret och stod till och med i skrivplanen
     («Väger källorna»), men skickades aldrig i någon generate-begäran. Exakt
     samma tomma löfte som förlagan var före app/forlaga.py.

Testerna frågar därför två saker, och den andra är den viktiga:
går fältet att LÄSA UPP ur prompten som gick till modellen — och är prompten
för en TOM ruta ord för ord den som gick i väg innan rutorna byggdes? Den andra
frågan är kassetternas: ett block som smyger in vid tomt fält gör varje
inspelat band omspelningsmoget.
"""
from __future__ import annotations

import copy
import json

import pytest

from app import exam_gen, lararord, lesson_board, notes_gen

SVART = "kvadratkomplettering satt inte — flera blandade ihop roten ur produkt och summa"
FOKUS = "mest ur provet, lite ur boken"


# ─────────────────────────────── blocken ────────────────────────────────

@pytest.mark.parametrize("bygg", [lararord.build_svart, lararord.build_fokus])
@pytest.mark.parametrize("tomt", [None, "", "   ", "\n\t ", 0])
def test_ett_tomt_falt_ger_inget_block(bygg, tomt):
    """Grundregeln. Tomt fält → tom sträng → anroparen lägger till ingenting,
    och prompten är identisk med gårdagens."""
    assert bygg(tomt) == ""


def test_svartblocket_sager_vem_som_talar():
    """Modellen möter svårigheten från tre håll — transkriptet, rättningen och
    läraren. Blocket måste säga vilket av dem det är, annars är det bara en rad
    till i en hög av signaler."""
    text = lararord.build_svart(SVART)
    assert "LÄRARENS EGNA ORD" in text
    assert SVART in text
    # Och att det är hennes iakttagelse som väger tyngst av dem.
    assert "väger tyngst" in text


def test_svartblocket_ber_om_plats_at_det_svara():
    """Att modellen VET vad som var svårt räcker inte — det ska få tid på
    pappret. Utan den meningen blev det en bisats i en genomgång som såg ut
    precis som den förra."""
    text = lararord.build_svart(SVART)
    assert "eget exempel" in text
    # Och eleverna ska inte läsa om att läraren tyckte något: pappret är deras.
    assert "till eleverna" in text


def test_fokusblocket_ar_en_viktning_och_inget_annat():
    text = lararord.build_fokus(FOKUS)
    assert "VÄGA TYNGST" in text
    assert FOKUS in text


def test_radbrytningar_och_dubbla_mellanslag_stadas():
    """Fälten kommer från en webbläsare. En inklistrad rad kan bära allt."""
    text = lararord.build_svart("  kvadrat­komplettering\n\n  satt   inte  ")
    assert "kvadrat­komplettering satt inte" in text
    assert "\n\n" not in text.split(":\n", 1)[1].split("\n")[0]


def test_en_inklistrad_uppsats_ater_inte_prompten():
    """Rutan är enradig i UI:t, men ingenting hindrar en hel
    lektionsanteckning. Taket finns så att boken och förlagan får plats kvar."""
    text = lararord.build_svart("derivator " * 400)
    assert len(text) < lararord.MAX_TECKEN + 600
    assert "[…]" in text


# ────────────────────────── prompterna, med fält ─────────────────────────

def test_tavelprompten_bar_svarigheten_fore_transkriptets():
    """Ordningen är påståendet: minnet bär «Svårighet att följa upp» ur
    transkriptet, och när de två talar om samma lektion ska läraren läsas
    först."""
    text = lesson_board.build_prompt(
        "Matematik, nivå 2c", "NA25", "andragradsekvationer",
        memory="Svårighet att följa upp: eleverna frågade om pq-formeln",
        svart=lararord.build_svart(SVART))
    assert SVART in text
    assert text.index("LÄRARENS EGNA ORD") < text.index("Svårighet att följa upp")
    # Uppdraget står ändå sist — ingen källa får skjuta undan det.
    assert text.rindex("Uppdrag:") > text.rindex("LÄRARENS EGNA ORD")


def test_tavelprompten_lagger_viktningen_sist_bland_kallorna():
    """«Mest ur provet, lite ur boken» är en dom över källorna och kan inte
    fällas innan de står i prompten."""
    text = lesson_board.build_prompt(
        "Matematik, nivå 2c", "NA25", "derivator",
        bok="LÄROBOKEN — s. 12–14 …", svart=lararord.build_svart(SVART),
        fokus=lararord.build_fokus(FOKUS))
    assert FOKUS in text
    assert text.index("LÄROBOKEN") < text.index("VÄGA TYNGST")
    assert text.index("LÄRARENS EGNA ORD") < text.index("VÄGA TYNGST")
    assert text.rindex("Uppdrag:") > text.rindex("VÄGA TYNGST")


@pytest.mark.parametrize("profil", ["prov", "arbetsblad", "gruppuppgift"])
def test_provprompten_bar_bada_falten_i_alla_profiler(profil):
    grupp = ({"elever": 3, "langd_min": 45, "redovisning": "muntligt"}
             if profil == "gruppuppgift" else None)
    text = exam_gen.build_prompt(
        "Matematik, nivå 2c", "NA25", ["Derivator"], antal=4, profil=profil,
        grupp=grupp, svart=lararord.build_svart(SVART),
        fokus=lararord.build_fokus(FOKUS))
    assert SVART in text and FOKUS in text
    assert text.index("LÄRARENS EGNA ORD") < text.index("VÄGA TYNGST")
    assert text.rindex("Uppdrag:") > text.rindex("VÄGA TYNGST")


def test_anteckningsprompten_bar_bada_falten():
    """Stödpappret är det läraren har i handen när något ska tas om — vad
    klassen hade svårt för är rakt på sak dess ärende."""
    text = notes_gen.build_prompt(
        "Matematik, nivå 2c", "NA25", "derivator",
        onskemal="tre exempel att gå igenom",
        svart=lararord.build_svart(SVART), fokus=lararord.build_fokus(FOKUS))
    assert SVART in text and FOKUS in text
    assert text.rindex("Uppdrag:") > text.rindex("VÄGA TYNGST")


# ───────────────── prompterna, utan fält: kassettkravet ──────────────────

def _tavla(**k):
    return lesson_board.build_prompt("Matematik, nivå 2c", "NA25", "derivator",
                                     memory="Senaste lektionen (2026-09-01).",
                                     bok="LÄROBOKEN — s. 12–14 …", **k)


def _prov(**k):
    return exam_gen.build_prompt("Matematik, nivå 2c", "NA25", ["Derivator"],
                                 antal=4, memory="Senaste lektionen.", **k)


def _anteckning(**k):
    return notes_gen.build_prompt("Matematik, nivå 2c", "NA25", "derivator",
                                  onskemal="tre exempel", **k)


@pytest.mark.parametrize("bygg", [_tavla, _prov, _anteckning])
def test_tomma_rutor_ger_byte_identisk_prompt(bygg):
    """KASSETTKRAVET. Skickar klienten inga fält — eller tomma — ska prompten
    vara EXAKT den som gick i väg innan fälten fanns. En enda extra radbrytning
    hade tvingat fram en omspelning av alla band (dyrt, två vändor sist)."""
    forut = bygg()
    assert bygg(svart="", fokus="") == forut
    assert bygg(svart=lararord.build_svart(None),
                fokus=lararord.build_fokus("  ")) == forut
    # Och inget spår av rutorna får finnas i den tomma prompten.
    assert "LÄRARENS EGNA ORD" not in forut
    assert "VÄGA TYNGST" not in forut


# ─────────────────────────────── rutterna ───────────────────────────────

def _events(resp) -> list[dict]:
    return [json.loads(r[len("data:"):]) for r in resp.text.splitlines()
            if r.startswith("data:")]


def _done(resp) -> dict:
    ev = [e for e in _events(resp) if e["type"] == "done"]
    assert ev, _events(resp)
    return ev[0]["result"]


def _fangad_prompt(monkeypatch, modul) -> list[str]:
    """Fångar prompten som verkligen gick till modellen (samma spion som
    test_forlaga)."""
    prompter: list[str] = []
    riktig = modul.build_prompt

    def spion(*a, **k):
        p = riktig(*a, **k)
        prompter.append(p)
        return p

    monkeypatch.setattr(modul, "build_prompt", spion)
    return prompter


def _stubba_tavla(monkeypatch):
    board = copy.deepcopy(lesson_board.FEW_SHOTS[0][1])
    monkeypatch.setattr(lesson_board, "_llm_round", lambda *a, **k: board)


def _stubba_prov(monkeypatch):
    monkeypatch.setattr(exam_gen, "_llm_round",
                        lambda *a, **k: {"titel": "Prov", "kurs": "x",
                                         "hjalpmedel": "", "uppgifter": [
                                             {"del": None, "formaga": "P",
                                              "typ": "rutin", "poang": [2, 0, 0],
                                              "text": "Beräkna", "losning": "1",
                                              "bedomning": "+2 E"}]})


def test_planeringsrutten_bar_bada_falten(llm_ready, monkeypatch):
    prompter = _fangad_prompt(monkeypatch, lesson_board)
    _stubba_tavla(monkeypatch)
    r = llm_ready.post("/api/planning/generate",
                       json={"moment": "andragradsekvationer", "klass": "NA25",
                             "svart": SVART, "fokus": FOKUS})
    assert r.status_code == 200
    _done(r)
    assert SVART in prompter[0] and FOKUS in prompter[0]


def test_planeringsrutten_utan_falten_namner_dem_inte(llm_ready, monkeypatch):
    """Den här är kassetternas test på ruttnivå: en vanlig begäran utan
    rutorna får inte bära ett spår av dem."""
    prompter = _fangad_prompt(monkeypatch, lesson_board)
    _stubba_tavla(monkeypatch)
    r = llm_ready.post("/api/planning/generate", json={"moment": "derivator"})
    assert r.status_code == 200
    _done(r)
    assert "LÄRARENS EGNA ORD" not in prompter[0]
    assert "VÄGA TYNGST" not in prompter[0]


def test_planeringsrutten_tar_tomma_stangar_som_franvarande(llm_ready, monkeypatch):
    """Klienten skickar bara ifyllda fält, men en tom sträng får inte heller
    öppna ett block — det är servern som är sista ordet."""
    prompter = _fangad_prompt(monkeypatch, lesson_board)
    _stubba_tavla(monkeypatch)
    r = llm_ready.post("/api/planning/generate",
                       json={"moment": "derivator", "svart": "  ", "fokus": ""})
    assert r.status_code == 200
    _done(r)
    assert "LÄRARENS EGNA ORD" not in prompter[0]
    assert "VÄGA TYNGST" not in prompter[0]


@pytest.mark.parametrize("typ", ["prov", "arbetsblad", "gruppuppgift", "diagnos"])
def test_provrutten_bar_bada_falten(llm_ready, monkeypatch, typ):
    cid = llm_ready.post("/api/courses",
                         json={"namn": "Matematik, nivå 2c"}).json()["id"]
    prompter = _fangad_prompt(monkeypatch, exam_gen)
    _stubba_prov(monkeypatch)
    r = llm_ready.post("/api/exams/generate",
                       json={"course_id": cid, "klass": "NA25", "antal": 4,
                             "typ": typ, "punkter_text": ["Derivator"],
                             "svart": SVART, "fokus": FOKUS})
    assert r.status_code == 200
    _done(r)
    assert SVART in prompter[0] and FOKUS in prompter[0]


def test_anteckningsrutten_bar_svarigheten(llm_ready, monkeypatch):
    prompter = _fangad_prompt(monkeypatch, notes_gen)
    monkeypatch.setattr(
        notes_gen, "_llm_round",
        lambda *a, **k: {"titel": "Stödanteckningar", "avsnitt": [
            {"rubrik": "Att ta upp", "punkter": ["kvadratkomplettering"]}]})
    r = llm_ready.post("/api/anteckningar/generate",
                       json={"kurs": "Matematik, nivå 2c", "klass": "NA25",
                             "moment": "derivator", "onskemal": "tre exempel",
                             "svart": SVART, "fokus": FOKUS})
    assert r.status_code == 200
    assert prompter, "prompten byggdes aldrig"
    assert SVART in prompter[0] and FOKUS in prompter[0]
